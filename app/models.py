import uuid
from datetime import UTC, datetime
from enum import Enum

from sqlalchemy import JSON, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from pgvector.sqlalchemy import Vector

from app.config import EMBEDDING_DIMENSIONS
from app.database import Base


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IncidentStatus(str, Enum):
    CREATED = "created"
    INVESTIGATING = "investigating"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    ESCALATED = "escalated"
    REJECTED = "rejected"
    FAILED = "failed"


def new_id() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(UTC)


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(16), index=True)
    service: Mapped[str] = mapped_column(String(100), index=True)
    logs: Mapped[str | None] = mapped_column(Text)

    status: Mapped[str] = mapped_column(String(24), default=IncidentStatus.CREATED.value, index=True)
    category: Mapped[str | None] = mapped_column(String(32))
    diagnosis: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[str | None] = mapped_column(String(16))
    summary: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[list[dict] | None] = mapped_column(JSON)
    runbooks: Mapped[list[dict] | None] = mapped_column(JSON)
    remediation: Mapped[list[dict] | None] = mapped_column(JSON)
    errors: Mapped[list[str] | None] = mapped_column(JSON)

    approval_status: Mapped[str] = mapped_column(String(16), default="none")
    approved_by: Mapped[str | None] = mapped_column(String(200))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    investigation_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class RunbookChunk(Base):
    """Retrieval index over runbooks/. Ids are content hashes, so re-ingesting is safe."""

    __tablename__ = "runbook_chunks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    source: Mapped[str] = mapped_column(String(200), index=True)
    heading: Mapped[str | None] = mapped_column(String(300))
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSIONS))
