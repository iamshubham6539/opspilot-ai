from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import IncidentStatus, Severity


class IncidentCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    severity: Severity
    service: str = Field(min_length=1, max_length=100)
    # Logs are untrusted text and can be big; cap them instead of accepting anything.
    logs: str | None = Field(default=None, max_length=200_000)


class IncidentSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    severity: Severity
    service: str
    status: IncidentStatus
    created_at: datetime


class IncidentRead(IncidentSummary):
    description: str | None
    logs: str | None
    category: str | None
    diagnosis: str | None
    confidence: str | None
    summary: str | None
    evidence: list[dict] | None
    runbooks: list[dict] | None
    remediation: list[dict] | None
    errors: list[str] | None
    approval_status: str
    approved_by: str | None
    approved_at: datetime | None
    investigation_started_at: datetime | None
    completed_at: datetime | None
    updated_at: datetime


class InvestigationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: IncidentStatus
    category: str | None
    diagnosis: str | None
    confidence: str | None
    summary: str | None
    evidence: list[dict] | None
    runbooks: list[dict] | None
    remediation: list[dict] | None
    errors: list[str] | None
    approval_status: str
    approved_by: str | None
    approved_at: datetime | None
    investigation_started_at: datetime | None
    completed_at: datetime | None


class ApprovalDecision(BaseModel):
    approved: bool
    comment: str | None = Field(default=None, max_length=2000)
