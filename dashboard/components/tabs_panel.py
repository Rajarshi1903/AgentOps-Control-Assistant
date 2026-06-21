"""
dashboard/components/tabs_panel.py

Tabbed dashboard panels for detailed AgentOps workflow inspection.

This module renders:
- Execution trace
- Business agent outputs
- Data access governance
- Policy evaluation
- Risk and approval
- Audit trace
- Raw state debug view
"""

from typing import Any, Dict

import streamlit as st

from dashboard.utils.state_helpers import as_dict, pretty_json


# ============================================================
# Main tabs renderer
# ============================================================

def render_tabs_panel(
    result: Dict[str, Any],
    show_raw_debug: bool,
) -> None:
    """
    Renders all detailed dashboard tabs.
    """

    coordinator_output = as_dict(result.get("coordinator_output"))
    forecasting_output = as_dict(result.get("forecasting_output"))
    inventory_output = as_dict(result.get("inventory_output"))
    procurement_output = as_dict(result.get("procurement_output"))
    logistics_output = as_dict(result.get("logistics_output"))

    policy_context_output = as_dict(result.get("policy_context_output"))
    policy_output = as_dict(result.get("policy_output"))
    policy_rag_decision = as_dict(result.get("policy_rag_decision"))
    risk_output = as_dict(result.get("risk_output"))
    approval_output = as_dict(result.get("approval_output"))
    audit_output = as_dict(result.get("audit_output"))
    final_response_output = as_dict(result.get("final_response_output"))

    policy_decision = policy_output.get("policy_decision")
    risk_score = risk_output.get("final_risk_score")
    risk_level = risk_output.get("risk_level")
    approval_status = approval_output.get("approval_status")
    audit_status = audit_output.get("audit_status")

    st.divider()

    tabs = st.tabs(
        [
            "Execution Trace",
            "Business Agents",
            "Data Access",
            "Policy",
            "Risk & Approval",
            "Audit",
            "Raw State",
        ]
    )

    with tabs[0]:
        _render_execution_trace(
            result=result,
            coordinator_output=coordinator_output,
        )

    with tabs[1]:
        _render_business_agents(
            forecasting_output=forecasting_output,
            inventory_output=inventory_output,
            procurement_output=procurement_output,
            logistics_output=logistics_output,
        )

    with tabs[2]:
        _render_data_access(
            policy_context_output=policy_context_output,
        )

    with tabs[3]:
        _render_policy(
            policy_decision=policy_decision,
            policy_output=policy_output,
            policy_rag_decision=policy_rag_decision,
            policy_context_output=policy_context_output,
        )

    with tabs[4]:
        _render_risk_approval(
            risk_score=risk_score,
            risk_level=risk_level,
            approval_status=approval_status,
            risk_output=risk_output,
            approval_output=approval_output,
        )

    with tabs[5]:
        _render_audit(
            audit_status=audit_status,
            audit_output=audit_output,
            final_response_output=final_response_output,
        )

    with tabs[6]:
        _render_raw_state(
            result=result,
            show_raw_debug=show_raw_debug,
        )


# ============================================================
# Tab 1: Execution Trace
# ============================================================

def _render_execution_trace(
    result: Dict[str, Any],
    coordinator_output: Dict[str, Any],
) -> None:
    """
    Renders execution trace tab.
    """

    st.subheader("Execution Trace")

    workflow_steps = result.get("workflow_steps", [])
    completed_steps = result.get("completed_steps", [])
    forbidden_steps = result.get("forbidden_steps", [])
    skip_reason = result.get("skip_reason", {})

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("#### Workflow Steps")
        st.write(workflow_steps)

    with col2:
        st.markdown("#### Completed Steps")
        st.write(completed_steps)

    with col3:
        st.markdown("#### Forbidden Steps")
        st.write(forbidden_steps)

    if skip_reason:
        st.markdown("#### Skip Reasons")
        st.json(skip_reason)

    st.markdown("#### Coordinator Output")

    if coordinator_output:
        st.json(coordinator_output)
    else:
        st.info("Coordinator output was not generated.")


