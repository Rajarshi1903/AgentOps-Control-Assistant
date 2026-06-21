"""
dashboard/components/summary_cards.py

Executive summary cards for the AgentOps dashboard.
"""

from typing import Any, Dict

import streamlit as st

from dashboard.utils.state_helpers import extract_outputs
from dashboard.utils.ui_helpers import (
    approval_color,
    decision_color,
    render_metric_card,
    risk_color,
)


def _count_governance_violations(result: Dict[str, Any]) -> int:
    """
    Counts governance violations from policy_context_output.
    """

    policy_context_output = result.get("policy_context_output") or {}
    violations = policy_context_output.get("governance_violations", [])

    if isinstance(violations, list):
        return len(violations)

    return 0


def render_summary_cards(result: Dict[str, Any]) -> None:
    """
    Renders executive workflow summary cards.
    """

    outputs = extract_outputs(result)

    policy_output = outputs["policy_output"]
    risk_output = outputs["risk_output"]
    approval_output = outputs["approval_output"]
    audit_output = outputs["audit_output"]

    final_decision = result.get("final_decision")
    policy_decision = policy_output.get("policy_decision")
    risk_score = risk_output.get("final_risk_score")
    risk_level = risk_output.get("risk_level")
    approval_status = approval_output.get("approval_status")
    audit_status = audit_output.get("audit_status")

    governance_violation_count = _count_governance_violations(result)

    st.subheader("Executive Workflow Summary")

    row1_col1, row1_col2, row1_col3, row1_col4 = st.columns(4)

    with row1_col1:
        render_metric_card(
            label="Final Decision",
            value=final_decision or "Unknown",
            color=decision_color(final_decision),
        )

    with row1_col2:
        render_metric_card(
            label="Policy Decision",
            value=policy_decision or "Unknown",
            color=decision_color(policy_decision),
        )

    with row1_col3:
        render_metric_card(
            label="Risk Level",
            value=risk_level or "Unknown",
            color=risk_color(risk_level),
        )

    with row1_col4:
        render_metric_card(
            label="Risk Score",
            value=risk_score if risk_score is not None else "N/A",
            color=risk_color(risk_level),
        )

    st.markdown("")

    row2_col1, row2_col2, row2_col3 = st.columns(3)

    with row2_col1:
        render_metric_card(
            label="Approval Status",
            value=approval_status or "Not Generated",
            color=approval_color(approval_status),
        )

    with row2_col2:
        render_metric_card(
            label="Governance Violations",
            value=governance_violation_count,
            color="#dc2626" if governance_violation_count else "#16a34a",
        )

    with row2_col3:
        render_metric_card(
            label="Audit Status",
            value=audit_status or "Unknown",
            color="#16a34a" if audit_status == "success" else "#6b7280",
        )

    errors = result.get("errors", [])

    if errors:
        st.error("Workflow completed with errors.")
        with st.expander("View errors"):
            st.json(errors)
    else:
        st.success("Workflow completed without graph errors.")