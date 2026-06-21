"""
dashboard/app.py

Main Streamlit entry point for the AgentOps Supply Chain Control Tower.

This app supports:
- Normal workflow execution
- LangGraph interrupt-based Human-in-the-Loop approval
- Workflow resume after human review
"""

import sys
from pathlib import Path
from typing import Any, Dict, Optional

import streamlit as st


# ============================================================
# Project path setup
# ============================================================
# Streamlit runs dashboard/app.py directly, so we must add the
# project root to sys.path before importing dashboard modules.
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from dashboard.config import DEFAULT_USER_ROLE, LAYOUT, PAGE_ICON, PAGE_TITLE
from dashboard.styles import load_css
from dashboard.components.header import render_header
from dashboard.components.query_panel import render_query_panel, render_sidebar
from dashboard.components.summary_cards import render_summary_cards
from dashboard.components.final_response_panel import render_final_response_panel
from dashboard.components.tabs_panel import render_tabs_panel
from dashboard.components.workflow_timeline import render_workflow_timeline
from dashboard.services.workflow_service import (
    get_interrupt_payload,
    has_interrupt,
    resume_workflow,
    run_workflow,
)


# ============================================================
# Page configuration
# ============================================================

st.set_page_config(
    page_title=PAGE_TITLE,
    page_icon=PAGE_ICON,
    layout=LAYOUT,
)


# ============================================================
# HITL helper functions
# ============================================================

def _extract_interrupt_value(interrupt_payload: Any) -> Dict[str, Any]:
    """
    Extracts the JSON-serializable interrupt payload from LangGraph result.

    LangGraph interrupt payload shape may vary depending on version:
    - list of interrupt objects
    - list of dictionaries
    - dictionary
    - object with .value
    """

    if not interrupt_payload:
        return {}

    if isinstance(interrupt_payload, list) and interrupt_payload:
        first_item = interrupt_payload[0]

        if isinstance(first_item, dict):
            return first_item.get("value", first_item)

        if hasattr(first_item, "value"):
            return first_item.value

        return {}

    if isinstance(interrupt_payload, dict):
        return interrupt_payload.get("value", interrupt_payload)

    if hasattr(interrupt_payload, "value"):
        return interrupt_payload.value

    return {}


