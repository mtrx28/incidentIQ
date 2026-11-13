"""Turn scored runs into results.json, results.md and traces.jsonl.

Output is deterministic: sorted keys, rounded numbers, no timestamps and no wall-clock timings
(latency is the latency recorded when each reply was first obtained). That is what lets replay mode
reproduce committed results byte for byte.
"""

import json
from pathlib import Path

from incidentiq import data
from incidentiq.config import RESULTS_DIR, load_config
from incidentiq.eval.metrics import auto_signals, breakdown, score_incident, summarise
from incidentiq.eval.runner import IncidentRun
from incidentiq.eval.variants import Variant

SPLIT_ORDER = ("test", "dev", "all")


def _redaction_block(rows: list[dict]) -> dict:
    """Static redaction scores (from results/redaction) plus this run's prompt-leak check."""
    block: dict = {"prompt_leaks_in_this_run": sum(len(r["leaks"]) for r in rows),
                   "leaked_types": sorted({t for r in rows for t in r["leaks"]})}
    path = RESULTS_DIR / "redaction" / "results.json"
    if path.exists():
        saved = json.loads(path.read_text(encoding="utf-8"))
        fp = saved["false_positives"]
        block["injected_pii_recall"] = saved["recall"]["overall"]
        block["hard_set_recall"] = saved["hard_cases"]["overall"]
        block["clean_lines_altered"] = fp["clean_lines"]
        block["lookalike_touched_rate"] = {k: v["rate"] for k, v in fp["lookalikes"].items()}
    return block


def build_results(variant: Variant, runs: list[IncidentRun]) -> dict:
    cfg = load_config()
    rows = [score_incident(r, data.load_ground_truth(r.incident_id), variant.verifier)
            for r in runs]
    splits = {name: [r for r in rows if name == "all" or r["split"] == name]
              for name in SPLIT_ORDER}
    results = {
        "run": variant.name, "description": variant.description, "model": cfg.llm_model,
        "embedder": cfg.embedding_model if variant.retrieval == "embedding" else "none (BM25)",
        "max_steps": cfg.max_steps,
        "splits": {
            name: {**summarise(subset), "by_category": breakdown(subset, "category"),
                   "by_hard_case": breakdown(subset, "hard_case")}
            for name, subset in splits.items() if subset},
        "redaction": _redaction_block(rows),
        "incidents": rows,
    }
    if data.log_scale() != 1:  # original results keep exactly their old shape
        results["condition"] = "scale100"
    return results


# --- markdown -----------------------------------------------------------------------------


def _pct(x: float) -> str:
    return f"{x:.1%}"


def _metric_rows(s: dict) -> list[tuple[str, str]]:
    a, e = s["accuracy"], s["efficiency"]
    return [
        ("Incidents", str(s["n"])),
        ("Accuracy", f"{_pct(a['rate'])} ({a['correct']}/{s['n']}; 95% CI "
                     f"{_pct(a['ci95'][0])} to {_pct(a['ci95'][1])})"),
        ("Strict accuracy (category + cites gold cause evidence)",
         f"{_pct(s['strict_accuracy']['rate'])} ({s['strict_accuracy']['correct']}/{s['n']})"),
        ("Citation validity (cited IDs that exist)", _pct(s["citation_validity"])),
        ("Citation support, lexical check", _pct(s["citation_support_lexical"])),
        ("Citation support, gold check", _pct(s["citation_support_gold"])),
        ("Gold evidence recall", _pct(s["gold_evidence_recall"])),
        ("Gold runbook section cited", _pct(s["gold_runbook_cited"])),
        ("Cause evidence retrieved at all", _pct(s["cause_evidence_retrieved"])),
        ("Tool calls per incident", f"{e['steps_per_incident']:.2f}"),
        ("LLM calls per incident", f"{e['llm_calls_per_incident']:.2f}"),
        ("Reporter retries per incident", f"{e['reporter_retries_per_incident']:.2f}"),
        ("Prompt / completion tokens per incident",
         f"{e['prompt_tokens_per_incident']:.0f} / {e['completion_tokens_per_incident']:.0f}"),
        ("LLM latency per incident (recorded)", f"{e['recorded_llm_latency_s_per_incident']:.1f} s"),
        ("Unverified diagnoses / failed runs / tool errors",
         f"{s['unverified']} / {s['failed_runs']} / {s['tool_errors']}"),
    ]


