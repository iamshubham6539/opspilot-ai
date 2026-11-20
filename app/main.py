import os
import secrets
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import APP_ENV
from app.database import get_db, init_db
from app.investigations import NotResumableError, mark_started, run_investigation, submit_decision
from app.models import Incident, IncidentStatus, Severity
from app.schemas import (
    ApprovalDecision,
    IncidentCreate,
    IncidentRead,
    IncidentSummary,
    InvestigationRead,
)
from app.tracing import validate_tracing


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Refuse to start with tracing switched on but unusable, instead of silently losing traces.
    validate_tracing()
    # Simple init strategy for now; Alembic once the schema stops moving.
    init_db()
    yield


app = FastAPI(title="OpsPilot AI", version="0.1.0", lifespan=lifespan)


def require_operator(x_api_key: str | None = Header(default=None)) -> str:
    """Approving a recommendation is a privileged action, so it needs a key."""
    expected = os.getenv("APPROVAL_API_KEY")
    if not expected:
        raise HTTPException(status_code=503, detail="approval is not configured")
    if not x_api_key or not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=401, detail="invalid approval key")
    return os.getenv("APPROVAL_ACTOR", "operator")


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "opspilot-ai",
        "version": app.version,
        "environment": APP_ENV,
    }


@app.post("/incidents", response_model=IncidentRead, status_code=201)
def create_incident(payload: IncidentCreate, db: Session = Depends(get_db)) -> Incident:
    incident = Incident(
        title=payload.title,
        description=payload.description,
        severity=payload.severity.value,
        service=payload.service,
        logs=payload.logs,
    )
    db.add(incident)
    db.commit()
    return incident


@app.get("/incidents", response_model=list[IncidentSummary])
def list_incidents(
    status: IncidentStatus | None = None,
    severity: Severity | None = None,
    service: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[Incident]:
    query = select(Incident).order_by(Incident.created_at.desc()).limit(limit).offset(offset)
    if status is not None:
        query = query.where(Incident.status == status.value)
    if severity is not None:
        query = query.where(Incident.severity == severity.value)
    if service is not None:
        query = query.where(Incident.service == service)
    return list(db.scalars(query))


@app.get("/incidents/{incident_id}", response_model=IncidentRead)
def get_incident(incident_id: str, db: Session = Depends(get_db)) -> Incident:
    return _incident_or_404(db, incident_id)


@app.post("/incidents/{incident_id}/investigate", response_model=IncidentRead, status_code=202)
def start_investigation(
    incident_id: str,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
) -> Incident:
    incident = _incident_or_404(db, incident_id)
    if incident.status not in (IncidentStatus.CREATED.value, IncidentStatus.FAILED.value):
        raise HTTPException(status_code=409, detail=f"cannot investigate an incident that is {incident.status}")

    mark_started(incident)
    db.commit()
    background.add_task(run_investigation, incident_id)
    return incident


@app.get("/incidents/{incident_id}/investigation", response_model=InvestigationRead)
def get_investigation(incident_id: str, db: Session = Depends(get_db)) -> Incident:
    return _incident_or_404(db, incident_id)


@app.post("/incidents/{incident_id}/approval", response_model=InvestigationRead)
def decide_approval(
    incident_id: str,
    decision: ApprovalDecision,
    actor: str = Depends(require_operator),
) -> Incident:
    try:
        return submit_decision(incident_id, decision.approved, actor, decision.comment)
    except LookupError:
        raise HTTPException(status_code=404, detail="Incident not found")
    except NotResumableError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


def _incident_or_404(db: Session, incident_id: str) -> Incident:
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident
