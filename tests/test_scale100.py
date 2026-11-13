"""The scale100 condition: 100x log volume generated at load time (docs/benchmark-scale100.md).

Scale-100 tests build about 51,000 lines per incident (about a second), so they use INC-001 and
INC-002 only.
"""

import json
import os
from collections import Counter

import pytest

from incidentiq import data
from incidentiq.agents.baseline import DUMP_LINES, baseline_messages, log_dump
from incidentiq.config import DATA_DIR
from incidentiq.eval import __main__ as cli
from incidentiq.eval.runner import run_one
from incidentiq.eval.variants import VARIANTS
from incidentiq.llm import MockLLM
from incidentiq.schemas import Evidence, GraphState, LogLine
from incidentiq.synthetic import NOISE, UNIVERSAL
from incidentiq.tools.logs import search_logs

IDS = ["INC-001", "INC-002"]
ADDED = data.EXTRA_LINES_PER_SERVICE


@pytest.fixture(autouse=True)
def _default_scale(monkeypatch):
    monkeypatch.delenv("INCIDENTIQ_LOG_SCALE", raising=False)


@pytest.fixture
def scale100(monkeypatch):
    monkeypatch.setenv("INCIDENTIQ_LOG_SCALE", "100")


def _added(lines):
    return [ln for ln in lines if int(ln.line_id[2:]) >= data.EXTRA_FIRST_ID]


def _original(incident_id):
    return data._original_logs(incident_id)


def _gold_log_ids(incident_id):
    return {g for g in data.load_ground_truth(incident_id).gold_evidence_ids if g.startswith("L-")}


# --- the switch ---------------------------------------------------------------------------


def test_scale_1_is_the_files_on_disk_untouched():
    for incident_id in IDS:
        text = (DATA_DIR / "logs" / f"{incident_id}.jsonl").read_text(encoding="utf-8")
        assert [ln.model_dump() for ln in data.load_logs(incident_id)] == \
            [json.loads(line) for line in text.splitlines()]


@pytest.mark.parametrize("value", ["2", "10", "1000", "", "100x", "0"])
def test_an_unsupported_scale_is_a_clear_error(monkeypatch, value):
    monkeypatch.setenv("INCIDENTIQ_LOG_SCALE", value)
    with pytest.raises(ValueError, match="INCIDENTIQ_LOG_SCALE must be one of"):
        data.load_logs("INC-001")


def test_scale_is_read_on_every_call(monkeypatch):
    n = len(data.load_logs("INC-001"))
    monkeypatch.setenv("INCIDENTIQ_LOG_SCALE", "100")
    assert len(data.load_logs("INC-001")) > n
    monkeypatch.setenv("INCIDENTIQ_LOG_SCALE", "1")
    assert len(data.load_logs("INC-001")) == n


# --- the generated lines ------------------------------------------------------------------


def test_scaled_logs_are_deterministic(scale100):
    first = data.load_logs("INC-001")
    data._scaled_logs.cache_clear()
    assert data.load_logs("INC-001") == first


@pytest.mark.parametrize("incident_id", IDS)
def test_exact_line_counts(scale100, incident_id):
    lines = data.load_logs(incident_id)
    assert len(lines) == len(_original(incident_id)) + len(NOISE) * ADDED
    assert Counter(ln.service for ln in _added(lines)) == {s: ADDED for s in NOISE}


@pytest.mark.parametrize("incident_id", IDS)
def test_added_ids_start_at_5000_and_follow_timestamp_then_service_order(scale100, incident_id):
    lines = data.load_logs(incident_id)
    ids = [ln.line_id for ln in lines]
    assert len(set(ids)) == len(ids)  # no collisions
    added = _added(lines)
    assert [ln.line_id for ln in added] == \
        [f"L-{data.EXTRA_FIRST_ID + n:04d}" for n in range(len(added))]
    assert [ln.ts for ln in lines] == sorted(ln.ts for ln in lines)
    added_keys = [(ln.ts, ln.service) for ln in added]
    assert added_keys == sorted(added_keys)  # added IDs rise in (timestamp, service) order
    assert added[0].line_id == "L-5000"
    assert max(int(ln.line_id[2:]) for ln in _original(incident_id)) < data.EXTRA_FIRST_ID


@pytest.mark.parametrize("incident_id", IDS)
def test_original_lines_keep_their_ids_and_text(scale100, incident_id):
    scaled = {ln.line_id: ln for ln in data.load_logs(incident_id)}
    originals = {ln.line_id: ln for ln in _original(incident_id)}
    assert all(scaled[i] == ln for i, ln in originals.items())
    assert all(scaled[g] == originals[g] for g in _gold_log_ids(incident_id))


