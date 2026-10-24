"""Generate the synthetic IncidentIQ dataset: runbooks, 40 labeled incidents, metrics and logs.

Fixed seed, so running it twice produces byte-identical files.

    python scripts/generate_data.py            # writes into data/
    python scripts/generate_data.py --out DIR  # writes elsewhere (used by the tests)
"""

import argparse
import json
import math
import random
import re
import shutil
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

from datagen import pii, runbooks
from datagen.catalog import (
    CAUSES,
    DEPENDENCIES,
    DISTRACTORS,
    METRICS,
    ONSET_IDX,
    PCT_METRICS,
    POINTS,
    SEED,
    SERVICES,
    STEP_MIN,
    Anomaly,
    CauseSpec,
    baseline,
    series_id,
)
from datagen.noise import NOISE, SYMPTOM, UNIVERSAL

from incidentiq.schemas import GroundTruth, Incident

HARD_TYPES = ["logs_only", "metrics_only", "overlapping", "runbook_needed"]
CFG_VARIANTS = [
    ("PAYMENTS_API_URL", "http://payments-stg.internal:8080", "http://payments.internal:8080"),
    ("MAX_BATCH_SIZE", "0", "500"),
    ("FEATURE_NEW_PRICING", "true", "false"),
    ("REQUEST_TIMEOUT_MS", "-1", "3000"),
]
ISO = "%Y-%m-%dT%H:%M:%SZ"
TOKEN = re.compile(r"\{(int|hex|pii|lk):([^}]+)\}")


# --- Planning ----------------------------------------------------------------------------


def plan_incidents() -> list[dict]:
    """4 incidents per category. Slot 3 is a hard case. Dev = 15, test = 25 (see README)."""
    items = []
    for ci, spec in enumerate(CAUSES):
        for slot in range(4):
            hard = HARD_TYPES[ci % 4] if slot == 3 else None
            dev = slot == 0 or (slot == 3 and ci < 5)
            items.append({"spec": spec, "ci": ci, "slot": slot, "hard": hard,
                          "split": "dev" if dev else "test"})
    random.Random(SEED).shuffle(items)  # so incident IDs do not reveal the category
    for n, item in enumerate(items, start=1):
        item["id"] = f"INC-{n:03d}"
    return items


# --- Template rendering ------------------------------------------------------------------


def _located(text: str, drawn: list[tuple[str, str]]) -> list[dict]:
    items = []
    for kind, value in drawn:
        start = text.find(value)
        assert start >= 0, (text, value)
        items.append({"type": kind, "value": value, "start": start, "end": start + len(value)})
    return items


def render(template: str, ctx: dict, rng: random.Random) -> tuple[str, list[dict], list[dict]]:
    """Fill a template.

    Returns the message, the PII items injected into it, and the look-alike strings in it:
    harmless tokens (hex IDs, SHAs, versions, 12-digit order refs) that a redactor could mistake
    for PII. Release versions that come from the incident context are not tagged.
    """
    pii_drawn: list[tuple[str, str]] = []
    lookalikes: list[tuple[str, str]] = []

    def sub(match: re.Match) -> str:
        kind, arg = match.groups()
        if kind == "int":
            lo, hi = arg.split(":")
            return str(rng.randint(int(lo), int(hi)))
        if kind == "hex":
            value = "".join(rng.choice("0123456789abcdef") for _ in range(int(arg)))
            lookalikes.append(("sha" if arg == "7" else "hex_id", value))
            return value
        if kind == "lk":
            if arg == "version":
                value = f"{rng.randint(1, 9)}.{rng.randint(0, 9)}.{rng.randint(0, 9)}"
            elif arg == "order_ref":
                value = str(rng.randint(202603000000, 202609999999))  # 12 digits, starts with 2
            else:
                raise ValueError(arg)
            lookalikes.append((arg, value))
            return value
        value = pii.generate(arg, rng)
        pii_drawn.append((arg, value))
        return value

    text = TOKEN.sub(sub, template).format_map(ctx)
    return text, _located(text, pii_drawn), _located(text, lookalikes)


# --- Metrics -----------------------------------------------------------------------------


def apply_anomaly(series: dict, service: str, a: Anomaly, rng: random.Random, scale: float = 1.0):
    values = series[(service, a.metric)]
    mean, _ = baseline(service, a.metric)
    target = mean * float(a.target[1:]) if isinstance(a.target, str) else a.target
    delta = (target - mean) * scale * rng.uniform(0.9, 1.1)
    start = ONSET_IDX - a.lead
    for i in range(POINTS):
        if a.shape == "step":
            f = 1.0 if i >= ONSET_IDX else 0.0
        elif a.shape == "ramp":
            f = min(1.0, (i - start + 1) / (a.lead + a.span + 1)) if i >= start else 0.0
        elif a.shape == "spike":
            f = math.exp(-(i - ONSET_IDX) / 2.5) if i >= ONSET_IDX else 0.0
        elif a.shape == "saw":
            f = ((i - start) % a.period + 1) / a.period if i >= start else 0.0
        else:
            raise ValueError(a.shape)
        values[i] += delta * f


