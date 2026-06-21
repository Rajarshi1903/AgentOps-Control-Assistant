"""
dashboard/components/workflow_timeline.py

Workflow execution timeline for the AgentOps dashboard.
"""

from typing import Any, Dict, List

import streamlit as st


STEP_LABELS = {
    "coordinator": "Coordinator",
    "forecasting": "Forecasting",
    "inventory": "Inventory",
    "procurement": "Procurement",
    "logistics": "Logistics",
    "policy_context": "Policy Context",
    "policy": "Policy",
    "risk": "Risk",
    "approval": "Approval",
    "audit": "Audit",
    "final_response": "Final Response",
}


CANONICAL_DISPLAY_ORDER = [
    "coordinator",
    "forecasting",
    "inventory",
    "procurement",
    "logistics",
    "policy_context",
    "policy",
    "risk",
    "approval",
    "audit",
    "final_response",
]


def _step_status(
    step: str,
    completed_steps: List[str],
    workflow_steps: List[str],
    forbidden_steps: List[str],
    skip_reason: Dict[str, Any],
    errors: List[Dict[str, Any]],
) -> Dict[str, str]:
    """
    Determines display status for a workflow step.
    """

    errored_steps = {
        str(error.get("step"))
        for error in errors
        if isinstance(error, dict)
    }

    if step in errored_steps:
        return {
            "icon": "❌",
            "status": "Failed",
            "color": "#dc2626",
        }

    if step in completed_steps:
        return {
            "icon": "✅",
            "status": "Completed",
            "color": "#16a34a",
        }

    if step in forbidden_steps or step in skip_reason:
        return {
            "icon": "⏭️",
            "status": "Skipped",
            "color": "#6b7280",
        }

    if step in workflow_steps:
        return {
            "icon": "⏳",
            "status": "Pending",
            "color": "#f59e0b",
        }

    return {
        "icon": "—",
        "status": "Not Planned",
        "color": "#9ca3af",
    }


def render_workflow_timeline(result: Dict[str, Any]) -> None:
    """
    Renders a professional horizontal workflow timeline.
    """

    st.subheader("Workflow Execution Timeline")

    workflow_steps = result.get("workflow_steps", []) or []
    completed_steps = result.get("completed_steps", []) or []
    forbidden_steps = result.get("forbidden_steps", []) or []
    skip_reason = result.get("skip_reason", {}) or {}
    errors = result.get("errors", []) or []

    timeline_html = ""

    for step in CANONICAL_DISPLAY_ORDER:
        status_info = _step_status(
            step=step,
            completed_steps=completed_steps,
            workflow_steps=workflow_steps,
            forbidden_steps=forbidden_steps,
            skip_reason=skip_reason,
            errors=errors,
        )

        label = STEP_LABELS.get(step, step)

        timeline_html += f"""
        <div style="
            min-width: 126px;
            max-width: 126px;
            padding: 14px 10px;
            border-radius: 16px;
            background: #ffffff;
            border: 1px solid #e5e7eb;
            border-top: 6px solid {status_info["color"]};
            box-shadow: 0 6px 16px rgba(15, 23, 42, 0.08);
            text-align: center;
            margin-right: 12px;
        ">
            <div style="font-size: 25px; line-height: 1.2;">
                {status_info["icon"]}
            </div>
            <div style="
                font-weight: 800;
                font-size: 13px;
                color: #111827;
                margin-top: 6px;
            ">
                {label}
            </div>
            <div style="
                font-size: 12px;
                color: #6b7280;
                margin-top: 4px;
            ">
                {status_info["status"]}
            </div>
        </div>
        """

    st.markdown(
        f"""
        <div style="
            display: flex;
            flex-direction: row;
            overflow-x: auto;
            padding: 10px 4px 18px 4px;
            margin-bottom: 8px;
        ">
            {timeline_html}
        </div>
        """,
        unsafe_allow_html=True,
    )

    if skip_reason:
        with st.expander("View skipped step reasons"):
            st.json(skip_reason)