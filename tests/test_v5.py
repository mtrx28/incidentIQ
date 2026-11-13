"""v5-scale: rarity-ranked log_search, default window, count/template header (see
docs/benchmark-scale100.md). Legacy behaviour (v1 to v4) must not change."""

import hashlib
import math
import time

import pytest

from incidentiq import data
from incidentiq.agents.toolbox import ALLOWED_ARGS, ToolBox
from incidentiq.eval import __main__ as cli
from incidentiq.eval.variants import VARIANTS
from incidentiq.schemas import LogLine, PlanStep
from incidentiq.tools import ToolError
from incidentiq.tools.logs import log_search, search_logs_rarity, template_of


@pytest.fixture(autouse=True)
def _default_scale(monkeypatch):
    monkeypatch.delenv("INCIDENTIQ_LOG_SCALE", raising=False)


def _line(n, message, level="INFO", ts="2026-03-01T10:00:00Z", service="auth"):
    return LogLine(line_id=f"L-{n:04d}", ts=ts, service=service, level=level, message=message)


def _fake_logs(monkeypatch, lines):
    monkeypatch.setattr(data, "load_logs", lambda incident_id: tuple(lines))


# --- ranking ------------------------------------------------------------------------------


def test_one_rare_line_outranks_a_thousand_identical_noise_lines(monkeypatch):
    noise = [_line(n, f"cache refresh ok took={n}ms") for n in range(1, 1001)]
    cause = _line(2000, "certificate renewal failed for host")
    _fake_logs(monkeypatch, noise + [cause])
    result = log_search("INC-001", mode="rarity", limit=1)
    assert [e.evidence_id for e in result.evidence] == ["L-2000"]


def test_a_matched_query_term_beats_rarity(monkeypatch):
    common = [_line(n, f"disk write failed block={n}") for n in range(10, 30)]
    # Both lines are rarer than the common ones, but only the first matches both query terms.
    _fake_logs(monkeypatch, [*common, _line(1, "disk full"), _line(2, "disk almost there"),
                             _line(3, "full of surprises")])
    top = log_search("INC-001", mode="rarity", query="disk full", limit=1)
    assert [e.evidence_id for e in top.evidence] == ["L-0001"]
    # A line that matches no query term is not a match, however rare it is.
    unrelated = log_search("INC-001", mode="rarity", query="disk", limit=30)
    assert "L-0003" not in {e.evidence_id for e in unrelated.evidence}


def test_there_is_no_level_bonus_and_ties_break_by_time_then_id(monkeypatch):
    # One template, so one score: an ERROR line gets no advantage over an INFO line.
    _fake_logs(monkeypatch, [_line(3, "x 1", level="INFO", ts="2026-03-01T10:00:00Z"),
                             _line(2, "x 2", level="ERROR", ts="2026-03-01T10:00:05Z"),
                             _line(1, "x 3", level="ERROR", ts="2026-03-01T10:00:00Z")])
    result = log_search("INC-001", mode="rarity", limit=2)
    assert [e.evidence_id for e in result.evidence] == ["L-0001", "L-0003"]  # time, then ID


def test_the_rarer_template_ranks_first_and_counts_are_per_template(monkeypatch):
    _fake_logs(monkeypatch, [_line(1, "a 1"), _line(2, "a 2"), _line(3, "a 3"),
                             _line(4, "different")])
    top, matches, counts = search_logs_rarity("INC-001", None, None, None, [], None, 1)
    assert [ln.line_id for ln in top] == ["L-0004"]
    assert len(matches) == 4 and counts["a <N>"] == 3
    assert 1 / math.log2(2 + 1) > 1 / math.log2(2 + 3)


def test_the_header(monkeypatch):
    lines = [_line(n, f"noise {n}") for n in range(1, 8)]
    lines += [_line(20, "rare", level="ERROR"), _line(21, "other", level="WARN")]
    _fake_logs(monkeypatch, lines)
    summary = log_search("INC-001", mode="rarity", limit=3).summary
    assert summary.startswith("9 matching log lines (showing the 3 rarest-template matches).")
    assert "Levels: ERROR 1, WARN 1, INFO 7. Distinct templates: 3." in summary
    assert "  7 x noise <N>" in summary
    assert "No start or end given" not in summary  # no alert time, so no default window


