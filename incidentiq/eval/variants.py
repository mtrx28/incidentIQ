"""The benchmark stages. Each is a set of switches, so the improvement story is reproducible."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Variant:
    name: str
    description: str
    kind: str  # "baseline" (one LLM call) or "agent" (the LangGraph loop)
    retrieval: str = "embedding"  # runbook search: "keyword" (BM25) or "embedding" (pgvector)
    verifier: bool = False  # citation verifier with up to 2 reporter retries
    tuned: bool = False  # v4 prompt and stopping-rule changes, written from dev failures only
    rarity: bool = False  # v5: rarity-ranked log_search, default window, header, prompt addendum
    filtered: bool = False  # baseline only: WARN/ERROR lines of the alerting service (v0b)
    in_original: bool = True  # part of `--run all` for the original condition (and `make eval`)


VARIANTS: dict[str, Variant] = {v.name: v for v in [
    Variant("v0-baseline",
            "Single LLM call with the alert and a dump of the last 100 log lines. No tools, no "
            "plan loop, no runbooks.", kind="baseline"),
    Variant("v1-tools",
            "Plan-act-observe loop with metrics, log search and keyword (BM25) runbook search. "
            "No verifier.", kind="agent", retrieval="keyword"),
    Variant("v2-retrieval",
            "v1 with dense-embedding runbook retrieval (pgvector, one chunk per section with the "
            "title and heading prepended).", kind="agent", retrieval="embedding"),
    Variant("v3-verifier",
            "v2 plus the citation verifier and up to 2 reporter retries.",
            kind="agent", retrieval="embedding", verifier=True),
    Variant("v4-final",
            "v3 plus prompt and stopping-rule refinements written from dev-split failures only.",
            kind="agent", retrieval="embedding", verifier=True, tuned=True),
    Variant("v0b-filtered-baseline",
            "Single LLM call with the alert and the last 100 WARN and ERROR log lines of the "
            "alerting service. Added for the scale100 condition; the first baseline is v0a.",
            kind="baseline", filtered=True, in_original=False),
    Variant("v5-scale",
            "v4 plus rarity-ranked log_search with a default window around the alert and a "
            "count/template header (and a prompt addendum describing them). Built for the "
            "scale100 condition; scope fixed in docs/benchmark-scale100.md.",
            kind="agent", retrieval="embedding", verifier=True, tuned=True, rarity=True,
            in_original=False),
]}