# ============================================================
# Tab 2: Business Agents
# ============================================================

def _render_business_agents(
    forecasting_output: Dict[str, Any],
    inventory_output: Dict[str, Any],
    procurement_output: Dict[str, Any],
    logistics_output: Dict[str, Any],
) -> None:
    """
    Renders business agents tab.
    """

    st.subheader("Business Agent Outputs")

    agent_tabs = st.tabs(
        [
            "Forecasting",
            "Inventory",
            "Procurement",
            "Logistics",
        ]
    )

    with agent_tabs[0]:
        _render_agent_output(
            title="Forecasting Agent",
            output=forecasting_output,
            empty_message="Forecasting agent did not run or produced no output.",
        )

    with agent_tabs[1]:
        _render_agent_output(
            title="Inventory Agent",
            output=inventory_output,
            empty_message="Inventory agent did not run or produced no output.",
        )

    with agent_tabs[2]:
        _render_agent_output(
            title="Procurement Agent",
            output=procurement_output,
            empty_message="Procurement agent did not run or produced no output.",
        )

    with agent_tabs[3]:
        _render_agent_output(
            title="Logistics Agent",
            output=logistics_output,
            empty_message="Logistics agent did not run or produced no output.",
        )


def _render_agent_output(
    title: str,
    output: Dict[str, Any],
    empty_message: str,
) -> None:
    """
    Renders one business agent output.
    """

    st.markdown(f"#### {title}")

    if not output:
        st.info(empty_message)
        return

    status = output.get("status", "unknown")
    message = output.get("message")

    col1, col2 = st.columns([1, 3])

    with col1:
        st.metric("Status", status)

    with col2:
        if message:
            st.write(message)
        else:
            st.write("No message available.")

    st.markdown("##### Raw Output")
    st.json(output)


# ============================================================
# Tab 3: Data Access
# ============================================================

def _render_data_access(
    policy_context_output: Dict[str, Any],
) -> None:
    """
    Renders data access governance tab.
    """

    st.subheader("Data Access Governance")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Restricted Requested",
            str(policy_context_output.get("user_requested_restricted_data", False)),
        )

    with col2:
        st.metric(
            "Restricted Accessed",
            str(policy_context_output.get("restricted_data_accessed", False)),
        )

    with col3:
        st.metric(
            "Unauthorized Access",
            str(policy_context_output.get("unauthorized_dataset_accessed", False)),
        )

    with col4:
        st.metric(
            "Forbidden Dataset Access",
            str(policy_context_output.get("agent_accessed_forbidden_dataset", False)),
        )

    st.markdown("#### Requested / Accessed Datasets")

    col_a, col_b, col_c = st.columns(3)

    with col_a:
        st.markdown("**Requested datasets**")
        st.write(policy_context_output.get("requested_datasets", []))

    with col_b:
        st.markdown("**Accessed datasets**")
        st.write(policy_context_output.get("dataset_accessed", []))

    with col_c:
        st.markdown("**Attempted datasets**")
        st.write(policy_context_output.get("dataset_access_attempted", []))

    requested_restricted = policy_context_output.get(
        "requested_restricted_datasets",
        [],
    )

    if requested_restricted:
        st.warning(f"Restricted dataset requested: {requested_restricted}")

    governance_violations = policy_context_output.get("governance_violations", [])

    if governance_violations:
        st.error(f"Governance violations: {governance_violations}")
    else:
        st.success("No governance violations detected in policy context.")

    st.markdown("#### Data Access Log")

    data_access_log = policy_context_output.get("data_access_log", [])

    if data_access_log:
        st.dataframe(data_access_log, use_container_width=True)
    else:
        st.info("No data access log found.")


# ============================================================
# Tab 4: Policy
# ============================================================

