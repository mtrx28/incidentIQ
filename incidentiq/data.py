"""Loaders for the bundled dataset in data/. Everything is read-only and cached."""

import csv
import json
from datetime import datetime
from functools import cache

from incidentiq.config import DATA_DIR
from incidentiq.schemas import GroundTruth, Incident, LogLine, Split

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
def load_logs(incident_id: str) -> tuple[LogLine, ...]:
    path = DATA_DIR / "logs" / f"{incident_id}.jsonl"
    with open(path, encoding="utf-8") as f:
        return tuple(LogLine(**json.loads(line)) for line in f)


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