@pytest.mark.parametrize("incident_id", IDS)
def test_original_lines_keep_their_exact_relative_order(scale100, incident_id):
    original_ids = [ln.line_id for ln in _original(incident_id)]
    assert [ln.line_id for ln in data.load_logs(incident_id) if ln.line_id in set(original_ids)]         == original_ids


def test_merge_keeps_tied_original_lines_in_file_order_and_puts_added_lines_after_them():
    def line(line_id, ts, service):
        return LogLine(line_id=line_id, ts=ts, service=service, level="INFO", message="m")

    t = "2026-03-01T10:00:00Z"
    original = (line("L-0001", t, "search"), line("L-0002", t, "auth"),
                line("L-0003", "2026-03-01T10:00:05Z", "auth"))
    added = [line("L-5000", t, "auth"), line("L-5001", t, "payments"),
             line("L-5002", "2026-03-01T10:00:05Z", "auth")]
    merged = data.merge_logs(original, added)
    assert [ln.line_id for ln in merged] == ["L-0001", "L-0002", "L-5000", "L-5001", "L-0003",
                                             "L-5002"]


def test_added_lines_are_inside_the_incident_window(scale100):
    incident = data.load_incident("INC-001")
    for ln in _added(data.load_logs("INC-001")):
        assert incident.window_start <= ln.ts < incident.window_end


def test_the_level_mix_follows_the_templates(scale100):
    added = _added(data.load_logs("INC-002"))
    for service in NOISE:
        templates = NOISE[service] + UNIVERSAL
        expected = Counter(level for level, _ in templates)
        actual = Counter(ln.level for ln in added if ln.service == service)
        for level in ("INFO", "WARN", "ERROR"):
            assert abs(actual[level] / ADDED - expected[level] / len(templates)) < 0.02
    assert not [ln for ln in added if ln.level == "ERROR"]  # no benign ERROR noise


def test_added_lines_contain_no_injected_pii(scale100):
    manifest = json.loads((DATA_DIR / "pii_manifest.json").read_text(encoding="utf-8"))
    for incident_id in IDS:
        values = [m["value"] for m in manifest if m["incident_id"] == incident_id]
        assert values
        text = "\n".join(ln.message for ln in _added(data.load_logs(incident_id)))
        assert not [v for v in values if v in text]


def test_log_search_works_unchanged_at_scale_100(scale100):
    lines, total = search_logs("INC-001", level="ERROR")
    assert 0 < len(lines) == total <= 30  # added noise has no ERROR lines
    assert search_logs("INC-001")[1] == len(data.load_logs("INC-001"))
    assert _gold_log_ids("INC-001") <= {ln.line_id for ln in data.load_logs("INC-001")}


def test_the_service_order_matches_the_generator():
    import sys

    sys.path.insert(0, str(DATA_DIR.parent / "scripts"))
    from datagen.catalog import SERVICES

    assert list(NOISE) == SERVICES


# --- the baselines ------------------------------------------------------------------------


@pytest.mark.parametrize("scale", ["1", "100"])
@pytest.mark.parametrize("incident_id", IDS)
def test_v0b_keeps_only_recent_warn_and_error_lines_of_the_alerting_service(
        monkeypatch, scale, incident_id):
    monkeypatch.setenv("INCIDENTIQ_LOG_SCALE", scale)
    incident = data.load_incident(incident_id)
    alert = data.parse_ts(incident.start_time)
    dump = log_dump(incident_id, filtered=True)
    assert 0 < len(dump) <= DUMP_LINES
    assert {ln.service for ln in dump} == {incident.service}
    assert {ln.level for ln in dump} <= {"WARN", "ERROR"}
    assert all(data.parse_ts(ln.ts) <= alert for ln in dump)
    eligible = [ln for ln in data.load_logs(incident_id)
                if ln.service == incident.service and ln.level in ("WARN", "ERROR")
                and data.parse_ts(ln.ts) <= alert]
    assert dump == eligible[-DUMP_LINES:]  # the latest ones, oldest first


def test_v0a_is_unchanged_and_v0b_is_a_different_prompt():
    state = GraphState(incident=data.load_incident("INC-001"))
    v0a_lines, v0b_lines = log_dump("INC-001"), log_dump("INC-001", filtered=True)
    assert v0a_lines != v0b_lines and len(v0a_lines) == DUMP_LINES

    def evidence(lines):
        return [Evidence(evidence_id=ln.line_id, kind="log", excerpt=ln.message) for ln in lines]

    a = baseline_messages(state, evidence(v0a_lines))
    b = baseline_messages(state, evidence(v0b_lines), filtered=True)
    assert a != b and "WARN and ERROR log lines of the alerting service" in b[1]["content"]
    assert "WARN and ERROR" not in a[1]["content"]


