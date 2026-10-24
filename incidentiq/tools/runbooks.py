"""runbook_retrieve: dense-embedding search over runbook sections in pgvector."""

from dataclasses import dataclass

import numpy as np
import psycopg

from incidentiq.schemas import Evidence, ToolResult
from incidentiq.store import db
from incidentiq.store.embed import Embedder, get_embedder
from incidentiq.tools import ToolError

DEFAULT_K = 3
MAX_K = 8


@dataclass
class Hit:
    section_id: str
    title: str
    heading: str
    text: str
    score: float  # cosine similarity, 1.0 = identical direction


def search_runbooks(conn: psycopg.Connection, embedder: Embedder, query: str,
                    k: int = DEFAULT_K) -> list[Hit]:
    if not query.strip():
        raise ToolError("query must not be empty")
    stored = db.stored_embedder(conn)
    if stored is None:
        raise ToolError("no runbooks ingested; run `make seed`")
    if stored != (embedder.name, embedder.dim):
        raise RuntimeError(
            f"database holds {stored[0]} embeddings but the query embedder is {embedder.name}")
    k = max(1, min(int(k), MAX_K))
    vec = np.array(embedder.embed([query])[0], dtype=np.float32)
    rows = conn.execute(
        "SELECT section_id, title, heading, text, 1 - (embedding <=> %s) AS score "
        "FROM runbook_chunks ORDER BY embedding <=> %s, section_id LIMIT %s",
        (vec, vec, k)).fetchall()
    return [Hit(*row) for row in rows]


def runbook_retrieve(query: str, k: int = DEFAULT_K, conn: psycopg.Connection | None = None,
                     embedder: Embedder | None = None) -> ToolResult:
    own_conn = conn is None
    conn = conn or db.connect()
    try:
        hits = search_runbooks(conn, embedder or get_embedder(), query, k)
    finally:
        if own_conn:
            conn.close()
    evidence = [
        Evidence(evidence_id=h.section_id, kind="runbook",
                 excerpt=f"{h.title} - {h.heading} (similarity {h.score:.2f}): {h.text}")
        for h in hits
    ]
    return ToolResult(
        tool="runbook_retrieve", args={"query": query, "k": k},
        summary=f"{len(hits)} runbook sections; best match {hits[0].section_id} "
                f"(similarity {hits[0].score:.2f})." if hits else "no runbook sections found.",
        evidence=evidence)
