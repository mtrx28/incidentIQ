"""The evaluation harness: scoring, variants, the baseline, reports and the CLI's exit paths."""

import json

import pytest

from incidentiq import data
from incidentiq.agents.baseline import DUMP_LINES, diagnose_baseline, log_dump
from incidentiq.agents.planner import planner_node
from incidentiq.eval import __main__ as cli
from incidentiq.eval.metrics import auto_signals, score_incident, summarise, wilson
from incidentiq.eval.report import build_results, comparison_markdown, render_files, to_markdown
from incidentiq.eval.runner import IncidentRun, find_leaks, run_one, run_variant
from incidentiq.eval.variants import VARIANTS
from incidentiq.llm import LiveLLM, MockLLM, QuotaExhausted, ResponseCache
from incidentiq.llm.live import RateLimited
from incidentiq.schemas import (
    Claim,
    Diagnosis,
    Evidence,
    GraphState,
    Hypothesis,
    Observation,
)
from incidentiq.tools.runbooks_keyword import keyword_runbook_retrieve, search_keyword

TRUTH_ID = next(i for i in data.list_incident_ids("dev")
                if data.load_ground_truth(i).root_cause_category == "disk_full"
                and not data.load_ground_truth(i).hard_case)
TRUTH = data.load_ground_truth(TRUTH_ID)
GOLD_LOG = next(i for i in TRUTH.gold_evidence_ids if i.startswith("L-"))
GOLD_RUNBOOK = TRUTH.gold_runbook_section


def _state(cites_claim, cites_action, category="disk_full", known=None) -> GraphState:
    known = known or {GOLD_LOG: "log", GOLD_RUNBOOK: "runbook", "L-9998": "log"}
    s = GraphState(incident=data.load_incident(TRUTH_ID), step_count=3)
    s.observations.append(Observation(
        step=1, tool="log_search", args={}, summary="s",
        evidence=[Evidence(evidence_id=i, kind=k, excerpt="No space left on device disk full "
                           "writes failed free space delete old logs")
                  for i, k in known.items()]))
    s.diagnosis = Diagnosis(
        incident_id=TRUTH_ID, root_cause_category=category, confidence="high",
        root_cause_summary="x",
        claims=[Claim(statement="Writes failed because the disk was full.",
                      evidence_ids=cites_claim)],
        recommended_actions=[Claim(statement="Free disk space by deleting old logs.",
                                   evidence_ids=cites_action)])
    return s


def _score(state, verifier_on=False) -> dict:
    return score_incident(IncidentRun(TRUTH_ID, state), TRUTH, verifier_on)


# --- scoring ------------------------------------------------------------------------------


def test_a_fully_correct_run_scores_everything():
    row = _score(_state([GOLD_LOG], [GOLD_RUNBOOK]))
    assert row["correct"] and row["strict_correct"] and row["gold_runbook_cited"]
    assert row["cited_valid"] == row["cited_total"] == 2
    assert row["supported_lexical"] == row["supported_gold"] == 2
    assert row["gold_cited"] == 2 and row["cause_evidence_retrieved"]


def test_right_category_without_cause_evidence_is_not_strictly_correct():
    row = _score(_state(["L-9998"], [GOLD_RUNBOOK]))
    assert row["correct"] and not row["strict_correct"] and row["supported_gold"] == 1


def test_wrong_category_is_wrong_whatever_it_cites():
    row = _score(_state([GOLD_LOG], [GOLD_RUNBOOK], category="bad_deployment"))
    assert not row["correct"] and not row["strict_correct"]


def test_citation_validity_counts_ids_never_retrieved():
    row = _score(_state([GOLD_LOG, "L-0000"], [GOLD_RUNBOOK]))
    assert row["cited_total"] == 3 and row["cited_valid"] == 2


def test_a_failed_run_counts_as_wrong_with_no_citations():
    row = score_incident(IncidentRun(TRUTH_ID, None, error="LLMOutputError: x"), TRUTH, True)
    assert not row["correct"] and row["cited_total"] == 0 and row["error"]
    assert "run failed" in auto_signals(row)[0]


def test_summary_pools_and_reports_a_confidence_interval():
    rows = [_score(_state([GOLD_LOG], [GOLD_RUNBOOK])),
            _score(_state([GOLD_LOG], [GOLD_RUNBOOK], category="bad_deployment"))]
    s = summarise(rows)
    assert s["n"] == 2 and s["accuracy"]["rate"] == 0.5 and s["accuracy"]["correct"] == 1
    lo, hi = s["accuracy"]["ci95"]
    assert lo < 0.5 < hi and s["citation_validity"] == 1.0


def test_wilson_interval():
    assert wilson(0, 0) == (0.0, 0.0)
    lo, hi = wilson(5, 10)
    assert 0.23 < lo < 0.24 and 0.76 < hi < 0.77
    assert wilson(25, 25)[1] == 1.0