def healthy_series(rng: random.Random) -> dict:
    return {
        (s, m): [baseline(s, m)[0] + rng.gauss(0, baseline(s, m)[1]) for _ in range(POINTS)]
        for s in SERVICES for m in METRICS
    }


def finalise(series: dict) -> None:
    for (_, metric), values in series.items():
        for i, v in enumerate(values):
            v = max(0.0, v)
            if metric in PCT_METRICS:
                v = min(100.0, v)
            values[i] = float(round(v)) if metric == "restarts" else round(v, 2)


def resolve(role: str, svc: str, dep: str, other: str | None) -> str:
    return {"svc": svc, "dep": dep, "other": other}[role]


# --- One incident ------------------------------------------------------------------------


def build_incident(item: dict) -> dict:
    spec: CauseSpec = item["spec"]
    hard: str | None = item["hard"]
    inc_id = item["id"]
    rng = random.Random(f"{SEED}-{inc_id}")

    svc = rng.choice(spec.services)
    dep = rng.choice(DEPENDENCIES[svc] or [s for s in SERVICES if s != svc])
    window_start = datetime(2026, 3, 1, tzinfo=UTC) + timedelta(
        days=rng.randint(0, 200), hours=rng.randint(0, 20))
    onset = window_start + timedelta(minutes=ONSET_IDX * STEP_MIN)
    window_end = window_start + timedelta(minutes=POINTS * STEP_MIN)
    detected = onset + timedelta(minutes=rng.randint(2, 4))

    cfg_key, bad_val, good_val = rng.choice(CFG_VARIANTS)
    major, minor, patch = rng.randint(2, 6), rng.randint(0, 19), rng.randint(1, 9)
    ctx = {
        "svc": svc, "dep": dep, "ver": f"{major}.{minor}.{patch}",
        "prev_ver": f"{major}.{minor}.{patch - 1}", "pool_max": rng.choice([20, 30, 50]),
        "db": f"{svc}-db-1", "dbname": svc, "ep": rng.choice(["orders", "cart", "stock", "pay"]),
        "client": rng.choice(["mobile-app", "partner-api", "web-frontend"]),
        "shard": rng.randint(1, 4), "sku": rng.randint(1000, 9999),
        "expiry": (onset - timedelta(minutes=1)).strftime(ISO),
        "now": (onset + timedelta(seconds=5)).strftime(ISO),
        "mig": onset.strftime("%Y%m%d"), "cfg_key": cfg_key, "bad_val": bad_val, "good_val": good_val,
    }

    # Pick the extra signals that make the case harder.
    secondary = None
    if hard == "overlapping":
        secondary = rng.choice([c for c in CAUSES if c.category != spec.category])
    excluded = {spec.category} | ({secondary.category} if secondary else set())
    pool = [d for d in DISTRACTORS if d.looks_like not in excluded]
    distractors = rng.sample(pool, rng.randint(1, 3))
    bystanders = {d.name: rng.choice([s for s in SERVICES if s != svc]) for d in distractors}

    # Metrics.
    series = healthy_series(rng)
    gold_metric_ids: list[str] = []
    for a in spec.symptom_metrics:
        apply_anomaly(series, resolve(a.role, svc, dep, None), a, rng)
    if hard != "logs_only":
        for a in spec.cause_metrics:
            service = resolve(a.role, svc, dep, None)
            apply_anomaly(series, service, a, rng)
            gold_metric_ids.append(series_id(service, a.metric))
    if secondary:
        for a in secondary.cause_metrics:
            apply_anomaly(series, resolve(a.role, svc, dep, None), a, rng, scale=0.45)
    for d in distractors:
        if d.metric:
            apply_anomaly(series, bystanders[d.name], d.metric, rng)
    finalise(series)

    # Logs.
    lines: list[dict] = []

    def add(ts: datetime, service: str, level: str, template: str, gold: bool = False) -> None:
        message, items, lookalikes = render(template, ctx, rng)
        lines.append({"ts": ts, "service": service, "level": level, "message": message,
                      "pii": items, "lookalikes": lookalikes, "gold": gold})

    def random_time(lo: datetime, hi: datetime) -> datetime:
        return lo + timedelta(seconds=rng.randint(0, int((hi - lo).total_seconds()) - 1))

    for s in SERVICES:
        templates = NOISE[s] + UNIVERSAL
        for _ in range(rng.randint(70, 90)):
            level, template = rng.choice(templates)
            add(random_time(window_start, window_end), s, level, template)
    for _ in range(rng.randint(20, 40)):
        level, template = rng.choice(SYMPTOM)
        add(random_time(onset, onset + timedelta(minutes=25)), svc, level, template)

    if hard != "metrics_only":
        cause_lines = spec.ambiguous_logs if hard == "runbook_needed" else spec.telltale_logs
        for ln in cause_lines:
            ts = onset + timedelta(seconds=ln.offset_s + rng.randint(-3, 3))
            add(ts, resolve(ln.role, svc, dep, None), ln.level, ln.message, gold=True)
    if secondary:
        for ln in rng.sample(secondary.telltale_logs, 2):
            ts = onset + timedelta(seconds=ln.offset_s + rng.randint(-3, 3))
            add(ts, resolve(ln.role, svc, dep, None), "WARN", ln.message)
    for d in distractors:
        for level, message in d.logs:
            add(onset + timedelta(seconds=rng.randint(-1200, 1200)), bystanders[d.name],
                level, message)
    for kind in pii.PII_TYPES:
        for _ in range(rng.randint(1, 2)):
            service, level, template = rng.choice(pii.PII_LINES[kind])
            add(random_time(window_start, window_end), service, level, template)

    lines.sort(key=lambda ln: ln["ts"])  # stable: ties keep insertion order
    pii_items, lookalike_items, gold_log_ids = [], [], []
    for n, ln in enumerate(lines, start=1):
        ln["line_id"] = f"L-{n:04d}"
        if ln["gold"]:
            gold_log_ids.append(ln["line_id"])
        where = {"incident_id": inc_id, "line_id": ln["line_id"]}
        pii_items += [{**where, **injected} for injected in ln["pii"]]
        lookalike_items += [{**where, **tok} for tok in ln["lookalikes"]]

    # Labels.
    runbook_ids = [f"R-{spec.runbook:02d}-{runbooks.MITIGATION}"]
    if hard == "runbook_needed":
        runbook_ids.append(f"R-{spec.runbook:02d}-{runbooks.CONFIRM}")
    alert_kind = rng.choice(spec.alert_kinds)
    since = detected.strftime("%H:%M")
    if alert_kind == "latency":
        alert = f"{svc}-service: p99 latency above 1000ms for 5 minutes (since {since} UTC)"
    else:
        alert = f"{svc}-service: HTTP error rate above 5% for 5 minutes (since {since} UTC)"

    incident = Incident(
        incident_id=inc_id, alert_text=alert, service=svc, start_time=detected.strftime(ISO),
        window_start=window_start.strftime(ISO), window_end=window_end.strftime(ISO))
    truth = GroundTruth(
        incident_id=inc_id, split=item["split"], root_cause_category=spec.category,
        root_cause_statement=spec.statement.format_map(ctx),
        gold_evidence_ids=sorted(set(gold_log_ids + gold_metric_ids + runbook_ids)),
        gold_runbook_section=runbook_ids[0], hard_case=hard,
        distractors=sorted([d.name for d in distractors]
                           + ([f"overlap:{secondary.category}"] if secondary else [])))

    return {"incident": incident, "truth": truth, "series": series, "window_start": window_start,
            "lines": lines, "pii_items": pii_items, "lookalike_items": lookalike_items}


