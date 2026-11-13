"""Loaders for the bundled dataset in data/. Everything is read-only and cached."""

import csv
import json
import os
import random
from datetime import datetime, timedelta
from functools import cache, lru_cache

from incidentiq.config import DATA_DIR
from incidentiq.schemas import GroundTruth, Incident, LogLine, Split
from incidentiq.synthetic import NOISE, SEED, UNIVERSAL, render

# series[(service, metric)] = (series_id, [(timestamp, value), ...])
Series = dict[tuple[str, str], tuple[str, list[tuple[str, float]]]]


def parse_ts(text: str) -> datetime:
    """Parse an ISO 8601 timestamp; a trailing Z means UTC."""
    return datetime.fromisoformat(text)


def list_incident_ids(split: Split | None = None) -> list[str]:
    if split is None:
        return sorted(p.stem for p in (DATA_DIR / "incidents").glob("*.json"))
    return json.loads((DATA_DIR / "split.json").read_text(encoding="utf-8"))[split]


@cache
def _incident_file(incident_id: str) -> dict:
    path = DATA_DIR / "incidents" / f"{incident_id}.json"
    if not path.exists():
        raise KeyError(f"unknown incident {incident_id!r}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_incident(incident_id: str) -> Incident:
    """The alert only. The agent must never be given the ground truth."""
    return Incident(**_incident_file(incident_id)["incident"])


def load_ground_truth(incident_id: str) -> GroundTruth:
    return GroundTruth(**_incident_file(incident_id)["ground_truth"])


@cache
def _original_logs(incident_id: str) -> tuple[LogLine, ...]:
    path = DATA_DIR / "logs" / f"{incident_id}.jsonl"
    with open(path, encoding="utf-8") as f:
        return tuple(LogLine(**json.loads(line)) for line in f)


# The `scale100` condition (docs/benchmark-scale100.md): extra healthy-traffic lines per service.
LOG_SCALES = (1, 100)
EXTRA_LINES_PER_SERVICE = 8500
EXTRA_FIRST_ID = 5000  # added lines are L-5000 upward; original IDs stop far below that
ISO = "%Y-%m-%dT%H:%M:%SZ"


def log_scale() -> int:
    """INCIDENTIQ_LOG_SCALE: 1 (the original data, default) or 100. Read on every call."""
    raw = os.environ.get("INCIDENTIQ_LOG_SCALE", "1")
    if raw not in {str(s) for s in LOG_SCALES}:
        raise ValueError(f"INCIDENTIQ_LOG_SCALE must be one of {LOG_SCALES}, got {raw!r}")
    return int(raw)


def load_logs(incident_id: str) -> tuple[LogLine, ...]:
    if log_scale() == 1:
        return _original_logs(incident_id)
    return _scaled_logs(incident_id)


@lru_cache(maxsize=2)  # about 51,000 lines per incident: keep a couple, never all 40
def _scaled_logs(incident_id: str) -> tuple[LogLine, ...]:
    """The original lines plus EXTRA_LINES_PER_SERVICE noise lines for every service.

    Added lines use only the generator's own NOISE and UNIVERSAL templates, spread uniformly over
    the incident window. Added lines are numbered from L-5000 in (timestamp, service) order. They are
    merged with the original lines by timestamp; on a tie the original lines come first, in their
    file order, then the added ones, so original lines keep their IDs and relative order exactly.
    """
    original = _original_logs(incident_id)
    incident = load_incident(incident_id)
    window_start = parse_ts(incident.window_start)
    seconds = int((parse_ts(incident.window_end) - window_start).total_seconds())
    rng = random.Random(f"{SEED}-{incident_id}-scale")

    added = []  # (ts, service, level, message)
    for service in NOISE:
        templates = NOISE[service] + UNIVERSAL
        for _ in range(EXTRA_LINES_PER_SERVICE):
            level, template = rng.choice(templates)
            ts = window_start + timedelta(seconds=rng.randint(0, seconds - 1))
            added.append((ts.strftime(ISO), service, level, render(template, {}, rng)[0]))
    added.sort(key=lambda x: (x[0], x[1]))
    new_lines = [LogLine(line_id=f"L-{EXTRA_FIRST_ID + n:04d}", ts=ts, service=service,
                         level=level, message=message)
                 for n, (ts, service, level, message) in enumerate(added)]
    return merge_logs(original, new_lines)


def merge_logs(original: tuple[LogLine, ...], added: list[LogLine]) -> tuple[LogLine, ...]:
    """Sort by (timestamp, is_added, service for added lines, position in its own list)."""
    keyed = [((ln.ts, False, "", n), ln) for n, ln in enumerate(original)]
    keyed += [((ln.ts, True, ln.service, n), ln) for n, ln in enumerate(added)]
    return tuple(ln for _, ln in sorted(keyed, key=lambda item: item[0]))


@cache
def load_metrics(incident_id: str) -> Series:
    series: Series = {}
    with open(DATA_DIR / "metrics" / f"{incident_id}.csv", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            key = (row["service"], row["metric"])
            if key not in series:
                series[key] = (row["series_id"], [])
            series[key][1].append((row["timestamp"], float(row["value"])))
    return series


def known_services(incident_id: str) -> list[str]:
    return sorted({service for service, _ in load_metrics(incident_id)})


def known_metrics(incident_id: str) -> list[str]:
    return sorted({metric for _, metric in load_metrics(incident_id)})
