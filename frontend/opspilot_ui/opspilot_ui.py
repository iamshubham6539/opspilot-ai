"""OpsPilot AI operator console, built with Reflex.

The browser only renders this component tree; every API call happens in
``opspilot_ui.state`` on the Reflex backend.
"""

import reflex as rx

from opspilot_ui.state import (
    SEVERITY_FORM_OPTIONS,
    SEVERITY_OPTIONS,
    STATUS_OPTIONS,
    OpsPilotState as S,
)


# --------------------------------------------------------------------- helpers


def card(*children, **props) -> rx.Component:
    style = {
        "padding": "16px",
        "border": "1px solid var(--gray-5)",
        "border_radius": "12px",
        "background": "var(--gray-2)",
        "width": "100%",
    }
    style.update(props)
    return rx.box(
        rx.vstack(*children, spacing="3", align="start", width="100%"),
        **style,
    )


def section(title: str, *children) -> rx.Component:
    return card(rx.heading(title, size="3"), *children)


def status_badge(status) -> rx.Component:
    return rx.badge(
        status,
        color_scheme=rx.match(
            status,
            ("completed", "green"),
            ("awaiting_approval", "amber"),
            ("rejected", "red"),
            ("failed", "red"),
            ("escalated", "orange"),
            ("investigating", "blue"),
            "gray",
        ),
        variant="soft",
        radius="full",
        size="1",
    )


def severity_badge(severity) -> rx.Component:
    return rx.badge(
        severity,
        color_scheme=rx.match(
            severity,
            ("critical", "red"),
            ("high", "red"),
            ("medium", "amber"),
            ("low", "gray"),
            "gray",
        ),
        variant="outline",
        radius="full",
        size="1",
    )


def meta_row(label: str, value) -> rx.Component:
    return rx.hstack(
        rx.text(label, size="1", color="gray", width="190px", flex_shrink="0"),
        rx.text(value, size="1"),
        width="100%",
        align="start",
    )


# ---------------------------------------------------------------------- header


def header() -> rx.Component:
    return rx.hstack(
        rx.vstack(
            rx.heading("OpsPilot AI", size="7"),
            rx.text("Incident investigation console", size="2", color="gray"),
            spacing="1",
            align="start",
        ),
        rx.spacer(),
        rx.hstack(
            rx.hstack(
                rx.text(S.incident_count.to_string(), weight="bold", size="2"),
                rx.text("incidents", size="2", color="gray"),
                spacing="1",
                align="center",
            ),
            rx.button("Refresh", on_click=S.refresh, variant="soft", size="2"),
            rx.color_mode.button(),
            spacing="3",
            align="center",
        ),
        width="100%",
        align="center",
    )


# ---------------------------------------------------------------- create panel


def create_form() -> rx.Component:
    return card(
        rx.heading("New incident", size="3"),
        rx.input(
            placeholder="Title, e.g. Checkout API 500s",
            value=S.new_title,
            on_change=S.set_new_title,
            width="100%",
        ),
        rx.hstack(
            rx.input(
                placeholder="Service, e.g. checkout-api",
                value=S.new_service,
                on_change=S.set_new_service,
                width="100%",
            ),
            rx.select(
                SEVERITY_FORM_OPTIONS,
                value=S.new_severity,
                on_change=S.set_new_severity,
                width="130px",
            ),
            spacing="2",
            width="100%",
        ),
        rx.text_area(
            placeholder="Description (optional)",
            value=S.new_description,
            on_change=S.set_new_description,
            width="100%",
            height="60px",
        ),
        rx.text_area(
            placeholder="Paste logs here. They are evidence, never executed.",
            value=S.new_logs,
            on_change=S.set_new_logs,
            width="100%",
            height="110px",
        ),
        rx.button("Create incident", on_click=S.create, width="100%"),
    )


# ---------------------------------------------------------------- incident list


def filters() -> rx.Component:
    return rx.grid(
        rx.select(
            STATUS_OPTIONS,
            value=S.status_value,
            on_change=S.set_status_filter,
            width="100%",
        ),
        rx.select(
            SEVERITY_OPTIONS,
            value=S.severity_value,
            on_change=S.set_severity_filter,
            width="100%",
        ),
        columns="1fr 120px",
        gap="8px",
        width="100%",
    )


def incident_row(item) -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.vstack(
                rx.text(item["title"], weight="bold", size="2"),
                rx.text(item["service"], size="1", color="gray"),
                spacing="0",
                align="start",
                width="100%",
            ),
            rx.vstack(
                status_badge(item["status"]),
                severity_badge(item["severity"]),
                spacing="1",
                align="end",
            ),
            width="100%",
            align="center",
            justify="between",
        ),
        on_click=S.select(item["id"]),
        padding="12px",
        border_radius="8px",
        border=rx.cond(
            S.selected_id == item["id"],
            "2px solid var(--accent-8)",
            "1px solid var(--gray-4)",
        ),
        background="var(--gray-1)",
        cursor="pointer",
        width="100%",
        _hover={"border_color": "var(--accent-8)"},
    )


