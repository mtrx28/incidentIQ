"""Split runbooks into one chunk per section and load them into pgvector.

    python -m incidentiq.store.ingest            # ingest (refuses to mix embedders)
    python -m incidentiq.store.ingest --reset    # rebuild the table from scratch
"""

import argparse

import numpy as np
import psycopg

from incidentiq.store import db
from incidentiq.store.chunking import Chunk, chunk_directory
from incidentiq.store.embed import Embedder, get_embedder


def ingest(conn: psycopg.Connection, embedder: Embedder, chunks: list[Chunk],
           reset: bool = False) -> int:
    existing = db.stored_embedder(conn)
    wanted = (embedder.name, embedder.dim)
    if existing and existing != wanted and not reset:
        raise RuntimeError(
            f"database was built with {existing[0]} (dim {existing[1]}) but the current embedder "
            f"is {wanted[0]} (dim {wanted[1]}). Embedders must not be mixed; rerun with --reset.")
    if reset or existing is None:
        db.reset_schema(conn, embedder.dim)
    else:
        conn.execute("TRUNCATE runbook_chunks RESTART IDENTITY")

    vectors = embedder.embed([c.embed_text for c in chunks])
    with conn.transaction():
        conn.execute("INSERT INTO embedding_config (id, model, dim) VALUES (1, %s, %s) "
                     "ON CONFLICT (id) DO UPDATE SET model = EXCLUDED.model, dim = EXCLUDED.dim",
                     (embedder.name, embedder.dim))
        for chunk, vec in zip(chunks, vectors, strict=True):
            conn.execute(
                "INSERT INTO runbook_chunks (runbook_id, section_id, heading, title, text, embedding) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (chunk.runbook_id, chunk.section_id, chunk.heading, chunk.title, chunk.text,
                 np.array(vec, dtype=np.float32)))
    return len(chunks)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true", help="drop and rebuild the tables")
    args = parser.parse_args()
    chunks = chunk_directory()
    with db.connect() as conn:
        n = ingest(conn, get_embedder(), chunks, reset=args.reset)
    print(f"ingested {n} runbook chunks")


if __name__ == "__main__":
    main()
