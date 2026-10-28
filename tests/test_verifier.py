"""The verifier's rules, and the retry loop around it."""

import json

import pytest

from incidentiq import data
from incidentiq.agents.graph import run_incident
from incidentiq.agents.toolbox import ToolBox
from incidentiq.agents.verifier import (
    LEXICAL_THRESHOLD,
    MAX_RETRIES,
    key_terms,
    lexical_overlap,
    verify,
)
from incidentiq.llm import MockLLM
from incidentiq.schemas import Claim, Diagnosis, Evidence, ToolResult

LOG = Evidence(
    evidence_id="L-0271", kind="log",
    excerpt="2026-03-11T02:40:12Z search ERROR HikariPool-1 - Connection is not available, request "
            "timed out after 30000ms (total=50, active=50, idle=0, waiting=50)")
METRIC = Evidence(
    evidence_id="M-050", kind="metric",
    excerpt="search.error_rate_pct from 2026-03-11T02:30:00Z to 2026-03-11T03:00:00Z: min=0.32 "
            "max=19.54 mean=14.03 last=19.54")
RUNBOOK = Evidence(
    evidence_id="R-02-5", kind="runbook",
    excerpt="Database connection pool exhaustion - Mitigation: Restart the affected instances to "
            "release held connections as a first step. Then raise the pool maximum.")
EVIDENCE = {e.evidence_id: [e] for e in (LOG, METRIC, RUNBOOK)}


def diagnosis(claims=None, actions=None, category="db_connection_pool_exhaustion") -> Diagnosis:
    return Diagnosis(
        incident_id="INC-006", root_cause_category=category, confidence="high",
        root_cause_summary="The connection pool was exhausted.",
        claims=claims or [
            Claim(statement="The database connection pool was exhausted: active connections "
                            "reached the pool maximum of 50 and requests timed out.",
                  evidence_ids=["L-0271"])],
        recommended_actions=[
            Claim(statement="Restart the affected instances to release held connections.",
                  evidence_ids=["R-02-5"])] if actions is None else actions)


# --- the happy path -----------------------------------------------------------------------


def test_a_grounded_diagnosis_passes():
    result = verify(diagnosis(), EVIDENCE)
    assert result.ok and result.errors == [] and result.method == "lexical"
    assert [c.supported for c in result.checks] == [True, True]
    assert all(c.method == "lexical" and c.overlap >= LEXICAL_THRESHOLD for c in result.checks)


def test_a_numeric_claim_is_matched_through_its_numbers():
    claim = Claim(statement="The error rate peaked at 19.54%.", evidence_ids=["M-050"])
    assert verify(diagnosis(claims=[claim]), EVIDENCE).ok


# --- rule 1: invented IDs -----------------------------------------------------------------


def test_invented_evidence_id_is_rejected_and_named():
    claim = Claim(statement="Connections were exhausted.", evidence_ids=["L-9999"])
    result = verify(diagnosis(claims=[claim]), EVIDENCE)
    assert not result.ok
    assert "L-9999" in result.errors[0] and "not retrieved" in result.errors[0]
    assert "L-0271" in result.errors[0]  # points the reporter at IDs that do exist
    assert result.checks[0].unknown_ids == ["L-9999"] and not result.checks[0].supported


def test_an_id_invented_inside_an_action_is_also_rule_1():
    action = Claim(statement="Restart the instances.", evidence_ids=["R-99-9"])
    result = verify(diagnosis(actions=[action]), EVIDENCE)
    assert not result.ok and "R-99-9" in result.errors[0]


def test_a_real_id_from_another_run_is_still_unknown():
    other_run = {"L-0271": [LOG]}  # this run never retrieved the metric
    claim = Claim(statement="Error rate peaked at 19.54%.", evidence_ids=["M-050"])
    assert not verify(diagnosis(claims=[claim]), other_run).ok


# --- rule 2: actions must cite a runbook --------------------------------------------------


def test_an_action_that_cites_a_log_line_instead_of_a_runbook_is_rejected():
    action = Claim(statement="Restart the affected instances.", evidence_ids=["L-0271"])
    result = verify(diagnosis(actions=[action]), EVIDENCE)
    assert not result.ok
    assert "must cite a runbook section" in result.errors[0] and "R-02-5" in result.errors[0]


def test_an_action_citing_a_log_and_a_runbook_is_fine():
    action = Claim(statement="Restart the affected instances to release connections.",
                   evidence_ids=["L-0271", "R-02-5"])
    assert verify(diagnosis(actions=[action]), EVIDENCE).ok


