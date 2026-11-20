import hashlib
import math
import os
import re
from pathlib import Path

from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
from sqlalchemy import delete, select

from app.config import EMBEDDING_DIMENSIONS, EMBEDDING_MODEL, EMBEDDING_PROVIDER, RUNBOOK_MAX_DISTANCE
from app.database import SessionLocal
from app.models import RunbookChunk

RUNBOOKS_DIR = Path(__file__).resolve().parent.parent / "runbooks"
MAX_CHUNK_CHARS = 1200
TOKEN = re.compile(r"[a-z0-9]+")

# Common words carry no retrieval signal in a bag-of-words stand-in.
STOPWORDS = {
    "a", "about", "after", "again", "all", "also", "an", "and", "any", "are", "as", "at",
    "be", "been", "before", "but", "by", "can", "could", "did", "do", "does", "down", "for",
    "from", "had", "has", "have", "he", "her", "here", "him", "his", "how", "if", "in",
    "into", "is", "it", "its", "just", "may", "might", "more", "most", "no", "not", "of",
    "off", "on", "once", "or", "our", "out", "over", "she", "should", "so", "some", "such",
    "than", "that", "the", "their", "them", "then", "there", "these", "they", "this",
    "those", "to", "under", "up", "us", "was", "we", "were", "what", "when", "which",
    "while", "who", "why", "will", "with", "would", "you", "your",
}


class EmbeddingError(RuntimeError):
    """Embeddings were unreachable or misconfigured."""


def chunk_markdown(text: str, source: str) -> list[dict]:
    sections = MarkdownHeaderTextSplitter(
        headers_to_split_on=[("#", "title"), ("##", "section")],
        strip_headers=False,
    ).split_text(text)

    limiter = RecursiveCharacterTextSplitter(chunk_size=MAX_CHUNK_CHARS, chunk_overlap=100)
    chunks = []
    for section in sections:
        heading = " / ".join(
            part for part in (section.metadata.get("title"), section.metadata.get("section")) if part
        )
        for piece in limiter.split_text(section.page_content):
            if piece.strip():
                chunks.append({"source": source, "heading": heading or None, "content": piece.strip()})
    return chunks


def embed(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []

    if EMBEDDING_PROVIDER == "mock":
        return [_mock_embedding(text) for text in texts]
    if EMBEDDING_PROVIDER != "openai":
        raise EmbeddingError(f"unsupported EMBEDDING_PROVIDER {EMBEDDING_PROVIDER!r}")

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise EmbeddingError("OPENAI_API_KEY is not set (use EMBEDDING_PROVIDER=mock for offline runs)")

    from langchain_openai import OpenAIEmbeddings

    model = OpenAIEmbeddings(
        model=EMBEDDING_MODEL,
        dimensions=EMBEDDING_DIMENSIONS,
        api_key=api_key,
        base_url=os.getenv("EMBEDDING_BASE_URL") or None,
    )
    try:
        return model.embed_documents(texts)
    except Exception as exc:
        raise EmbeddingError(f"embedding call failed: {exc}") from exc


def _mock_embedding(text: str) -> list[float]:
    """Deterministic hashed bag of words. Offline substitute, not a real embedding model."""
    vector = [0.0] * EMBEDDING_DIMENSIONS
    for token in TOKEN.findall(text.lower()):
        if token in STOPWORDS or len(token) < 3:
            continue
        bucket = int(hashlib.sha256(token.encode()).hexdigest()[:8], 16) % EMBEDDING_DIMENSIONS
        vector[bucket] += 1.0
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def _chunk_id(source: str, heading: str | None, content: str) -> str:
    return hashlib.sha256(f"{source}|{heading}|{content}".encode()).hexdigest()[:32]


def ingest_runbooks(directory: Path = RUNBOOKS_DIR) -> dict:
    """Upserts the current runbook files and drops chunks that no longer exist."""
    paths = sorted(directory.glob("*.md"))
    chunks = []
    for path in paths:
        chunks.extend(chunk_markdown(path.read_text(), path.name))

    vectors = embed([chunk["content"] for chunk in chunks])
    keep = {_chunk_id(c["source"], c["heading"], c["content"]) for c in chunks}

    with SessionLocal() as session:
        if keep:
            session.execute(delete(RunbookChunk).where(RunbookChunk.id.not_in(keep)))
        else:
            session.execute(delete(RunbookChunk))

        existing = set(session.scalars(select(RunbookChunk.id)))
        added = 0
        for chunk, vector in zip(chunks, vectors):
            chunk_id = _chunk_id(chunk["source"], chunk["heading"], chunk["content"])
            if chunk_id in existing:
                continue
            session.add(RunbookChunk(id=chunk_id, embedding=vector, **chunk))
            added += 1
        session.commit()

    return {"documents": len(paths), "chunks": len(chunks), "added": added}


def retrieve_runbooks(query: str, limit: int = 3, max_distance: float | None = None) -> list[dict]:
    """Nearest runbook chunks for a query. Returns [] rather than padding with weak matches."""
    if not query.strip():
        raise ValueError("query must not be empty")
    limit = max(1, min(limit, 10))
    threshold = RUNBOOK_MAX_DISTANCE if max_distance is None else max_distance

    distance = RunbookChunk.embedding.cosine_distance(embed([query])[0]).label("distance")
    with SessionLocal() as session:
        rows = session.execute(select(RunbookChunk, distance).order_by(distance).limit(limit)).all()

    return [
        {
            "source": row.source,
            "heading": row.heading,
            "content": row.content,
            "distance": round(float(score), 4),
        }
        for row, score in rows
        if score <= threshold
    ]


if __name__ == "__main__":
    print(ingest_runbooks())
