"""The agent loop with a scripted mock LLM and fake tools: no network, no database."""

import json

import pytest

from incidentiq import data
from incidentiq.agents.graph import run_incident
from incidentiq.agents.toolbox import ToolBox
from incidentiq.llm import MockLLM
from incidentiq.schemas import Evidence, PlanStep, ToolResult
from incidentiq.tools import ToolError

INC = "INC-001"
SERVICE = data.load_incident(INC).service


def _plan(*steps, done=False, why="because") -> str:
    return json.dumps({"reasoning": why, "done": done, "steps": [
        {"tool": t, "args": a, "reason": "r"} for t, a in steps]})


def _observe(category="disk_full", ids=("L-0001",)) -> str:
    return json.dumps({"summary": "saw something", "hypotheses": [
        {"root_cause_category": category, "rationale": "evidence", "supporting_evidence_ids": list(ids)}]})


def _report(cites=("L-0001",), actions=("R-06-5",)) -> str:
    return json.dumps({
        "incident_id": "WRONG", "root_cause_category": "disk_full", "confidence": "high",
        "root_cause_summary": "The disk filled up.",
        "claims": [{"statement": "writes failed", "evidence_ids": list(cites)}],
        "recommended_actions": [{"statement": "free space", "evidence_ids": list(actions)}],
        "ruled_out": []})


def fake_runbooks(query, k=3):
    return ToolResult(tool="runbook_retrieve", args={"query": query, "k": k}, summary="1 section",
                      evidence=[Evidence(evidence_id="R-06-5", kind="runbook",
                                         excerpt="Disk full - Mitigation: free space")])


def _toolbox():
    return ToolBox(INC, runbook_search=fake_runbooks)


def _llm(*, planner, observer=None, reporter=None):
    return MockLLM(rules=[
        ("ROLE: planner", planner),
        ("ROLE: observer", observer or _observe()),
        ("ROLE: reporter", reporter or _report())])


def test_loop_runs_tools_then_reports_and_stops_when_the_planner_is_done():
    llm = _llm(planner=[
        _plan(("log_search", {"service": SERVICE, "level": "ERROR"}), ("runbook_retrieve", {"query": "disk"})),
        _plan(done=True)])
    result = run_incident(INC, llm, _toolbox())
    s = result.state
    assert [o.tool for o in s.observations] == ["log_search", "runbook_retrieve"]
    assert s.step_count == 2 and s.planner_done
    assert s.diagnosis and s.diagnosis.incident_id == INC  # copied from the state, not the model
    assert len(s.planner_notes) == 2 and len(s.observer_notes) == 1
    assert [o.round for o in s.observations] == [1, 1]


def test_the_step_cap_stops_a_planner_that_never_finishes():
    llm = _llm(planner=_plan(("log_search", {"service": SERVICE, "query": "x"}),
                             ("metrics_query", {"service": SERVICE, "metric": "cpu_pct"}),
                             ("metrics_query", {"service": SERVICE, "metric": "memory_pct"})))
    # the same plan every round: duplicates still count as steps, so the cap ends the loop
    result = run_incident(INC, llm, _toolbox(), max_steps=5)
    assert result.state.step_count == 5 and result.state.diagnosis is not None
    assert llm.stats.calls < 20


def test_a_planner_that_asks_for_nothing_ends_the_loop():
    result = run_incident(INC, _llm(planner=_plan()), _toolbox())
    assert result.state.step_count == 0 and result.state.diagnosis is not None


def test_bad_tool_arguments_become_an_error_observation_the_planner_can_see():
    llm = _llm(planner=[
        _plan(("metrics_query", {"service": "nope", "metric": "cpu_pct"}),
              ("log_search", {"bogus": 1})),
        _plan(done=True)])
    s = run_incident(INC, llm, _toolbox()).state
    assert all(o.error for o in s.observations) and len(s.observations) == 2
    assert "unknown service" in s.observations[0].summary
    assert "no argument" in s.observations[1].summary
    second_planner_prompt = next(m for m in llm.sent if "ROLE: planner" in m[0]["content"]
                                 and "Tool error" in m[1]["content"])
    assert second_planner_prompt


def test_repeating_an_identical_call_is_flagged_not_rerun():
    step = ("log_search", {"service": SERVICE, "query": "error"})
    llm = _llm(planner=[_plan(step), _plan(step), _plan(done=True)])
    obs = run_incident(INC, llm, _toolbox()).state.observations
    assert not obs[0].error and obs[1].error and "Duplicate" in obs[1].summary


def test_hypotheses_citing_unknown_evidence_are_filtered():
    llm = _llm(planner=[_plan(("log_search", {"service": SERVICE, "level": "ERROR"})),
                        _plan(done=True)],
               observer=_observe(ids=("L-9999",)))
    s = run_incident(INC, llm, _toolbox()).state
    assert s.hypotheses[0].supporting_evidence_ids == []


def test_the_second_observe_prompt_points_at_the_new_results():
    llm = _llm(planner=[
        _plan(("log_search", {"service": SERVICE, "level": "ERROR"})),
        _plan(("metrics_query", {"service": SERVICE, "metric": "cpu_pct"})),
        _plan(done=True)])
    run_incident(INC, llm, _toolbox())
    observer_prompts = [m[1]["content"] for m in llm.sent if "ROLE: observer" in m[0]["content"]]
    assert "steps 1 onwards" in observer_prompts[0] and "steps 2 onwards" in observer_prompts[1]


class LeakyTools(ToolBox):
    """A tool that returns raw PII, to check the act node redacts before anything is stored."""

    def run(self, step: PlanStep) -> ToolResult:
        return ToolResult(
            tool=step.tool, args=dict(step.args), summary="found sam@example.org",
            evidence=[Evidence(evidence_id="L-0001", kind="log",
                               excerpt="login failed for sam@example.org api_key=iq_sk_abcdefghijklmnop12345678")])


def test_tool_output_is_redacted_before_it_is_stored_or_sent_to_the_model():
    llm = _llm(planner=[_plan(("log_search", {"service": SERVICE})), _plan(done=True)])
    s = run_incident(INC, llm, LeakyTools(INC)).state
    stored = s.model_dump_json()
    sent = json.dumps(llm.sent)
    for secret in ("sam@example.org", "iq_sk_abcdefghijklmnop12345678"):
        assert secret not in stored and secret not in sent
    assert "[EMAIL_1]" in s.observations[0].evidence[0].excerpt


def test_alert_text_pii_is_redacted_in_prompts(monkeypatch):
    incident = data.load_incident(INC).model_copy(
        update={"alert_text": "checkout errors; customer sam@example.org reported"})
    monkeypatch.setattr(data, "load_incident", lambda _id: incident)
    llm = _llm(planner=_plan())
    run_incident(INC, llm, _toolbox())
    assert "sam@example.org" not in json.dumps(llm.sent)


def test_validation_errors_are_shown_to_the_reporter_on_a_retry():
    from incidentiq.agents.prompts import reporter_messages
    from incidentiq.schemas import GraphState

    state = GraphState(incident=data.load_incident(INC),
                       validation_errors=["claim 1 cites unknown ID L-9999"])
    assert "L-9999" in reporter_messages(state)[1]["content"]


def test_toolbox_rejects_unknown_arguments_and_missing_required_ones():
    box = _toolbox()
    with pytest.raises(ToolError, match="needs argument"):
        box.run(PlanStep(tool="metrics_query", args={"service": SERVICE}, reason=""))
    with pytest.raises(ToolError, match="whole number"):
        box.run(PlanStep(tool="log_search", args={"limit": "many"}, reason=""))
