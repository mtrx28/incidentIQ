import pytest
from pydantic import ValidationError

from incidentiq.config import load_config
from incidentiq.schemas import (
    ROOT_CAUSES,
    Claim,
    Diagnosis,
    Evidence,
    GraphState,
    Incident,
    Observation,
)


def _incident() -> Incident:
    return Incident(
        incident_id="INC-001",
        alert_text="checkout error rate above 5% since 14:02",
        service="checkout",
        start_time="2026-01-01T14:02:00Z",
        window_start="2026-01-01T13:00:00Z",
        window_end="2026-01-01T15:00:00Z",
    )


def _diagnosis(**overrides) -> dict:
    base = {
        "incident_id": "INC-001",
        "root_cause_category": "bad_deployment",
        "root_cause_summary": "Release 4.2 introduced a null-pointer regression.",
        "confidence": "high",
        "claims": [Claim(statement="Errors began at deploy time", evidence_ids=["L-0001"])],
        "recommended_actions": [Claim(statement="Roll back", evidence_ids=["R-1-4"])],
    }
    base.update(overrides)
    return base


def test_there_are_ten_root_causes():
    assert len(ROOT_CAUSES) == 10


def test_valid_diagnosis():
    d = Diagnosis(**_diagnosis())
    assert d.unverified is False and d.ruled_out == []


def test_unknown_category_rejected():
    with pytest.raises(ValidationError):
        Diagnosis(**_diagnosis(root_cause_category="gremlins"))


def test_claim_needs_evidence():
    with pytest.raises(ValidationError):
        Claim(statement="no proof", evidence_ids=[])


def test_diagnosis_needs_a_claim():
    with pytest.raises(ValidationError):
        Diagnosis(**_diagnosis(claims=[]))


def test_known_evidence_ids_collects_across_observations():
    state = GraphState(incident=_incident())
    state.observations.append(
        Observation(
            step=1,
            tool="log_search",
            args={"service": "checkout"},
            summary="two lines",
            evidence=[
                Evidence(evidence_id="L-0001", kind="log", excerpt="ERROR boom"),
                Evidence(evidence_id="L-0002", kind="log", excerpt="ERROR boom again"),
            ],
        )
    )
    assert state.known_evidence_ids() == {"L-0001", "L-0002"}


def test_config_rejects_bad_mode(monkeypatch):
    monkeypatch.setenv("INCIDENTIQ_LLM", "nonsense")
    with pytest.raises(ValueError):
        load_config()


def test_config_defaults_to_replay(monkeypatch):
    monkeypatch.delenv("INCIDENTIQ_LLM", raising=False)
    assert load_config().llm_mode == "replay"