def test_auto_signals_flag_the_usual_suspects():
    row = _score(_state([GOLD_LOG], [GOLD_RUNBOOK], category="bad_deployment"))
    row |= {"steps": 2, "retrieved_runbook": False, "cause_evidence_retrieved": False}
    signals = auto_signals(row)
    assert "stopped after 2 steps" in signals and "no runbook retrieved" in signals
    assert "never retrieved the cause evidence" in signals


# --- variants -----------------------------------------------------------------------------


def test_the_five_stages_differ_exactly_as_the_story_says():
    v = VARIANTS
    original = [name for name, variant in v.items() if variant.in_original]
    assert original == ["v0-baseline", "v1-tools", "v2-retrieval", "v3-verifier", "v4-final"]
    assert v["v0-baseline"].kind == "baseline"
    assert (v["v1-tools"].retrieval, v["v1-tools"].verifier) == ("keyword", False)
    assert (v["v2-retrieval"].retrieval, v["v2-retrieval"].verifier) == ("embedding", False)
    assert v["v3-verifier"].verifier and not v["v3-verifier"].tuned
    assert v["v4-final"].verifier and v["v4-final"].tuned


# --- the v0 baseline ----------------------------------------------------------------------


def test_the_baseline_dump_is_the_last_100_lines_before_the_alert():
    lines = log_dump(TRUTH_ID)
    alert = data.parse_ts(data.load_incident(TRUTH_ID).start_time)
    assert len(lines) == DUMP_LINES
    assert all(data.parse_ts(ln.ts) <= alert for ln in lines)
    assert [ln.ts for ln in lines] == sorted(ln.ts for ln in lines)


def test_the_baseline_makes_one_call_and_cites_only_the_dump():
    dump_id = log_dump(TRUTH_ID)[-1].line_id
    reply = json.dumps({
        "incident_id": "x", "root_cause_category": "disk_full", "confidence": "low",
        "root_cause_summary": "disk", "claims": [{"statement": "full", "evidence_ids": [dump_id]}],
        "recommended_actions": [], "ruled_out": []})
    llm = MockLLM(rules=[("ROLE: baseline", reply)])
    result = diagnose_baseline(TRUTH_ID, llm)
    assert llm.stats.calls == 1 and result.state.step_count == 0
    assert result.state.diagnosis.incident_id == TRUTH_ID
    assert dump_id in result.state.known_evidence_ids()


# --- keyword retrieval (v1) ---------------------------------------------------------------


def test_keyword_search_matches_exact_words_but_not_meaning():
    top = [h.section_id for h in search_keyword("no space left on device write failed", 3)]
    assert any(i.startswith("R-06-") for i in top)
    assert search_keyword("zzzz qqqq", 3) == []  # nothing in common: no hits
    assert [h.section_id for h in search_keyword("disk full", 5)] == \
        [h.section_id for h in search_keyword("disk full", 5)]


def test_keyword_tool_result_has_the_same_shape_as_the_embedding_tool():
    result = keyword_runbook_retrieve("restart pods connection pool", 2)
    assert result.tool == "runbook_retrieve" and all(e.kind == "runbook" for e in result.evidence)


# --- running ------------------------------------------------------------------------------


def test_leak_detection_finds_injected_values_in_prompts():
    item = next(i for i in json.loads((data.DATA_DIR / "pii_manifest.json").read_text())
                if i["incident_id"] == TRUTH_ID)
    assert find_leaks(TRUTH_ID, [[{"role": "user", "content": f"x {item['value']} y"}]]) \
        == [item["type"]]
    assert find_leaks(TRUTH_ID, [[{"role": "user", "content": "nothing here"}]]) == []


def test_a_model_that_never_returns_valid_output_is_recorded_not_fatal():
    llm = MockLLM(default="not json")
    run = run_one(VARIANTS["v0-baseline"], TRUTH_ID, llm)
    assert run.state is None and "LLMOutputError" in run.error
    assert run.llm["calls"] == 3  # the schema retries were counted


def test_run_variant_reports_progress_per_incident():
    lines: list[str] = []
    run_variant(VARIANTS["v0-baseline"], [TRUTH_ID], MockLLM(default="not json"),
                progress=lines.append)
    assert len(lines) == 1 and TRUTH_ID in lines[0] and "MISS" in lines[0]


# --- tuned stopping rule (v4) -------------------------------------------------------------


def _planner_says_done() -> MockLLM:
    return MockLLM(rules=[("ROLE: planner", json.dumps(
        {"reasoning": "done", "done": True, "steps": []}))])


def _state_without_runbook() -> GraphState:
    s = GraphState(incident=data.load_incident(TRUTH_ID), step_count=2)
    s.hypotheses = [Hypothesis(root_cause_category="disk_full", rationale="r")]
    return s


