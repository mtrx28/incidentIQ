"""Planner node: decide the next tool calls, or decide that the evidence is enough."""

from incidentiq import data
from incidentiq.agents.prompts import planner_messages
from incidentiq.llm.base import LLMClient
from incidentiq.schemas import GraphState, PlannerDecision


def planner_node(state: GraphState, llm: LLMClient) -> dict:
    remaining = state.max_steps - state.step_count
    if remaining <= 0:
        return {"plan": [], "planner_done": True}
    messages = planner_messages(
        state, data.known_services(state.incident.incident_id),
        data.known_metrics(state.incident.incident_id))
    decision = llm.complete(messages, PlannerDecision)
    assert isinstance(decision, PlannerDecision)
    steps = decision.steps[:remaining]
    return {
        "plan": steps,
        # No steps proposed means nothing more to do, whatever the model said.
        "planner_done": decision.done or not steps,
        "planner_notes": [*state.planner_notes, decision.reasoning],
    }
