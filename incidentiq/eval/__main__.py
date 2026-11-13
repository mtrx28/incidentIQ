"""Evaluation CLI.

    python -m incidentiq.eval --run v4-final --split test --llm replay
    python -m incidentiq.eval --run all --split all --llm replay --check   # what `make eval` does
    python -m incidentiq.eval --run v1-tools --split dev --llm live        # records (resumable)
    python -m incidentiq.eval --run v0b-filtered-baseline --condition scale100 --split dev --llm live

Live runs call the model once per distinct prompt and save the replies, so a run that stops at the
free tier's daily limit can be repeated the next day and carries on where it left off. Results are
only written for a run that finished.
"""

import argparse
import os
import sys
from pathlib import Path

from incidentiq import data
from incidentiq.config import RESULTS_DIR
from incidentiq.eval.report import (
    comparison_markdown,
    load_notes,
    render_files,
    write_files,
)
from incidentiq.eval.runner import run_variant
from incidentiq.eval.variants import VARIANTS
from incidentiq.llm import CacheMiss, QuotaExhausted, get_llm

SCALE_ENV = "INCIDENTIQ_LOG_SCALE"


SCALE100_RUNS = ["v0-baseline", "v0b-filtered-baseline", "v4-final"]  # v5-scale joins later


def _variant_names(run: str, scale100: bool) -> list[str]:
    """`all` is the five original runs (no v0b, so `make eval` is unchanged), or under scale100
    exactly SCALE100_RUNS. Other runs are not part of the scale100 comparison."""
    if scale100 and run != "all" and run not in SCALE100_RUNS:
        raise ValueError(f"{run} is not part of the scale100 condition; choose from "
                         f"{SCALE100_RUNS}")
    if run != "all":
        return [run]
    if scale100:
        return SCALE100_RUNS
    return [name for name, v in VARIANTS.items() if v.in_original]


def _compare(committed: Path, fresh: dict[str, str]) -> list[str]:
    problems = []
    for name, text in fresh.items():
        path = committed / name
        if not path.exists():
            problems.append(f"{path} is missing")
        elif path.read_text(encoding="utf-8") != text:
            problems.append(f"{path} differs from the replayed result")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m incidentiq.eval", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", required=True, help=f"one of {list(VARIANTS)} or 'all'")
    parser.add_argument("--split", choices=["dev", "test", "all"], default="test")
    parser.add_argument("--llm", choices=["replay", "live"], default="replay")
    parser.add_argument("--condition", choices=["original", "scale100"], default="original",
                        help="scale100 = 100x log volume (docs/benchmark-scale100.md); results go "
                             "to results/scale100/")
    parser.add_argument("--out", type=Path, help="output directory (single run only)")
    parser.add_argument("--incidents", help="comma-separated incident IDs (for quick tests)")
    parser.add_argument("--max-steps", type=int)
    parser.add_argument("--quiet", action="store_true",
                        help="no per-incident lines (use on the test split while tuning on dev, "
                             "so individual test failures are not seen)")
    parser.add_argument("--check", action="store_true",
                        help="replay and compare with the committed results instead of writing")
    args = parser.parse_args(argv)

    # The data loader reads the condition from the environment; restore it afterwards.
    previous = os.environ.get(SCALE_ENV)
    os.environ[SCALE_ENV] = "100" if args.condition == "scale100" else "1"
    try:
        return _run(args, parser)
    finally:
        if previous is None:
            del os.environ[SCALE_ENV]
        else:
            os.environ[SCALE_ENV] = previous


def _run(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    scale100 = args.condition == "scale100"
    results_dir = RESULTS_DIR / "scale100" if scale100 else RESULTS_DIR
    try:
        names = _variant_names(args.run, scale100)
    except ValueError as exc:
        parser.error(str(exc))
    unknown = [n for n in names if n not in VARIANTS]
    if unknown:
        parser.error(f"unknown run {unknown}; choose from {list(VARIANTS)}")
    if args.out and len(names) > 1:
        parser.error("--out works with a single --run")
    ids = (args.incidents.split(",") if args.incidents
           else data.list_incident_ids(None if args.split == "all" else args.split))

    llm = get_llm(args.llm)
    all_results, problems = [], []
    for name in names:
        variant = VARIANTS[name]
        out_dir = args.out or results_dir / name
        try:
            runs = run_variant(variant, ids, llm, max_steps=args.max_steps,
                               progress=(lambda _line: None) if args.quiet else print)
        except QuotaExhausted as exc:
            print(f"\nSTOPPED: {exc}\nNothing was written for {name}; rerun the same command to "
                  f"continue.", file=sys.stderr)
            return 3
        except CacheMiss as exc:
            print(f"\nCACHE MISS while replaying {name}:\n{exc}", file=sys.stderr)
            return 2
        results, files = render_files(variant, runs, load_notes(out_dir))
        all_results.append(results)
        if args.check:
            problems += _compare(out_dir, files)
        else:
            write_files(out_dir, files)
            print(f"wrote {out_dir}")

    if len(names) > 1 and not args.check:
        (results_dir / "comparison.md").write_text(
            comparison_markdown(all_results), encoding="utf-8", newline="\n")
    print()
    print(comparison_markdown(all_results))
    if args.check:
        if problems:
            print("REPLAY CHECK FAILED:\n  " + "\n  ".join(problems), file=sys.stderr)
            return 1
        print(f"Replay check passed: {len(names)} run(s) reproduce the committed results exactly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
