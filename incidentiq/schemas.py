"""Pydantic models shared by the data generator, tools, agents and eval harness."""

from typing import Literal

from pydantic import BaseModel, Field

# Fixed list of root-cause categories. Diagnosis.root_cause_category must be one of these.
RootCause = Literal[
    "bad_deployment",
    "db_connection_pool_exhaustion",
    "slow_query_missing_index",
    "downstream_timeout",
    "memory_leak_oom",
    "disk_full",
    "expired_tls_cert",
    "misconfiguration",
    "traffic_spike_rate_limit",
    "cache_stampede_outage",
]
ROOT_CAUSES: tuple[str, ...] = RootCause.__args__  # type: ignore[attr-defined]

EvidenceKind = Literal["log", "metric", "runbook"]
Tool = Literal["metrics_query", "log_search", "runbook_retrieve"]
Split = Literal["dev", "test"]


# --- Incident data (inputs and ground truth) ---------------------------------------------


class Incident(BaseModel):
    """What the agent is given: the alert, never the ground truth."""

    incident_id: str
    alert_text: str
    service: str
    start_time: str  # ISO 8601
    window_start: str
    window_end: str


class GroundTruth(BaseModel):
    """Labels used only by the eval harness."""

    incident_id: str
    split: Split
    root_cause_category: RootCause
    root_cause_statement: str
    gold_evidence_ids: list[str] = Field(min_length=1)
    gold_runbook_section: str  # evidence ID such as "R-12-3"
    hard_case: str | None = None  # "logs_only", "metrics_only", "overlapping", "runbook_needed"
    distractors: list[str] = Field(default_factory=list)  # red herrings injected, for failure analysis


# --- Raw data and tool results ------------------------------------------------------------


class LogLine(BaseModel):
    line_id: str  # "L-0421"
    ts: str  # ISO 8601, UTC
    service: str
    level: str
    message: str


# --- Agent output -------------------------------------------------------------------------


class Evidence(BaseModel):
    evidence_id: str  # "L-0421", "M-017", "R-12-3"
    kind: EvidenceKind
    excerpt: str  # short, already redacted


class ToolResult(BaseModel):
    """What a tool returns, before redaction. `evidence` holds the citable items."""

    tool: Tool
    args: dict[str, str | int | float | None]
    summary: str
    evidence: list[Evidence]


class Claim(BaseModel):
    statement: str
    evidence_ids: list[str] = Field(min_length=1)


class Diagnosis(BaseModel):
    incident_id: str
    root_cause_category: RootCause
    root_cause_summary: str
    confidence: Literal["low", "medium", "high"]
    claims: list[Claim] = Field(min_length=1)
    recommended_actions: list[Claim]  # each action cites a runbook section
    ruled_out: list[str] = Field(default_factory=list)
    unverified: bool = False  # set if the verifier gave up


# --- LangGraph state ----------------------------------------------------------------------


class PlanStep(BaseModel):
    tool: Tool
    args: dict[str, str | int | float | None] = Field(default_factory=dict)
    reason: str


class Observation(BaseModel):
    """One redacted tool result. `evidence` holds the citable items it produced."""

    step: int
    tool: Tool
    args: dict[str, str | int | float | None]
    summary: str
    evidence: list[Evidence]


class Hypothesis(BaseModel):
    root_cause_category: RootCause
    rationale: str
    supporting_evidence_ids: list[str] = Field(default_factory=list)


class GraphState(BaseModel):
    incident: Incident
    plan: list[PlanStep] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    step_count: int = 0
    max_steps: int = 8
    planner_done: bool = False
    diagnosis: Diagnosis | None = None
    validation_errors: list[str] = Field(default_factory=list)
    retries: int = 0

    def known_evidence_ids(self) -> set[str]:
        """Every evidence ID collected in this run. The verifier checks citations against it."""
        return {e.evidence_id for o in self.observations for e in o.evidence}
