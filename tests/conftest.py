import os
import tempfile

# Tests default to SQLite and offline embeddings. Point TEST_DATABASE_URL at a Postgres
# database with pgvector to run the retrieval tests against the real index.
database_url = os.getenv("TEST_DATABASE_URL")
if not database_url:
    db_file = os.path.join(tempfile.mkdtemp(prefix="opspilot-tests-"), "opspilot.db")
    database_url = f"sqlite+pysqlite:///{db_file}"
os.environ["DATABASE_URL"] = database_url
os.environ.setdefault("EMBEDDING_PROVIDER", "mock")
os.environ.setdefault("LLM_PROVIDER", "mock")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import delete  # noqa: E402

from app.database import engine, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Incident  # noqa: E402


@pytest.fixture(autouse=True)
def empty_database():
    init_db()
    with engine.begin() as conn:
        conn.execute(delete(Incident))


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def sample_incident() -> dict:
    return {
        "title": "Checkout API 500s",
        "description": "Checkout requests fail after the deploy.",
        "severity": "high",
        "service": "checkout-api",
        "logs": "2026-10-19T10:02:11Z ERROR pool exhausted: connection timeout after 5000ms",
    }


@pytest.fixture
def create_incident(client: TestClient):
    def create(**overrides) -> dict:
        payload = {"title": "Checkout API 500s", "severity": "high", "service": "checkout-api"}
        payload.update(overrides)
        response = client.post("/incidents", json=payload)
        assert response.status_code == 201, response.text
        return response.json()

    return create
