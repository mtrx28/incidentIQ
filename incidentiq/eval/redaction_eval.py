"""Score the redactor against the injected PII/secrets and the look-alike strings.

Recall: an injected value counts as caught only if the full original string no longer appears in
the redacted line (a partly redacted phone number is a miss).

False positives, three views:
  * clean lines altered: lines with no injected PII that the redactor changed at all.
  * look-alike tokens touched: harmless hex IDs, SHAs, versions and 12-digit order refs that a
    finding overlaps, per type, and which detector fired on them.
  * spurious findings: findings that overlap no injected item, by detector, with examples.

    python -m incidentiq.eval.redaction_eval [--out results/redaction] [--update-known-misses]
"""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from incidentiq import data
from incidentiq.config import DATA_DIR, RESULTS_DIR, ROOT
from incidentiq.eval.redaction_hard_cases import hard_cases
from incidentiq.redaction import Redactor

KNOWN_MISSES = ROOT / "tests" / "redaction_known_misses.json"


def _overlaps(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start < b_end and b_start < a_end


def _load_manifests() -> tuple[dict, dict]:
    pii: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for item in json.loads((DATA_DIR / "pii_manifest.json").read_text(encoding="utf-8")):
        pii[(item["incident_id"], item["line_id"])].append(item)
    lookalikes: dict[tuple[str, str], list[dict]] = defaultdict(list)
    path = DATA_DIR / "lookalike_manifest.jsonl"
    for line in path.read_text(encoding="utf-8").splitlines():
        item = json.loads(line)
        lookalikes[(item["incident_id"], item["line_id"])].append(item)
    return pii, lookalikes


def evaluate(verhoeff: bool = True) -> dict:
    pii, lookalikes = _load_manifests()
    recall = defaultdict(lambda: [0, 0])  # type -> [caught, total]
    misses: list[dict] = []
    clean_lines = clean_altered = 0
    la_total: Counter = Counter()
    la_touched: Counter = Counter()
    confusion: dict[str, Counter] = defaultdict(Counter)
    spurious: Counter = Counter()
    spurious_examples: dict[str, list[str]] = defaultdict(list)
    gold_altered: list[dict] = []
    gold_total = 0

    for incident_id in data.list_incident_ids():
        gold = {i for i in data.load_ground_truth(incident_id).gold_evidence_ids
                if i.startswith("L-")}
        redactor = Redactor(verhoeff=verhoeff)  # one per incident, like a real run
        for line in data.load_logs(incident_id):
            clean, findings = redactor.redact(line.message)
            injected = pii.get((incident_id, line.line_id), [])

            for item in injected:
                caught = item["value"] not in clean
                recall[item["type"]][1] += 1
                recall[item["type"]][0] += caught
                if not caught:
                    misses.append({"incident_id": incident_id, "line_id": line.line_id,
                                   "type": item["type"], "start": item["start"],
                                   "value": item["value"], "redacted_line": clean})
            if not injected:
                clean_lines += 1
                clean_altered += bool(findings)

            for token in lookalikes.get((incident_id, line.line_id), []):
                la_total[token["type"]] += 1
                hit = [f for f in findings
                       if _overlaps(f.start, f.end, token["start"], token["end"])]
                if hit:
                    la_touched[token["type"]] += 1
                    for f in hit:
                        confusion[token["type"]][f.detector] += 1

            for f in findings:
                if not any(_overlaps(f.start, f.end, i["start"], i["end"]) for i in injected):
                    spurious[f.detector] += 1
                    if len(spurious_examples[f.detector]) < 5:
                        spurious_examples[f.detector].append(line.message[f.start:f.end])

            if line.line_id in gold:
                gold_total += 1
                if findings:
                    gold_altered.append({"incident_id": incident_id, "line_id": line.line_id,
                                         "redacted_line": clean})

    caught = sum(c for c, _ in recall.values())
    total = sum(t for _, t in recall.values())
    return {
        "config": {"aadhaar_verhoeff": verhoeff},
        "recall": {
            "overall": {"caught": caught, "total": total, "rate": round(caught / total, 4)},
            "by_type": {k: {"caught": c, "total": t, "rate": round(c / t, 4)}
                        for k, (c, t) in sorted(recall.items())},
        },
        "false_positives": {
            "clean_lines": {"total": clean_lines, "altered": clean_altered,
                            "rate": round(clean_altered / clean_lines, 4)},
            "lookalikes": {
                k: {"total": la_total[k], "touched": la_touched[k],
                    "rate": round(la_touched[k] / la_total[k], 4),
                    "fired_detectors": dict(confusion[k])}
                for k in sorted(la_total)},
            "spurious_findings_by_detector": dict(spurious),
            "spurious_examples": dict(spurious_examples),
        },
        "gold_log_lines": {"total": gold_total, "altered": len(gold_altered),
                           "examples": gold_altered[:5]},
        "misses": misses,
    }


def evaluate_hard_cases() -> dict:
    """Recall on hand-written lines in formats the injected data does not use."""
    by_type = defaultdict(lambda: [0, 0])
    misses = []
    for case in hard_cases():
        clean, _ = Redactor().redact(case["line"])
        caught = case["value"] not in clean
        by_type[case["type"]][1] += 1
        by_type[case["type"]][0] += caught
        if not caught:
            misses.append({"type": case["type"], "value": case["value"], "redacted_line": clean})
    caught = sum(c for c, _ in by_type.values())
    total = sum(t for _, t in by_type.values())
    return {"overall": {"caught": caught, "total": total, "rate": round(caught / total, 4)},
            "by_type": {k: {"caught": c, "total": t, "rate": round(c / t, 4)}
                        for k, (c, t) in sorted(by_type.items())},
            "misses": misses}


def to_markdown(main: dict, no_checksum: dict) -> str:
    r, fp = main["recall"], main["false_positives"]
    lines = [
        "# Redaction evaluation", "",
        f"Recall: **{r['overall']['caught']} of {r['overall']['total']} injected items caught "
        f"({r['overall']['rate']:.1%})**. A value counts as caught only if the full original "
        "string is gone from the redacted line.", "",
        "| Type | Caught | Total | Recall |", "|---|---|---|---|",
    ]
    for k, v in r["by_type"].items():
        lines.append(f"| {k} | {v['caught']} | {v['total']} | {v['rate']:.1%} |")
    c = fp["clean_lines"]
    lines += ["", "## False positives", "",
              f"Clean lines altered: **{c['altered']} of {c['total']} ({c['rate']:.1%})**.", "",
              "| Look-alike | Tokens | Touched | Rate | Detector that fired |",
              "|---|---|---|---|---|"]
    for k, v in fp["lookalikes"].items():
        fired = ", ".join(f"{d} ({n})" for d, n in v["fired_detectors"].items()) or "-"
        lines.append(f"| {k} | {v['total']} | {v['touched']} | {v['rate']:.1%} | {fired} |")
    lines += ["", "Spurious findings by detector (findings that overlap no injected item): "
              + (", ".join(f"{d}: {n}" for d, n in fp["spurious_findings_by_detector"].items())
                 or "none"), ""]
    g = main["gold_log_lines"]
    lines += [f"Gold evidence log lines altered by redaction: {g['altered']} of {g['total']}.", "",
              "## Ablation: Aadhaar without the Verhoeff checksum", "",
              f"Without the checksum, Aadhaar recall is "
              f"{no_checksum['recall']['by_type']['aadhaar']['rate']:.1%} and "
              f"{no_checksum['false_positives']['lookalikes']['order_ref']['rate']:.1%} of "
              "12-digit order refs are touched "
              f"(with the checksum: {main['recall']['by_type']['aadhaar']['rate']:.1%} and "
              f"{fp['lookalikes']['order_ref']['rate']:.1%}).", "",
              f"## Misses ({len(main['misses'])})", ""]
    for m in main["misses"]:
        lines.append(f"- {m['incident_id']} {m['line_id']} [{m['type']}] `{m['value']}` -> "
                     f"`{m['redacted_line']}`")
    hard = main["hard_cases"]
    lines += ["", "## Hard cases (hand-written, formats the injected data does not use)", "",
              f"**{hard['overall']['caught']} of {hard['overall']['total']} caught "
              f"({hard['overall']['rate']:.1%})**. The injected-set score above is optimistic "
              "because the detectors were written against the same generator; this is the "
              "more realistic number.", "",
              "| Type | Caught | Total | Recall |", "|---|---|---|---|"]
    for k, v in hard["by_type"].items():
        lines.append(f"| {k} | {v['caught']} | {v['total']} | {v['rate']:.1%} |")
    lines += ["", f"### Hard-case misses ({len(hard['misses'])})", ""]
    for m in hard["misses"]:
        lines.append(f"- [{m['type']}] `{m['value']}` -> `{m['redacted_line']}`")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=RESULTS_DIR / "redaction")
    parser.add_argument("--update-known-misses", action="store_true",
                        help="rewrite tests/redaction_known_misses.json from the current misses")
    args = parser.parse_args()

    result = evaluate(verhoeff=True)
    result["hard_cases"] = evaluate_hard_cases()
    ablation = evaluate(verhoeff=False)
    result["ablation_no_aadhaar_checksum"] = {
        k: ablation[k] for k in ("config", "recall", "false_positives")}
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "results.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    markdown = to_markdown(result, ablation)
    (args.out / "results.md").write_text(markdown, encoding="utf-8", newline="\n")
    if args.update_known_misses:
        keys = sorted([m["incident_id"], m["line_id"], m["start"]] for m in result["misses"])
        KNOWN_MISSES.write_text(json.dumps(keys, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(markdown)


if __name__ == "__main__":
    main()
