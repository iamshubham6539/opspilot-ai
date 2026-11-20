from fastapi.testclient import TestClient

from app.main import app


def test_health_reports_ok(client: TestClient):
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "opspilot-ai"
    assert body["version"] == app.version


def test_unknown_route_returns_404(client: TestClient):
    assert client.get("/does-not-exist").status_code == 404
