"""Verifier: check that a diagnosis is grounded in the evidence collected during this run.

Deterministic rules first:
  1. every cited evidence ID was actually retrieved in this run (no invented IDs);
  2. every recommended action cites a runbook section, and there is at least one action;
  3. the cited evidence supports the statement (lexical overlap, optionally an LLM yes/no check);
  4. the root-cause category is one of the allowed values.

Rule 3 is approximate. Lexical overlap measures how many of a statement's key terms appear in
the evidence it cites. It catches statements that have nothing to do with their citations, but it
cannot judge meaning, so it can reject a fair paraphrase and accept a loosely related one. The
optional LLM check gives rejected statements a second chance; `Verification.method` and each
`ClaimCheck.method` say which check decided.
"""

import re

from incidentiq.llm.base import LLMClient, LLMOutputError
from incidentiq.schemas import (
    ROOT_CAUSES,
    Claim,
    ClaimCheck,
    Diagnosis,
    Entailment,
    Evidence,
    GraphState,
    Verification,
)

MAX_RETRIES = 2  # reporter retries after a failed verification
LEXICAL_THRESHOLD = 0.3  # share of a statement's key terms that must appear in its evidence

_STOPWORDS = frozenset(["a", "an", "and", "are", "as", "at", "be", "been", "by", "for", "from", "has", "have", "in", "into", "is", "it", "its", "of", "on", "or", "than", "that", "the", "their", "then", "there", "these", "this", "those", "to", "was", "were", "which", "while", "with", "within", "would", "also", "after", "before", "during", "over", "under", "both", "each", "other", "some", "such", "only", "more", "most", "not", "no", "but", "if", "so", "can", "could", "may", "might", "will", "shall", "do", "does", "did", "being", "about", "above", "across", "against", "all", "any", "because", "between", "how", "out", "up", "down", "off"])
_TOKEN = re.compile(r"\d+(?:\.\d+)?|[a-z]+")


def _stem(word: str) -> str:
    """Crude plural/tense stripping so 'timeouts' matches 'timeout' and 'failed' matches 'fail'."""
    if word.isdigit() or len(word) <= 4:
        return word
    for suffix in ("ing", "ed", "es", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[: -len(suffix)]
    return word


def key_terms(text: str) -> set[str]:
    return {_stem(t) for t in _TOKEN.findall(text.lower())
            if t not in _STOPWORDS and (len(t) >= 3 or t.replace(".", "").isdigit())}


def lexical_overlap(statement: str, evidence_text: str) -> float:
    terms = key_terms(statement)
    if not terms:
        return 0.0
    return len(terms & key_terms(evidence_text)) / len(terms)


def collect_evidence(state: GraphState) -> dict[str, list[Evidence]]:
    """Every evidence item seen in this run, by ID (an ID can appear in several observations)."""
    found: dict[str, list[Evidence]] = {}
    for obs in state.observations:
        for e in obs.evidence:
            found.setdefault(e.evidence_id, []).append(e)
    return found


def _head(text: str, n: int = 70) -> str:
    return text if len(text) <= n else text[:n].rstrip() + "..."


def _entails(llm: LLMClient, statement: str, excerpts: list[str]) -> bool:
    evidence = "\n".join(f"- {x}" for x in excerpts)
    messages = [
        {"role": "system", "content": (
            "ROLE: entailment checker\nYou check whether evidence supports a statement. Answer "
            "supported=true only if the evidence itself states or directly implies the statement. "
            'Reply with only JSON: {"supported": true, "reason": "one short sentence"}')},
        {"role": "user", "content": f"Statement: {statement}\n\nEvidence:\n{evidence}"},
    ]
    try:
        verdict = llm.complete(messages, Entailment)
    except LLMOutputError:
        return False
    assert isinstance(verdict, Entailment)
    return verdict.supported


def verify(diagnosis: Diagnosis, evidence: dict[str, list[Evidence]],
           llm: LLMClient | None = None, threshold: float = LEXICAL_THRESHOLD) -> Verification:
    """Check `diagnosis` against `evidence`. Pass `llm` to enable the entailment second chance."""
    errors: list[str] = []
    checks: list[ClaimCheck] = []
    kind_of = {i: items[0].kind for i, items in evidence.items()}
    retrieved_runbooks = sorted(i for i, k in kind_of.items() if k == "runbook")

    if diagnosis.root_cause_category not in ROOT_CAUSES:  # rule 4
        errors.append(f"root_cause_category {diagnosis.root_cause_category!r} is not allowed; "
                      f"use one of {list(ROOT_CAUSES)}")

    def check(section: str, index: int, claim: Claim) -> None:
        label = f"{section} {index} ({_head(claim.statement)!r})"
        unknown = [i for i in claim.evidence_ids if i not in evidence]
        if unknown:  # rule 1
            same_kind = sorted(i for i in evidence if i[0] == unknown[0][0])[:20]
            hint = f" For example: {', '.join(same_kind)}." if same_kind else ""
            errors.append(f"{label} cites {', '.join(unknown)}, which was not retrieved in this "
                          f"investigation. Cite only IDs from the evidence list.{hint}")
            checks.append(ClaimCheck(section=section, index=index, unknown_ids=unknown,
                                     supported=False))
            return
        if section == "action" and not any(kind_of[i] == "runbook" for i in claim.evidence_ids):
            hint = (f" Retrieved runbook sections: {', '.join(retrieved_runbooks)}."
                    if retrieved_runbooks else "")
            errors.append(f"{label} cites {', '.join(claim.evidence_ids)}, but a recommended "
                          f"action must cite a runbook section (R-...).{hint}")
            checks.append(ClaimCheck(section=section, index=index, supported=False))
            return
        excerpts = [e.excerpt for i in claim.evidence_ids for e in evidence[i]]  # rule 3
        overlap = round(lexical_overlap(claim.statement, " ".join(excerpts)), 3)
        if overlap >= threshold:
            checks.append(ClaimCheck(section=section, index=index, overlap=overlap,
                                     method="lexical", supported=True))
        elif llm is not None and _entails(llm, claim.statement, excerpts):
            checks.append(ClaimCheck(section=section, index=index, overlap=overlap,
                                     method="llm", supported=True))
        else:
            checks.append(ClaimCheck(section=section, index=index, overlap=overlap,
                                     method="llm" if llm is not None else "lexical",
                                     supported=False))
            cited = ", ".join(claim.evidence_ids)
            errors.append(f"{label} is not supported by the evidence it cites ({cited}): only "
                          f"{overlap:.0%} of its key terms appear there. Cite evidence that "
                          f"states it, or rewrite or remove the claim.")

    for i, claim in enumerate(diagnosis.claims, start=1):
        check("claim", i, claim)
    for i, action in enumerate(diagnosis.recommended_actions, start=1):
        check("action", i, action)
    if not diagnosis.recommended_actions:  # rule 2: a diagnosis with no next step is not useful
        if retrieved_runbooks:
            errors.append("There are no recommended actions. Add at least one, citing a "
                          f"retrieved runbook section ({', '.join(retrieved_runbooks)}).")
        else:
            errors.append("There are no recommended actions, and no runbook section was "
                          "retrieved to cite.")

    return Verification(ok=not errors, errors=errors,
                        method="lexical+llm" if llm is not None else "lexical", checks=checks)
