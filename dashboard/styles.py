"""
dashboard/styles.py

Custom CSS for dashboard visual polish.
"""

import streamlit as st


def load_css() -> None:
    """
    Loads global dashboard CSS.
    """

    st.markdown(
        """
        <style>
            /* ============================================================
               Global layout
            ============================================================ */

            .main .block-container {
                padding-top: 1.6rem;
                padding-bottom: 2rem;
                max-width: 1400px;
            }

            /* Prevent long text from breaking dashboard layout */
            div, span, p {
                overflow-wrap: anywhere;
                word-break: normal;
            }

            /* ============================================================
               Header
            ============================================================ */

            .control-tower-header {
                padding: 1.25rem 1.5rem;
                border-radius: 18px;
                background: linear-gradient(135deg, #111827 0%, #1f2937 60%, #374151 100%);
                color: white;
                margin-bottom: 1.25rem;
                box-shadow: 0 10px 25px rgba(0, 0, 0, 0.12);
            }

            .control-tower-title {
                font-size: 2rem;
                font-weight: 800;
                margin-bottom: 0.25rem;
                line-height: 1.2;
            }

            .control-tower-subtitle {
                font-size: 0.98rem;
                color: #d1d5db;
                line-height: 1.45;
            }

            /* ============================================================
               Executive metric cards
            ============================================================ */

            .metric-card {
                padding: 16px 18px;
                border-radius: 16px;
                background-color: #ffffff;
                border: 1px solid #e5e7eb;
                box-shadow: 0 6px 18px rgba(15, 23, 42, 0.08);
                min-height: 96px;
                height: auto;
                overflow: visible;
                white-space: normal;
            }

            .metric-label {
                font-size: 13px;
                color: #6b7280;
                margin-bottom: 6px;
                font-weight: 700;
                line-height: 1.25;
                text-transform: uppercase;
                letter-spacing: 0.02em;
            }

            .metric-value {
                font-size: 22px;
                color: #111827;
                font-weight: 800;
                line-height: 1.25;
                white-space: normal;
                overflow-wrap: anywhere;
                word-break: normal;
            }

            /* Use this for long values inside cards */
            .metric-value-small {
                font-size: 17px;
                color: #111827;
                font-weight: 800;
                line-height: 1.35;
                white-space: normal;
                overflow-wrap: anywhere;
                word-break: normal;
            }

            /* ============================================================
               Generic section cards
            ============================================================ */

            .section-card {
                padding: 18px;
                border-radius: 16px;
                background-color: #ffffff;
                border: 1px solid #e5e7eb;
                box-shadow: 0 6px 18px rgba(15, 23, 42, 0.06);
                margin-bottom: 1rem;
                overflow-wrap: anywhere;
            }

            .status-pill {
                display: inline-block;
                padding: 0.25rem 0.65rem;
                border-radius: 999px;
                font-size: 0.8rem;
                font-weight: 700;
                color: white;
                white-space: normal;
            }

            .small-muted {
                color: #6b7280;
                font-size: 0.85rem;
                line-height: 1.4;
            }

            /* ============================================================
               Human-in-the-Loop approval panel
            ============================================================ */

            .hitl-container {
                padding: 1.25rem 1.35rem;
                border-radius: 18px;
                background: #ffffff;
                border: 1px solid #e5e7eb;
                box-shadow: 0 8px 24px rgba(15, 23, 42, 0.08);
                margin-top: 1rem;
                margin-bottom: 1.2rem;
                overflow-wrap: anywhere;
            }

            .hitl-title {
                margin-bottom: 0.25rem;
                color: #111827;
                font-size: 1.55rem;
                font-weight: 850;
                line-height: 1.25;
            }

            .hitl-subtitle {
                color: #6b7280;
                font-size: 0.95rem;
                margin-bottom: 1rem;
                line-height: 1.45;
            }

            .hitl-card {
                padding: 14px 16px;
                border-radius: 14px;
                background: #f9fafb;
                border: 1px solid #e5e7eb;
                min-height: 96px;
                height: auto;
                overflow: visible;
                overflow-wrap: anywhere;
                word-break: normal;
                white-space: normal;
                box-shadow: 0 4px 12px rgba(15, 23, 42, 0.05);
            }

            .hitl-card-label {
                font-size: 0.76rem;
                color: #6b7280;
                font-weight: 800;
                text-transform: uppercase;
                letter-spacing: 0.04em;
                margin-bottom: 7px;
                line-height: 1.25;
            }

            .hitl-card-value {
                font-size: 1.18rem;
                color: #111827;
                font-weight: 850;
                line-height: 1.28;
                white-space: normal;
                overflow-wrap: anywhere;
                word-break: normal;
            }

            .hitl-card-value-small {
                font-size: 1rem;
                color: #111827;
                font-weight: 800;
                line-height: 1.35;
                white-space: normal;
                overflow-wrap: anywhere;
                word-break: normal;
            }

            .hitl-section-title {
                font-size: 1.12rem;
                font-weight: 850;
                color: #111827;
                margin-top: 1.05rem;
                margin-bottom: 0.55rem;
                line-height: 1.25;
            }

            .hitl-action-box {
                padding: 14px 16px;
                border-radius: 14px;
                background: #f8fafc;
                border-left: 5px solid #2563eb;
                color: #111827;
                font-size: 0.96rem;
                line-height: 1.45;
                overflow-wrap: anywhere;
                word-break: normal;
                white-space: normal;
                margin-bottom: 1rem;
            }

            .hitl-muted-box {
                padding: 12px 14px;
                border-radius: 12px;
                background: #f9fafb;
                border: 1px solid #e5e7eb;
                color: #374151;
                font-size: 0.92rem;
                line-height: 1.4;
                overflow-wrap: anywhere;
                word-break: normal;
                white-space: normal;
            }

            /* ============================================================
               Policy / governance chips
            ============================================================ */

            .hitl-chip {
                display: inline-block;
                padding: 6px 10px;
                margin: 4px 5px 4px 0;
                border-radius: 999px;
                background: #eef2ff;
                color: #3730a3;
                font-size: 0.82rem;
                font-weight: 750;
                border: 1px solid #c7d2fe;
                line-height: 1.25;
                max-width: 100%;
                white-space: normal;
                overflow-wrap: anywhere;
                word-break: normal;
            }

            .hitl-chip-danger {
                display: inline-block;
                padding: 6px 10px;
                margin: 4px 5px 4px 0;
                border-radius: 999px;
                background: #fee2e2;
                color: #991b1b;
                font-size: 0.82rem;
                font-weight: 750;
                border: 1px solid #fecaca;
                line-height: 1.25;
                max-width: 100%;
                white-space: normal;
                overflow-wrap: anywhere;
                word-break: normal;
            }

            .hitl-chip-success {
                display: inline-block;
                padding: 6px 10px;
                margin: 4px 5px 4px 0;
                border-radius: 999px;
                background: #dcfce7;
                color: #166534;
                font-size: 0.82rem;
                font-weight: 750;
                border: 1px solid #bbf7d0;
                line-height: 1.25;
                max-width: 100%;
                white-space: normal;
                overflow-wrap: anywhere;
                word-break: normal;
            }

            .hitl-chip-warning {
                display: inline-block;
                padding: 6px 10px;
                margin: 4px 5px 4px 0;
                border-radius: 999px;
                background: #fef3c7;
                color: #92400e;
                font-size: 0.82rem;
                font-weight: 750;
                border: 1px solid #fde68a;
                line-height: 1.25;
                max-width: 100%;
                white-space: normal;
                overflow-wrap: anywhere;
                word-break: normal;
            }

            /* ============================================================
               Streamlit native element improvements
            ============================================================ */

            /* Improve st.metric wrapping slightly where Streamlit metrics are still used */
            [data-testid="stMetricValue"] {
                white-space: normal;
                overflow-wrap: anywhere;
                word-break: normal;
                font-size: 1.35rem;
                line-height: 1.25;
            }

            [data-testid="stMetricLabel"] {
                white-space: normal;
                overflow-wrap: anywhere;
                word-break: normal;
            }

            /* Improve dataframe / json surroundings */
            [data-testid="stExpander"] {
                border-radius: 12px;
                overflow: hidden;
            }

            /* Better form spacing */
            div[data-testid="stForm"] {
                border-radius: 16px;
                border: 1px solid #e5e7eb;
                padding: 1rem;
                background: #ffffff;
                box-shadow: 0 4px 14px rgba(15, 23, 42, 0.05);
            }

            /* Better buttons */
            .stButton > button {
                border-radius: 10px;
                font-weight: 700;
            }

            /* Better radio text wrapping */
            div[role="radiogroup"] label {
                white-space: normal;
                overflow-wrap: anywhere;
            }

        </style>
        """,
        unsafe_allow_html=True,
    )