def to_markdown(results: dict, notes: dict[str, str]) -> str:
    splits = [n for n in SPLIT_ORDER if n in results["splits"]]
    condition = f" --condition {results['condition']}" if "condition" in results else ""
    md = [f"# {results['run']}", "", results["description"], "",
          f"Model `{results['model']}`; embedder `{results['embedder']}`; step cap "
          f"{results['max_steps']}. Reproduce with `python -m incidentiq.eval --run "
          f"{results['run']} --llm replay{condition}`.", "",
          "The **test** split (25 incidents) is the held-out set used for reported numbers; "
          "**dev** (15) was used while tuning. With these sample sizes the confidence intervals "
          "are wide.", ""]
    table = {n: dict(_metric_rows(results["splits"][n])) for n in splits}
    md += ["| Metric | " + " | ".join(splits) + " |", "|---|" + "---|" * len(splits)]
    for label, _ in _metric_rows(results["splits"][splits[0]]):
        md.append(f"| {label} | " + " | ".join(table[n][label] for n in splits) + " |")

    for name in splits[:1]:
        s = results["splits"][name]
        md += ["", f"## Accuracy by category ({name})", "", "| Category | Correct | n |", "|---|---|---|"]
        md += [f"| {k} | {v['correct']} | {v['n']} |" for k, v in s["by_category"].items()]
        md += ["", f"## Accuracy by case type ({name})", "", "| Case | Correct | n |", "|---|---|---|"]
        md += [f"| {k} | {v['correct']} | {v['n']} |" for k, v in s["by_hard_case"].items()]

    r = results["redaction"]
    md += ["", "## Redaction", "",
           f"Prompt-leak check for this run: **{r['prompt_leaks_in_this_run']}** injected PII "
           f"values found in prompts sent to the model"
           + (f" (types: {', '.join(r['leaked_types'])})" if r["leaked_types"] else "") + "."]
    if "injected_pii_recall" in r:
        i, h, c = r["injected_pii_recall"], r["hard_set_recall"], r["clean_lines_altered"]
        md += [f"Redactor on the injected set: {i['caught']}/{i['total']} caught ({_pct(i['rate'])}); "
               f"on the independent hard set: {h['caught']}/{h['total']} ({_pct(h['rate'])}); "
               f"clean lines altered: {c['altered']}/{c['total']} ({_pct(c['rate'])}). "
               "Details: `results/redaction/results.md`."]

    failures = [x for x in results["incidents"] if not x["correct"]]
    md += ["", f"## Failures ({len(failures)} of {len(results['incidents'])} incidents)", "",
           "`Signals` are mechanical hints; `Reason` is written by hand from the trace "
           "(`failure_notes.json`).", "",
           "| Incident | Split | Case | True | Predicted | Steps | Signals | Reason |",
           "|---|---|---|---|---|---|---|---|"]
    for x in failures:
        md.append(f"| {x['incident_id']} | {x['split']} | {x['hard_case']} | {x['category']} | "
                  f"{x['predicted']} | {x['steps']} | {'; '.join(auto_signals(x)) or '-'} | "
                  f"{notes.get(x['incident_id'], '(not yet analysed)')} |")
    return "\n".join(md) + "\n"


def comparison_markdown(all_results: list[dict]) -> str:
    md = ["# Benchmark versions", "",
          "Held-out **test** split unless noted. Same model and data for every row; only the "
          "system changes. Accuracy intervals are 95% Wilson intervals.", "",
          "| Version | Test accuracy | Strict | Cite validity | Support (lexical / gold) | "
          "Gold recall | Gold runbook cited | LLM calls | Dev accuracy |",
          "|---|---|---|---|---|---|---|---|---|"]
    for res in all_results:
        t = res["splits"].get("test")
        d = res["splits"].get("dev")
        if t is None:
            continue
        a = t["accuracy"]
        md.append(
            f"| {res['run']} | {_pct(a['rate'])} ({a['correct']}/{t['n']}, "
            f"{_pct(a['ci95'][0])}-{_pct(a['ci95'][1])}) | {_pct(t['strict_accuracy']['rate'])} | "
            f"{_pct(t['citation_validity'])} | {_pct(t['citation_support_lexical'])} / "
            f"{_pct(t['citation_support_gold'])} | {_pct(t['gold_evidence_recall'])} | "
            f"{_pct(t['gold_runbook_cited'])} | {t['efficiency']['llm_calls_per_incident']:.1f} | "
            f"{_pct(d['accuracy']['rate']) if d else '-'} |")
    return "\n".join(md) + "\n"


# --- files --------------------------------------------------------------------------------


def _dump(obj) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def render_files(variant: Variant, runs: list[IncidentRun], notes: dict[str, str]
                 ) -> tuple[dict, dict[str, str]]:
    """Returns (results dict, {filename: text}) without touching the disk."""
    results = build_results(variant, runs)
    traces = []
    for run, row in zip(runs, results["incidents"], strict=True):
        truth = data.load_ground_truth(run.incident_id)
        traces.append(json.dumps({
            "incident_id": run.incident_id, "scores": row,
            "ground_truth": truth.model_dump(), "error": run.error,
            "state": run.state.model_dump(mode="json") if run.state else None,
        }, sort_keys=True, ensure_ascii=False))
    return results, {"results.json": _dump(results), "results.md": to_markdown(results, notes),
                     "traces.jsonl": "\n".join(traces) + "\n"}


def load_notes(out_dir: Path) -> dict[str, str]:
    path = out_dir / "failure_notes.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def write_files(out_dir: Path, files: dict[str, str]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        with open(out_dir / name, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