# --- templates ----------------------------------------------------------------------------


@pytest.mark.parametrize("message, expected", [
    ("request took 1523ms", "request took <N>ms"),
    ("deploy abc123def456 done", "deploy <HEX> done"),
    ("connect to 10.0.3.17 failed", "connect to <IP> failed"),
    ("user 'alice' not found", "user <Q> not found"),
    ('flag "new_ui" set to "on"', "flag <Q> set to <Q>"),
    ("don't retry, can't connect 5 times", "don't retry, can't connect <N> times"),
    ("pool full", "pool full"),
    ("a 1 b 22 c 333", "a <N> b <N> c <N>"),
])
def test_template_normalisation(message, expected):
    assert template_of(message) == expected


# --- default window -----------------------------------------------------------------------


def _timed_logs(monkeypatch):
    stamps = ["09:00:00", "09:14:00", "09:20:00", "09:44:00", "09:48:59", "09:49:01", "10:30:00"]
    _fake_logs(monkeypatch, [_line(n, "m", ts=f"2026-03-01T{t}Z") for n, t in enumerate(stamps)])


def test_the_default_window_is_30_minutes_before_to_5_after_the_alert(monkeypatch):
    _timed_logs(monkeypatch)
    result = log_search("INC-001", mode="rarity", alert_time="2026-03-01T09:44:00Z")
    assert [e.evidence_id for e in result.evidence] == ["L-0001", "L-0002", "L-0003", "L-0004"]
    assert "default window 2026-03-01T09:14:00Z to 2026-03-01T09:49:00Z" in result.summary


@pytest.mark.parametrize("kwargs, expected", [
    ({"start": "2026-03-01T09:40:00Z"}, ["L-0003", "L-0004", "L-0005", "L-0006"]),
    ({"end": "2026-03-01T09:15:00Z"}, ["L-0000", "L-0001"]),
    ({"start": "2026-03-01T09:00:00Z", "end": "2026-03-01T09:01:00Z"}, ["L-0000"]),
])
def test_explicit_start_or_end_wins_over_the_default_window(monkeypatch, kwargs, expected):
    _timed_logs(monkeypatch)
    result = log_search("INC-001", mode="rarity", alert_time="2026-03-01T09:44:00Z", **kwargs)
    assert [e.evidence_id for e in result.evidence] == expected
    assert "default window" not in result.summary


def test_legacy_mode_ignores_the_alert_time(monkeypatch):
    _timed_logs(monkeypatch)
    result = log_search("INC-001", alert_time="2026-03-01T09:44:00Z")
    assert len(result.evidence) == 7 and "default window" not in result.summary


def test_unknown_mode_is_an_error():
    with pytest.raises(ToolError, match="mode must be one of"):
        log_search("INC-001", mode="fancy")


# --- legacy output is unchanged -----------------------------------------------------------


def test_legacy_mode_output_is_byte_identical_to_the_version_before_v5():
    # The hash was taken from the code before v5 was written.
    cases = [("INC-001", {}), ("INC-001", {"query": "timeout error", "level": "WARN"}),
             ("INC-002", {"query": "connection pool"}), ("INC-002", {"level": "ERROR"}),
             ("INC-003", {"query": "deploy", "start": "2026-03-01T00:00:00Z"})]
    out = "\n".join(log_search(inc, **kw).model_dump_json() for inc, kw in cases)
    assert hashlib.sha256(out.encode()).hexdigest()[:16] == "0305edc8eea69168"


# --- ToolBox ------------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["mode", "alert_time"])
def test_the_model_cannot_pass_mode_or_alert_time(name):
    box = ToolBox("INC-001", log_mode="rarity")
    with pytest.raises(ToolError, match="no argument"):
        box.run(PlanStep(tool="log_search", args={name: "rarity"}, reason="r"))


