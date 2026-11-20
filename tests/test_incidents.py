from fastapi.testclient import TestClient


def test_create_incident_stores_submitted_data(client: TestClient):
    response = client.post(
        "/incidents",
        json={
            "title": "Checkout API 500s",
            "description": "Checkout requests fail after the deploy.",
            "severity": "high",
            "service": "checkout-api",
            "logs": "ERROR pool exhausted",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert len(body["id"]) == 32
    assert body["severity"] == "high"
    assert body["status"] == "created"
    assert body["logs"] == "ERROR pool exhausted"
    # Nothing is diagnosed yet.
    assert body["diagnosis"] is None
    assert body["evidence"] is None
    assert body["remediation"] is None


def test_create_incident_rejects_bad_input(client: TestClient):
    bad_severity = client.post(
        "/incidents",
        json={"title": "Disk full", "severity": "urgent", "service": "billing-api"},
    )
    short_title = client.post(
        "/incidents",
        json={"title": "x", "severity": "low", "service": "billing-api"},
    )
    huge_logs = client.post(
        "/incidents",
        json={
            "title": "Disk full",
            "severity": "low",
            "service": "billing-api",
            "logs": "x" * 200_001,
        },
    )

    assert bad_severity.status_code == 422
    assert short_title.status_code == 422
    assert huge_logs.status_code == 422


def test_get_incident_returns_it(client: TestClient, create_incident):
    created = create_incident(service="payments-api")

    response = client.get(f"/incidents/{created['id']}")

    assert response.status_code == 200
    assert response.json()["service"] == "payments-api"


def test_get_unknown_incident_returns_404(client: TestClient):
    response = client.get("/incidents/ffffffffffffffffffffffffffffffff")

    assert response.status_code == 404
    assert response.json()["detail"] == "Incident not found"


def test_list_incidents_filters_and_paginates(client: TestClient, create_incident):
    create_incident(service="checkout-api", severity="high")
    create_incident(service="checkout-api", severity="low", title="Slow checkout")
    create_incident(service="search-api", severity="critical")

    all_incidents = client.get("/incidents").json()
    checkout_incidents = client.get("/incidents", params={"service": "checkout-api"}).json()
    critical_incidents = client.get("/incidents", params={"severity": "critical"}).json()
    one_incident = client.get("/incidents", params={"limit": 1}).json()

    assert len(all_incidents) == 3
    assert len(checkout_incidents) == 2
    assert len(critical_incidents) == 1
    assert len(one_incident) == 1
    # The list view stays small: no log blobs.
    assert "logs" not in all_incidents[0]


def test_list_incidents_rejects_bad_pagination(client: TestClient):
    assert client.get("/incidents", params={"limit": 0}).status_code == 422
    assert client.get("/incidents", params={"offset": -1}).status_code == 422
