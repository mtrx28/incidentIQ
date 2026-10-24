"""Retrieval-only evaluation: how often does runbook search surface the gold runbook section?

No LLM is involved, so this shows how much of the end-to-end accuracy retrieval can account for.
Two query modes bracket what an agent might ask:

  alert           the alert text alone. Alerts are generic, so this is a lower bound.
  alert+evidence  the alert plus the gold log lines (or, when the incident has no gold logs,
                  a description of the gold metrics). This approximates an agent that has already
                  found the telltale evidence, so it is closer to an upper bound.
  diagnosed-fix   "how to mitigate and fix <true category>": the follow-up question once an agent
                  has a diagnosis. It uses the true label, so it is an upper bound that isolates
                  how well Mitigation sections can be found.

A "section hit" needs a gold runbook section in the top k. A "runbook hit" only needs any section
of the gold runbook, which is the weaker test.

    python -m incidentiq.eval.retrieval_eval --split test --out results/retrieval
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

from incidentiq import data
from incidentiq.config import RESULTS_DIR
from incidentiq.store import db
from incidentiq.store.embed import get_embedder
from incidentiq.tools.runbooks import search_runbooks

MODES = ("alert", "alert+evidence", "diagnosed-fix")
KS = (1, 3)


def build_query(incident_id: str, mode: str) -> str:
    incident = data.load_incident(incident_id)
    if mode == "alert":
        return incident.alert_text
    truth = data.load_ground_truth(incident_id)
    if mode == "diagnosed-fix":
        # Uses the TRUE category, so this is an upper bound for the step where an agent that has
        # reached a diagnosis asks the runbooks how to fix it.
        return f"how to mitigate and fix {truth.root_cause_category.replace('_', ' ')}"
    parts = [incident.alert_text]
    log_ids = {i for i in truth.gold_evidence_ids if i.startswith("L-")}
    if log_ids:
        parts += [ln.message for ln in data.load_logs(incident_id) if ln.line_id in log_ids]
    else:
        names = {sid: (svc, metric) for (svc, metric), (sid, _) in
                 data.load_metrics(incident_id).items()}
        for sid in (i for i in truth.gold_evidence_ids if i.startswith("M-")):
            svc, metric = names[sid]
            parts.append(f"{svc} {metric.replace('_', ' ')} abnormal")
    return ". ".join(parts)


def evaluate(split: str | None, conn, embedder) -> dict:
    per_incident = []
    for incident_id in data.list_incident_ids(None if split == "all" else split):
        truth = data.load_ground_truth(incident_id)
        gold_sections = {i for i in truth.gold_evidence_ids if i.startswith("R-")}
        gold_runbooks = {s[:4] for s in gold_sections}  # "R-02"
        row = {"incident_id": incident_id, "category": truth.root_cause_category,
               "hard_case": truth.hard_case, "gold_sections": sorted(gold_sections)}
        for mode in MODES:
            hits = search_runbooks(conn, embedder, build_query(incident_id, mode), max(KS))
            ids = [h.section_id for h in hits]
            row[mode] = {
                "top": ids,
                **{f"section@{k}": bool(gold_sections & set(ids[:k])) for k in KS},
                **{f"runbook@{k}": bool(gold_runbooks & {i[:4] for i in ids[:k]}) for k in KS},
            }
        per_incident.append(row)

    def rate(rows: list[dict], mode: str, key: str) -> float:
        return round(sum(r[mode][key] for r in rows) / len(rows), 3) if rows else 0.0

    groups: dict[str, list[dict]] = {"all": per_incident}
    by_hard = defaultdict(list)
    for r in per_incident:
        by_hard[r["hard_case"] or "standard"].append(r)
    groups.update(by_hard)
    summary = {
        name: {"n": len(rows), **{mode: {f"{kind}@{k}": rate(rows, mode, f"{kind}@{k}")
                                         for kind in ("section", "runbook") for k in KS}
                                  for mode in MODES}}
        for name, rows in groups.items()
    }
    return {"split": split, "embedder": embedder.name, "summary": summary,
            "incidents": per_incident}


def to_markdown(result: dict) -> str:
    lines = [f"# Retrieval-only evaluation ({result['split']} split)", "",
             f"Embedder: `{result['embedder']}`. Section hit = a gold runbook section is in the "
             "top k; runbook hit = any section of the gold runbook is.", "",
             "| Group | n | Query | section@1 | section@3 | runbook@1 | runbook@3 |",
             "|---|---|---|---|---|---|---|"]
    for name, s in result["summary"].items():
        for mode in MODES:
            m = s[mode]
            lines.append(f"| {name} | {s['n']} | {mode} | {m['section@1']:.0%} | "
                         f"{m['section@3']:.0%} | {m['runbook@1']:.0%} | {m['runbook@3']:.0%} |")
    misses = [r for r in result["incidents"] if not r["alert+evidence"]["section@3"]]
    lines += ["", f"## Misses with alert+evidence queries (section@3): {len(misses)}", ""]
    for r in misses:
        lines.append(f"- {r['incident_id']} ({r['category']}, {r['hard_case'] or 'standard'}): "
                     f"gold {r['gold_sections']}, got {r['alert+evidence']['top']}")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=["dev", "test", "all"], default="all")
    parser.add_argument("--out", type=Path, default=RESULTS_DIR / "retrieval")
    args = parser.parse_args()
    with db.connect() as conn:
        result = evaluate(args.split, conn, get_embedder())
    args.out.mkdir(parents=True, exist_ok=True)
    stem = f"{args.split}"
    (args.out / f"{stem}.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    (args.out / f"{stem}.md").write_text(to_markdown(result), encoding="utf-8", newline="\n")
    print(to_markdown(result))


if __name__ == "__main__":
    main()