def _render_value_card(
    label: str,
    value: Any,
    accent_color: str = "#2563eb",
    small: bool = False,
) -> None:
    """
    Renders a custom responsive card.

    This avoids st.metric truncation for long text values such as:
    - Procurement Manager
    - Data Governance / Compliance Team
    - Revision Requested
    """

    value_class = "hitl-card-value-small" if small else "hitl-card-value"

    st.markdown(
        f"""
        <div class="hitl-card" style="border-top: 5px solid {accent_color};">
            <div class="hitl-card-label">{label}</div>
            <div class="{value_class}">{value if value is not None else "N/A"}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_chips(
    values: Any,
    empty_text: str,
    danger: bool = False,
) -> None:
    """
    Renders list values as professional chips instead of raw JSON.
    """

    if not values:
        st.markdown(
            f"""
            <div class="hitl-muted-box">{empty_text}</div>
            """,
            unsafe_allow_html=True,
        )
        return

    if not isinstance(values, list):
        values = [values]

    chip_class = "hitl-chip-danger" if danger else "hitl-chip"

    chips_html = "".join(
        f'<span class="{chip_class}">{str(item)}</span>'
        for item in values
    )

    st.markdown(chips_html, unsafe_allow_html=True)


def _render_human_review_panel(
    interrupt_payload: Any,
    run_id: str,
) -> Optional[Dict[str, Any]]:
    """
    Renders human approval panel and resumes the paused LangGraph workflow.

    Returns:
        resumed workflow result if review was submitted,
        otherwise None.
    """

    review_request = _extract_interrupt_value(interrupt_payload)

    if not review_request:
        st.error("Human review was required, but the interrupt payload could not be read.")
        return None

    st.divider()

    st.warning("Human approval is required before the workflow can continue.")

    st.markdown(
        """
        <div class="hitl-container">
            <h2 style="margin-bottom: 0.25rem; color: #111827;">
                Human-in-the-Loop Approval Review
            </h2>
            <div style="color: #6b7280; font-size: 0.95rem; margin-bottom: 1rem;">
                Review the escalated workflow decision and submit a human approval outcome.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # --------------------------------------------------------
    # Top review cards
    # --------------------------------------------------------
    col1, col2, col3 = st.columns([1.4, 1, 1])

    with col1:
        _render_value_card(
            label="Reviewer Role",
            value=review_request.get("reviewer_role", "N/A"),
            accent_color="#7c3aed",
            small=True,
        )

    with col2:
        risk_level = review_request.get("risk_level", "N/A")
        risk_color = "#dc2626" if risk_level in {"High", "Critical"} else "#f59e0b"

        _render_value_card(
            label="Risk Level",
            value=risk_level,
            accent_color=risk_color,
        )

    with col3:
        _render_value_card(
            label="Risk Score",
            value=review_request.get("risk_score", "N/A"),
            accent_color="#f59e0b",
        )

    # --------------------------------------------------------
    # Action under review
    # --------------------------------------------------------
    st.markdown(
        """
        <div class="hitl-section-title">Action Under Review</div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
        <div class="hitl-action-box">
            {review_request.get("action_under_review", "No action details available.")}
        </div>
        """,
        unsafe_allow_html=True,
    )

    # --------------------------------------------------------
    # Policy and governance context
    # --------------------------------------------------------
    st.markdown(
        """
        <div class="hitl-section-title">Policy and Governance Context</div>
        """,
        unsafe_allow_html=True,
    )

    context_col1, context_col2 = st.columns([1, 1.4])

    with context_col1:
        _render_value_card(
            label="Policy Decision",
            value=review_request.get("policy_decision", "N/A"),
            accent_color="#f59e0b",
            small=True,
        )

        st.markdown("<br>", unsafe_allow_html=True)

        _render_value_card(
            label="Approval ID",
            value=review_request.get("approval_id", "N/A"),
            accent_color="#2563eb",
            small=True,
        )

    with context_col2:
        st.markdown("**Triggered Policies**")
        _render_chips(
            values=review_request.get("triggered_policies", []),
            empty_text="No triggered policies found.",
            danger=False,
        )

        st.markdown("<br>", unsafe_allow_html=True)

        st.markdown("**Governance Violations**")
        _render_chips(
            values=review_request.get("governance_violations", []),
            empty_text="No governance violations found.",
            danger=True,
        )

    # --------------------------------------------------------
    # Human review form
    # --------------------------------------------------------
    st.markdown(
        """
        <div class="hitl-section-title">Reviewer Decision</div>
        """,
        unsafe_allow_html=True,
    )

    with st.form("human_review_form"):
        decision = st.radio(
            "Select decision",
            options=["Approve", "Reject", "Request Revision"],
            horizontal=True,
        )

        reviewed_by = st.text_input(
            "Reviewed By",
            value=review_request.get("reviewer_role") or "Human Reviewer",
        )

        comment = st.text_area(
            "Reviewer Comment",
            placeholder="Add approval reason, rejection reason, or revision instruction...",
            height=100,
        )

        submitted_review = st.form_submit_button(
            "Submit Human Review and Resume Workflow",
            type="primary",
        )

    if not submitted_review:
        st.info(
            "The workflow is currently paused at the Approval Agent. "
            "Submit a human review decision to resume Audit Logger and Final Response Agent."
        )
        return None

    human_review = {
        "decision": decision,
        "comment": comment,
        "reviewed_by": reviewed_by,
    }

    with st.spinner("Resuming workflow after human review..."):
        resumed_result = resume_workflow(
            run_id=run_id,
            human_review=human_review,
        )

    st.session_state["last_result"] = resumed_result
    st.session_state["pending_human_review"] = None
    st.session_state["pending_run_id"] = None
    st.session_state["human_review_submitted"] = human_review

    st.success("Human review submitted. Workflow resumed successfully.")

    return resumed_result


# ============================================================
# App initialization
# ============================================================

load_css()
render_header()


# ============================================================
# Sidebar and query input
# ============================================================

selected_sample, show_raw_debug = render_sidebar()

user_query, user_role, submitted = render_query_panel(
    selected_sample=selected_sample,
)


# ============================================================
# Execute workflow
# ============================================================

if submitted:
    if not user_query.strip():
        st.warning("Please enter a query before running the workflow.")
        st.stop()

    # Clear old HITL/session state for new run.
    st.session_state["pending_human_review"] = None
    st.session_state["pending_run_id"] = None
    st.session_state["human_review_submitted"] = None

    with st.spinner("Running AgentOps workflow..."):
        try:
            result = run_workflow(
                user_query=user_query.strip(),
                user_role=user_role.strip() or DEFAULT_USER_ROLE,
            )

            st.session_state["last_query"] = user_query
            st.session_state["last_result"] = result

            # ------------------------------------------------
            # Detect LangGraph interrupt from Approval Agent.
            # If interrupt exists, store it and rerun UI so the
            # human review panel can be displayed.
            # ------------------------------------------------
            if has_interrupt(result):
                run_id = result.get("run_id")

                st.session_state["pending_human_review"] = get_interrupt_payload(result)
                st.session_state["pending_run_id"] = run_id

                st.rerun()

        except Exception as exc:
            st.error(f"Workflow execution failed: {exc}")
            st.stop()


# ============================================================
# Read current session state
# ============================================================

result = st.session_state.get("last_result")
pending_human_review = st.session_state.get("pending_human_review")
pending_run_id = st.session_state.get("pending_run_id")


# ============================================================
# Empty state
# ============================================================

if not result:
    st.info("Enter a query and click **Run Workflow** to see the dashboard output.")
    st.stop()


# ============================================================
# Human-in-the-loop approval pause
# ============================================================

if pending_human_review and pending_run_id:
    resumed_result = _render_human_review_panel(
        interrupt_payload=pending_human_review,
        run_id=pending_run_id,
    )

    # If the human has not submitted review yet, stop here.
    # Do not render incomplete workflow output below.
    if resumed_result is None:
        st.stop()

    result = resumed_result


# ============================================================
# Safety check:
# If result still contains interrupt after resume attempt,
# keep showing HITL panel instead of rendering final dashboard.
# ============================================================

if isinstance(result, dict) and has_interrupt(result):
    run_id = result.get("run_id")

    st.session_state["pending_human_review"] = get_interrupt_payload(result)
    st.session_state["pending_run_id"] = run_id

    st.rerun()


# ============================================================
# Main dashboard rendering
# ============================================================

render_summary_cards(result)

render_workflow_timeline(result)

render_final_response_panel(result)

render_tabs_panel(
    result=result,
    show_raw_debug=show_raw_debug,
)