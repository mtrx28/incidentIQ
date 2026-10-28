"""The LangGraph control loop: plan -> act -> observe, then report.

    planner --(more steps)--> act --> observe --> planner ...
    planner --(done, or step cap reached)--> reporter --> END

With the verifier on, the diagnosis is checked after the reporter. On failure the problems go
back to the reporter (at most MAX_RETRIES times); after that the diagnosis is kept but marked
unverified:

    reporter --> verifier --(ok, or retries used up)--> END
                          --(problems found)---------> reporter
"""

import time
from dataclasses import dataclass

from langgraph.graph import END, StateGraph

from incidentiq import data
from incidentiq.agents.investigator import act_node, observe_node
from incidentiq.agents.planner import planner_node
from incidentiq.agents.reporter import reporter_node
from incidentiq.agents.toolbox import ToolBox
from incidentiq.agents.verifier import MAX_RETRIES, collect_evidence, verify
from incidentiq.config import load_config
from incidentiq.llm.base import LLMClient, LLMStats
from incidentiq.schemas import GraphState


@dataclass
class AgentResult:
    state: GraphState
    stats: LLMStats
    elapsed_s: float


def verifier_node(state: GraphState, llm: LLMClient, use_llm: bool) -> dict:
    assert state.diagnosis is not None
    result = verify(state.diagnosis, collect_evidence(state), llm if use_llm else None)
    if result.ok:
        return {"verification": result, "validation_errors": []}
    if state.retries < MAX_RETRIES:
        return {"verification": result, "validation_errors": result.errors,
                "retries": state.retries + 1}
    # Out of retries: keep the last attempt, but say plainly that it did not pass.
    return {"verification": result, "validation_errors": result.errors,
            "diagnosis": state.diagnosis.model_copy(update={"unverified": True})}


def build_graph(llm: LLMClient, toolbox: ToolBox, verify_output: bool = True,
                llm_entailment: bool = False):
    def route_after_planner(state: GraphState) -> str:
        if state.planner_done or state.step_count >= state.max_steps:
            return "reporter"
        return "act"

    def route_after_verifier(state: GraphState) -> str:
        done = state.diagnosis is not None and state.diagnosis.unverified
        return "end" if done or not state.validation_errors else "reporter"

    graph = StateGraph(GraphState)
    graph.add_node("planner", lambda s: planner_node(s, llm))
    graph.add_node("act", lambda s: act_node(s, toolbox, llm))
    graph.add_node("observe", lambda s: observe_node(s, llm))
    graph.add_node("reporter", lambda s: reporter_node(s, llm))
    graph.set_entry_point("planner")
    graph.add_conditional_edges("planner", route_after_planner,
                                {"act": "act", "reporter": "reporter"})
    graph.add_edge("act", "observe")
    graph.add_edge("observe", "planner")
    if verify_output:
        graph.add_node("verifier", lambda s: verifier_node(s, llm, llm_entailment))
        graph.add_edge("reporter", "verifier")
        graph.add_conditional_edges("verifier", route_after_verifier,
                                    {"end": END, "reporter": "reporter"})
    else:
        graph.add_edge("reporter", END)
    return graph.compile()


def run_incident(incident_id: str, llm: LLMClient, toolbox: ToolBox | None = None,
                 max_steps: int | None = None, verify_output: bool = True,
                 llm_entailment: bool = False) -> AgentResult:
    llm.start_incident()  # fresh placeholder numbering, shared by tool output and prompts
    own_toolbox = toolbox is None
    toolbox = toolbox or ToolBox(incident_id)
    max_steps = max_steps or load_config().max_steps
    state = GraphState(incident=data.load_incident(incident_id), max_steps=max_steps)
    started = time.monotonic()
    try:
        final = build_graph(llm, toolbox, verify_output, llm_entailment).invoke(
            state, config={"recursion_limit": 6 * max_steps + 10})
    finally:
        if own_toolbox:
            toolbox.close()
    final = final if isinstance(final, GraphState) else GraphState.model_validate(final)
    return AgentResult(final, llm.stats, time.monotonic() - started)