def test_no_recommended_actions_is_rejected():
    result = verify(diagnosis(actions=[]), EVIDENCE)
    assert not result.ok and "no recommended actions" in result.errors[0].lower()
    assert "R-02-5" in result.errors[0]


def test_no_actions_and_no_runbook_retrieved_says_so():
    result = verify(diagnosis(actions=[]), {"L-0271": [LOG]})
    assert "no runbook section was retrieved" in result.errors[0]


# --- rule 3: support ----------------------------------------------------------------------


def test_a_claim_unrelated_to_its_citation_is_rejected():
    claim = Claim(statement="The disk filled up and writes failed with ENOSPC.",
                  evidence_ids=["L-0271"])
    result = verify(diagnosis(claims=[claim]), EVIDENCE)
    assert not result.ok
    assert "not supported by the evidence it cites" in result.errors[0]
    assert result.checks[0].overlap < LEXICAL_THRESHOLD and not result.checks[0].supported


def test_a_claim_that_cites_the_wrong_evidence_kind_is_caught():
    claim = Claim(statement="The database connection pool was exhausted with 50 active "
                            "connections.", evidence_ids=["M-050"])  # a metric, not the log
    assert not verify(diagnosis(claims=[claim]), EVIDENCE).ok


def test_overlap_helpers():
    assert key_terms("Timeouts were failing") == key_terms("timeout fail")
    assert lexical_overlap("the pool is exhausted", "pool exhausted everywhere") == 1.0
    assert lexical_overlap("", "anything") == 0.0
    assert lexical_overlap("pool exhausted", "disk full") == 0.0


# --- rule 4: category ---------------------------------------------------------------------


def test_a_category_outside_the_allowed_list_is_rejected():
    bad = diagnosis().model_copy(update={"root_cause_category": "gremlins"})  # skips validation
    result = verify(bad, EVIDENCE)
    assert not result.ok and "gremlins" in result.errors[0]


# --- optional LLM entailment --------------------------------------------------------------

PARAPHRASE = Claim(statement="Requests stalled because every database session was occupied.",
                   evidence_ids=["L-0271"])


def _entailment(supported: bool) -> MockLLM:
    return MockLLM(rules=[("ROLE: entailment checker",
                           json.dumps({"supported": supported, "reason": "r"}))])


def test_lexical_rejection_can_be_overturned_by_the_llm():
    llm = _entailment(True)
    result = verify(diagnosis(claims=[PARAPHRASE]), EVIDENCE, llm)
    assert result.ok and result.method == "lexical+llm"
    assert result.checks[0].method == "llm" and llm.stats.calls == 1


def test_llm_can_confirm_the_rejection():
    result = verify(diagnosis(claims=[PARAPHRASE]), EVIDENCE, _entailment(False))
    assert not result.ok and result.checks[0].method == "llm"


def test_llm_is_not_called_when_the_lexical_check_passes():
    llm = _entailment(False)
    assert verify(diagnosis(), EVIDENCE, llm).ok
    assert llm.stats.calls == 0


def test_llm_is_not_called_for_invented_ids():
    llm = _entailment(True)
    claim = Claim(statement="Something happened.", evidence_ids=["L-9999"])
    assert not verify(diagnosis(claims=[claim]), EVIDENCE, llm).ok
    assert llm.stats.calls == 0


def test_an_unusable_llm_answer_counts_as_unsupported():
    llm = MockLLM(rules=[("ROLE: entailment checker", "not json at all")])
    assert not verify(diagnosis(claims=[PARAPHRASE]), EVIDENCE, llm).ok


# --- the retry loop in the graph ----------------------------------------------------------

INC = "INC-001"
SERVICE = data.load_incident(INC).service


def _plan(*steps, done=False) -> str:
    return json.dumps({"reasoning": "why", "done": done, "steps": [
        {"tool": t, "args": a, "reason": "r"} for t, a in steps]})


OBSERVE = json.dumps({"summary": "s", "hypotheses": []})


def _report(statement="Writes failed because the disk was full.", cites=("L-0001",),
            actions=("R-06-5",)) -> str:
    return json.dumps({
        "incident_id": INC, "root_cause_category": "disk_full", "confidence": "high",
        "root_cause_summary": "The disk filled up.",
        "claims": [{"statement": statement, "evidence_ids": list(cites)}],
        "recommended_actions": [{"statement": "Free disk space by deleting old logs.",
                                 "evidence_ids": list(actions)}],
        "ruled_out": []})


