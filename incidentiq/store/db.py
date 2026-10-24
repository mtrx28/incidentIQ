"""Postgres + pgvector connection and schema."""

import psycopg
from pgvector.psycopg import register_vector

from incidentiq.config import load_config


def connect(url: str | None = None) -> psycopg.Connection:
    # The extension must exist before the vector type can be registered on the connection.
    conn = psycopg.connect(url or load_config().database_url, autocommit=True)
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    register_vector(conn)
    return conn


def reset_schema(conn: psycopg.Connection, dim: int) -> None:
    """Drop and recreate the runbook tables for an embedder of the given dimension."""
    conn.execute("DROP TABLE IF EXISTS runbook_chunks")
    conn.execute("DROP TABLE IF EXISTS embedding_config")
    conn.execute("""
        CREATE TABLE embedding_config (
            id    int PRIMARY KEY CHECK (id = 1),
            model text NOT NULL,
            dim   int  NOT NULL
        )""")
    conn.execute(f"""
        CREATE TABLE runbook_chunks (
            id         serial PRIMARY KEY,
            runbook_id int  NOT NULL,
            section_id text NOT NULL UNIQUE,   -- evidence ID, e.g. R-02-5
            heading    text NOT NULL,
            title      text NOT NULL,
            text       text NOT NULL,
            embedding  vector({int(dim)}) NOT NULL
        )""")
    # HNSW with cosine distance. With ~144 chunks Postgres will often pick a sequential scan
    # anyway, which is fine; the index is here so the design holds at larger corpus sizes.
    conn.execute(
        "CREATE INDEX runbook_chunks_embedding_idx ON runbook_chunks "
        "USING hnsw (embedding vector_cosine_ops)")


def stored_embedder(conn: psycopg.Connection) -> tuple[str, int] | None:
    """(model, dim) the table was built with, or None if nothing has been ingested."""
    try:
        row = conn.execute("SELECT model, dim FROM embedding_config WHERE id = 1").fetchone()
    except psycopg.errors.UndefinedTable:
        return None
    return (row[0], row[1]) if row else None
