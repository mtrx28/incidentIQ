"""Reporter node: write the final Diagnosis from the collected evidence."""

from incidentiq.agents.prompts import reporter_messages
from incidentiq.llm.base import LLMClient
from incidentiq.schemas import Diagnosis, GraphState


def reporter_node(state: GraphState, llm: LLMClient) -> dict:
    diagnosis = llm.complete(reporter_messages(state), Diagnosis)
    assert isinstance(diagnosis, Diagnosis)
    # The incident ID is known; do not trust the model to copy it.
    diagnosis = diagnosis.model_copy(update={"incident_id": state.incident.incident_id})
    return {"diagnosis": diagnosis}
