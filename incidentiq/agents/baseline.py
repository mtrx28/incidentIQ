"""v0 baseline: one LLM call with the alert and a dump of recent logs. No tools, no loop.

The dump is the last DUMP_LINES log lines (all services) up to the alert time, which is roughly
what a first, simple implementation would paste into a prompt. The number was fixed before any
results were seen and is not tuned. Everything is redacted before it reaches the model, like in the
agent, and the diagnosis is validated against the same schema.

v0b (`filtered=True`) is the fairer baseline for high-volume logs: the last DUMP_LINES WARN and
ERROR lines of the alerting service only, up to the alert time. Nothing else changes.
"""

import time

from incidentiq import data
from incidentiq.agents.graph import AgentResult
from incidentiq.agents.prompts import CATEGORY_LIST
from incidentiq.llm.base import LLMClient, Message
from incidentiq.schemas import Diagnosis, Evidence, GraphState, LogLine, Observation

DUMP_LINES = 100


def log_dump(incident_id: str, filtered: bool = False) -> list[LogLine]:
    incident = data.load_incident(incident_id)
    alert_time = data.parse_ts(incident.start_time)
    before = [ln for ln in data.load_logs(incident_id) if data.parse_ts(ln.ts) <= alert_time]
    if filtered:
        before = [ln for ln in before
                  if ln.service == incident.service and ln.level in ("WARN", "ERROR")]
    return before[-DUMP_LINES:]


def _what(filtered: bool) -> str:
    return "WARN and ERROR log lines of the alerting service" if filtered else "log lines"


def baseline_messages(state: GraphState, lines: list[Evidence], filtered: bool = False
                      ) -> list[Message]:
    i = state.incident
    system = f"""ROLE: baseline
You are an assistant that helps on-call engineers find the root cause of an incident. You are \
given the alert and a dump of the most recent log lines. You have no other tools.

Root-cause categories (root_cause_category must be exactly one of these):
{CATEGORY_LIST}

Rules:
- claims: factual statements about what the logs show. Each cites one or more log line IDs from \
the dump (like L-0123) that actually support it. Never invent an ID.
- recommended_actions must be an empty list: no runbooks are available.
- confidence: low, medium or high.

Reply with only JSON in this shape:
{{"incident_id": "{i.incident_id}", "root_cause_category": "disk_full", \
"root_cause_summary": "one or two sentences", "confidence": "high", \
"claims": [{{"statement": "...", "evidence_ids": ["L-0123"]}}], "recommended_actions": [], \
"ruled_out": ["..."]}}"""
    dump = "\n".join(f"[{e.evidence_id}] {e.excerpt}" for e in lines)
    user = (f"Alert: {i.alert_text}\nAlerting service: {i.service}\nAlert time: {i.start_time}\n\n"
            f"The last {len(lines)} {_what(filtered)} before the alert, oldest first:\n{dump}")
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def diagnose_baseline(incident_id: str, llm: LLMClient, filtered: bool = False) -> AgentResult:
    llm.start_incident()
    started = time.monotonic()
    state = GraphState(incident=data.load_incident(incident_id), step_count=0)
    evidence = [
        Evidence(evidence_id=ln.line_id, kind="log",
                 excerpt=llm.redactor.redact(f"{ln.ts} {ln.service} {ln.level} {ln.message}")[0])
        for ln in log_dump(incident_id, filtered)
    ]
    # The dump is recorded as one observation so citation checks work the same way as for agents.
    state.observations.append(Observation(
        step=0, round=0, tool="log_search", args={"end": state.incident.start_time},
        summary=f"Dump of the last {len(evidence)} {_what(filtered)} before the alert.",
        evidence=evidence))
    diagnosis = llm.complete(baseline_messages(state, evidence, filtered), Diagnosis)
    assert isinstance(diagnosis, Diagnosis)
    state.diagnosis = diagnosis.model_copy(update={"incident_id": incident_id})
    return AgentResult(state, llm.stats, time.monotonic() - started)
