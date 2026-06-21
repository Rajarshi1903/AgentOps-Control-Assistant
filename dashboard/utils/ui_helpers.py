"""
dashboard/utils/ui_helpers.py

UI helper functions for colors, badges, and visual elements.
"""

from typing import Any, Optional

import streamlit as st


def decision_color(decision: Optional[str]) -> str:
    """
    Returns color for decision badge.
    """

    if decision == "Allow":
        return "#16a34a"

    if decision == "Escalate":
        return "#f59e0b"

    if decision == "Block":
        return "#dc2626"

    return "#6b7280"


def risk_color(risk_level: Optional[str]) -> str:
    """
    Returns color for risk badge.
    """

    if risk_level == "Low":
        return "#16a34a"

    if risk_level == "Medium":
        return "#f59e0b"

    if risk_level in {"High", "Critical"}:
        return "#dc2626"

    return "#6b7280"


def approval_color(approval_status: Optional[str]) -> str:
    """
    Returns color for approval badge.
    """

    if approval_status == "Approved":
        return "#16a34a"

    if approval_status == "Pending":
        return "#f59e0b"

    if approval_status == "Blocked":
        return "#dc2626"

    if approval_status == "Not Required":
        return "#2563eb"

    return "#6b7280"


def render_metric_card(
    label: str,
    value: Any,
    color: str,
) -> None:
    """
    Renders a professional metric card with a colored accent.
    """

    st.markdown(
        f"""
        <div class="metric-card" style="border-left: 7px solid {color};">
            <div class="metric-label">{label}</div>
            <div class="metric-value">{value}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_status_pill(
    label: str,
    color: str,
) -> None:
    """
    Renders a small status pill.
    """

    st.markdown(
        f"""
        <span class="status-pill" style="background-color: {color};">
            {label}
        </span>
        """,
        unsafe_allow_html=True,
    )