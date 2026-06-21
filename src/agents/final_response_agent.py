import os
import random
import time
from typing import Any, Dict, List

from src.schemas.agent_outputs import FinalResponseOutput
from src.services.llm_client import call_llm_json


# ============================================================
# LLM-powered Final Response Agent
# ============================================================
# Purpose:
# Converts complete LangGraph state into a business-readable,
# governance-aware final response.
#
# Design:
# - LLM generates only the short response summary and natural-language explanation.
# - Deterministic code generates detailed markdown response and next action.
# - LLM does NOT make decisions.
# - final_decision, policy_decision, risk score, approval status,
#   reviewer role, and governance violations remain grounded in state.
# - Deterministic response is used as fallback if LLM fails.
#
# Important:
# - Does NOT make policy decisions.
# - Does NOT calculate risk.
# - Does NOT approve/reject actions.
# - Does NOT call RAG.
# - Uses only existing state facts.
# ============================================================


ENABLE_LLM_FINAL_RESPONSE = (
    os.getenv("ENABLE_LLM_FINAL_RESPONSE", "true").strip().lower() == "true"
)


# ============================================================
# Utility helpers
# ============================================================

def _safe_model_dump(model: Any) -> Dict[str, Any]:
    """
    Supports Pydantic v1/v2 and dictionaries.
    """

    if model is None:
        return {}

    if isinstance(model, dict):
        return model

    if hasattr(model, "model_dump"):
        return model.model_dump()

    if hasattr(model, "dict"):
        return model.dict()

    return dict(model)


def _as_dict(value: Any) -> Dict[str, Any]:
    """
    Converts dict-like or Pydantic object into plain dictionary.
    """

    if value is None:
        return {}

    if isinstance(value, dict):
        return value

    if hasattr(value, "model_dump"):
        return value.model_dump()

    if hasattr(value, "dict"):
        return value.dict()

    return {}


def _as_list(value: Any) -> List[Any]:
    """
    Safely converts value to list.
    """

    if value is None:
        return []

    if isinstance(value, list):
        return value

    if isinstance(value, tuple):
        return list(value)

    if isinstance(value, set):
        return list(value)

    return [value]


def _string_list(value: Any) -> List[str]:
    """
    Converts value to clean list[str].
    """

    cleaned: List[str] = []

    for item in _as_list(value):
        if item is None:
            continue

        item_str = str(item).strip()

        if not item_str:
            continue

        if item_str.lower() in {"none", "null"}:
            continue

        if item_str not in cleaned:
            cleaned.append(item_str)

    return cleaned


def _format_inr(value: Any) -> str:
    """
    Formats numeric value as INR.
    """

    try:
        amount = float(value)
        return f"INR {amount:,.2f}"
    except (TypeError, ValueError):
        return "INR 0.00"


def _unique_preserve_order(values: List[Any]) -> List[Any]:
    """
    Deduplicates values while preserving order.
    """

    seen = set()
    result = []

    for value in values:
        key = str(value)

        if key not in seen:
            seen.add(key)
            result.append(value)

    return result


# ============================================================
# Evidence and policy helpers
# ============================================================

def _get_triggered_policy_names(policy_output: Dict[str, Any]) -> List[str]:
    """
    Extracts triggered policy names from policy_output.
    """

    policies = policy_output.get("triggered_policies", [])
    names: List[str] = []

    for policy in _as_list(policies):
        policy_dict = _as_dict(policy)
        name = policy_dict.get("policy_name")

        if name:
            names.append(str(name))

    return _unique_preserve_order(names)


