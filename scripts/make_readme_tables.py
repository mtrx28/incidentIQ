"""Generate the README's result tables from the committed result files.

    python scripts/make_readme_tables.py            # print the tables
    python scripts/make_readme_tables.py --write    # rewrite them in README.md between markers
    python scripts/make_readme_tables.py --check    # exit 1 if README.md differs from the files

Nothing here is typed by hand: every number comes from results/<run>/results.json,
results/redaction/results.json and results/retrieval/*.json. The blocks live in README.md and
docs/evaluation.md. tests/test_readme_tables.py fails if a file and this script's output disagree.
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
README = ROOT / "README.md"
EVAL_DOC = ROOT / "docs" / "evaluation.md"
RUNS = ["v0-baseline", "v1-tools", "v2-retrieval", "v3-verifier", "v4-final"]
# block name -> the file that holds it
REDACTION_DOC = ROOT / "docs" / "redaction.md"
BLOCK_FILES = {"results": README, "redaction": README, "retrieval": README, "paired": EVAL_DOC,
               "redaction-doc": REDACTION_DOC}
BLOCKS = tuple(BLOCK_FILES)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _pct(x: float) -> str:
    return f"{x:.1%}"


def results_table() -> str:
    head = ("| Version | Test accuracy (95% Wilson interval) | Strict accuracy | Citation validity "
            "| Support: lexical / gold | Gold evidence recall | Gold runbook cited "
            "| LLM calls / incident | Prompt / completion tokens / incident | Dev accuracy |")
    lines = [head, "|---|---|---|---|---|---|---|---|---|---|"]
    for run in RUNS:
        res = _load(RESULTS / run / "results.json")
        t, d = res["splits"]["test"], res["splits"]["dev"]
        a, e = t["accuracy"], t["efficiency"]
        lines.append(
            f"| [{run}](results/{run}/results.md) "
            f"| {_pct(a['rate'])} ({a['correct']}/{t['n']}; {_pct(a['ci95'][0])} to "
            f"{_pct(a['ci95'][1])}) "
            f"| {_pct(t['strict_accuracy']['rate'])} | {_pct(t['citation_validity'])} "
            f"| {_pct(t['citation_support_lexical'])} / {_pct(t['citation_support_gold'])} "
            f"| {_pct(t['gold_evidence_recall'])} | {_pct(t['gold_runbook_cited'])} "
            f"| {e['llm_calls_per_incident']:.2f} "
            f"| {e['prompt_tokens_per_incident']:.0f} / {e['completion_tokens_per_incident']:.0f} "
            f"| {_pct(d['accuracy']['rate'])} ({d['accuracy']['correct']}/{d['n']}) |")
    return "\n".join(lines)


def redaction_table() -> str:
    res = _load(RESULTS / "redaction" / "results.json")
    rec, hard, fp = res["recall"], res["hard_cases"], res["false_positives"]
    o, h = rec["overall"], hard["overall"]
    out = [f"Injected set: {o['caught']}/{o['total']} caught ({_pct(o['rate'])}). "
           f"Independent hand-written hard set: {h['caught']}/{h['total']} ({_pct(h['rate'])}). "
           f"Clean lines altered: {fp['clean_lines']['altered']}/{fp['clean_lines']['total']} "
           f"({_pct(fp['clean_lines']['rate'])}).", "",
           "| Type | Injected set (caught / total) | Hard set (caught / total) |", "|---|---|---|"]
    for kind in sorted(set(rec["by_type"]) | set(hard["by_type"])):
        cells = []
        for part in (rec["by_type"], hard["by_type"]):
            cell = part.get(kind)
            cells.append(f"{cell['caught']}/{cell['total']} ({_pct(cell['rate'])})" if cell else "-")
        out.append(f"| {kind} | {cells[0]} | {cells[1]} |")
    out += ["", "| Look-alike type (clean) | Tokens | Altered | Rate | Detector that fired |",
            "|---|---|---|---|---|"]
    for kind, v in sorted(fp["lookalikes"].items()):
        fired = ", ".join(f"{k} ({n})" for k, n in sorted(v["fired_detectors"].items())) or "-"
        out.append(f"| {kind} | {v['total']} | {v['touched']} | {_pct(v['rate'])} | {fired} |")
    return "\n".join(out)


def retrieval_table() -> str:
    backends = [("embedding (pgvector)", _load(RESULTS / "retrieval" / "all.json")),
                ("keyword (BM25)", _load(RESULTS / "retrieval" / "all-keyword.json"))]
    out = ["| Query | Search | section@1 | section@3 | runbook@1 | runbook@3 |",
           "|---|---|---|---|---|---|"]
    for mode in ("alert", "alert+evidence", "diagnosed-fix"):
        for name, res in backends:
            s = res["summary"]["all"][mode]
            out.append(f"| {mode} | {name} | {_pct(s['section@1'])} | {_pct(s['section@3'])} "
                       f"| {_pct(s['runbook@1'])} | {_pct(s['runbook@3'])} |")
    return "\n".join(out)


def _correct_on_test(run: str) -> dict[str, bool]:
    res = _load(RESULTS / run / "results.json")
    return {x["incident_id"]: x["correct"] for x in res["incidents"] if x["split"] == "test"}


def paired_table() -> str:
    """Counts only: how the same test incidents fared in two versions."""
    pairs = [("v1-tools", "v4-final"), ("v0-baseline", "v4-final")]
    out = ["| Comparison (test split) | wrong to right | right to wrong | both right | both wrong |",
           "|---|---|---|---|---|"]
    for old, new in pairs:
        a, b = _correct_on_test(old), _correct_on_test(new)
        ids = sorted(a)
        assert ids == sorted(b)
        w2r = sum(not a[i] and b[i] for i in ids)
        r2w = sum(a[i] and not b[i] for i in ids)
        both = sum(a[i] and b[i] for i in ids)
        neither = sum(not a[i] and not b[i] for i in ids)
        out.append(f"| {old} to {new} | {w2r} | {r2w} | {both} | {neither} |")
    return "\n".join(out)


GENERATORS = {"results": results_table, "redaction": redaction_table,
              "retrieval": retrieval_table, "paired": paired_table,
              "redaction-doc": redaction_table}


def block(name: str) -> str:
    return (f"<!-- BEGIN GENERATED:{name} (python scripts/make_readme_tables.py --write) -->\n"
            f"{GENERATORS[name]()}\n<!-- END GENERATED:{name} -->")


def _pattern(name: str) -> re.Pattern:
    return re.compile(rf"<!-- BEGIN GENERATED:{name} .*?-->\n.*?<!-- END GENERATED:{name} -->",
                      re.DOTALL)


def extract(readme_text: str, name: str) -> str | None:
    match = _pattern(name).search(readme_text)
    return match.group(0) if match else None


def rewrite(text: str, names: tuple[str, ...]) -> str:
    for name in names:
        if extract(text, name) is None:
            raise SystemExit(f"no generated block for {name!r}")
        text = _pattern(name).sub(lambda _m, n=name: block(n), text, count=1)
    return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--write", action="store_true", help="rewrite the blocks in README.md")
    parser.add_argument("--check", action="store_true", help="exit 1 if README.md is out of date")
    args = parser.parse_args(argv)
    if not (args.write or args.check):
        print("\n\n".join(block(n) for n in BLOCKS))
        return 0
    stale = False
    for path in sorted(set(BLOCK_FILES.values())):
        names = tuple(n for n, p in BLOCK_FILES.items() if p == path)
        current = path.read_text(encoding="utf-8")
        updated = rewrite(current, names)
        if args.check:
            if updated != current:
                print(f"{path.name}: tables are out of date; run with --write", file=sys.stderr)
                stale = True
        else:
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(updated)
            print(f"{path.name} updated")
    if args.check and not stale:
        print("tables are up to date")
    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(main())
