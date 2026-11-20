import json
import os
import re
from typing import Any, TypeVar

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)

FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


class LLMError(RuntimeError):
    """The model was unreachable, or its answer was unusable."""


def get_llm() -> BaseChatModel | None:
    """Returns the configured chat model, or None for offline mock mode."""
    provider = os.getenv("LLM_PROVIDER", "openai").lower()

    if provider == "mock":
        return None
    if provider != "openai":
        raise LLMError(f"unsupported LLM_PROVIDER {provider!r}")

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise LLMError("OPENAI_API_KEY is not set (use LLM_PROVIDER=mock for offline runs)")

    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
        api_key=api_key,
        # Any OpenAI-compatible endpoint can be used by pointing this at it.
        base_url=os.getenv("LLM_BASE_URL") or None,
        timeout=float(os.getenv("LLM_TIMEOUT_SECONDS", "30")),
        max_retries=int(os.getenv("LLM_MAX_RETRIES", "2")),
    )


def ask(node: str, instructions: str, payload: str, schema: type[T]) -> T:
    """Runs one workflow node's prompt and returns validated structured output."""
    model = get_llm()

    if model is None:
        raw: Any = MOCK_RESPONSES[node]
    else:
        try:
            raw = model.invoke([SystemMessage(content=instructions), HumanMessage(content=payload)]).content
        except Exception as exc:
            raise LLMError(f"{node} call failed: {exc}") from exc

    return parse(raw, node, schema)


def parse(raw: Any, node: str, schema: type[T]) -> T:
    if not isinstance(raw, str):
        raise LLMError(f"{node}: expected text, got {type(raw).__name__}")

    text = FENCE.sub("", raw.strip())
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMError(f"{node}: response was not JSON ({exc})") from exc
    if not isinstance(data, dict):
        raise LLMError(f"{node}: response must be a JSON object")

    try:
        return schema.model_validate(data)
    except ValidationError as exc:
        raise LLMError(f"{node}: response did not match {schema.__name__} ({exc.error_count()} problem(s))") from exc


# Offline mode only (LLM_PROVIDER=mock). These replies are fixtures, not a model.
MOCK_RESPONSES = {
    "classify": json.dumps(
        {
            "category": "database_connection",
            "symptoms": ["connection timeouts", "error rate spike"],
            "summary": "Checkout requests fail with connection pool timeouts",
        }
    ),
    "analyze": json.dumps(
        {
            "observed": [
                "ERROR lines report pool exhaustion and connection timeouts",
                "checkout-api is degraded with 49 of 50 database connections in use",
                "checkout-api 2.14.3 lowered the database pool size from 100 to 50",
            ],
            "hypotheses": [
                {
                    "cause": "Connection pool saturation after the 2.14.3 pool-size change",
                    "supporting_evidence": [
                        "49 of 50 connections in use",
                        "errors begin with pool exhaustion",
                    ],
                    "confidence": "medium",
                }
            ],
            "evidence_gaps": ["no connection wait-time metrics"],
        }
    ),
    "validate": json.dumps(
        {
            "supported": True,
            "confidence": "medium",
            "root_cause": "Connection pool saturation after 2.14.3 reduced the pool size from 100 to 50",
            "issues": ["no connection wait-time metrics to confirm saturation timing"],
            "needs_more_evidence": False,
        }
    ),
    "recommend": json.dumps(
        {
            "actions": [
                {
                    "action": "Roll back checkout-api to 2.14.2",
                    "why": "restores the pool size that the 2.14.3 config change lowered",
                    "risk": "medium",
                    "requires_approval": True,
                },
                {
                    "action": "Review pool sizing against peak connection demand before re-applying",
                    "why": "prevents the same change from breaking checkout again",
                    "risk": "low",
                    "requires_approval": False,
                },
            ],
            "escalate": False,
            "summary": "Roll back the pool-size change, then re-check sizing",
        }
    ),
}