def _extract_policy_evidence(
    policy_rag_decision: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Extracts compact PDF policy evidence from policy_rag_decision.
    """

    evidence_items: List[Dict[str, Any]] = []
    rules = policy_rag_decision.get("triggered_rules", [])

    for rule in _as_list(rules):
        rule_dict = _as_dict(rule)
        evidence = _as_dict(rule_dict.get("evidence"))

        evidence_items.append(
            {
                "policy_name": rule_dict.get("policy_name"),
                "policy_area": rule_dict.get("policy_area"),
                "action": rule_dict.get("action"),
                "severity": rule_dict.get("severity"),
                "evidence_text": evidence.get("evidence_text"),
                "source_document": evidence.get("source_document"),
                "source_page": evidence.get("source_page"),
                "chunk_id": evidence.get("chunk_id"),
                "confidence": rule_dict.get("confidence"),
            }
        )

    return evidence_items


def _collect_source_files_and_records(
    state: Dict[str, Any],
    policy_context_output: Dict[str, Any],
) -> Dict[str, List[str]]:
    """
    Collects source files and record IDs from outputs and policy context.
    """

    source_files: List[str] = []
    source_record_ids: List[str] = []

    for key in [
        "forecasting_output",
        "inventory_output",
        "procurement_output",
        "logistics_output",
        "policy_output",
        "risk_output",
        "approval_output",
        "audit_output",
    ]:
        output = _as_dict(state.get(key))

        files = output.get("source_files", [])
        record_ids = output.get("source_record_ids", [])

        if isinstance(files, list):
            source_files.extend(files)

        if isinstance(record_ids, list):
            source_record_ids.extend([str(item) for item in record_ids])

    source_files.extend(
        _string_list(policy_context_output.get("dataset_accessed", []))
    )

    source_files.extend(
        _string_list(policy_context_output.get("dataset_access_attempted", []))
    )

    policy_rag_decision = _as_dict(state.get("policy_rag_decision"))

    if policy_rag_decision:
        source_files.append("agentops_supply_chain_policy_handbook.pdf")

        for page in policy_rag_decision.get("source_pages", []):
            source_record_ids.append(f"policy_page_{page}")

    return {
        "source_files": _unique_preserve_order(source_files),
        "source_record_ids": _unique_preserve_order(source_record_ids),
    }


# ============================================================
# Structured summary builders
# ============================================================

def _build_business_summary(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Builds structured business summary from agent outputs and policy context.
    """

    policy_context_output = _as_dict(state.get("policy_context_output"))
    forecasting_output = _as_dict(state.get("forecasting_output"))
    inventory_output = _as_dict(state.get("inventory_output"))
    procurement_output = _as_dict(state.get("procurement_output"))
    logistics_output = _as_dict(state.get("logistics_output"))

    return {
        "product_id": (
            policy_context_output.get("product_id")
            or state.get("product_id")
            or forecasting_output.get("product_id")
            or inventory_output.get("product_id")
            or procurement_output.get("product_id")
        ),
        "product_name": policy_context_output.get("product_name"),
        "region": (
            policy_context_output.get("region")
            or state.get("region")
            or forecasting_output.get("region")
            or inventory_output.get("region")
            or procurement_output.get("region")
            or logistics_output.get("destination_region")
        ),

        # Agent statuses/messages
        "forecasting_status": policy_context_output.get("forecasting_status"),
        "inventory_status": policy_context_output.get("inventory_status"),
        "procurement_status": policy_context_output.get("procurement_status"),
        "logistics_status": policy_context_output.get("logistics_status"),
        "agent_messages": policy_context_output.get("agent_messages", {}),
        "successful_agents": policy_context_output.get("successful_agents", []),
        "failed_agents": policy_context_output.get("failed_agents", []),
        "skipped_agents": policy_context_output.get("skipped_agents", []),
        "not_run_agents": policy_context_output.get("not_run_agents", []),
        "non_action_agents": policy_context_output.get("non_action_agents", []),

        # Forecasting
        "forecasted_demand": policy_context_output.get(
            "forecasted_demand",
            forecasting_output.get("forecasted_demand"),
        ),
        "historical_avg_demand": forecasting_output.get("historical_avg_demand"),
        "recent_avg_demand": forecasting_output.get("recent_avg_demand"),
        "forecast_confidence": policy_context_output.get(
            "forecast_confidence",
            forecasting_output.get("forecast_confidence"),
        ),
        "demand_spike_detected": policy_context_output.get(
            "demand_spike_detected",
            forecasting_output.get("demand_spike_detected"),
        ),
        "forecast_visualizations": forecasting_output.get("visualization_files", []),

        # Inventory
        "current_stock": policy_context_output.get(
            "current_stock",
            inventory_output.get("current_stock"),
        ),
        "safety_stock": policy_context_output.get(
            "safety_stock",
            inventory_output.get("safety_stock"),
        ),
        "reorder_point": policy_context_output.get(
            "reorder_point",
            inventory_output.get("reorder_point"),
        ),
        "stock_position": policy_context_output.get(
            "stock_position",
            inventory_output.get("stock_position"),
        ),
        "shortage_quantity": policy_context_output.get(
            "shortage_quantity",
            inventory_output.get("shortage_quantity"),
        ),
        "procurement_required": policy_context_output.get(
            "procurement_required",
            inventory_output.get("procurement_required"),
        ),
        "stock_below_reorder_point": policy_context_output.get(
            "stock_below_reorder_point",
            inventory_output.get("stock_below_reorder_point"),
        ),
        "forecast_creates_shortage": policy_context_output.get(
            "forecast_creates_shortage",
            inventory_output.get("forecast_creates_shortage"),
        ),

        # Procurement
        "procurement_recommendation_exists": policy_context_output.get(
            "procurement_recommendation_exists"
        ),
        "procurement_action_required": policy_context_output.get(
            "procurement_action_required",
            procurement_output.get("action_required"),
        ),
        "procurement_recommendation_generated": policy_context_output.get(
            "procurement_recommendation_generated",
            procurement_output.get("recommendation_generated"),
        ),
        "procurement_skipped_reason": policy_context_output.get(
            "procurement_skipped_reason",
            procurement_output.get("procurement_skipped_reason"),
        ),
        "recommended_quantity": policy_context_output.get(
            "recommended_quantity",
            procurement_output.get("recommended_quantity"),
        ),
        "recommended_supplier_id": policy_context_output.get(
            "recommended_supplier_id",
            procurement_output.get("recommended_supplier_id"),
        ),
        "recommended_supplier_name": policy_context_output.get(
            "recommended_supplier_name",
            procurement_output.get("recommended_supplier_name"),
        ),
        "supplier_region": policy_context_output.get(
            "supplier_region",
            procurement_output.get("supplier_region"),
        ),
        "unit_cost": policy_context_output.get(
            "unit_cost",
            procurement_output.get("unit_cost"),
        ),
        "procurement_value": policy_context_output.get(
            "procurement_value",
            procurement_output.get("procurement_value"),
        ),
        "supplier_approval_status": policy_context_output.get(
            "supplier_is_approved",
            procurement_output.get("is_approved"),
        ),
        "supplier_compliance_status": policy_context_output.get(
            "supplier_compliance_status",
            procurement_output.get("compliance_status"),
        ),
        "supplier_is_unapproved": policy_context_output.get("supplier_is_unapproved"),
        "supplier_is_non_compliant": policy_context_output.get("supplier_is_non_compliant"),
        "supplier_under_review": policy_context_output.get("supplier_under_review"),
        "supplier_reliability_score": policy_context_output.get(
            "reliability_score",
            procurement_output.get("reliability_score"),
        ),
        "supplier_lead_time_days": policy_context_output.get(
            "lead_time_days",
            procurement_output.get("lead_time_days"),
        ),

        # Logistics
        "logistics_action_required": policy_context_output.get(
            "logistics_action_required",
            logistics_output.get("action_required"),
        ),
        "logistics_route_exists": policy_context_output.get("logistics_route_exists"),
        "route_generated": policy_context_output.get(
            "route_generated",
            logistics_output.get("route_generated"),
        ),
        "logistics_skipped_reason": policy_context_output.get(
            "logistics_skipped_reason",
            logistics_output.get("logistics_skipped_reason"),
        ),
        "recommended_route_id": policy_context_output.get(
            "recommended_route_id",
            logistics_output.get("recommended_route_id"),
        ),
        "warehouse_id": policy_context_output.get(
            "warehouse_id",
            logistics_output.get("warehouse_id"),
        ),
        "origin_region": policy_context_output.get(
            "origin_region",
            logistics_output.get("origin_region"),
        ),
        "destination_node": policy_context_output.get(
            "destination_node",
            logistics_output.get("destination_node"),
        ),
        "transport_mode": policy_context_output.get(
            "transport_mode",
            logistics_output.get("transport_mode"),
        ),
        "distance_km": policy_context_output.get(
            "distance_km",
            logistics_output.get("distance_km"),
        ),
        "route_risk_level": policy_context_output.get(
            "route_risk_level",
            logistics_output.get("route_risk_level"),
        ),
        "route_score": policy_context_output.get(
            "route_score",
            logistics_output.get("route_score"),
        ),
        "route_disruption_exists": policy_context_output.get(
            "route_disruption_exists",
            logistics_output.get("route_disruption_exists"),
        ),
        "route_disruption_severity": policy_context_output.get(
            "route_disruption_severity",
            logistics_output.get("route_disruption_severity"),
        ),
        "route_disruption_status": policy_context_output.get(
            "route_disruption_status",
            logistics_output.get("route_disruption_status"),
        ),
        "impact_delay_days": policy_context_output.get(
            "impact_delay_days",
            logistics_output.get("impact_delay_days"),
        ),
        "impact_cost": policy_context_output.get(
            "impact_cost",
            logistics_output.get("impact_cost"),
        ),
        "estimated_time_days": policy_context_output.get(
            "estimated_time_days",
            logistics_output.get("estimated_time_days"),
        ),
        "adjusted_time_days": policy_context_output.get(
            "adjusted_time_days",
            logistics_output.get("adjusted_time_days"),
        ),
        "base_cost": policy_context_output.get(
            "base_cost",
            logistics_output.get("base_cost"),
        ),
        "adjusted_route_cost": policy_context_output.get(
            "adjusted_route_cost",
            logistics_output.get("adjusted_route_cost"),
        ),
    }


def _build_governance_summary(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Builds structured governance summary from policy context,
    policy/risk/approval/audit outputs.
    """

    policy_context_output = _as_dict(state.get("policy_context_output"))
    policy_output = _as_dict(state.get("policy_output"))
    policy_rag_decision = _as_dict(state.get("policy_rag_decision"))
    risk_output = _as_dict(state.get("risk_output"))
    approval_output = _as_dict(state.get("approval_output"))
    audit_output = _as_dict(state.get("audit_output"))

    approval_output_present = bool(approval_output)

    return {
        "final_decision": state.get("final_decision"),
        "policy_decision": policy_output.get("policy_decision"),
        "context_build_status": policy_context_output.get("context_build_status"),
        "governance_violations": policy_context_output.get("governance_violations", []),
        "has_governance_violation": policy_context_output.get("has_governance_violation"),
        "triggered_policies": _get_triggered_policy_names(policy_output),

        "workflow_steps": policy_context_output.get("workflow_steps", state.get("workflow_steps", [])),
        "completed_steps": policy_context_output.get("completed_steps", state.get("completed_steps", [])),
        "forbidden_steps": policy_context_output.get("forbidden_steps", state.get("forbidden_steps", [])),
        "skip_reason": policy_context_output.get("skip_reason", state.get("skip_reason", {})),
        "not_run_agents": policy_context_output.get("not_run_agents", []),
        "successful_agents": policy_context_output.get("successful_agents", []),
        "failed_agents": policy_context_output.get("failed_agents", []),
        "skipped_agents": policy_context_output.get("skipped_agents", []),
        "non_action_agents": policy_context_output.get("non_action_agents", []),

        "requested_datasets": policy_context_output.get("requested_datasets", []),
        "requested_restricted_datasets": policy_context_output.get("requested_restricted_datasets", []),
        "forbidden_datasets": policy_context_output.get("forbidden_datasets", []),
        "dataset_accessed": policy_context_output.get("dataset_accessed", []),
        "dataset_access_attempted": policy_context_output.get("dataset_access_attempted", []),
        "user_requested_restricted_data": policy_context_output.get("user_requested_restricted_data"),
        "restricted_data_accessed": policy_context_output.get("restricted_data_accessed"),
        "unauthorized_dataset_accessed": policy_context_output.get("unauthorized_dataset_accessed"),
        "agent_accessed_forbidden_dataset": policy_context_output.get("agent_accessed_forbidden_dataset"),
        "user_instruction_violation": policy_context_output.get("user_instruction_violation"),
        "user_requested_no_citations": policy_context_output.get("user_requested_no_citations"),
        "source_citation_missing": policy_context_output.get("source_citation_missing"),

        "policy_rag_decision": policy_rag_decision.get("decision"),
        "policy_rag_confidence": policy_rag_decision.get("confidence"),
        "policy_rag_source_pages": policy_rag_decision.get("source_pages"),
        "policy_rag_final_reason": policy_rag_decision.get("final_reason"),
        "policy_rag_evidence_available": policy_rag_decision.get("evidence_available"),
        "policy_rag_error": policy_rag_decision.get("error"),

        "risk_score": risk_output.get("final_risk_score"),
        "risk_level": risk_output.get("risk_level"),
        "risk_factors": [
            _as_dict(factor).get("factor")
            for factor in risk_output.get("risk_factors_triggered", [])
        ],

        "approval_output_present": approval_output_present,
        "approval_required": approval_output.get("approval_required"),
        "approval_status": approval_output.get("approval_status"),
        "reviewer_role": approval_output.get("reviewer_role"),
        "approval_id": approval_output.get("approval_id"),
        "action_under_review": approval_output.get("action_under_review"),

        "audit_event_id": audit_output.get("audit_event_id"),
        "audit_status": audit_output.get("audit_status"),
        "audit_database_path": audit_output.get("database_path"),
    }


# ============================================================
# Deterministic fallback builders
# ============================================================

def _determine_recommended_next_action(
    final_decision: str,
    approval_output: Dict[str, Any],
    governance_summary: Dict[str, Any],
) -> str:
    """
    Determines recommended next action using only actual state facts.
    """

    approval_status = approval_output.get("approval_status")
    reviewer_role = approval_output.get("reviewer_role")
    approval_output_present = bool(approval_output)

    if final_decision == "Block":
        return (
            "Do not proceed. The workflow was blocked by policy or governance controls. "
            "Review the triggered policies, governance violations, and source evidence before revising the request."
        )

    if final_decision == "Escalate":
        if approval_output_present and approval_status == "Pending" and reviewer_role:
            return (
                f"Wait for human review from {reviewer_role}. The action must not be executed until approval is granted."
            )

        if not approval_output_present:
            return (
                "Human review is required by policy, but no approval workflow output was generated. "
                "Review the policy and risk outputs before taking further action."
            )

        return (
            "Human review is required before execution. Review the approval output before proceeding."
        )

    if final_decision == "Allow":
        if approval_output_present and approval_status == "Approved":
            return (
                "The completed workflow is allowed by policy and approved. Proceed within the scope of the completed steps."
            )

        if approval_output_present and approval_status == "Not Required":
            return (
                "The completed workflow is allowed by policy and no human approval is required. "
                "Proceed within the scope of the completed steps."
            )

        if not approval_output_present:
            return (
                "The completed workflow is allowed by policy. Use the generated output within the scope of the steps that actually ran."
            )

        return (
            "The completed workflow is allowed by policy. Review the approval output before taking any execution action."
        )

    return "Review the workflow output before taking action."


def _build_response_summary(
    business_summary: Dict[str, Any],
    governance_summary: Dict[str, Any],
) -> str:
    """
    Builds short deterministic executive summary.
    """

    product_id = business_summary.get("product_id") or "the selected product"
    region = business_summary.get("region") or "the selected region"

    final_decision = governance_summary.get("final_decision") or "Unknown"
    risk_score = governance_summary.get("risk_score")
    risk_level = governance_summary.get("risk_level")
    approval_output_present = governance_summary.get("approval_output_present")
    approval_status = governance_summary.get("approval_status")

    approval_text = (
        f"Approval status is {approval_status}."
        if approval_output_present
        else "No approval output was generated for this workflow."
    )

    return (
        f"The workflow for {product_id} in {region} completed with final decision "
        f"{final_decision}. Risk score is {risk_score} with risk level {risk_level}. "
        f"{approval_text}"
    )


def _build_deterministic_natural_language_explanation(
    business_summary: Dict[str, Any],
    governance_summary: Dict[str, Any],
    recommended_next_action: str,
) -> str:
    """
    Deterministic fallback natural-language explanation.
    Used only if LLM fails.
    """

    product_id = business_summary.get("product_id") or "the selected product"
    region = business_summary.get("region") or "the selected region"
    final_decision = governance_summary.get("final_decision") or "Unknown"
    policy_decision = governance_summary.get("policy_decision") or "Unknown"
    risk_score = governance_summary.get("risk_score")
    risk_level = governance_summary.get("risk_level")

    approval_output_present = governance_summary.get("approval_output_present")
    approval_status = governance_summary.get("approval_status")
    reviewer_role = governance_summary.get("reviewer_role")

    governance_violations = _string_list(governance_summary.get("governance_violations", []))
    forbidden_steps = _string_list(governance_summary.get("forbidden_steps", []))
    skip_reason = _as_dict(governance_summary.get("skip_reason"))

    sentences = [
        f"The AgentOps Control Tower evaluated {product_id} in {region} and returned a final decision of {final_decision}.",
        f"The Policy Engine decision was {policy_decision}, and the Risk Scoring Engine assigned a score of {risk_score} with a {risk_level} risk level.",
    ]

    if forbidden_steps:
        skipped_text = ", ".join(forbidden_steps)
        sentences.append(
            f"The following workflow steps were intentionally skipped based on user instruction: {skipped_text}."
        )

        if skip_reason:
            sentences.append(
                "The skip reasons were captured in the workflow state for audit traceability."
            )

    if governance_violations:
        sentences.append(
            "The main governance signal(s) identified were: "
            + ", ".join(governance_violations)
            + "."
        )

    if approval_output_present:
        if approval_status == "Blocked":
            sentences.append(
                "The approval status is Blocked, so the workflow cannot proceed as-is."
            )
        elif approval_status == "Pending":
            if reviewer_role:
                sentences.append(
                    f"The approval status is Pending and requires review from {reviewer_role}."
                )
            else:
                sentences.append("The approval status is Pending.")
        elif approval_status == "Approved":
            sentences.append("The approval status is Approved.")
        elif approval_status == "Not Required":
            sentences.append("No human approval is required for the completed workflow.")
        else:
            sentences.append(f"The approval status is {approval_status}.")
    else:
        sentences.append("No approval output was generated for this workflow.")

    sentences.append(f"The recommended next action is: {recommended_next_action}")

    return " ".join(sentences)


def _build_deterministic_detailed_response(
    state: Dict[str, Any],
    business_summary: Dict[str, Any],
    governance_summary: Dict[str, Any],
    evidence_summary: List[Dict[str, Any]],
    natural_language_explanation: str,
    recommended_next_action: str,
) -> str:
    """
    Builds deterministic markdown response.
    """

    lines: List[str] = []

    user_query = state.get("user_query", "")

    lines.append("## AgentOps Control Tower Final Response")

    if user_query:
        lines.append(f"**User query:** {user_query}")

    lines.append("")
    lines.append("### Natural Language Explanation")
    lines.append(natural_language_explanation)

    lines.append("")
    lines.append("### Business Summary")

    product_id = business_summary.get("product_id") or "N/A"
    product_name = business_summary.get("product_name") or "N/A"
    region = business_summary.get("region") or "N/A"

    lines.append(f"- Product ID: `{product_id}`")
    lines.append(f"- Product name: `{product_name}`")
    lines.append(f"- Region: `{region}`")

    if business_summary.get("forecasted_demand") is not None:
        lines.append(f"- Forecasted demand: `{business_summary.get('forecasted_demand')}` units")
        lines.append(f"- Forecast confidence: `{business_summary.get('forecast_confidence')}`")
        lines.append(f"- Demand spike detected: `{business_summary.get('demand_spike_detected')}`")

    if business_summary.get("current_stock") is not None:
        lines.append(f"- Current stock: `{business_summary.get('current_stock')}`")
        lines.append(f"- Safety stock: `{business_summary.get('safety_stock')}`")
        lines.append(f"- Reorder point: `{business_summary.get('reorder_point')}`")
        lines.append(f"- Stock position: `{business_summary.get('stock_position')}`")
        lines.append(f"- Shortage quantity: `{business_summary.get('shortage_quantity')}`")
        lines.append(f"- Procurement required: `{business_summary.get('procurement_required')}`")

    if business_summary.get("recommended_supplier_id") is not None:
        lines.append("")
        lines.append("### Procurement Recommendation")
        lines.append(
            f"- Recommended supplier: `{business_summary.get('recommended_supplier_id')}` "
            f"({business_summary.get('recommended_supplier_name')})"
        )
        lines.append(f"- Recommended quantity: `{business_summary.get('recommended_quantity')}`")
        lines.append(f"- Procurement value: `{_format_inr(business_summary.get('procurement_value'))}`")
        lines.append(f"- Supplier approval status: `{business_summary.get('supplier_approval_status')}`")
        lines.append(f"- Supplier compliance status: `{business_summary.get('supplier_compliance_status')}`")
        lines.append(f"- Supplier reliability score: `{business_summary.get('supplier_reliability_score')}`")
        lines.append(f"- Supplier lead time: `{business_summary.get('supplier_lead_time_days')}` days")

    if business_summary.get("recommended_route_id") is not None:
        lines.append("")
        lines.append("### Logistics Recommendation")
        lines.append(f"- Recommended route: `{business_summary.get('recommended_route_id')}`")
        lines.append(f"- Warehouse: `{business_summary.get('warehouse_id')}`")
        lines.append(f"- Transport mode: `{business_summary.get('transport_mode')}`")
        lines.append(f"- Distance: `{business_summary.get('distance_km')}` km")
        lines.append(f"- Route risk level: `{business_summary.get('route_risk_level')}`")
        lines.append(f"- Route disruption exists: `{business_summary.get('route_disruption_exists')}`")
        lines.append(
            f"- Disruption status/severity: "
            f"`{business_summary.get('route_disruption_status')}` / "
            f"`{business_summary.get('route_disruption_severity')}`"
        )
        lines.append(f"- Adjusted time: `{business_summary.get('adjusted_time_days')}` days")
        lines.append(f"- Adjusted route cost: `{_format_inr(business_summary.get('adjusted_route_cost'))}`")

    forbidden_steps = _string_list(governance_summary.get("forbidden_steps", []))
    skip_reason = _as_dict(governance_summary.get("skip_reason"))

    if forbidden_steps or skip_reason:
        lines.append("")
        lines.append("### Skipped Workflow Steps")
        if forbidden_steps:
            lines.append(f"- Forbidden/skipped steps: `{forbidden_steps}`")
        if skip_reason:
            lines.append(f"- Skip reasons: `{skip_reason}`")

    lines.append("")
    lines.append("### Governance Summary")
    lines.append(f"- Final decision: `{governance_summary.get('final_decision')}`")
    lines.append(f"- Policy decision: `{governance_summary.get('policy_decision')}`")
    lines.append(f"- Context build status: `{governance_summary.get('context_build_status')}`")
    lines.append(f"- Governance violations: `{governance_summary.get('governance_violations')}`")
    lines.append(f"- Triggered policies: `{governance_summary.get('triggered_policies')}`")
    lines.append(f"- Requested datasets: `{governance_summary.get('requested_datasets')}`")
    lines.append(f"- Requested restricted datasets: `{governance_summary.get('requested_restricted_datasets')}`")
    lines.append(f"- Dataset accessed: `{governance_summary.get('dataset_accessed')}`")
    lines.append(f"- Dataset access attempted: `{governance_summary.get('dataset_access_attempted')}`")
    lines.append(f"- User requested restricted data: `{governance_summary.get('user_requested_restricted_data')}`")
    lines.append(f"- Restricted data accessed: `{governance_summary.get('restricted_data_accessed')}`")
    lines.append(f"- Unauthorized dataset accessed: `{governance_summary.get('unauthorized_dataset_accessed')}`")
    lines.append(f"- User requested no citations: `{governance_summary.get('user_requested_no_citations')}`")
    lines.append(f"- Source citation missing: `{governance_summary.get('source_citation_missing')}`")

    policy_reason = governance_summary.get("policy_rag_final_reason")
    if policy_reason:
        lines.append(f"- PDF policy reason: {policy_reason}")

    lines.append("")
    lines.append("### Risk Summary")
    lines.append(f"- Risk score: `{governance_summary.get('risk_score')}`")
    lines.append(f"- Risk level: `{governance_summary.get('risk_level')}`")
    lines.append(f"- Risk factors: `{governance_summary.get('risk_factors')}`")

    lines.append("")
    lines.append("### Approval Summary")
    if governance_summary.get("approval_output_present"):
        lines.append(f"- Approval required: `{governance_summary.get('approval_required')}`")
        lines.append(f"- Approval status: `{governance_summary.get('approval_status')}`")
        lines.append(f"- Reviewer role: `{governance_summary.get('reviewer_role')}`")
        lines.append(f"- Approval ID: `{governance_summary.get('approval_id')}`")
        lines.append(f"- Action under review: `{governance_summary.get('action_under_review')}`")
    else:
        lines.append("- Approval output: `Not generated for this workflow`")

    if evidence_summary:
        lines.append("")
        lines.append("### PDF Policy Evidence")

        for index, evidence in enumerate(evidence_summary, start=1):
            lines.append(f"**Evidence {index}:**")
            lines.append(f"- Policy: `{evidence.get('policy_name')}`")
            lines.append(f"- Policy area: `{evidence.get('policy_area')}`")
            lines.append(f"- Action: `{evidence.get('action')}`")
            lines.append(f"- Severity: `{evidence.get('severity')}`")
            lines.append(f"- Source document: `{evidence.get('source_document')}`")
            lines.append(f"- Source page: `{evidence.get('source_page')}`")
            lines.append(f"- Confidence: `{evidence.get('confidence')}`")
            lines.append(f"- Evidence text: {evidence.get('evidence_text')}")
            lines.append("")

    lines.append("")
    lines.append("### Audit Summary")
    lines.append(f"- Audit status: `{governance_summary.get('audit_status')}`")
    lines.append(f"- Audit event ID: `{governance_summary.get('audit_event_id')}`")
    lines.append(f"- Audit database path: `{governance_summary.get('audit_database_path')}`")

    lines.append("")
    lines.append("### Recommended Next Action")
    lines.append(recommended_next_action)

    return "\n".join(lines)


# ============================================================
# LLM generation
# ============================================================

def _generate_response_style_variation() -> Dict[str, Any]:
    """
    Generates lightweight variation instructions.
    """

    styles = [
        "executive concise",
        "business analyst",
        "operations manager",
        "risk and governance focused",
        "supply chain planning focused",
        "audit-ready explanation",
    ]

    openings = [
        "Start with the final decision and explain the business implication.",
        "Start by summarizing what the workflow evaluated.",
        "Start by explaining whether the completed workflow output can be used.",
        "Start with the operational outcome and then explain governance.",
        "Start by highlighting the next action required.",
    ]

    structures = [
        "Use one compact paragraph for the natural language explanation.",
        "Use one paragraph followed by a short next-action sentence.",
        "Use a concise business-friendly paragraph.",
        "Use a manager-demo-ready executive paragraph.",
    ]

    return {
        "style": random.choice(styles),
        "opening_instruction": random.choice(openings),
        "structure_instruction": random.choice(structures),
        "variation_seed": f"{int(time.time())}-{random.randint(1000, 9999)}",
    }


def _build_llm_verified_facts(
    business_summary: Dict[str, Any],
    governance_summary: Dict[str, Any],
    evidence_summary: List[Dict[str, Any]],
    recommended_next_action: str,
) -> Dict[str, Any]:
    """
    Builds strict factual payload for LLM.
    """

    return {
        "business_summary": business_summary,
        "governance_summary": governance_summary,
        "policy_evidence_summary": evidence_summary,
        "recommended_next_action": recommended_next_action,
    }


def _llm_generate_final_response(
    verified_facts: Dict[str, Any],
    deterministic_natural_language_explanation: str,
) -> Dict[str, str]:
    """
    Uses LLM only for:
    - response_summary
    - natural_language_explanation

    The LLM does NOT generate:
    - detailed_response
    - recommended_next_action
    """

    style_variation = _generate_response_style_variation()

    system_message = """
You are a business communication assistant for an AgentOps Supply Chain Control Tower.

You must output JSON only.

Your task:
Generate only:
1. response_summary
2. natural_language_explanation

Do not generate detailed_response.
Do not generate recommended_next_action.
The detailed markdown response and next action are generated deterministically by the system.

Very important:
The natural_language_explanation must be LLM-generated and business-friendly. It must combine the factual outputs from forecasting, inventory, procurement, logistics, policy, risk, approval, audit, and policy context into one concise business-readable paragraph.

Strict factual rules:
- Use only the verified facts provided.
- Do not invent facts.
- Do not hide governance violations.
- Do not change final_decision.
- Do not change policy_decision.
- Do not change risk_score.
- Do not change risk_level.
- Do not change approval_status.
- Do not change reviewer_role.
- Do not change recommended_next_action.
- Do not say an action can proceed if final_decision is Block.
- Do not say an action can execute if final_decision is Escalate and approval_status is Pending.
- If an agent failed, mention that the decision is constrained by the failed agent output.
- If restricted data was requested or accessed, explicitly mention that governance issue.
- If unauthorized or user-forbidden dataset access occurred, explicitly mention that governance issue.
- If source citation is missing or the user requested no citations, explicitly mention the traceability issue.
- If final_decision is Block, clearly state that the recommendation must not be executed even if business agents produced outputs.

Inventory grounding rules:
- Do not describe inventory as sufficient if stock_position is "Below Reorder Point" or "Below Safety Stock".
- If stock_position is "Below Reorder Point", state that stock is below the reorder threshold.
- If shortage_quantity is 0, say there is no forecast-based shortage; do not automatically call inventory sufficient unless stock_position also indicates healthy/sufficient stock.
- Use procurement_required exactly as supplied in verified facts.
- If stock_position and procurement_required appear inconsistent, mention the inconsistency neutrally instead of resolving it yourself.

Procurement grounding rules:
- If procurement_recommendation_exists is false, do not say a supplier was selected or procurement was recommended.
- If procurement_recommendation_generated is false, do not describe procurement as a real procurement recommendation.
- If recommended_supplier_id is null, do not say a supplier was selected.
- If recommended_quantity is 0, do not describe procurement as a real procurement quantity.
- If procurement_status is "skipped", describe procurement as skipped or not required, not as executed.

Logistics grounding rules:
- If logistics_route_exists is false, do not say a route was selected.
- If route_generated is false, do not describe logistics as a real route recommendation.
- If recommended_route_id is null, do not say logistics selected a route.
- If logistics_status is "skipped", describe logistics as skipped or not required, not as executed.

Approval grounding rules:
- Do not use the word "approved" unless approval_status is exactly "Approved".
- Do not say "approval was granted" unless approval_status is exactly "Approved".
- If approval_output_present is false, do not say approval is pending, approved, rejected, blocked, granted, or assigned.
- If approval_output_present is false, say that no approval output was generated only if approval context is relevant.
- If final_decision is Allow and approval_output_present is false, say "allowed by policy" rather than "approved".
- If approval_status is "Blocked", do not say a team or reviewer blocked the action. Say the workflow was blocked by policy, and reviewer_role identifies the responsible review owner.

Skipped-step grounding rules:
- If inventory_status is "not_run", do not describe inventory as evaluated.
- If procurement_status is "not_run", do not describe procurement as recommended, approved, pending, or executable.
- If logistics_status is "not_run", do not describe logistics as recommended, approved, pending, or executable.
- If forbidden_steps or skip_reason are present, explain that those steps were intentionally skipped when relevant.
- Do not imply skipped steps were executed.

Writing rules:
- Make the response business-friendly and manager-demo-ready.
- Avoid robotic repetition.
- Explain what happened, why the decision was made, risk level, approval context if present, and next action.
- The natural_language_explanation should be a fresh paragraph and not a copy of the deterministic fallback.
- Preserve all critical facts exactly.
- Keep response_summary short.

Return JSON only.
"""

    user_message = f"""
STYLE VARIATION:
{style_variation}

VERIFIED FACTS:
{verified_facts}

DETERMINISTIC FALLBACK NATURAL LANGUAGE EXPLANATION:
{deterministic_natural_language_explanation}

Return JSON exactly in this shape:
{{
  "response_summary": "short executive summary",
  "natural_language_explanation": "one business-friendly paragraph generated from the verified facts"
}}
"""

    messages = [
        {"role": "system", "content": system_message.strip()},
        {"role": "user", "content": user_message.strip()},
    ]

    return call_llm_json(
        messages=messages,
        temperature=0.7,
        max_tokens=3500,
    )


def _validate_llm_output(
    llm_output: Dict[str, Any],
    deterministic_response_summary: str,
    deterministic_natural_language_explanation: str,
    deterministic_next_action: str,
) -> Dict[str, str]:
    """
    Validates LLM output shape.

    LLM is allowed to provide only:
    - response_summary
    - natural_language_explanation

    recommended_next_action is always deterministic.
    """

    response_summary = (
        llm_output.get("response_summary")
        or deterministic_response_summary
    )

    natural_language_explanation = (
        llm_output.get("natural_language_explanation")
        or deterministic_natural_language_explanation
    )

    return {
        "response_summary": str(response_summary),
        "natural_language_explanation": str(natural_language_explanation),
        "recommended_next_action": str(deterministic_next_action),
    }


def _replace_natural_language_section(
    detailed_response: str,
    natural_language_explanation: str,
) -> str:
    """
    Replaces the Natural Language Explanation section in markdown.
    """

    section_heading = "### Natural Language Explanation"

    if section_heading not in detailed_response:
        return (
            detailed_response
            + "\n\n### Natural Language Explanation\n"
            + natural_language_explanation
        )

    start = detailed_response.find(section_heading)
    content_start = start + len(section_heading)
    next_section_start = detailed_response.find("\n### ", content_start)

    if next_section_start == -1:
        return (
            detailed_response[:content_start]
            + "\n"
            + natural_language_explanation
        )

    return (
        detailed_response[:content_start]
        + "\n"
        + natural_language_explanation
        + "\n"
        + detailed_response[next_section_start:]
    )


def _build_verified_facts_block(
    final_decision: str,
    governance_summary: Dict[str, Any],
) -> str:
    """
    Appends deterministic verified facts after final response.
    """

    return f"""

---

### Verified System Facts
- Final decision: `{final_decision}`
- Policy decision: `{governance_summary.get("policy_decision")}`
- Context build status: `{governance_summary.get("context_build_status")}`
- Governance violations: `{governance_summary.get("governance_violations")}`
- Risk score: `{governance_summary.get("risk_score")}`
- Risk level: `{governance_summary.get("risk_level")}`
- Approval output present: `{governance_summary.get("approval_output_present")}`
- Approval required: `{governance_summary.get("approval_required")}`
- Approval status: `{governance_summary.get("approval_status")}`
- Reviewer role: `{governance_summary.get("reviewer_role")}`
- Forbidden steps: `{governance_summary.get("forbidden_steps")}`
- Requested restricted datasets: `{governance_summary.get("requested_restricted_datasets")}`
- Restricted data accessed: `{governance_summary.get("restricted_data_accessed")}`
- Unauthorized dataset accessed: `{governance_summary.get("unauthorized_dataset_accessed")}`
- Source citation missing: `{governance_summary.get("source_citation_missing")}`
- PDF policy source pages: `{governance_summary.get("policy_rag_source_pages")}`
- Final response source: `{governance_summary.get("final_response_source")}`
"""


# ============================================================
# Main LangGraph node
# ============================================================

def final_response_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    LangGraph Final Response node.
    """

    policy_context_output = _as_dict(state.get("policy_context_output"))
    policy_rag_decision = _as_dict(state.get("policy_rag_decision"))
    approval_output = _as_dict(state.get("approval_output"))

    business_summary = _build_business_summary(state)
    governance_summary = _build_governance_summary(state)
    evidence_summary = _extract_policy_evidence(policy_rag_decision)

    final_decision = (
        state.get("final_decision")
        or governance_summary.get("policy_decision")
        or "Unknown"
    )

    deterministic_next_action = _determine_recommended_next_action(
        final_decision=final_decision,
        approval_output=approval_output,
        governance_summary=governance_summary,
    )

    deterministic_response_summary = _build_response_summary(
        business_summary=business_summary,
        governance_summary=governance_summary,
    )

    deterministic_natural_language_explanation = (
        _build_deterministic_natural_language_explanation(
            business_summary=business_summary,
            governance_summary=governance_summary,
            recommended_next_action=deterministic_next_action,
        )
    )

    deterministic_detailed_response = _build_deterministic_detailed_response(
        state=state,
        business_summary=business_summary,
        governance_summary=governance_summary,
        evidence_summary=evidence_summary,
        natural_language_explanation=deterministic_natural_language_explanation,
        recommended_next_action=deterministic_next_action,
    )

    response_summary = deterministic_response_summary
    natural_language_explanation = deterministic_natural_language_explanation
    recommended_next_action = deterministic_next_action
    detailed_response = deterministic_detailed_response

    llm_used = False
    llm_error = None

    source_context = _collect_source_files_and_records(
        state=state,
        policy_context_output=policy_context_output,
    )

    verified_facts = _build_llm_verified_facts(
        business_summary=business_summary,
        governance_summary=governance_summary,
        evidence_summary=evidence_summary,
        recommended_next_action=deterministic_next_action,
    )

    if ENABLE_LLM_FINAL_RESPONSE:
        try:
            llm_output = _llm_generate_final_response(
                verified_facts=verified_facts,
                deterministic_natural_language_explanation=deterministic_natural_language_explanation,
            )

            validated_output = _validate_llm_output(
                llm_output=llm_output,
                deterministic_response_summary=deterministic_response_summary,
                deterministic_natural_language_explanation=deterministic_natural_language_explanation,
                deterministic_next_action=deterministic_next_action,
            )

            response_summary = validated_output["response_summary"]
            natural_language_explanation = validated_output["natural_language_explanation"]
            recommended_next_action = validated_output["recommended_next_action"]

            detailed_response = _replace_natural_language_section(
                detailed_response=deterministic_detailed_response,
                natural_language_explanation=natural_language_explanation,
            )

            llm_used = True

        except Exception as exc:
            llm_error = str(exc)

    governance_summary["llm_final_response_enabled"] = ENABLE_LLM_FINAL_RESPONSE
    governance_summary["llm_final_response_used"] = llm_used
    governance_summary["llm_final_response_error"] = llm_error
    governance_summary["final_response_source"] = (
        "llm_generated_business_explanation"
        if llm_used
        else "deterministic_fallback"
    )

    if not llm_used and llm_error:
        detailed_response = (
            deterministic_detailed_response
            + "\n\n---\n"
            + "**LLM generation note:** LLM final response generation failed. "
            + "The deterministic fallback response was returned instead. "
            + f"Error: {llm_error}"
        )

    detailed_response = detailed_response + _build_verified_facts_block(
        final_decision=final_decision,
        governance_summary=governance_summary,
    )

    output = FinalResponseOutput(
        run_id=state.get("run_id", "RUN-UNKNOWN"),
        step_id="STEP-010",
        agent_id="final_response_agent",
        agent_name="LLM Final Response Agent",
        status="success",
        source_files=source_context["source_files"],
        source_record_ids=source_context["source_record_ids"],
        message=response_summary,
        final_decision=final_decision,
        response_summary=response_summary,
        natural_language_explanation=natural_language_explanation,
        recommended_next_action=recommended_next_action,
        business_summary=business_summary,
        governance_summary=governance_summary,
        evidence_summary=evidence_summary,
        detailed_response=detailed_response,
    )

    return {
        "final_response_output": _safe_model_dump(output),
        "final_response": detailed_response,
    }


# Backward-compatible alias if workflow_graph imports a different name.
final_response_agent = final_response_node