def test_untuned_planner_may_finish_without_runbook_guidance():
    update = planner_node(_state_without_runbook(), _planner_says_done(), tuned=False)
    assert update["planner_done"] and update["plan"] == []


def test_tuned_planner_is_sent_to_get_runbook_guidance_first():
    update = planner_node(_state_without_runbook(), _planner_says_done(), tuned=True)
    assert not update["planner_done"]
    step = update["plan"][0]
    assert step.tool == "runbook_retrieve" and "disk full" in step.args["query"]


def test_tuned_planner_finishes_once_a_runbook_was_retrieved():
    s = _state_without_runbook()
    s.observations.append(Observation(
        step=1, tool="runbook_retrieve", args={}, summary="s",
        evidence=[Evidence(evidence_id="R-06-5", kind="runbook", excerpt="x")]))
    assert planner_node(s, _planner_says_done(), tuned=True)["planner_done"]


# --- reports ------------------------------------------------------------------------------


def _runs() -> list[IncidentRun]:
    return [IncidentRun(TRUTH_ID, _state([GOLD_LOG], [GOLD_RUNBOOK], category="bad_deployment"),
                        {"calls": 5, "prompt_tokens": 1000, "completion_tokens": 100,
                         "latency_s": 12.5, "retries": 0, "redactions": 0})]


def test_reports_are_deterministic_and_carry_no_timestamps():
    variant = VARIANTS["v3-verifier"]
    a = render_files(variant, _runs(), {})[1]
    b = render_files(variant, _runs(), {})[1]
    assert a == b
    assert set(a) == {"results.json", "results.md", "traces.jsonl"}
    assert "elapsed" not in a["results.json"] and "T0" not in a["results.md"]


def test_the_failure_table_uses_hand_written_notes_when_present():
    results = build_results(VARIANTS["v3-verifier"], _runs())
    assert "(not yet analysed)" in to_markdown(results, {})
    md = to_markdown(results, {TRUTH_ID: "chose the wrong database cause"})
    assert "chose the wrong database cause" in md and TRUTH_ID in md


def test_results_include_every_split_that_was_run_and_the_redaction_block():
    results = build_results(VARIANTS["v2-retrieval"], _runs())
    assert "dev" in results["splits"] and "test" not in results["splits"]
    assert results["splits"]["dev"]["n"] == 1 and "by_hard_case" in results["splits"]["dev"]
    assert results["redaction"]["prompt_leaks_in_this_run"] == 0


def test_comparison_table_has_a_row_per_run_with_test_results():
    results = build_results(VARIANTS["v2-retrieval"], _runs())
    assert comparison_markdown([results]).count("v2-retrieval") == 0  # no test split ran
    results["splits"]["test"] = results["splits"]["dev"]
    assert comparison_markdown([results]).count("v2-retrieval") == 1


# --- CLI paths ----------------------------------------------------------------------------


def test_replay_with_nothing_recorded_exits_with_a_cache_miss(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path))
    code = cli.main(["--run", "v0-baseline", "--llm", "replay", "--incidents", TRUTH_ID,
                     "--out", str(tmp_path / "out")])
    assert code == 2 and "CACHE MISS" in capsys.readouterr().err


def test_hitting_the_daily_quota_stops_cleanly_and_writes_nothing(tmp_path, monkeypatch, capsys):
    def transport(messages, json_mode):
        raise RateLimited("quota PerDay", daily=True)

    live = LiveLLM("m", transport, ResponseCache(tmp_path / "cache"), sleep=lambda s: None)
    monkeypatch.setattr(cli, "get_llm", lambda mode: live)
    out = tmp_path / "out"
    code = cli.main(["--run", "v0-baseline", "--llm", "live", "--incidents", TRUTH_ID,
                     "--out", str(out)])
    assert code == 3 and "rerun" in capsys.readouterr().err and not out.exists()
    assert issubclass(QuotaExhausted, RuntimeError)


def test_check_mode_reports_a_difference_instead_of_overwriting(tmp_path):
    files = {"results.json": "{}\n", "results.md": "a\n"}
    (tmp_path / "results.json").write_text("{}\n", encoding="utf-8")
    problems = cli._compare(tmp_path, files)
    assert problems == [f"{tmp_path / 'results.md'} is missing"]
    (tmp_path / "results.md").write_text("different\n", encoding="utf-8")
    assert "differs" in cli._compare(tmp_path, files)[0]
    (tmp_path / "results.md").write_text("a\n", encoding="utf-8")
    assert cli._compare(tmp_path, files) == []


def test_unknown_run_name_is_rejected():
    with pytest.raises(SystemExit):
        cli.main(["--run", "v9-magic"])