# --- Output ------------------------------------------------------------------------------


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def write_json(path: Path, obj) -> None:
    write_text(path, json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


def generate(out: Path) -> dict:
    for sub in ("incidents", "metrics", "logs", "runbooks"):
        shutil.rmtree(out / sub, ignore_errors=True)

    for number, title, bodies in runbooks.RUNBOOKS:
        write_text(out / "runbooks" / f"{number:02d}-{runbooks.slug(title)}.md",
                   runbooks.render(number, title, bodies))

    items = plan_incidents()
    split: dict[str, list[str]] = {"dev": [], "test": []}
    all_pii: list[dict] = []
    all_lookalikes: list[dict] = []
    for item in sorted(items, key=lambda i: i["id"]):
        built = build_incident(item)
        inc_id = item["id"]
        split[item["split"]].append(inc_id)
        all_pii += built["pii_items"]
        all_lookalikes += built["lookalike_items"]

        write_json(out / "incidents" / f"{inc_id}.json", {
            "incident": built["incident"].model_dump(), "ground_truth": built["truth"].model_dump()})

        rows = ["timestamp,series_id,service,metric,value"]
        for (service, metric) in sorted(built["series"], key=lambda k: series_id(*k)):
            for i, v in enumerate(built["series"][(service, metric)]):
                ts = (built["window_start"] + timedelta(minutes=i * STEP_MIN)).strftime(ISO)
                rows.append(f"{ts},{series_id(service, metric)},{service},{metric},{v}")
        write_text(out / "metrics" / f"{inc_id}.csv", "\n".join(rows) + "\n")

        log_rows = [json.dumps({"line_id": ln["line_id"], "ts": ln["ts"].strftime(ISO),
                                "service": ln["service"], "level": ln["level"],
                                "message": ln["message"]}, sort_keys=True, ensure_ascii=False)
                    for ln in built["lines"]]
        write_text(out / "logs" / f"{inc_id}.jsonl", "\n".join(log_rows) + "\n")

    write_json(out / "split.json", {k: sorted(v) for k, v in split.items()})
    write_json(out / "pii_manifest.json", all_pii)
    # One JSON object per line: there are tens of thousands of these.
    write_text(out / "lookalike_manifest.jsonl", "".join(
        json.dumps(x, sort_keys=True) + "\n" for x in all_lookalikes))
    return {"incidents": len(items), "dev": len(split["dev"]), "test": len(split["test"]),
            "pii_items": len(all_pii), "lookalikes": len(all_lookalikes)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=HERE.parent / "data")
    args = parser.parse_args()
    print(generate(args.out))


if __name__ == "__main__":
    main()
