import pytest
from fastapi.testclient import TestClient

LOGS = (
    "2026-10-19T10:02:11Z ERROR pool exhausted: connection timeout after 5000ms\n"
    "2026-10-19T10:02:12Z WARN retrying inventory lookup\n"
)


@pytest.fixture(autouse=True)
def no_runbooks(monkeypatch):
    """Keep API tests off the vector index; retrieval has its own tests."""
    monkeypatch.setattr("app.agent.retrieve_runbooks", lambda query, limit=3: [])


@pytest.fixture
def approval_key(monkeypatch):
    monkeypatch.setenv("APPROVAL_API_KEY", "test-approval-key")
    monkeypatch.setenv("APPROVAL_ACTOR", "operator")
    return "test-approval-key"


def start(client: TestClient, incident_id: str) -> dict:
    response = client.post(f"/incidents/{incident_id}/investigate")
    assert response.status_code == 202, response.text
    return response.json()


def test_investigation_runs_and_waits_for_approval(client, create_incident):
    incident = create_incident(logs=LOGS)

    started = start(client, incident["id"])

    assert started["status"] == "investigating"

    result = client.get(f"/incidents/{incident['id']}/investigation").json()
    assert result["status"] == "awaiting_approval"
    assert result["diagnosis"].startswith("Connection pool saturation")
    assert result["category"] == "database_connection"
    assert result["approval_status"] == "pending"
    assert result["evidence"]
    assert result["remediation"][0]["requires_approval"] is True
    assert result["investigation_started_at"] is not None


def test_investigation_is_visible_on_the_incident(client, create_incident):
    incident = create_incident(logs=LOGS)
    start(client, incident["id"])

    fetched = client.get(f"/incidents/{incident['id']}").json()

    assert fetched["status"] == "awaiting_approval"
    assert fetched["evidence"]
    assert fetched["remediation"]


def test_unknown_incident_cannot_be_investigated(client):
    assert client.post("/incidents/ffffffffffffffffffffffffffffffff/investigate").status_code == 404
    assert client.get("/incidents/ffffffffffffffffffffffffffffffff/investigation").status_code == 404


def test_incident_cannot_be_investigated_twice(client, create_incident):
    incident = create_incident(logs=LOGS)
    start(client, incident["id"])

    assert client.post(f"/incidents/{incident['id']}/investigate").status_code == 409


def test_approval_requires_a_key(client, create_incident, approval_key):
    incident = create_incident(logs=LOGS)
    start(client, incident["id"])

    missing = client.post(f"/incidents/{incident['id']}/approval", json={"approved": True})
    wrong = client.post(
        f"/incidents/{incident['id']}/approval",
        json={"approved": True},
        headers={"X-API-Key": "not-the-key"},
    )

    assert missing.status_code == 401
    assert wrong.status_code == 401


def test_approval_is_unavailable_without_configuration(client, create_incident, monkeypatch):
    monkeypatch.delenv("APPROVAL_API_KEY", raising=False)
    incident = create_incident(logs=LOGS)
    start(client, incident["id"])

    response = client.post(
        f"/incidents/{incident['id']}/approval",
        json={"approved": True},
        headers={"X-API-Key": "anything"},
    )

    assert response.status_code == 503


def test_approval_completes_the_investigation(client, create_incident, approval_key):
    incident = create_incident(logs=LOGS)
    start(client, incident["id"])

    response = client.post(
        f"/incidents/{incident['id']}/approval",
        json={"approved": True, "comment": "roll it back"},
        headers={"X-API-Key": approval_key},
    )

    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "completed"
    assert result["approval_status"] == "approved"
    assert result["approved_by"] == "operator"
    assert result["approved_at"] is not None
    assert result["remediation"][0]["approval"] == "approved"

    stored = client.get(f"/incidents/{incident['id']}").json()
    assert stored["status"] == "completed"
    assert stored["approval_status"] == "approved"


def test_rejection_prevents_the_actions(client, create_incident, approval_key):
    incident = create_incident(logs=LOGS)
    start(client, incident["id"])

    response = client.post(
        f"/incidents/{incident['id']}/approval",
        json={"approved": False, "comment": "not during peak"},
        headers={"X-API-Key": approval_key},
    )

    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "rejected"
    assert result["approval_status"] == "rejected"
    assert result["remediation"][0]["approval"] == "rejected"

    # A rejected incident cannot be approved afterwards.
    again = client.post(
        f"/incidents/{incident['id']}/approval",
        json={"approved": True},
        headers={"X-API-Key": approval_key},
    )
    assert again.status_code == 409


def test_approval_is_rejected_when_nothing_is_pending(client, create_incident, approval_key):
    incident = create_incident(logs=LOGS)

    response = client.post(
        f"/incidents/{incident['id']}/approval",
        json={"approved": True},
        headers={"X-API-Key": approval_key},
    )

    assert response.status_code == 409
    assert "not awaiting approval" in response.json()["detail"]


def test_approval_of_unknown_incident_returns_404(client, approval_key):
    response = client.post(
        "/incidents/ffffffffffffffffffffffffffffffff/approval",
        json={"approved": True},
        headers={"X-API-Key": approval_key},
    )

    assert response.status_code == 404


def test_background_model_failure_marks_the_incident_failed(client, create_incident, monkeypatch):
    incident = create_incident(logs=LOGS)

    def broken_model():
        raise RuntimeError("model provider is down")

    monkeypatch.setattr("app.llm.get_llm", broken_model)
    start(client, incident["id"])

    result = client.get(f"/incidents/{incident['id']}/investigation").json()
    assert result["status"] == "failed"
    assert "model provider is down" in result["errors"][0]
    assert result["diagnosis"] is None
