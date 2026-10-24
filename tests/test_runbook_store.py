"""pgvector round trip with a tiny deterministic embedder (needs `make up`, not the real model)."""

import hashlib
import math

import psycopg
import pytest

from incidentiq.config import load_config
from incidentiq.store import db
from incidentiq.store.chunking import chunk_directory
from incidentiq.store.ingest import ingest
from incidentiq.tools import ToolError
from incidentiq.tools.runbooks import runbook_retrieve, search_runbooks

pytestmark = pytest.mark.db


class HashEmbedder:
    """Bag-of-words hashing into 384 dims: similar wording gives similar vectors."""

    dim = 384

    def __init__(self, name: str = "test-hash-embedder"):
        self.name = name

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            vec = [0.0] * self.dim
            for word in text.lower().split():
                h = int(hashlib.md5(word.strip(".,:;-()").encode()).hexdigest(), 16)
                vec[h % self.dim] += 1.0
            norm = math.sqrt(sum(x * x for x in vec)) or 1.0
            out.append([x / norm for x in vec])
        return out


TEST_DB = "incidentiq_test"


@pytest.fixture(scope="module")
def conn():
    """A separate database, so these tests never overwrite the real ingested runbooks."""
    base = load_config().database_url
    try:
        with psycopg.connect(base, autocommit=True) as admin:
            exists = admin.execute("SELECT 1 FROM pg_database WHERE datname = %s",
                                   (TEST_DB,)).fetchone()
            if not exists:
                admin.execute(f"CREATE DATABASE {TEST_DB}")
        c = db.connect(base.rsplit("/", 1)[0] + f"/{TEST_DB}")
    except psycopg.OperationalError as exc:  # pragma: no cover
        pytest.skip(f"database not available: {exc}")
    ingest(c, HashEmbedder(), chunk_directory(), reset=True)
    yield c
    c.close()


def test_ingest_loads_every_section(conn):
    assert conn.execute("SELECT count(*) FROM runbook_chunks").fetchone()[0] == 18 * 8


def test_retrieval_returns_scored_sections_best_first(conn):
    hits = search_runbooks(conn, HashEmbedder(), "disk full no space left on device", k=3)
    assert len(hits) == 3 and hits[0].score >= hits[1].score >= hits[2].score
    assert hits[0].section_id.startswith("R-06-")


def test_tool_result_cites_section_ids(conn):
    result = runbook_retrieve("expired certificate handshake", k=2, conn=conn,
                              embedder=HashEmbedder())
    assert [e.kind for e in result.evidence] == ["runbook", "runbook"]
    assert result.evidence[0].evidence_id.startswith("R-")


def test_empty_query_is_rejected(conn):
    with pytest.raises(ToolError):
        search_runbooks(conn, HashEmbedder(), "  ")


def test_mixing_embedders_is_refused(conn):
    with pytest.raises(RuntimeError, match="must not be mixed"):
        ingest(conn, HashEmbedder("another-model"), chunk_directory())
    with pytest.raises(RuntimeError):
        search_runbooks(conn, HashEmbedder("another-model"), "disk")