def test_allowed_args_are_unchanged():
    assert ALLOWED_ARGS["log_search"] == {"service", "start", "end", "query", "level", "limit"}


def test_toolbox_threads_the_alert_time_for_rarity_only():
    incident = data.load_incident("INC-001")
    step = PlanStep(tool="log_search", args={"service": incident.service}, reason="r")
    assert "default window" in ToolBox("INC-001", log_mode="rarity").run(step).summary
    legacy = ToolBox("INC-001").run(step)
    assert "default window" not in legacy.summary and "Levels:" not in legacy.summary


# --- variant and CLI ----------------------------------------------------------------------


def test_v5_is_v4_plus_rarity_and_only_in_scale100():
    v4, v5 = VARIANTS["v4-final"], VARIANTS["v5-scale"]
    assert (v5.kind, v5.retrieval, v5.verifier, v5.tuned) == (
        v4.kind, v4.retrieval, v4.verifier, v4.tuned)
    assert v5.rarity and not v5.in_original
    assert not any(v.rarity for n, v in VARIANTS.items() if n != "v5-scale")


def test_run_all_under_scale100_includes_v5_and_the_original_does_not():
    assert cli._variant_names("all", scale100=True) == [
        "v0-baseline", "v0b-filtered-baseline", "v4-final", "v5-scale"]
    assert "v5-scale" not in cli._variant_names("all", scale100=False)
    assert cli._variant_names("v5-scale", scale100=True) == ["v5-scale"]


def test_v5_is_rejected_under_the_original_condition(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--run", "v5-scale", "--incidents", "INC-002"])
    assert exc.value.code == 2
    assert "only for the scale100 condition" in capsys.readouterr().err


@pytest.mark.parametrize("run", ["v1-tools", "v2-retrieval", "v3-verifier"])
def test_the_middle_agents_are_still_rejected_under_scale100(capsys, run):
    with pytest.raises(SystemExit):
        cli.main(["--condition", "scale100", "--run", run, "--incidents", "INC-002"])
    assert "not part of the scale100 condition" in capsys.readouterr().err


def test_the_agent_run_sends_the_addendum_for_v5_only():
    from incidentiq.eval.runner import run_one
    from incidentiq.llm import MockLLM

    def system_prompt(name):
        llm = MockLLM(default="not json")
        run_one(VARIANTS[name], "INC-002", llm)
        return llm.sent[0][0]["content"]

    assert "Log search at high volume" in system_prompt("v5-scale")
    assert "Log search at high volume" not in system_prompt("v4-final")


# --- speed --------------------------------------------------------------------------------


def test_a_search_at_scale_100_takes_under_200_ms_when_warm(monkeypatch):
    monkeypatch.setenv("INCIDENTIQ_LOG_SCALE", "100")
    incident = data.load_incident("INC-002")
    data.load_logs("INC-002")  # generating the lines is not part of the search
    log_search("INC-002", mode="rarity", alert_time=incident.start_time)
    started = time.perf_counter()
    log_search("INC-002", mode="rarity", alert_time=incident.start_time)
    assert time.perf_counter() - started < 0.2


# --- results record the log mode ----------------------------------------------------------


@pytest.mark.parametrize("run, recorded", [("v5-scale", "rarity"), ("v4-final", None)])
def test_only_v5_results_record_the_log_mode(monkeypatch, tmp_path, run, recorded):
    import json

    from incidentiq.llm import MockLLM

    monkeypatch.setattr(cli, "get_llm", lambda mode: MockLLM(default="not json"))
    monkeypatch.setattr(cli, "RESULTS_DIR", tmp_path)
    cli.main(["--condition", "scale100", "--run", run, "--incidents", "INC-002"])
    results = json.loads((tmp_path / "scale100" / run / "results.json").read_text(encoding="utf-8"))
    assert results.get("log_mode") == recorded
    assert "rarity" in VARIANTS["v5-scale"].description
