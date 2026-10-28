"""Act and observe nodes: run the planned tools, then update what we believe.

Everything a tool returns is redacted here, before it is stored in the state or shown to a model.
The redactor is the LLM client's own, so placeholder numbering is shared with its prompt guard.
"""

import json

from incidentiq.agents.prompts import observer_messages
from incidentiq.agents.toolbox import ToolBox
from incidentiq.llm.base import LLMClient
from incidentiq.redaction import redact_tool_result
from incidentiq.schemas import GraphState, Hypothesis, Observation, ObserveUpdate, PlanStep
from incidentiq.tools import ToolError


def _signature(step: PlanStep) -> str:
    return json.dumps([step.tool, {k: v for k, v in step.args.items() if v not in (None, "")}],
                      sort_keys=True)


def act_node(state: GraphState, toolbox: ToolBox, llm: LLMClient) -> dict:
    observations = list(state.observations)
    seen = {_signature(PlanStep(tool=o.tool, args=o.args, reason="")) for o in observations}
    step_count = state.step_count
    round_no = len(state.planner_notes)

    for step in state.plan[: state.max_steps - step_count]:
        step_count += 1
        reason, _ = llm.redactor.redact(step.reason)
        args = {k: llm.redactor.redact(v)[0] if isinstance(v, str) else v
                for k, v in step.args.items()}
        if _signature(step) in seen:
            observations.append(Observation(
                step=step_count, round=round_no, tool=step.tool, args=args, reason=reason,
                error=True, evidence=[],
                summary="Duplicate call: this exact tool call was already made; see its earlier "
                        "result. Ask for something new."))
            continue
        seen.add(_signature(step))
        try:
            result, _ = redact_tool_result(toolbox.run(step), llm.redactor)
            observations.append(Observation(
                step=step_count, round=round_no, tool=step.tool, args=args, reason=reason,
                summary=result.summary, evidence=result.evidence))
        except ToolError as exc:
            observations.append(Observation(
                step=step_count, round=round_no, tool=step.tool, args=args, reason=reason,
                error=True, evidence=[], summary=f"Tool error: {exc}"))
    return {"observations": observations, "step_count": step_count, "plan": []}


def observe_node(state: GraphState, llm: LLMClient) -> dict:
    # The prompt points the model at the results added since the last observe round.
    update = llm.complete(observer_messages(state, state.observed_through + 1), ObserveUpdate)
    assert isinstance(update, ObserveUpdate)
    known = state.known_evidence_ids()
    hypotheses = [
        Hypothesis(root_cause_category=h.root_cause_category, rationale=h.rationale,
                   # Citations to evidence we never collected are dropped, not trusted.
                   supporting_evidence_ids=[i for i in h.supporting_evidence_ids if i in known])
        for h in update.hypotheses
    ]
    return {"hypotheses": hypotheses, "observer_notes": [*state.observer_notes, update.summary],
            "observed_through": state.step_count}
