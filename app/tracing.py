"""LangSmith tracing is opt-in: traces contain incident text, so enabling it is a decision."""

import os


class TracingError(RuntimeError):
    pass


def tracing_enabled() -> bool:
    return os.getenv("LANGSMITH_TRACING", "").strip().lower() in {"1", "true", "yes", "on"}


def validate_tracing() -> None:
    if tracing_enabled() and not os.getenv("LANGSMITH_API_KEY"):
        raise TracingError("LANGSMITH_API_KEY is required when LANGSMITH_TRACING is enabled")


def tracing_run_config(incident: dict) -> dict:
    """Run name, tags, and metadata for one investigation; empty when tracing is off."""
    if not tracing_enabled():
        return {}
    validate_tracing()
    return {
        "run_name": f"investigate {incident['service']}",
        "tags": ["opspilot", f"severity:{incident.get('severity', 'unknown')}"],
        "metadata": {"incident_id": incident["id"], "service": incident["service"]},
    }
