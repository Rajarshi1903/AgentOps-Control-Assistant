"""
dashboard/components/query_panel.py

Query input and sidebar controls.
"""

from typing import Tuple

import streamlit as st

from dashboard.config import DEFAULT_USER_ROLE, SAMPLE_QUERIES


def render_sidebar() -> Tuple[str, bool]:
    """
    Renders sidebar controls.

    Returns:
        selected_sample, show_raw_debug
    """

    st.sidebar.title("🧭 Control Tower")

    st.sidebar.markdown(
        """
        This dashboard runs the full AgentOps supply chain workflow and displays:

        - Business agent results
        - Data access governance
        - Policy decision
        - Risk score
        - Approval status
        - Audit trace
        - LLM final response
        """
    )

    st.sidebar.divider()

    selected_sample = st.sidebar.selectbox(
        "Load sample query",
        options=["Custom"] + list(SAMPLE_QUERIES.keys()),
    )

    st.sidebar.divider()

    show_raw_debug = st.sidebar.checkbox(
        "Show raw debug sections",
        value=True,
    )

    return selected_sample, show_raw_debug


def render_query_panel(selected_sample: str) -> Tuple[str, str, bool]:
    """
    Renders main query form.

    Returns:
        user_query, user_role, submitted
    """

    default_query = ""

    if selected_sample != "Custom":
        default_query = SAMPLE_QUERIES[selected_sample]

    with st.form("workflow_form"):
        user_query = st.text_area(
            "Enter supply chain query",
            value=default_query,
            height=120,
            placeholder=(
                "Example: For P-105 in South, run an audit-ready supply chain decision..."
            ),
        )

        user_role = st.text_input(
            "User role",
            value=DEFAULT_USER_ROLE,
        )

        submitted = st.form_submit_button(
            "Run Workflow",
            type="primary",
        )

    return user_query, user_role, submitted