GOOD_REPORT = _report()
BAD_REPORT = _report(cites=("L-9999",))  # invented ID


def _tools():
    def runbooks(query, k=3):
        return ToolResult(tool="runbook_retrieve", args={"query": query, "k": k}, summary="1",
                          evidence=[Evidence(evidence_id="R-06-5", kind="runbook",
                                             excerpt="Disk full - Mitigation: Free disk space by "
                                                     "deleting old logs and stale files.")])

    class Tools(ToolBox):
        def run(self, step):
            if step.tool == "log_search":
                return ToolResult(
                    tool="log_search", args={}, summary="1 line",
                    evidence=[Evidence(evidence_id="L-0001", kind="log",
                                       excerpt="ERROR write failed: No space left on device, "
                                               "disk full, writes failed")])
            return super().run(step)

    return Tools(INC, runbook_search=runbooks)


def _agent(reports: list[str], **kwargs):
    llm = MockLLM(rules=[
        ("ROLE: planner", [_plan(("log_search", {}), ("runbook_retrieve", {"query": "disk"})),
                           _plan(done=True)]),
        ("ROLE: observer", OBSERVE),
        ("ROLE: reporter", reports)])
    return llm, run_incident(INC, llm, _tools(), **kwargs).state


def _reporter_calls(llm) -> int:
    return sum("ROLE: reporter" in m[0]["content"] for m in llm.sent)


def test_a_good_report_passes_first_time_without_retries():
    llm, s = _agent([GOOD_REPORT])
    assert s.verification.ok and s.retries == 0 and not s.diagnosis.unverified
    assert s.validation_errors == [] and _reporter_calls(llm) == 1


def test_a_failed_report_is_sent_back_with_the_problems_and_then_passes():
    llm, s = _agent([BAD_REPORT, GOOD_REPORT])
    assert s.verification.ok and s.retries == 1 and not s.diagnosis.unverified
    assert _reporter_calls(llm) == 2
    retry_prompt = [m for m in llm.sent if "ROLE: reporter" in m[0]["content"]][1][1]["content"]
    assert "rejected for these problems" in retry_prompt and "L-9999" in retry_prompt
    assert s.diagnosis.claims[0].evidence_ids == ["L-0001"]


def test_retry_exhaustion_keeps_the_last_report_marked_unverified():
    llm, s = _agent([BAD_REPORT])  # the same bad report on every attempt
    assert _reporter_calls(llm) == 1 + MAX_RETRIES
    assert s.retries == MAX_RETRIES
    assert s.diagnosis is not None and s.diagnosis.unverified is True
    assert not s.verification.ok and "L-9999" in s.validation_errors[0]


def test_the_retry_budget_is_two():
    assert MAX_RETRIES == 2


def test_a_report_that_recovers_on_the_last_retry_is_still_verified():
    llm, s = _agent([BAD_REPORT, BAD_REPORT, GOOD_REPORT])
    assert s.verification.ok and s.retries == 2 and not s.diagnosis.unverified
    assert _reporter_calls(llm) == 3


def test_with_the_verifier_off_a_bad_report_goes_through_unchecked():
    llm, s = _agent([BAD_REPORT], verify_output=False)
    assert s.verification is None and not s.diagnosis.unverified and _reporter_calls(llm) == 1


def test_unsupported_claim_in_the_loop_is_rejected_then_fixed():
    unrelated = _report(statement="The TLS certificate expired yesterday.")
    llm, s = _agent([unrelated, GOOD_REPORT])
    assert s.verification.ok and s.retries == 1  # fixed on the retry
    assert "not supported by the evidence" in "\n".join(
        m[1]["content"] for m in llm.sent if "ROLE: reporter" in m[0]["content"])


@pytest.mark.parametrize("flag", [True, False])
def test_entailment_is_off_unless_requested(flag):
    llm = MockLLM(rules=[
        ("ROLE: planner", [_plan(("log_search", {}), ("runbook_retrieve", {"query": "d"})),
                           _plan(done=True)]),
        ("ROLE: observer", OBSERVE),
        ("ROLE: reporter", _report(statement="Requests stalled as the volume ran out of space.")),
        ("ROLE: entailment checker", json.dumps({"supported": True, "reason": "ok"}))])
    run_incident(INC, llm, _tools(), llm_entailment=flag)
    asked = any("ROLE: entailment checker" in m[0]["content"] for m in llm.sent)
    assert asked == flag
