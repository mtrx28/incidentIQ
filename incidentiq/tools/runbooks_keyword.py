"""A keyword (BM25) runbook search, used by the v1 benchmark stage instead of embeddings.

It indexes only the section body, with no title or heading, and matches exact words. It exists so
the benchmark can show what dense retrieval adds: it cannot match "stalled" to "waiting" or find a
section whose key term appears only in its heading.
"""

import math
from collections import Counter
from functools import cache

from incidentiq.schemas import Evidence, ToolResult
from incidentiq.store.chunking import Chunk, chunk_directory
from incidentiq.text import STOPWORDS, words
from incidentiq.tools import ToolError
from incidentiq.tools.runbooks import DEFAULT_K, MAX_K, Hit

K1, B = 1.5, 0.75


def _terms(text: str) -> list[str]:
    return [w for w in words(text) if w not in STOPWORDS]


@cache
def _index() -> tuple[list[Chunk], list[Counter], dict[str, int], float]:
    chunks = chunk_directory()
    counts = [Counter(_terms(c.text)) for c in chunks]
    doc_freq: Counter = Counter()
    for c in counts:
        doc_freq.update(c.keys())
    avg_len = sum(sum(c.values()) for c in counts) / len(counts)
    return chunks, counts, dict(doc_freq), avg_len


def search_keyword(query: str, k: int = DEFAULT_K) -> list[Hit]:
    if not query.strip():
        raise ToolError("query must not be empty")
    chunks, counts, doc_freq, avg_len = _index()
    n = len(chunks)
    terms = set(_terms(query))
    scored = []
    for chunk, tf in zip(chunks, counts, strict=True):
        length = sum(tf.values())
        score = 0.0
        for t in terms & tf.keys():
            idf = math.log(1 + (n - doc_freq[t] + 0.5) / (doc_freq[t] + 0.5))
            score += idf * tf[t] * (K1 + 1) / (tf[t] + K1 * (1 - B + B * length / avg_len))
        scored.append((score, chunk))
    scored.sort(key=lambda s: (-s[0], s[1].section_id))
    k = max(1, min(int(k), MAX_K))
    return [Hit(c.section_id, c.title, c.heading, c.text, round(score, 3))
            for score, c in scored[:k] if score > 0]


def keyword_runbook_retrieve(query: str, k: int = DEFAULT_K) -> ToolResult:
    hits = search_keyword(query, k)
    evidence = [Evidence(evidence_id=h.section_id, kind="runbook",
                         excerpt=f"{h.title} - {h.heading} (match score {h.score:.1f}): {h.text}")
                for h in hits]
    summary = (f"{len(hits)} runbook sections; best match {hits[0].section_id} "
               f"(match score {hits[0].score:.1f})." if hits else "no runbook sections matched.")
    return ToolResult(tool="runbook_retrieve", args={"query": query, "k": k}, summary=summary,
                      evidence=evidence)
