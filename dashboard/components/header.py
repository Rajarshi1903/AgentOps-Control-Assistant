"""
dashboard/components/header.py

Dashboard header component.
"""

import streamlit as st


def render_header() -> None:
    """
    Renders the dashboard header.
    """

    st.markdown(
        """
        <div class="control-tower-header">
            <div class="control-tower-title">🧭 AgentOps Supply Chain Control Tower</div>
            <div class="control-tower-subtitle">
                Governed multi-agent workflow for forecasting, inventory, procurement,
                logistics, policy evaluation, risk scoring, approval, audit, and LLM final response.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )