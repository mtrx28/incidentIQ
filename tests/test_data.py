"""Checks on the synthetic dataset and its generator."""

import csv
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from datagen import pii, runbooks
from generate_data import generate

from incidentiq.schemas import ROOT_CAUSES, GroundTruth, Incident


def _digest(directory: Path) -> dict[str, str]:
    return {
        str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(directory.rglob("*")) if p.is_file()
    }


@pytest.fixture(scope="module")
def data(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("data")
    generate(out)
    return out


def _incidents(data: Path):
    for path in sorted((data / "incidents").glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        yield Incident(**raw["incident"]), GroundTruth(**raw["ground_truth"])


def _logs(data: Path, incident_id: str) -> list[dict]:
    text = (data / "logs" / f"{incident_id}.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines()]


def test_generator_is_deterministic(data, tmp_path):
    generate(tmp_path)
    assert _digest(tmp_path) == _digest(data)


def test_committed_data_is_up_to_date(data):
    """If this fails, rerun `python scripts/generate_data.py` and commit the result."""
    assert _digest(ROOT / "data") == _digest(data)


def test_forty_incidents_balanced_across_ten_categories(data):
    truths = [t for _, t in _incidents(data)]
    assert len(truths) == 40
    counts = Counter(t.root_cause_category for t in truths)
    assert set(counts) == set(ROOT_CAUSES) and set(counts.values()) == {4}


def test_split_is_15_dev_25_test_and_covers_every_hard_case(data):
    truths = [t for _, t in _incidents(data)]
    assert Counter(t.split for t in truths) == {"dev": 15, "test": 25}
    for split in ("dev", "test"):
        hard = {t.hard_case for t in truths if t.split == split and t.hard_case}
        assert hard == {"logs_only", "metrics_only", "overlapping", "runbook_needed"}
    split_file = json.loads((data / "split.json").read_text())
    assert [len(split_file["dev"]), len(split_file["test"])] == [15, 25]


def test_runbooks_have_expected_sections(data):
    files = sorted((data / "runbooks").glob("*.md"))
    assert 15 <= len(files) <= 20
    for f in files:
        headings = re.findall(r"^## \d+\. (.+)$", f.read_text(encoding="utf-8"), re.MULTILINE)
        assert headings == runbooks.SECTIONS


def test_every_runbook_section_is_long_enough_to_stand_alone_as_a_chunk(data):
    for f in sorted((data / "runbooks").glob("*.md")):
        text = f.read_text(encoding="utf-8")
        for number, body in re.findall(r"^## (\d+)\. .+\n\n(.+)$", text, re.MULTILINE):
            assert len(body.split()) >= 30, (f.name, number)


def test_lookalike_manifest_positions_match_log_text(data):
    rows = [json.loads(x) for x in
            (data / "lookalike_manifest.jsonl").read_text(encoding="utf-8").splitlines()]
    assert {"hex_id", "sha", "version", "order_ref"} <= {r["type"] for r in rows}
    order_refs = [r for r in rows if r["type"] == "order_ref"]
    assert len(order_refs) >= 100 and all(len(r["value"]) == 12 for r in order_refs)
    lines: dict[str, dict[str, str]] = {}
    for r in rows[::25]:  # a sample is enough; every item is built the same way
        by_id = lines.setdefault(
            r["incident_id"],
            {ln["line_id"]: ln["message"] for ln in _logs(data, r["incident_id"])})
        assert by_id[r["line_id"]][r["start"]:r["end"]] == r["value"]


def test_gold_evidence_ids_exist(data):
    runbook_sections = {
        f"R-{f.name[:2]}-{n}"
        for f in (data / "runbooks").glob("*.md") for n in range(1, 9)
    }
    for incident, truth in _incidents(data):
        log_ids = {ln["line_id"] for ln in _logs(data, incident.incident_id)}
        with open(data / "metrics" / f"{incident.incident_id}.csv", newline="") as f:
            metric_ids = {row["series_id"] for row in csv.DictReader(f)}
        known = log_ids | metric_ids | runbook_sections
        assert set(truth.gold_evidence_ids) <= known, incident.incident_id
        assert truth.gold_runbook_section in truth.gold_evidence_ids


def test_hard_cases_hide_the_right_evidence(data):
    for incident, truth in _incidents(data):
        kinds = {i[0] for i in truth.gold_evidence_ids}
        if truth.hard_case == "logs_only":
            assert "M" not in kinds
        if truth.hard_case == "metrics_only":
            assert "L" not in kinds
        if truth.hard_case is None:
            assert {"L", "M", "R"} <= kinds


def test_alert_text_does_not_leak_the_cause(data):
    banned = ["deploy", "pool", "index", "disk", "memory", "oom", "cache", "tls", "cert",
              "config", "rate limit", "traffic", "timeout", "query"]
    for incident, _ in _incidents(data):
        assert not any(w in incident.alert_text.lower() for w in banned), incident.alert_text


def test_every_incident_has_noise_and_distractors(data):
    for incident, truth in _incidents(data):
        assert len(_logs(data, incident.incident_id)) > 400
        assert truth.distractors


def test_pii_manifest_positions_match_log_text(data):
    manifest = json.loads((data / "pii_manifest.json").read_text(encoding="utf-8"))
    assert {m["type"] for m in manifest} == set(pii.PII_TYPES)
    by_incident: dict[str, dict[str, str]] = {}
    for m in manifest:
        lines = by_incident.setdefault(
            m["incident_id"],
            {ln["line_id"]: ln["message"] for ln in _logs(data, m["incident_id"])})
        assert lines[m["line_id"]][m["start"]:m["end"]] == m["value"]


def test_injected_cards_are_luhn_valid(data):
    manifest = json.loads((data / "pii_manifest.json").read_text(encoding="utf-8"))
    cards = [m["value"] for m in manifest if m["type"] == "card"]
    assert cards and all(pii.luhn_valid(c) for c in cards)


def test_metric_values_are_sane(data):
    path = data / "metrics" / "INC-001.csv"
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 54 * 36
    for row in rows:
        value = float(row["value"])
        assert value >= 0
        if row["metric"].endswith("_pct"):
            assert value <= 100
