"""log_search: keyword search over one incident's logs, ranked and capped."""

import re

from incidentiq import data
from incidentiq.schemas import Evidence, LogLine, ToolResult
from incidentiq.tools import ToolError

MAX_RESULTS = 30
LEVELS = ("DEBUG", "INFO", "WARN", "ERROR")
_LEVEL_WEIGHT = {"ERROR": 2.0, "WARN": 1.0, "INFO": 0.2, "DEBUG": 0.0}


def _terms(query: str | None) -> list[str]:
    return sorted(set(re.findall(r"[a-z0-9_.:=/-]+", (query or "").lower())))


def search_logs(
    incident_id: str, service: str | None = None, start: str | None = None,
    end: str | None = None, query: str | None = None, level: str | None = None,
    limit: int = MAX_RESULTS,
) -> tuple[list[LogLine], int]:
    """Returns (lines, total_matches). Lines are the best `limit` matches in time order.

    A line matches if it passes the service/time/level filters and, when a query is given,
    contains at least one query term. Relevance is the number of distinct terms matched plus a
    small bonus for ERROR and WARN lines, so a precise query beats a bare level filter.
    """
    if service is not None and service not in data.known_services(incident_id):
        raise ToolError(f"unknown service {service!r}; choose from {data.known_services(incident_id)}")
    if level is not None and level.upper() not in LEVELS:
        raise ToolError(f"level must be one of {LEVELS}")
    limit = max(1, min(int(limit), MAX_RESULTS))
    lo = data.parse_ts(start) if start else None
    hi = data.parse_ts(end) if end else None
    terms = _terms(query)

    scored: list[tuple[float, LogLine]] = []
    for line in data.load_logs(incident_id):
        if service and line.service != service:
            continue
        if level and line.level != level.upper():
            continue
        if lo or hi:
            ts = data.parse_ts(line.ts)
            if (lo and ts < lo) or (hi and ts > hi):
                continue
        text = line.message.lower()
        hits = sum(1 for t in terms if t in text)
        if terms and hits == 0:
            continue
        scored.append((hits + _LEVEL_WEIGHT[line.level] * 0.5, line))

    # Best first; ties broken by time so the result is deterministic.
    scored.sort(key=lambda s: (-s[0], s[1].ts, s[1].line_id))
    top = sorted((line for _, line in scored[:limit]), key=lambda line: (line.ts, line.line_id))
    return top, len(scored)


def log_search(
    incident_id: str, service: str | None = None, start: str | None = None,
    end: str | None = None, query: str | None = None, level: str | None = None,
    limit: int = MAX_RESULTS,
) -> ToolResult:
    lines, total = search_logs(incident_id, service, start, end, query, level, limit)
    evidence = [
        Evidence(evidence_id=ln.line_id, kind="log",
                 excerpt=f"{ln.ts} {ln.service} {ln.level} {ln.message}")
        for ln in lines
    ]
    note = f" (showing the {len(lines)} most relevant)" if total > len(lines) else ""
    return ToolResult(
        tool="log_search",
        args={"service": service, "start": start, "end": end, "query": query, "level": level,
              "limit": limit},
        summary=f"{total} matching log lines{note}.",
        evidence=evidence)