def incident_list() -> rx.Component:
    return card(
        rx.hstack(
            rx.heading("Incidents", size="3"),
            rx.spacer(),
            rx.text(S.incident_count.to_string(), size="1", color="gray"),
            width="100%",
            align="center",
        ),
        filters(),
        rx.cond(
            S.incident_count == 0,
            rx.text("No incidents match these filters.", size="2", color="gray"),
            rx.vstack(
                rx.foreach(S.incidents, incident_row),
                spacing="2",
                width="100%",
            ),
        ),
    )


# -------------------------------------------------------------- detail sections


def diagnosis_section() -> rx.Component:
    return section(
        "Diagnosis",
        rx.cond(
            S.detail["diagnosis"] != "",
            rx.vstack(
                rx.hstack(
                    rx.badge(S.detail["category"], variant="surface", radius="full"),
                    rx.text("confidence: ", S.detail["confidence"], size="1", color="gray"),
                    spacing="2",
                    align="center",
                ),
                rx.text(S.detail["diagnosis"], size="3", weight="medium"),
                rx.cond(
                    S.detail["summary"] != "",
                    rx.text(S.detail["summary"], size="2", color="gray"),
                ),
                spacing="2",
                align="start",
                width="100%",
            ),
            rx.text("No diagnosis yet. Run the investigation.", size="2", color="gray"),
        ),
    )


def approval_section() -> rx.Component:
    return rx.cond(
        S.awaiting_approval,
        card(
            rx.heading("Approval gate", size="3"),
            rx.text(
                "A sensitive action is proposed. Nothing is executed until an operator decides.",
                size="2",
                color="gray",
            ),
            rx.input(
                placeholder="X-API-Key",
                type="password",
                value=S.approval_key,
                on_change=S.set_approval_key,
                width="100%",
            ),
            rx.input(
                placeholder="Comment (optional)",
                value=S.comment,
                on_change=S.set_comment,
                width="100%",
            ),
            rx.hstack(
                rx.button("Approve", on_click=S.decide(True), color_scheme="green"),
                rx.button(
                    "Reject", on_click=S.decide(False), color_scheme="red", variant="soft"
                ),
                spacing="2",
            ),
            border="1px solid var(--amber-7)",
            background="var(--amber-2)",
        ),
    )


def action_card(action) -> rx.Component:
    return rx.box(
        rx.flex(
            rx.text(action["action"], weight="bold", size="2", flex="1", min_width="220px"),
            rx.hstack(
                rx.badge(action["risk"], variant="soft", color_scheme="gray", size="1"),
                rx.cond(
                    action["requires_approval"],
                    rx.badge(
                        "needs approval", color_scheme="amber", variant="outline", size="1"
                    ),
                    rx.fragment(),
                ),
                rx.cond(
                    action["approval"] != "",
                    rx.badge(
                        action["approval"], color_scheme="green", variant="soft", size="1"
                    ),
                    rx.fragment(),
                ),
                spacing="2",
                flex_wrap="wrap",
                justify="end",
            ),
            width="100%",
            align="center",
            justify="between",
            gap="8px",
            flex_wrap="wrap",
        ),
        rx.text(action["why"], size="1", color="gray"),
        padding="12px",
        border="1px solid var(--gray-4)",
        border_radius="8px",
        width="100%",
    )


def remediation_section() -> rx.Component:
    return section(
        "Remediation",
        rx.cond(
            S.remediation_items.length() > 0,
            rx.vstack(rx.foreach(S.remediation_items, action_card), spacing="2", width="100%"),
            rx.text(
                "No remediation proposed. Approval is only requested when an action is sensitive.",
                size="2",
                color="gray",
            ),
        ),
    )


def runbook_card(runbook) -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.text(runbook["source"], weight="bold", size="2"),
            rx.spacer(),
            rx.text("distance ", runbook["distance"].to_string(), size="1", color="gray"),
            width="100%",
            align="center",
        ),
        rx.cond(
            runbook["heading"] != "",
            rx.text(runbook["heading"], size="1", color="gray"),
        ),
        rx.text(runbook["content"], size="1"),
        padding="12px",
        border="1px solid var(--gray-4)",
        border_radius="8px",
        width="100%",
    )


def runbooks_section() -> rx.Component:
    return section(
        "Runbooks retrieved",
        rx.cond(
            S.runbook_items.length() > 0,
            rx.vstack(rx.foreach(S.runbook_items, runbook_card), spacing="2", width="100%"),
            rx.text(
                "No runbook matched. Either the index is empty or the query was too far from it.",
                size="2",
                color="gray",
            ),
        ),
    )


