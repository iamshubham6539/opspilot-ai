"""Evaluation harness over a small fixed incident set.

Run it against the configured provider:

    DATABASE_URL=... LLM_PROVIDER=mock EMBEDDING_PROVIDER=mock python eval.py

Numbers are counted from the run, never estimated. Metrics that depend on the model
(classification, diagnosis keywords) only mean something with a real provider; the
script prints the provider it used so results are never read out of context.
"""

import json
import os
import uuid
from pathlib import Path

from app.agent import investigate
from app.retrieval import ingest_runbooks

DATASET = Path(__file__).parent / "tests" / "eval_cases.json"
TOOLS = ["search_logs", "check_service_health", "get_recent_deployments"]


def main() -> None:
    cases = json.loads(DATASET.read_text())
    print(f"model provider: {os.getenv('LLM_PROVIDER', 'openai')}")
    try:
        print(f"runbook index: {ingest_runbooks()}")
    except Exception as exc:
        print(f"runbook index unavailable: {exc}")

    rows = []
    for case in cases:
        result = investigate({**case["incident"], "id": uuid.uuid4().hex})
        rows.append(_score(case, result))

    _print_rows(rows)
    _print_summary(rows)


def _score(case: dict, result: dict) -> dict:
    status = result["status"]
    sources = [chunk["source"] for chunk in result["runbooks"]]
    expected_runbook = case["expected_runbook"]
    if expected_runbook:
        retrieval = sources[:1] == [expected_runbook]
    else:
        retrieval = sources == []

    escalated = status == "escalated"
    if case["expect_escalated"]:
        completion = escalated
        gating = not result["pending_actions"]
    else:
        completion = status in {"awaiting_approval", "completed", "rejected"}
        gating = (status == "awaiting_approval") == case["expect_sensitive"]

    evidence_sources = {item["source"] for item in result["evidence"]}
    evidence_ok = evidence_sources == set(TOOLS) and not any(
        item.get("error") for item in result["evidence"]
    )

    diagnosis = result["diagnosis"] or ""
    keywords_ok = (
        all(word in diagnosis.lower() for word in case["diagnosis_keywords"])
        if not case["expect_escalated"]
        else escalated
    )

    return {
        "name": case["name"],
        "status": status,
        "category": result["category"],
        "classification": result["category"] == case["expected_category"],
        "retrieval": retrieval,
        "completion": completion,
        "gating": gating,
        "evidence": evidence_ok,
        "keywords": keywords_ok,
        "runbook": sources[0] if sources else "-",
        "diagnosis": diagnosis[:60],
    }


def _print_rows(rows: list[dict]) -> None:
    print(f"\n{'case':30} {'status':18} {'category':20} {'runbook':24} diagnosis")
    for row in rows:
        print(
            f"{row['name']:30} {row['status']:18} {str(row['category']):20} "
            f"{row['runbook']:24} {row['diagnosis']}"
        )


def _print_summary(rows: list[dict]) -> None:
    print("\nmetric                              score")
    for key, label in [
        ("classification", "classification accuracy (model)"),
        ("retrieval", "runbook hit@1"),
        ("completion", "task completion"),
        ("gating", "approval gating"),
        ("evidence", "evidence coverage"),
        ("keywords", "diagnosis keywords (model)"),
    ]:
        passed = sum(row[key] for row in rows)
        print(f"{label:35} {passed}/{len(rows)} ({passed / len(rows):.0%})")


if __name__ == "__main__":
    main()