def test_at_scale_100_v0a_sees_seconds_and_v0b_sees_the_cause(scale100):
    incident = data.load_incident("INC-001")
    gold = _gold_log_ids("INC-001")
    v0a = log_dump("INC-001")
    assert (data.parse_ts(incident.start_time) - data.parse_ts(v0a[0].ts)).total_seconds() < 120
    assert not gold & {ln.line_id for ln in v0a}
    assert gold & {ln.line_id for ln in log_dump("INC-001", filtered=True)}


def test_v0b_is_a_baseline_variant_outside_the_original_run_all():
    v = VARIANTS["v0b-filtered-baseline"]
    assert v.kind == "baseline" and v.filtered and not v.in_original


def test_run_all_is_five_runs_originally_and_exactly_four_under_scale100():
    assert cli._variant_names("all", scale100=False) == [
        "v0-baseline", "v1-tools", "v2-retrieval", "v3-verifier", "v4-final"]
    assert cli._variant_names("all", scale100=True) == [
        "v0-baseline", "v0b-filtered-baseline", "v4-final", "v5-scale"]
    assert cli._variant_names("v1-tools", scale100=False) == ["v1-tools"]
    assert cli._variant_names("v0b-filtered-baseline", scale100=True) == ["v0b-filtered-baseline"]


@pytest.mark.parametrize("run", ["v1-tools", "v2-retrieval", "v3-verifier"])
def test_the_middle_agents_cannot_be_run_under_scale100(capsys, run):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--condition", "scale100", "--run", run, "--incidents", "INC-002"])
    assert exc.value.code == 2
    assert "not part of the scale100 condition" in capsys.readouterr().err


def test_different_evidence_means_a_different_prompt_so_a_different_cache_key(monkeypatch):
    def prompt_for(scale):
        monkeypatch.setenv("INCIDENTIQ_LOG_SCALE", scale)
        llm = MockLLM(default="not json")
        run_one(VARIANTS["v0-baseline"], "INC-001", llm)
        return llm.sent[0]

    assert prompt_for("1") != prompt_for("100")


# --- CLI ----------------------------------------------------------------------------------


def _run_cli(monkeypatch, tmp_path, args):
    seen = []

    def fake_llm(mode):
        seen.append(os.environ.get("INCIDENTIQ_LOG_SCALE"))
        return MockLLM(default="not json")

    monkeypatch.setattr(cli, "get_llm", fake_llm)
    monkeypatch.setattr(cli, "RESULTS_DIR", tmp_path)
    return cli.main(args + ["--run", "v0b-filtered-baseline", "--incidents", "INC-002"]), seen


def test_condition_scale100_sets_the_scale_and_writes_under_results_scale100(
        monkeypatch, tmp_path):
    code, seen = _run_cli(monkeypatch, tmp_path, ["--condition", "scale100"])
    assert code == 0 and seen == ["100"]
    out = tmp_path / "scale100" / "v0b-filtered-baseline"
    results = json.loads((out / "results.json").read_text(encoding="utf-8"))
    assert results["condition"] == "scale100"
    assert "--condition scale100" in (out / "results.md").read_text(encoding="utf-8")
    assert "INCIDENTIQ_LOG_SCALE" not in os.environ  # restored after the run


def test_condition_original_is_the_default_and_keeps_the_old_paths(monkeypatch, tmp_path):
    monkeypatch.setenv("INCIDENTIQ_LOG_SCALE", "100")  # even if set, original forces 1
    code, seen = _run_cli(monkeypatch, tmp_path, [])
    assert code == 0 and seen == ["1"]
    out = tmp_path / "v0b-filtered-baseline"
    assert (out / "results.json").exists() and not (tmp_path / "scale100").exists()
    assert "condition" not in json.loads((out / "results.json").read_text(encoding="utf-8"))
    assert os.environ["INCIDENTIQ_LOG_SCALE"] == "100"  # the caller's value is put back


@pytest.mark.parametrize("condition, folder", [("original", ""), ("scale100", "scale100")])
def test_check_compares_with_the_committed_files_of_each_condition(
        monkeypatch, tmp_path, capsys, condition, folder):
    code, _ = _run_cli(monkeypatch, tmp_path, ["--condition", condition, "--check"])
    expected = tmp_path / folder / "v0b-filtered-baseline" / "results.json"
    assert code == 1 and f"{expected} is missing" in capsys.readouterr().err
    assert _run_cli(monkeypatch, tmp_path, ["--condition", condition])[0] == 0
    assert _run_cli(monkeypatch, tmp_path, ["--condition", condition, "--check"])[0] == 0


def test_scale100_replay_with_nothing_recorded_is_a_cache_miss_not_a_crash(
        monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path))
    code = cli.main(["--condition", "scale100", "--run", "v0-baseline", "--llm", "replay",
                     "--incidents", "INC-002", "--out", str(tmp_path / "out")])
    assert code == 2 and "CACHE MISS" in capsys.readouterr().err