def evidence_card(item) -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.badge(item["source"], variant="soft", color_scheme="blue", size="1"),
            rx.text(item["summary"], size="2"),
            width="100%",
            align="center",
            spacing="2",
        ),
        rx.code(
            item["pretty"],
            white_space="pre-wrap",
            font_size="11px",
            display="block",
            max_height="220px",
            overflow_y="auto",
            width="100%",
            padding="8px",
            border_radius="6px",
        ),
        padding="12px",
        border="1px solid var(--gray-4)",
        border_radius="8px",
        width="100%",
    )


def evidence_section() -> rx.Component:
    return section(
        "Evidence",
        rx.cond(
            S.evidence_items.length() > 0,
            rx.vstack(rx.foreach(S.evidence_items, evidence_card), spacing="2", width="100%"),
            rx.text("No evidence gathered yet.", size="2", color="gray"),
        ),
    )


def errors_section() -> rx.Component:
    return rx.cond(
        S.error_messages.length() > 0,
        section(
            "Pipeline warnings",
            rx.foreach(
                S.error_messages,
                lambda message: rx.callout(
                    message, color_scheme="amber", variant="surface", width="100%"
                ),
            ),
        ),
    )


def metadata_section() -> rx.Component:
    return section(
        "Timeline",
        meta_row("Incident id", S.detail["id"]),
        meta_row("Created", S.detail["created_at"]),
        rx.cond(
            S.detail["investigation_started_at"] != "",
            meta_row("Investigation started", S.detail["investigation_started_at"]),
        ),
        rx.cond(
            S.detail["completed_at"] != "",
            meta_row("Completed", S.detail["completed_at"]),
        ),
        meta_row("Approval", S.detail["approval_status"]),
        rx.cond(
            S.detail["approved_by"] != "",
            meta_row("Decided by", S.detail["approved_by"]),
        ),
    )


def detail_panel() -> rx.Component:
    return rx.cond(
        S.has_detail,
        rx.vstack(
            rx.hstack(
                rx.vstack(
                    rx.heading(S.detail["title"], size="5"),
                    rx.hstack(
                        rx.text(S.detail["service"], size="2", color="gray"),
                        status_badge(S.detail["status"]),
                        severity_badge(S.detail["severity"]),
                        spacing="2",
                        align="center",
                    ),
                    spacing="1",
                    align="start",
                ),
                rx.spacer(),
                rx.button(
                    rx.cond(
                        S.running,
                        "Investigating...",
                        rx.cond(
                            S.can_investigate,
                            "Run investigation",
                            rx.cond(S.awaiting_approval, "Awaiting approval", "Investigation finished"),
                        ),
                    ),
                    on_click=S.investigate,
                    disabled=S.busy | (~S.can_investigate),
                    loading=S.busy,
                    size="3",
                ),
                width="100%",
                align="center",
            ),
            rx.cond(
                S.detail["logs"] != "",
                section(
                    "Submitted logs",
                    rx.code(
                        S.detail["logs"],
                        white_space="pre-wrap",
                        font_size="11px",
                        display="block",
                        max_height="200px",
                        overflow_y="auto",
                        width="100%",
                    ),
                ),
            ),
            diagnosis_section(),
            approval_section(),
            remediation_section(),
            runbooks_section(),
            evidence_section(),
            errors_section(),
            metadata_section(),
            spacing="4",
            width="100%",
            align="start",
        ),
        card(
            rx.vstack(
                rx.text("No incident selected.", weight="bold", size="3"),
                rx.text(
                    "Pick one on the left, or create a new incident to run the agent.",
                    size="2",
                    color="gray",
                ),
                spacing="2",
                align="center",
                padding="24px",
            ),
        ),
    )


# ------------------------------------------------------------------------ page


def index() -> rx.Component:
    return rx.box(
        rx.vstack(
            header(),
            rx.cond(
                S.error != "",
                rx.callout(S.error, color_scheme="red", variant="surface", width="100%"),
            ),
            rx.cond(
                S.flash != "",
                rx.callout(S.flash, color_scheme="green", variant="surface", width="100%"),
            ),
            rx.flex(
                rx.vstack(
                    create_form(),
                    incident_list(),
                    spacing="4",
                    width="390px",
                    min_width="300px",
                    flex_shrink="0",
                ),
                rx.box(detail_panel(), flex="1 1 520px", min_width="320px"),
                direction="row",
                flex_wrap="wrap",
                gap="16px",
                width="100%",
                align="start",
            ),
            spacing="4",
            width="100%",
            style={
                "max_width": "1500px",
                "margin": "0 auto",
                "padding": "24px",
                "box_sizing": "border-box",
            },
        ),
        min_height="100vh",
        background="var(--gray-1)",
    )


app = rx.App()
app.add_page(
    index,
    route="/",
    title="OpsPilot AI",
    description="Incident investigation console",
    on_load=S.on_load,
)
