"""Backend state for the OpsPilot operator console.

All FastAPI calls happen here, server side, so the browser never talks to the
API directly and no CORS setup is needed. Point OPSPILOT_API_URL at the API.
"""

import asyncio
import json
import os

import httpx
import reflex as rx
from dotenv import load_dotenv

# Reflex does not export the app's .env to the state process, so load it here.
load_dotenv()

API_URL = os.getenv("OPSPILOT_API_URL", "http://127.0.0.1:8000").rstrip("/")

STATUS_OPTIONS = [
    "all",
    "created",
    "investigating",
    "awaiting_approval",
    "completed",
    "rejected",
    "escalated",
    "failed",
]
SEVERITY_OPTIONS = ["all", "low", "medium", "high", "critical"]
SEVERITY_FORM_OPTIONS = ["low", "medium", "high", "critical"]

POLL_INTERVAL_SECONDS = 1.5
POLL_ATTEMPTS = 40

EMPTY_DETAIL: dict = {}


class OpsPilotState(rx.State):
    """Everything the console renders is derived from these fields."""

    incidents: list[dict] = []
    detail: dict = {}
    selected_id: str = ""

    status_filter: str = ""
    severity_filter: str = ""

    # New-incident form.
    new_title: str = ""
    new_service: str = ""
    new_severity: str = "high"
    new_description: str = ""
    new_logs: str = ""

    # Approval panel.
    approval_key: str = os.getenv("OPSPILOT_APPROVAL_KEY", "")
    comment: str = ""

    error: str = ""
    flash: str = ""
    busy: bool = False

    # ---------------------------------------------------------------- computed

    @rx.var
    def has_detail(self) -> bool:
        return bool(self.detail)

    @rx.var
    def awaiting_approval(self) -> bool:
        return self.detail.get("status") == "awaiting_approval"

    @rx.var
    def running(self) -> bool:
        return self.detail.get("status") == "investigating"

    @rx.var
    def can_investigate(self) -> bool:
        # Mirrors the API: only a fresh or previously failed incident can run.
        return self.detail.get("status") in ("created", "failed")

    @rx.var
    def incident_count(self) -> int:
        return len(self.incidents)

    @rx.var
    def status_value(self) -> str:
        return self.status_filter or "all"

    @rx.var
    def severity_value(self) -> str:
        return self.severity_filter or "all"

    @rx.var
    def evidence_items(self) -> list[dict]:
        return self.detail.get("evidence") or []

    @rx.var
    def runbook_items(self) -> list[dict]:
        return self.detail.get("runbooks") or []

    @rx.var
    def remediation_items(self) -> list[dict]:
        return self.detail.get("remediation") or []

    @rx.var
    def error_messages(self) -> list[str]:
        return self.detail.get("errors") or []

    # ---------------------------------------------------------------- helpers

    def _fail(self, response: httpx.Response, action: str) -> None:
        self.error = f"{action} failed ({response.status_code}): {response.text[:400]}"
        self.flash = ""

    def _normalise(self, data: dict) -> dict:
        """Stable shapes so the UI can index every key without null checks."""
        for key in ("evidence", "runbooks", "remediation", "errors"):
            if not isinstance(data.get(key), list):
                data[key] = []
        for key in (
            "description",
            "logs",
            "category",
            "diagnosis",
            "confidence",
            "summary",
            "investigation_started_at",
            "completed_at",
            "approved_by",
        ):
            if data.get(key) is None:
                data[key] = ""
        for item in data["evidence"]:
            item["pretty"] = json.dumps(item.get("data"), indent=2, default=str)
        for item in data["remediation"]:
            item.setdefault("approval", "")
        # Backend tracebacks can be huge; keep the callout readable.
        data["errors"] = [
            message if len(message) <= 240 else message[:237] + "..."
            for message in data["errors"]
        ]
        return data

    async def _load_list(self, client: httpx.AsyncClient) -> None:
        params = {}
        if self.status_filter:
            params["status"] = self.status_filter
        if self.severity_filter:
            params["severity"] = self.severity_filter
        response = await client.get(f"{API_URL}/incidents", params=params)
        if response.status_code != 200:
            self._fail(response, "Loading incidents")
            return
        self.incidents = response.json()

    async def _load_detail(self, client: httpx.AsyncClient) -> None:
        if not self.selected_id:
            self.detail = EMPTY_DETAIL
            return
        response = await client.get(f"{API_URL}/incidents/{self.selected_id}")
        if response.status_code != 200:
            self._fail(response, "Loading incident")
            return
        self.detail = self._normalise(response.json())

    # ----------------------------------------------------------------- events

    @rx.event
    async def on_load(self):
        await self.refresh()

    @rx.event
    async def refresh(self):
        self.error = ""
        async with httpx.AsyncClient(timeout=20) as client:
            await self._load_list(client)
            await self._load_detail(client)

    @rx.event
    def set_status_filter(self, value: str):
        self.status_filter = "" if value == "all" else value
        return OpsPilotState.refresh

    @rx.event
    def set_severity_filter(self, value: str):
        self.severity_filter = "" if value == "all" else value
        return OpsPilotState.refresh

    @rx.event
    def set_new_title(self, value: str):
        self.new_title = value

    @rx.event
    def set_new_service(self, value: str):
        self.new_service = value

    @rx.event
    def set_new_severity(self, value: str):
        self.new_severity = value

    @rx.event
    def set_new_description(self, value: str):
        self.new_description = value

    @rx.event
    def set_new_logs(self, value: str):
        self.new_logs = value

    @rx.event
    def set_approval_key(self, value: str):
        self.approval_key = value

    @rx.event
    def set_comment(self, value: str):
        self.comment = value

    @rx.event
    async def select(self, incident_id: str):
        self.selected_id = incident_id
        self.comment = ""
        self.flash = ""
        self.error = ""
        async with httpx.AsyncClient(timeout=20) as client:
            await self._load_detail(client)

    @rx.event
    async def create(self):
        self.error = ""
        self.flash = ""
        if not self.new_title.strip() or not self.new_service.strip():
            self.error = "Title and service are required."
            return

        payload = {
            "title": self.new_title.strip(),
            "severity": self.new_severity,
            "service": self.new_service.strip(),
            "description": self.new_description.strip() or None,
            "logs": self.new_logs or None,
        }

        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(f"{API_URL}/incidents", json=payload)
            if response.status_code != 201:
                self._fail(response, "Creating the incident")
                return

            incident = response.json()
            self.selected_id = incident["id"]
            self.new_title = ""
            self.new_service = ""
            self.new_description = ""
            self.new_logs = ""
            await self._load_list(client)
            await self._load_detail(client)

        self.flash = f"Incident {self.selected_id[:8]} created."

    @rx.event
    async def investigate(self):
        if not self.selected_id:
            return

        self.busy = True
        self.error = ""
        self.flash = ""

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(f"{API_URL}/incidents/{self.selected_id}/investigate")
            if response.status_code != 202:
                self._fail(response, "Starting the investigation")
                self.busy = False
                return

            await self._load_list(client)
            await self._load_detail(client)

            # The API runs the graph in the background; poll until it settles.
            for _ in range(POLL_ATTEMPTS):
                if self.detail.get("status") not in ("investigating", "created"):
                    break
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
                await self._load_list(client)
                await self._load_detail(client)
                yield

            await self._load_list(client)
            await self._load_detail(client)

        self.busy = False

    @rx.event
    async def decide(self, approved: bool):
        self.error = ""
        self.flash = ""

        if not self.approval_key.strip():
            self.error = "An approval key is required (X-API-Key)."
            return

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{API_URL}/incidents/{self.selected_id}/approval",
                json={"approved": approved, "comment": self.comment.strip() or None},
                headers={"X-API-Key": self.approval_key.strip()},
            )
            if response.status_code != 200:
                self._fail(response, "Recording the decision")
                return

            self.comment = ""
            self.flash = "Approved." if approved else "Rejected."
            await self._load_list(client)
            await self._load_detail(client)
