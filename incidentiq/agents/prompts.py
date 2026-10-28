"""Prompt text for the planner, observer and reporter.

Prompts must be deterministic (no timestamps, no set ordering), because replay mode finds
recorded answers by hashing them. Each system prompt starts with a `ROLE:` line.
"""

import json

from incidentiq.llm.base import Message
from incidentiq.schemas import GraphState, Observation

CATEGORIES = {
    "bad_deployment": "a new release introduced a defect (errors begin right after a deploy)",
    "db_connection_pool_exhaustion": "every database connection in the pool is in use, so requests wait",
    "slow_query_missing_index": "a database query became slow (for example a missing index)",
    "downstream_timeout": "a dependency the service calls is slow or unresponsive",
    "memory_leak_oom": "memory grows until the process is killed (OOM) and restarts",
    "disk_full": "a volume is full so writes fail",
    "expired_tls_cert": "a TLS certificate expired so handshakes fail",
    "misconfiguration": "a wrong environment variable, setting or feature flag",
    "traffic_spike_rate_limit": "request volume far above capacity, causing rate limiting or load shedding",
    "cache_stampede_outage": "the cache is down or emptied so everything falls through to the database",
}
_CATEGORY_LIST = "\n".join(f"- {name}: {text}" for name, text in CATEGORIES.items())

_TOOLS = """Tools (all read-only):
- metrics_query: summarise one metric of one service. args: service, metric, optional start and end \
(ISO 8601 UTC), optional aggregation (mean, max, min or last). Reports min, max, mean, and whether \
the metric changed abruptly and when. Evidence IDs look like M-021.
- log_search: search log lines. args: optional service, start, end, query (keywords; a line matches \
if it contains any of them), level (ERROR, WARN or INFO), limit (at most 30). Evidence IDs look \
like L-0123.
- runbook_retrieve: search runbook sections by meaning. args: query (a descriptive sentence), \
optional k (at most 8). Evidence IDs look like R-02-5."""

MAX_EXCERPT = 700


def _fmt_args(args: dict) -> str:
    return json.dumps({k: v for k, v in args.items() if v is not None}, sort_keys=True)


def format_observations(observations: list[Observation]) -> str:
    if not observations:
        return "None yet."
    blocks = []
    for o in observations:
        head = f"Step {o.step}: {o.tool} {_fmt_args(o.args)}"
        if o.reason:
            head += f" (asked because: {o.reason})"
        lines = [f"{head}\n  Result: {o.summary}"]
        for e in o.evidence:
            excerpt = e.excerpt if len(e.excerpt) <= MAX_EXCERPT else e.excerpt[:MAX_EXCERPT] + "..."
            lines.append(f"  [{e.evidence_id}] {excerpt}")
        blocks.append("\n".join(lines))
    return "\n".join(blocks)


def _hypotheses(state: GraphState) -> str:
    if not state.hypotheses:
        return "None yet."
    return "\n".join(
        f"- {h.root_cause_category}: {h.rationale} (evidence: "
        f"{', '.join(h.supporting_evidence_ids) or 'none'})" for h in state.hypotheses)


def _incident_block(state: GraphState) -> str:
    i = state.incident
    return (f"Alert: {i.alert_text}\nAlerting service: {i.service}\nAlert time: {i.start_time}\n"
            f"Data available from {i.window_start} to {i.window_end}")


def planner_messages(state: GraphState, services: list[str], metrics: list[str]) -> list[Message]:
    remaining = state.max_steps - state.step_count
    system = f"""ROLE: planner
You are the planner of an assistant that helps on-call engineers find the root cause of an \
incident. You investigate by calling read-only tools and decide when you have enough evidence. \
You never change anything.

{_TOOLS}

Timestamps (start, end) must be complete ISO 8601 UTC strings such as {state.incident.start_time}; \
a bare time like "02:30:00Z" is rejected.

Services: {', '.join(services)}
Metrics: {', '.join(metrics)}

Root-cause categories:
{_CATEGORY_LIST}

Guidance:
- Start around the alert time. Check the alerting service's logs and metrics, then follow the \
evidence, including to its dependencies.
- Logs contain unrelated noise and red herrings. Prefer a cause supported by several independent \
signals, ideally both logs and metrics, over a single suspicious line.
- Before finishing, call runbook_retrieve for your leading hypothesis (describe the cause and ask \
how to mitigate it), so the diagnosis can recommend steps taken from runbooks.
- Ask for at most 3 steps per round. You have {remaining} tool calls left in total.

Reply with only JSON in this shape:
{{"reasoning": "what you think so far and why these steps", "done": false, \
"steps": [{{"tool": "log_search", "args": {{"service": "checkout", "query": "error"}}, \
"reason": "why"}}]}}
Set "done" to true, with an empty "steps" list, only when you have enough evidence and have \
retrieved runbook guidance."""
    user = f"""{_incident_block(state)}

Tool calls used so far: {state.step_count} of {state.max_steps}

Evidence gathered so far:
{format_observations(state.observations)}

Current hypotheses:
{_hypotheses(state)}

Decide the next steps."""
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def observer_messages(state: GraphState, first_new_step: int) -> list[Message]:
    system = f"""ROLE: observer
You review the results of an incident investigation. Write a short summary of what the latest \
results show, then update the list of hypotheses (at most 4, most likely first).

Root-cause categories:
{_CATEGORY_LIST}

Each hypothesis has root_cause_category (one of the categories), rationale, and \
supporting_evidence_ids (only IDs that appear in the evidence below).

Reply with only JSON in this shape:
{{"summary": "...", "hypotheses": [{{"root_cause_category": "disk_full", "rationale": "...", \
"supporting_evidence_ids": ["L-0123"]}}]}}"""
    user = f"""{_incident_block(state)}

Evidence so far (the latest results are steps {first_new_step} onwards):
{format_observations(state.observations)}

Previous hypotheses:
{_hypotheses(state)}"""
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def reporter_messages(state: GraphState) -> list[Message]:
    system = f"""ROLE: reporter
You write the final diagnosis of an incident from the evidence gathered. Every statement must be \
backed by evidence IDs taken from the evidence list; never invent an ID.

Root-cause categories (root_cause_category must be exactly one of these):
{_CATEGORY_LIST}

Rules:
- claims: factual statements about what the evidence shows. Each cites one or more evidence IDs \
(log lines L-..., metrics M-..., runbook sections R-...) that actually support it.
- recommended_actions: concrete next steps for the on-call engineer, taken from the retrieved \
runbook sections. Each cites at least one runbook section ID (R-...).
- ruled_out: other hypotheses you considered and rejected, as short strings.
- confidence: low, medium or high.

Reply with only JSON in this shape:
{{"incident_id": "{state.incident.incident_id}", "root_cause_category": "disk_full", \
"root_cause_summary": "one or two sentences", "confidence": "high", \
"claims": [{{"statement": "...", "evidence_ids": ["L-0123", "M-021"]}}], \
"recommended_actions": [{{"statement": "...", "evidence_ids": ["R-06-5"]}}], \
"ruled_out": ["..."]}}"""
    user = f"""{_incident_block(state)}

Evidence:
{format_observations(state.observations)}

Hypotheses from the investigation:
{_hypotheses(state)}"""
    if state.validation_errors:
        problems = "\n".join(f"- {e}" for e in state.validation_errors)
        user += (f"\n\nYour previous diagnosis was rejected for these problems. Fix them and "
                 f"reply with the corrected JSON:\n{problems}")
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]
