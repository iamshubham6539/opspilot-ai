import math
import os

import pytest
from sqlalchemy import delete, func, select

from app.config import EMBEDDING_DIMENSIONS, RUNBOOK_MAX_DISTANCE
from app.database import SessionLocal
from app.models import RunbookChunk
from app.retrieval import EmbeddingError, chunk_markdown, embed, ingest_runbooks, retrieve_runbooks

needs_postgres = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL", "").startswith("postgresql"),
    reason="needs Postgres with pgvector (set TEST_DATABASE_URL)",
)


@pytest.fixture
def index():
    with SessionLocal() as session:
        session.execute(delete(RunbookChunk))
        session.commit()
    ingest_runbooks()
    yield
    with SessionLocal() as session:
        session.execute(delete(RunbookChunk))
        session.commit()


def test_chunk_markdown_keeps_source_heading_and_text():
    text = "# Pool problems\n\n## Symptoms\n\npool exhausted errors\n\n## Checks\n\ncheck in_use\n"

    chunks = chunk_markdown(text, "database_connection.md")

    assert {chunk["source"] for chunk in chunks} == {"database_connection.md"}
    assert any("Pool problems" in chunk["heading"] for chunk in chunks)
    assert any("pool exhausted" in chunk["content"] for chunk in chunks)
    assert all(chunk["content"].strip() for chunk in chunks)


def test_long_sections_are_split():
    text = "# Big\n\n## Section\n\n" + "connection " * 800

    chunks = chunk_markdown(text, "big.md")

    assert len(chunks) > 1
    assert all(len(chunk["content"]) <= 1200 for chunk in chunks)


def test_mock_embeddings_are_deterministic_and_normalized():
    first = embed(["connection pool exhausted"])[0]
    second = embed(["connection pool exhausted"])[0]
    unrelated = embed(["sourdough bread"])[0]

    assert first == second
    assert first != unrelated
    assert len(first) == EMBEDDING_DIMENSIONS
    assert math.isclose(sum(value * value for value in first), 1.0, rel_tol=1e-9)


def test_openai_embeddings_need_a_key(monkeypatch):
    monkeypatch.setattr("app.retrieval.EMBEDDING_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(EmbeddingError, match="OPENAI_API_KEY"):
        embed(["anything"])


def test_unknown_embedding_provider_is_rejected(monkeypatch):
    monkeypatch.setattr("app.retrieval.EMBEDDING_PROVIDER", "local")

    with pytest.raises(EmbeddingError, match="unsupported"):
        embed(["anything"])


@needs_postgres
def test_ingesting_twice_does_not_duplicate(index):
    before = _chunk_count()

    second = ingest_runbooks()

    assert before > 0
    assert second["added"] == 0
    assert _chunk_count() == before


@needs_postgres
@pytest.mark.parametrize(
    ("query", "source"),
    [
        ("connection pool exhausted, timeouts acquiring connection", "database_connection.md"),
        ("p99 latency high, requests very slow, slow queries", "high_latency.md"),
        ("health checks fail, 503 service unavailable", "service_unavailable.md"),
    ],
)
def test_relevant_runbook_is_retrieved(index, query, source):
    hits = retrieve_runbooks(query, limit=3)

    assert hits, "expected at least one relevant chunk"
    assert hits[0]["source"] == source
    assert hits[0]["distance"] <= RUNBOOK_MAX_DISTANCE
    assert set(hits[0]) == {"source", "heading", "content", "distance"}


@needs_postgres
@pytest.mark.parametrize(
    "query",
    [
        "how to bake sourdough bread",
        "quarterly marketing budget planning",
        "the office printer is out of toner",
    ],
)
def test_irrelevant_queries_return_nothing(index, query):
    assert retrieve_runbooks(query) == []


@needs_postgres
def test_empty_index_returns_nothing():
    with SessionLocal() as session:
        session.execute(delete(RunbookChunk))
        session.commit()

    assert retrieve_runbooks("connection pool exhausted") == []


@needs_postgres
def test_deleted_runbook_chunks_are_removed(tmp_path):
    (tmp_path / "old.md").write_text("# Old\n\n## Steps\n\nrestart things\n")

    ingest_runbooks(tmp_path)
    assert _sources() == {"old.md"}

    (tmp_path / "old.md").unlink()
    ingest_runbooks(tmp_path)

    assert _chunk_count() == 0


def test_empty_query_is_rejected():
    with pytest.raises(ValueError):
        retrieve_runbooks("   ")


def _chunk_count() -> int:
    with SessionLocal() as session:
        return session.scalar(select(func.count()).select_from(RunbookChunk)) or 0


def _sources() -> set[str]:
    with SessionLocal() as session:
        return set(session.scalars(select(RunbookChunk.source)))
