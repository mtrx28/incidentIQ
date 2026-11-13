"""Run one benchmark variant over a list of incidents."""

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from functools import cache

from incidentiq import data
from incidentiq.agents.baseline import diagnose_baseline
from incidentiq.agents.graph import run_incident
from incidentiq.agents.toolbox import ToolBox
from incidentiq.config import DATA_DIR
from incidentiq.eval.variants import Variant
from incidentiq.llm.base import LLMClient, LLMOutputError, LLMStats
from incidentiq.schemas import GraphState
from incidentiq.tools.runbooks_keyword import keyword_runbook_retrieve


@dataclass
class IncidentRun:
    incident_id: str
    state: GraphState | None  # None when the run failed
    llm: dict = field(default_factory=dict)  # this incident's share of the client's stats
    leaks: list[str] = field(default_factory=list)  # injected PII types found in prompts
    error: str | None = None


@cache
def _injected() -> dict[str, list[dict]]:
    by_incident: dict[str, list[dict]] = {}
    for item in json.loads((DATA_DIR / "pii_manifest.json").read_text(encoding="utf-8")):
        by_incident.setdefault(item["incident_id"], []).append(item)
    return by_incident


def find_leaks(incident_id: str, prompts: list[list[dict]]) -> list[str]:
    """Types of injected values that appear verbatim in any prompt sent to the model."""
    text = "\n".join(m["content"] for messages in prompts for m in messages)
    return sorted(i["type"] for i in _injected().get(incident_id, []) if i["value"] in text)


def _delta(before: LLMStats, after: LLMStats) -> dict:
    return {k: round(getattr(after, k) - getattr(before, k), 3) for k in asdict(after)}


def run_one(variant: Variant, incident_id: str, llm: LLMClient, max_steps: int | None = None
            ) -> IncidentRun:
    """Run one incident. A model that cannot produce valid output is recorded as a failure;
    infrastructure problems (cache miss, quota, database down) are raised, not hidden."""
    before, sent_before = LLMStats(**asdict(llm.stats)), len(llm.sent)
    error, state = None, None
    try:
        if variant.kind == "baseline":
            state = diagnose_baseline(incident_id, llm, variant.filtered).state
        else:
            toolbox = (ToolBox(incident_id, runbook_search=keyword_runbook_retrieve)
                       if variant.retrieval == "keyword" else None)
            state = run_incident(incident_id, llm, toolbox, max_steps=max_steps,
                                 verify_output=variant.verifier, tuned=variant.tuned,
                                 v5=variant.rarity).state
    except LLMOutputError as exc:
        error = f"LLMOutputError: {exc}"
    return IncidentRun(incident_id, state, _delta(before, llm.stats),
                       find_leaks(incident_id, llm.sent[sent_before:]), error)


def run_variant(variant: Variant, incident_ids: list[str], llm: LLMClient,
                progress: Callable[[str], None] = print, max_steps: int | None = None
                ) -> list[IncidentRun]:
    runs = []
    for n, incident_id in enumerate(incident_ids, start=1):
        run = run_one(variant, incident_id, llm, max_steps)
        truth = data.load_ground_truth(incident_id)
        predicted = run.state.diagnosis.root_cause_category if run.state and run.state.diagnosis \
            else f"ERROR ({run.error})"
        mark = "ok  " if predicted == truth.root_cause_category else "MISS"
        progress(f"[{variant.name} {n}/{len(incident_ids)}] {incident_id} {mark} "
                 f"predicted={predicted} true={truth.root_cause_category} "
                 f"llm_calls={run.llm.get('calls', 0):.0f}")
        runs.append(run)
    return runs