def _render_policy(
    policy_decision: Any,
    policy_output: Dict[str, Any],
    policy_rag_decision: Dict[str, Any],
    policy_context_output: Dict[str, Any],
) -> None:
    """
    Renders policy evaluation tab.
    """

    st.subheader("Policy Evaluation")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Policy Decision", policy_decision or "Unknown")

    with col2:
        st.metric(
            "RAG Decision",
            policy_rag_decision.get("decision", "Unknown"),
        )

    with col3:
        st.metric(
            "RAG Confidence",
            policy_rag_decision.get("confidence", "N/A"),
        )

    st.markdown("#### Triggered Policies")

    triggered_policies = policy_output.get("triggered_policies", [])

    if triggered_policies:
        st.dataframe(triggered_policies, use_container_width=True)
    else:
        st.success("No triggered policies.")

    st.markdown("#### Policy Output")

    if policy_output:
        st.json(policy_output)
    else:
        st.info("Policy output was not generated.")

    st.markdown("#### Policy RAG Decision")

    if policy_rag_decision:
        st.json(policy_rag_decision)
    else:
        st.info("Policy RAG decision was not generated.")

    st.markdown("#### Policy Context Output")

    with st.expander("View policy context output"):
        if policy_context_output:
            st.json(policy_context_output)
        else:
            st.info("Policy context output was not generated.")


# ============================================================
# Tab 5: Risk & Approval
# ============================================================

def _render_risk_approval(
    risk_score: Any,
    risk_level: Any,
    approval_status: Any,
    risk_output: Dict[str, Any],
    approval_output: Dict[str, Any],
) -> None:
    """
    Renders risk and approval tab.
    """

    st.subheader("Risk and Approval")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Risk Score",
            risk_score if risk_score is not None else "N/A",
        )

    with col2:
        st.metric(
            "Risk Level",
            risk_level or "Unknown",
        )

    with col3:
        st.metric(
            "Approval Required",
            approval_output.get("approval_required", "Not Generated"),
        )

    with col4:
        st.metric(
            "Approval Status",
            approval_status or "Not Generated",
        )

    st.markdown("#### Risk Factors")

    risk_factors = risk_output.get("risk_factors_triggered", [])

    if risk_factors:
        st.dataframe(risk_factors, use_container_width=True)
    else:
        st.success("No additional risk factors triggered.")

    st.markdown("#### Risk Output")

    if risk_output:
        st.json(risk_output)
    else:
        st.info("Risk output was not generated.")

    st.markdown("#### Approval Output")

    if approval_output:
        st.json(approval_output)
    else:
        st.info("Approval output was not generated for this workflow.")


# ============================================================
# Tab 6: Audit
# ============================================================

def _render_audit(
    audit_status: Any,
    audit_output: Dict[str, Any],
    final_response_output: Dict[str, Any],
) -> None:
    """
    Renders audit tab.
    """

    st.subheader("Audit Trace")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Audit Status", audit_status or "Unknown")

    with col2:
        st.metric(
            "Audit Event ID",
            audit_output.get("audit_event_id", "N/A"),
        )

    with col3:
        st.metric(
            "Records Written",
            audit_output.get("records_written", "N/A"),
        )

    st.markdown("#### Audit Output")

    if audit_output:
        st.json(audit_output)
    else:
        st.info("Audit output was not generated.")

    st.markdown("#### Source Evidence")

    source_files = final_response_output.get("source_files", [])
    source_record_ids = final_response_output.get("source_record_ids", [])

    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown("**Source files**")
        st.write(source_files)

    with col_b:
        st.markdown("**Source record IDs**")
        st.write(source_record_ids)


# ============================================================
# Tab 7: Raw State
# ============================================================

def _render_raw_state(
    result: Dict[str, Any],
    show_raw_debug: bool,
) -> None:
    """
    Renders raw state tab.
    """

    st.subheader("Raw State Debug View")

    if show_raw_debug:
        st.code(pretty_json(result), language="json")
    else:
        st.info("Enable raw debug sections from the sidebar.")