"""Planner node: decide the next tool calls, or decide that the evidence is enough."""

from incidentiq import data
from incidentiq.agents.prompts import CATEGORIES, planner_messages
from incidentiq.llm.base import LLMClient
from incidentiq.schemas import GraphState, PlannerDecision, PlanStep


def _mitigation_step(state: GraphState) -> PlanStep:
    """A runbook lookup for the leading hypothesis (or the alert, if there is none yet)."""
    if state.hypotheses:
        cause = state.hypotheses[0].root_cause_category
        query = f"how to mitigate and fix {cause.replace('_', ' ')}: {CATEGORIES[cause]}"
    else:
        query = f"how to mitigate and fix: {state.incident.alert_text}"
    return PlanStep(tool="runbook_retrieve", args={"query": query},
                    reason="Retrieve mitigation guidance before diagnosing.")


def planner_node(state: GraphState, llm: LLMClient, tuned: bool = False, v5: bool = False) -> dict:
    remaining = state.max_steps - state.step_count
    if remaining <= 0:
        return {"plan": [], "planner_done": True}
    messages = planner_messages(
        state, data.known_services(state.incident.incident_id),
        data.known_metrics(state.incident.incident_id), tuned, v5)
    decision = llm.complete(messages, PlannerDecision)
    assert isinstance(decision, PlannerDecision)
    steps = decision.steps[:remaining]
    done = decision.done or not steps  # no steps proposed means nothing more to do
    # Tuned stopping rule: never finish without runbook guidance, because a diagnosis with no
    # recommended action cannot pass verification.
    has_runbook = any(e.kind == "runbook" for o in state.observations for e in o.evidence)
    if tuned and done and not has_runbook and not any(s.tool == "runbook_retrieve" for s in steps):
        steps, done = [_mitigation_step(state)], False
    return {
        "plan": steps,
        "planner_done": done,
        "planner_notes": [*state.planner_notes, decision.reasoning],
    }
