"""Command line: `incidentiq diagnose <incident_id>` (or `--demo`)."""

import argparse
import json
import sys
import textwrap

from incidentiq import data
from incidentiq.agents.graph import AgentResult, run_incident
from incidentiq.llm import get_llm
from incidentiq.schemas import Diagnosis


def demo_incident_id() -> str:
    """A fixed, ordinary dev-split incident: connection pool exhaustion, no hard-case twist."""
    for incident_id in data.list_incident_ids("dev"):
        truth = data.load_ground_truth(incident_id)
        if truth.root_cause_category == "db_connection_pool_exhaustion" and not truth.hard_case:
            return incident_id
    raise LookupError("no demo incident found")


def _wrap(text: str, indent: str = "    ") -> str:
    return textwrap.fill(text, width=100, initial_indent=indent, subsequent_indent=indent)


def render_diagnosis(d: Diagnosis) -> str:
    lines = [f"Root cause: {d.root_cause_category}  (confidence: {d.confidence})",
             _wrap(d.root_cause_summary), "", "Claims:"]
    for c in d.claims:
        lines += [_wrap(f"- {c.statement}", "  "), f"      cites: {', '.join(c.evidence_ids)}"]
    lines += ["", "Recommended actions:"]
    for a in d.recommended_actions:
        lines += [_wrap(f"- {a.statement}", "  "), f"      cites: {', '.join(a.evidence_ids)}"]
    if d.ruled_out:
        lines += ["", "Ruled out:"] + [_wrap(f"- {r}", "  ") for r in d.ruled_out]
    if d.unverified:
        lines += ["", "WARNING: this diagnosis could not be verified."]
    return "\n".join(lines)


def render_verification(s) -> list[str]:
    v = s.verification
    methods = sorted({c.method for c in v.checks if c.method != "none"}) or ["none"]
    status = "PASSED" if v.ok else ("FAILED, marked unverified" if s.diagnosis and
                                    s.diagnosis.unverified else "retrying")
    lines = [f"VERIFIER: {status} ({len(v.checks)} statements checked; support decided by "
             f"{'+'.join(methods)}; reporter retries used: {s.retries})"]
    lines += [_wrap(f"- {e}", "  ") for e in v.errors]
    return lines + [""]


def render_result(result: AgentResult) -> str:
    s = result.state
    out = [f"INCIDENT {s.incident.incident_id}", _wrap(s.incident.alert_text, "  "), ""]
    for round_no, note in enumerate(s.planner_notes, start=1):
        out += ["Plan: " + textwrap.fill(note, width=100, subsequent_indent="      ")]
        for o in (o for o in s.observations if o.round == round_no):
            args = json.dumps({k: v for k, v in o.args.items() if v is not None}, sort_keys=True)
            out += [f"  Step {o.step}: {o.tool} {args}"]
            if o.reason:
                out += [_wrap(f"why: {o.reason}", "      ")]
            out += [_wrap(f"result: {o.summary}", "      ")]
            for e in o.evidence[:6]:
                out += [_wrap(f"[{e.evidence_id}] {e.excerpt}", "        ")[:260]]
            if len(o.evidence) > 6:
                out += [f"        ... and {len(o.evidence) - 6} more"]
        out.append("")
    if s.hypotheses:
        out += ["Hypotheses: " + "; ".join(h.root_cause_category for h in s.hypotheses), ""]
    if s.diagnosis:
        out += ["DIAGNOSIS", render_diagnosis(s.diagnosis), ""]
    if s.verification:
        out += render_verification(s)
    st = result.stats
    out += [f"Steps used: {s.step_count}/{s.max_steps}. LLM calls: {st.calls} "
            f"({st.retries} retries), tokens in/out: {st.prompt_tokens}/{st.completion_tokens}, "
            f"redactions applied to prompts and replies: {st.redactions}."]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="incidentiq")
    sub = parser.add_subparsers(dest="command", required=True)
    d = sub.add_parser("diagnose", help="diagnose one bundled incident")
    d.add_argument("incident_id", nargs="?", help="e.g. INC-001")
    d.add_argument("--demo", action="store_true", help="use the bundled sample incident")
    d.add_argument("--llm", choices=["replay", "live", "mock"], help="override INCIDENTIQ_LLM")
    d.add_argument("--max-steps", type=int)
    d.add_argument("--no-verify", action="store_true", help="skip the citation verifier")
    d.add_argument("--llm-entailment", action="store_true",
                   help="let the LLM re-check statements the lexical check rejects (extra calls)")
    args = parser.parse_args(argv)
    incident_id = demo_incident_id() if args.demo else args.incident_id
    if not incident_id:
        parser.error("give an incident ID or --demo")
    result = run_incident(incident_id, get_llm(args.llm), max_steps=args.max_steps,
                          verify_output=not args.no_verify, llm_entailment=args.llm_entailment)
    print(render_result(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
