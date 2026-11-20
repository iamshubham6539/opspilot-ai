from app.agent import InvestigationState, investigate, resume_investigation
from app.database import SessionLocal
from app.models import Incident, IncidentStatus, utcnow

FINISHED = {
    IncidentStatus.COMPLETED.value,
    IncidentStatus.ESCALATED.value,
    IncidentStatus.REJECTED.value,
    IncidentStatus.FAILED.value,
}


class NotResumableError(RuntimeError):
    pass


def mark_started(incident: Incident) -> None:
    """Clears the previous result so a retry cannot mix old and new evidence."""
    incident.status = IncidentStatus.INVESTIGATING.value
    incident.investigation_started_at = utcnow()
    incident.completed_at = None
    incident.approval_status = "none"
    incident.approved_by = None
    incident.approved_at = None
    incident.category = None
    incident.diagnosis = None
    incident.confidence = None
    incident.summary = None
    incident.evidence = None
    incident.runbooks = None
    incident.remediation = None
    incident.errors = None


def run_investigation(incident_id: str) -> None:
    """Runs in the background: it owns its session and never raises."""
    with SessionLocal() as session:
        incident = session.get(Incident, incident_id)
        if incident is None:
            return
        try:
            state = investigate(_payload(incident))
        except Exception as exc:
            _mark_failed(session, incident, exc)
            return
        _store(session, incident, state)


def submit_decision(incident_id: str, approved: bool, actor: str, comment: str | None) -> Incident:
    with SessionLocal() as session:
        incident = session.get(Incident, incident_id)
        if incident is None:
            raise LookupError("Incident not found")
        if incident.status != IncidentStatus.AWAITING_APPROVAL.value:
            raise NotResumableError(f"incident is '{incident.status}', not awaiting approval")

        # Claim the decision before resuming so a double submit cannot run it twice.
        incident.status = IncidentStatus.INVESTIGATING.value
        session.commit()

        try:
            state = resume_investigation(
                incident_id,
                {"approved": approved, "by": actor, "comment": comment},
                _payload(incident),
            )
        except Exception as exc:
            _mark_failed(session, incident, exc)
            raise NotResumableError(f"could not resume the investigation: {exc}") from exc

        _store(session, incident, state)
        return incident


def _payload(incident: Incident) -> dict:
    return {
        "id": incident.id,
        "title": incident.title,
        "description": incident.description or "",
        "service": incident.service,
        "severity": incident.severity,
        "logs": incident.logs or "",
    }


def _store(session, incident: Incident, state: InvestigationState) -> None:
    incident.status = state["status"]
    incident.category = state["category"]
    incident.diagnosis = state["diagnosis"]
    incident.confidence = state["confidence"]
    incident.summary = state["summary"] or None
    incident.evidence = state["evidence"]
    incident.runbooks = state["runbooks"]
    incident.remediation = state["remediation"]
    incident.errors = state["errors"] or None

    if state["status"] == IncidentStatus.AWAITING_APPROVAL.value:
        incident.approval_status = "pending"
    if state["approval"]:
        incident.approval_status = "approved" if state["approval"]["approved"] else "rejected"
        incident.approved_by = state["approval"]["by"]
        incident.approved_at = utcnow()
    if state["status"] in FINISHED:
        incident.completed_at = incident.completed_at or utcnow()

    session.commit()


def _mark_failed(session, incident: Incident, exc: Exception) -> None:
    incident.status = IncidentStatus.FAILED.value
    incident.errors = (incident.errors or []) + [str(exc)]
    incident.completed_at = utcnow()
    session.commit()
