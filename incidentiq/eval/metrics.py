"""Scoring. Definitions (all computed from the run's own records and the labeled ground truth):

accuracy            predicted root-cause category equals the true one.
strict accuracy     category correct AND the diagnosis cites at least one gold log or metric ID,
                    i.e. it points at the evidence that actually shows the cause.
citation validity   share of cited IDs (claims and actions) that were retrieved in this run.
citation support    share of statements whose cited evidence supports them, two ways:
                      lexical  the verifier's own overlap check (so, for runs with the verifier
                               on, this measure partly grades its own homework);
                      gold     the statement cites at least one gold evidence ID (stricter, and
                               independent of the verifier).
gold recall         share of the incident's gold evidence IDs that appear in the citations.
gold runbook cited  an action cites the gold runbook section.
Failed runs (the model never produced valid output) count as wrong with no citations.
"""

import math
from collections import defaultdict

from incidentiq.agents.verifier import collect_evidence, verify
from incidentiq.eval.runner import IncidentRun
from incidentiq.schemas import GroundTruth


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% confidence interval for a proportion. Wide for small n, which is the honest picture."""
    if n == 0:
        return 0.0, 0.0
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4)


def score_incident(run: IncidentRun, truth: GroundTruth, verifier_on: bool) -> dict:
    gold = set(truth.gold_evidence_ids)
    gold_cause = {i for i in gold if i[0] in "LM"}  # log and metric evidence of the cause
    gold_runbook = {i for i in gold if i.startswith("R-")}
    state, diag = run.state, run.state.diagnosis if run.state else None

    statements = (diag.claims + diag.recommended_actions) if diag else []
    cited_per_statement = [list(dict.fromkeys(s.evidence_ids)) for s in statements]
    cited = {i for ids in cited_per_statement for i in ids}
    known = state.known_evidence_ids() if state else set()
    cited_total = sum(len(ids) for ids in cited_per_statement)
    cited_valid = sum(i in known for ids in cited_per_statement for i in ids)
    supported_lexical = 0
    if diag and state:
        supported_lexical = sum(c.supported for c in verify(diag, collect_evidence(state)).checks)

    predicted = diag.root_cause_category if diag else None
    correct = predicted == truth.root_cause_category
    return {
        "incident_id": truth.incident_id, "split": truth.split,
        "category": truth.root_cause_category, "hard_case": truth.hard_case or "standard",
        "predicted": predicted, "correct": correct,
        "strict_correct": correct and bool(cited & gold_cause),
        "error": run.error,
        "cited_total": cited_total, "cited_valid": cited_valid,
        "statements": len(statements), "supported_lexical": supported_lexical,
        "supported_gold": sum(bool(set(ids) & gold) for ids in cited_per_statement),
        "gold_total": len(gold), "gold_cited": len(cited & gold),
        "gold_runbook_cited": bool(cited & gold_runbook),
        "cause_evidence_retrieved": bool(known & gold_cause),
        "hypothesis_had_truth": bool(state) and any(
            h.root_cause_category == truth.root_cause_category for h in state.hypotheses),
        "steps": state.step_count if state else 0,
        "tools": [o.tool for o in state.observations if o.step > 0] if state else [],
        "tool_errors": sum(o.error for o in state.observations) if state else 0,
        "hit_step_cap": bool(state) and state.step_count >= state.max_steps,
        "retrieved_runbook": any(e.kind == "runbook" for o in state.observations
                                 for e in o.evidence) if state else False,
        "reporter_retries": state.retries if state else 0,
        "unverified": bool(diag and diag.unverified),
        "verified": (bool(state.verification and state.verification.ok) if verifier_on and state
                     else None),
        "llm": run.llm, "leaks": run.leaks,
    }


def _rate(k: float, n: float) -> float:
    return round(k / n, 4) if n else 0.0


def summarise(rows: list[dict]) -> dict:
    n = len(rows)
    correct = sum(r["correct"] for r in rows)
    lo, hi = wilson(correct, n)

    def mean(key: str) -> float:
        return round(sum(r[key] for r in rows) / n, 3) if n else 0.0

    def llm_mean(key: str) -> float:
        return round(sum(r["llm"].get(key, 0) for r in rows) / n, 3) if n else 0.0

    return {
        "n": n,
        "accuracy": {"correct": correct, "rate": _rate(correct, n), "ci95": [lo, hi]},
        "strict_accuracy": {"correct": sum(r["strict_correct"] for r in rows),
                            "rate": _rate(sum(r["strict_correct"] for r in rows), n)},
        "citation_validity": _rate(sum(r["cited_valid"] for r in rows),
                                   sum(r["cited_total"] for r in rows)),
        "citation_support_lexical": _rate(sum(r["supported_lexical"] for r in rows),
                                          sum(r["statements"] for r in rows)),
        "citation_support_gold": _rate(sum(r["supported_gold"] for r in rows),
                                       sum(r["statements"] for r in rows)),
        "gold_evidence_recall": round(sum(_rate(r["gold_cited"], r["gold_total"])
                                          for r in rows) / n, 4) if n else 0.0,
        "gold_runbook_cited": _rate(sum(r["gold_runbook_cited"] for r in rows), n),
        "cause_evidence_retrieved": _rate(sum(r["cause_evidence_retrieved"] for r in rows), n),
        "efficiency": {
            "steps_per_incident": mean("steps"), "llm_calls_per_incident": llm_mean("calls"),
            "reporter_retries_per_incident": mean("reporter_retries"),
            "prompt_tokens_per_incident": llm_mean("prompt_tokens"),
            "completion_tokens_per_incident": llm_mean("completion_tokens"),
            "recorded_llm_latency_s_per_incident": llm_mean("latency_s"),
        },
        "unverified": sum(r["unverified"] for r in rows),
        "failed_runs": sum(bool(r["error"]) for r in rows),
        "tool_errors": sum(r["tool_errors"] for r in rows),
        "prompt_leaks": sum(len(r["leaks"]) for r in rows),
    }


def breakdown(rows: list[dict], key: str) -> dict:
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        groups[r[key]].append(r)
    return {k: {"n": len(v), "correct": sum(r["correct"] for r in v),
                "rate": _rate(sum(r["correct"] for r in v), len(v))}
            for k, v in sorted(groups.items())}


def auto_signals(r: dict) -> list[str]:
    """Mechanical hints for writing the failure analysis by hand. Not the analysis itself."""
    signals = []
    if r["error"]:
        signals.append("run failed: model never returned valid output")
    if r["steps"] and r["steps"] <= 3:
        signals.append(f"stopped after {r['steps']} steps")
    if r["hit_step_cap"]:
        signals.append("hit the step cap")
    if not r["cause_evidence_retrieved"]:
        signals.append("never retrieved the cause evidence")
    if r["hypothesis_had_truth"]:
        signals.append("true cause was among its hypotheses")
    if r["steps"] and not r["retrieved_runbook"]:
        signals.append("no runbook retrieved")
    if r["unverified"]:
        signals.append("unverified after retries")
    return signals
