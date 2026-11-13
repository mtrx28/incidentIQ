"""log_search: keyword search over one incident's logs, ranked and capped."""

import math
import re
from collections import Counter
from datetime import timedelta
from functools import lru_cache

from incidentiq import data
from incidentiq.schemas import Evidence, LogLine, ToolResult
from incidentiq.tools import ToolError, parse_time_arg

MAX_RESULTS = 30
LEVELS = ("DEBUG", "INFO", "WARN", "ERROR")
_LEVEL_WEIGHT = {"ERROR": 2.0, "WARN": 1.0, "INFO": 0.2, "DEBUG": 0.0}
MODES = ("legacy", "rarity")
# Default window of the rarity mode when the caller gives no start and no end.
WINDOW_BEFORE, WINDOW_AFTER = timedelta(minutes=30), timedelta(minutes=5)
TOP_TEMPLATES = 5

# Replaced in this order: quoted values, IP addresses, hex strings, then any other digit run.
_TEMPLATE_RULES = [
    (re.compile(r"""(?<!\w)(?:"[^"]*"|'[^']*')"""), "<Q>"),
    (re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b"), "<IP>"),
    (re.compile(r"\b[0-9a-f]{6,}\b", re.IGNORECASE), "<HEX>"),
    (re.compile(r"\d+"), "<N>"),
]


def _terms(query: str | None) -> list[str]:
    return sorted(set(re.findall(r"[a-z0-9_.:=/-]+", (query or "").lower())))


def _matches(incident_id: str, service: str | None, lo, hi, terms: list[str],
             level: str | None) -> list[tuple[int, LogLine]]:
    """The lines that pass the filters, each with the number of distinct query terms it contains."""
    matches = []
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
        matches.append((hits, line))
    return matches


@lru_cache(maxsize=100_000)
def template_of(message: str) -> str:
    """The message with its variable parts (quoted values, IPs, hex strings, numbers) replaced
    by placeholders, so lines that differ only in those parts share one template."""
    for pattern, placeholder in _TEMPLATE_RULES:
        message = pattern.sub(placeholder, message)
    return message


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
    lo, hi = parse_time_arg(start, "start"), parse_time_arg(end, "end")
    terms = _terms(query)

    scored = [(hits + _LEVEL_WEIGHT[line.level] * 0.5, line)
              for hits, line in _matches(incident_id, service, lo, hi, terms, level)]

    # Best first; ties broken by time so the result is deterministic.
    scored.sort(key=lambda s: (-s[0], s[1].ts, s[1].line_id))
    top = sorted((line for _, line in scored[:limit]), key=lambda line: (line.ts, line.line_id))
    return top, len(scored)


def search_logs_rarity(
    incident_id: str, service: str | None, lo, hi, terms: list[str], level: str | None,
    limit: int,
) -> tuple[list[LogLine], list[LogLine], Counter]:
    """Returns (best `limit` lines in time order, all matching lines, template counts).

    score = distinct query terms matched + 1 / log2(2 + f), where f is the number of matching
    lines that share the line's template. A line that occurs once beats a line that occurs
    thousands of times, and a matched query term is worth more than any rarity. No level bonus.
    """
    matches = _matches(incident_id, service, lo, hi, terms, level)
    counts = Counter(template_of(line.message) for _, line in matches)
    scored = [(hits + 1 / math.log2(2 + counts[template_of(line.message)]), line)
              for hits, line in matches]
    scored.sort(key=lambda s: (-s[0], s[1].ts, s[1].line_id))
    top = sorted((line for _, line in scored[:limit]), key=lambda line: (line.ts, line.line_id))
    return top, [line for _, line in matches], counts


def _header(matches: list[LogLine], counts: Counter, window: str) -> str:
    levels = Counter(line.level for line in matches)
    by_level = ", ".join(f"{lv} {levels[lv]}" for lv in reversed(LEVELS) if levels[lv])
    # Most frequent first; equal counts in alphabetical order, so the text is deterministic.
    top = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:TOP_TEMPLATES]
    frequent = "\n".join(f"  {n} x {t}" for t, n in top)
    return (f"{window}Levels: {by_level or 'none'}. Distinct templates: {len(counts)}.\n"
            f"Most frequent templates:\n{frequent}\n")


def log_search(
    incident_id: str, service: str | None = None, start: str | None = None,
    end: str | None = None, query: str | None = None, level: str | None = None,
    limit: int = MAX_RESULTS, mode: str = "legacy", alert_time: str | None = None,
) -> ToolResult:
    """`mode` is chosen by the caller of the tool, never by the model. "rarity" ranks rare
    templates first, adds a count/template header, and, when neither start nor end is given,
    searches from 30 minutes before to 5 minutes after `alert_time`."""
    if mode not in MODES:
        raise ToolError(f"mode must be one of {MODES}")
    if mode == "rarity":
        return _log_search_rarity(incident_id, service, start, end, query, level, limit, alert_time)
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


def _log_search_rarity(
    incident_id: str, service: str | None, start: str | None, end: str | None,
    query: str | None, level: str | None, limit: int, alert_time: str | None,
) -> ToolResult:
    if service is not None and service not in data.known_services(incident_id):
        raise ToolError(f"unknown service {service!r}; choose from {data.known_services(incident_id)}")
    if level is not None and level.upper() not in LEVELS:
        raise ToolError(f"level must be one of {LEVELS}")
    limit = max(1, min(int(limit), MAX_RESULTS))
    lo, hi = parse_time_arg(start, "start"), parse_time_arg(end, "end")
    window = ""
    if not start and not end and alert_time:
        alert = data.parse_ts(alert_time)
        lo, hi = alert - WINDOW_BEFORE, alert + WINDOW_AFTER
        window = (f"No start or end given, so searched the default window "
                  f"{lo.strftime('%Y-%m-%dT%H:%M:%SZ')} to {hi.strftime('%Y-%m-%dT%H:%M:%SZ')}. ")
    lines, matches, counts = search_logs_rarity(
        incident_id, service, lo, hi, _terms(query), level, limit)
    evidence = [
        Evidence(evidence_id=ln.line_id, kind="log",
                 excerpt=f"{ln.ts} {ln.service} {ln.level} {ln.message}")
        for ln in lines
    ]
    note = f" (showing the {len(lines)} rarest-template matches)" if len(matches) > len(lines) else ""
    return ToolResult(
        tool="log_search",
        args={"service": service, "start": start, "end": end, "query": query, "level": level,
              "limit": limit},
        summary=f"{len(matches)} matching log lines{note}.\n" + _header(matches, counts, window),
        evidence=evidence)
