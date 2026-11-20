import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from app.agent import investigate
from app.tracing import TracingError, tracing_enabled, tracing_run_config

INCIDENT = {
    "id": "c" * 32,
    "title": "Checkout API 500s",
    "description": "Errors after deploy",
    "service": "checkout-api",
    "severity": "high",
    "logs": "2026-10-19T10:02:11Z ERROR pool exhausted: connection timeout after 5000ms",
    "reference_time": "2026-10-19T12:00:00+00:00",
}


def test_tracing_is_off_by_default(monkeypatch):
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)

    assert tracing_enabled() is False
    assert tracing_run_config(INCIDENT) == {}


def test_enabled_tracing_names_the_run_without_incident_text(monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "test-key")

    config = tracing_run_config(INCIDENT)

    assert config["run_name"] == "investigate checkout-api"
    assert config["tags"] == ["opspilot", "severity:high"]
    assert config["metadata"] == {"incident_id": INCIDENT["id"], "service": "checkout-api"}
    assert "pool exhausted" not in json.dumps(config)


def test_enabling_tracing_without_a_key_is_an_error(monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)

    with pytest.raises(TracingError, match="LANGSMITH_API_KEY"):
        tracing_run_config(INCIDENT)


def test_investigate_passes_the_trace_config_to_the_graph(monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "test-key")

    class FakeGraph:
        config = None

        def invoke(self, state, config):
            self.config = config
            return {**state, "status": "completed"}

    fake = FakeGraph()
    monkeypatch.setattr("app.agent.get_graph", lambda: fake)

    investigate(INCIDENT)

    assert fake.config["run_name"] == "investigate checkout-api"
    assert fake.config["metadata"]["incident_id"] == INCIDENT["id"]
    assert fake.config["configurable"]["thread_id"] == INCIDENT["id"]


def test_traces_are_sent_to_the_configured_endpoint(tmp_path: Path):
    """A collector stands in for LangSmith so this proves real emission, not just config."""
    bodies: list[str] = []

    class Collector(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("content-length", 0))
            bodies.append(self.rfile.read(length).decode(errors="ignore"))
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Collector)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        env = {
            **os.environ,
            "LANGSMITH_TRACING": "true",
            "LANGSMITH_API_KEY": "test-key",
            "LANGSMITH_ENDPOINT": f"http://127.0.0.1:{server.server_port}",
            "LANGSMITH_PROJECT": "opspilot-test",
            "LLM_PROVIDER": "mock",
            "EMBEDDING_PROVIDER": "mock",
        }
        code = (
            "from app.agent import investigate\n"
            f"result = investigate({INCIDENT!r})\n"
            "assert result['status'] == 'awaiting_approval', result['status']\n"
        )
        completed = subprocess.run(
            [sys.executable, "-c", code],
            cwd=Path(__file__).parent.parent,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert completed.returncode == 0, completed.stderr

        deadline = time.time() + 5
        payload = ""
        while time.time() < deadline:
            payload = "".join(bodies)
            if "investigate checkout-api" in payload and INCIDENT["id"] in payload:
                break
            time.sleep(0.1)
    finally:
        server.shutdown()

    assert "investigate checkout-api" in payload
    assert INCIDENT["id"] in payload
    assert "test-key" not in payload
