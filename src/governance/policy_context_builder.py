"""
Policy Context Builder for the AgentOps Supply Chain Control Tower.

Purpose
-------
This node converts scattered workflow facts into one normalized governance
context for the Policy Engine, Risk Engine, Approval Agent, Audit Logger, and
Final Response Agent.

It does NOT make the final policy decision.
It only builds factual context from:
- Coordinator output
- Forecasting output
- Inventory output
- Procurement output
- Logistics output
- Data access logs
- User constraints
- Source traceability
- Agent failure status

The Policy Engine should later consume `policy_context_output` and decide:
- Allow
- Escalate
- Block
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from src.services.data_access_guard import (
    RESTRICTED_DATASETS,
    build_policy_context_access_summary,
    normalize_dataset_list,
)


# ============================================================
# Constants
# ============================================================

BUSINESS_STEPS = {
    "forecasting",
    "inventory",
    "procurement",
    "logistics",
}

AGENT_OUTPUT_KEYS = {
    "forecasting": "forecasting_output",
    "inventory": "inventory_output",
    "procurement": "procurement_output",
    "logistics": "logistics_output",
}

TRACEABILITY_RELEVANT_OUTPUTS = [
    "forecasting_output",
    "inventory_output",
    "procurement_output",
    "logistics_output",
]

NON_SUBSTANTIVE_STATUSES = {
    "skipped",
    "not_required",
    "not required",
    "not_run",
    "not run",
}


# ============================================================
# Utility helpers
# ============================================================

def _as_dict(value: Any) -> Dict[str, Any]:
    """
    Converts Pydantic object or dict-like object to dictionary.
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
    Safely converts a value to a list.
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
    Converts a value to a clean list[str].
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


def _as_bool(value: Any) -> bool:
    """
    Safely converts common bool-like values to bool.
    """

    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "y", "1"}

    if isinstance(value, (int, float)):
        return bool(value)

    return False


def _safe_float(value: Any, default: float = 0.0) -> float:
    """
    Safely converts a value to float.
    """

    if value is None:
        return default

    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    """
    Safely converts a value to int.
    """

    if value is None:
        return default

    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return default


def _get_output_status(output: Dict[str, Any]) -> str:
    """
    Returns normalized status from an agent output.
    """

    if not output:
        return "not_run"

    status = str(output.get("status", "unknown")).strip().lower()

    if not status:
        return "unknown"

    return status


def _has_traceability(output: Dict[str, Any]) -> bool:
    """
    Checks whether an agent output has both source_files and source_record_ids.
    """

    source_files = _string_list(output.get("source_files", []))
    source_record_ids = _string_list(output.get("source_record_ids", []))

    return bool(source_files) and bool(source_record_ids)


def _is_successful_output(output: Dict[str, Any]) -> bool:
    """
    Returns True if an output exists and status is success.
    """

    return bool(output) and _get_output_status(output) == "success"


def _is_skipped_or_non_action_output(output: Dict[str, Any]) -> bool:
    """
    Returns True when an output explicitly represents skipped/no-action work.
    """

    status = _get_output_status(output)

    if status in NON_SUBSTANTIVE_STATUSES:
        return True

    action_required = output.get("action_required")
    recommendation_generated = output.get("recommendation_generated")
    route_generated = output.get("route_generated")

    if action_required is not None and not _as_bool(action_required):
        if recommendation_generated is not None and not _as_bool(recommendation_generated):
            return True

        if route_generated is not None and not _as_bool(route_generated):
            return True

    return False


def _is_substantive_output(output_key: str, output: Dict[str, Any]) -> bool:
    """
    Determines whether an output is substantive enough to require traceability.

    This prevents no-op/skipped outputs from being falsely treated as missing
    source citations.

    General principles:
    - failed / skipped / not_run outputs are not substantive recommendations
    - forecasting is substantive if it produced forecasted_demand
    - inventory is substantive if it produced current_stock
    - procurement is substantive if it generated an actual recommendation
    - logistics is substantive if it generated an actual route
    """

    if not output:
        return False

    status = _get_output_status(output)

    if status in {"failed", "not_run", "unknown"}:
        return False

    if _is_skipped_or_non_action_output(output):
        return False

    if output_key == "forecasting_output":
        return status == "success" and output.get("forecasted_demand") is not None

    if output_key == "inventory_output":
        return status == "success" and output.get("current_stock") is not None

    if output_key == "procurement_output":
        recommendation_generated = output.get("recommendation_generated")

        if recommendation_generated is not None:
            return status == "success" and _as_bool(recommendation_generated)

        recommended_supplier_id = output.get("recommended_supplier_id")
        recommended_quantity = _safe_int(output.get("recommended_quantity"), 0)
        procurement_value = _safe_float(output.get("procurement_value"), 0.0)

        return bool(recommended_supplier_id) and (
            recommended_quantity > 0 or procurement_value > 0
        )

    if output_key == "logistics_output":
        route_generated = output.get("route_generated")

        if route_generated is not None:
            return status == "success" and _as_bool(route_generated)

        recommended_route_id = output.get("recommended_route_id")

        return bool(recommended_route_id)

    return status == "success"


# ============================================================
# Context extraction helpers
# ============================================================

def _extract_agent_outputs(state: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    Extracts major agent outputs from state.
    """

    return {
        "coordinator_output": _as_dict(state.get("coordinator_output")),
        "forecasting_output": _as_dict(state.get("forecasting_output")),
        "inventory_output": _as_dict(state.get("inventory_output")),
        "procurement_output": _as_dict(state.get("procurement_output")),
        "logistics_output": _as_dict(state.get("logistics_output")),
        "policy_rag_decision": _as_dict(state.get("policy_rag_decision")),
    }


def _build_agent_status_summary(outputs: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """
    Builds status summary for business agents.
    """

    forecasting_status = _get_output_status(outputs["forecasting_output"])
    inventory_status = _get_output_status(outputs["inventory_output"])
    procurement_status = _get_output_status(outputs["procurement_output"])
    logistics_status = _get_output_status(outputs["logistics_output"])

    status_by_agent = {
        "forecasting_agent": forecasting_status,
        "inventory_agent": inventory_status,
        "procurement_agent": procurement_status,
        "logistics_agent": logistics_status,
    }

    failed_agents = [
        agent_id
        for agent_id, status in status_by_agent.items()
        if status == "failed"
    ]

    successful_agents = [
        agent_id
        for agent_id, status in status_by_agent.items()
        if status == "success"
    ]

    skipped_agents = [
        agent_id
        for agent_id, status in status_by_agent.items()
        if status in NON_SUBSTANTIVE_STATUSES
    ]

    not_run_agents = [
        agent_id
        for agent_id, status in status_by_agent.items()
        if status == "not_run"
    ]

    non_action_agents = []

    if _is_skipped_or_non_action_output(outputs["procurement_output"]):
        non_action_agents.append("procurement_agent")

    if _is_skipped_or_non_action_output(outputs["logistics_output"]):
        non_action_agents.append("logistics_agent")

    return {
        "forecasting_status": forecasting_status,
        "inventory_status": inventory_status,
        "procurement_status": procurement_status,
        "logistics_status": logistics_status,
        "status_by_agent": status_by_agent,
        "failed_agents": failed_agents,
        "successful_agents": successful_agents,
        "skipped_agents": skipped_agents,
        "not_run_agents": not_run_agents,
        "non_action_agents": list(dict.fromkeys(non_action_agents)),
        "any_agent_failed": bool(failed_agents),
    }


def _build_forbidden_step_summary(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compares forbidden_steps with completed_steps to detect instruction violations.
    """

    forbidden_steps = _string_list(state.get("forbidden_steps", []))
    completed_steps = _string_list(state.get("completed_steps", []))
    skip_reason = _as_dict(state.get("skip_reason", {}))

    completed_forbidden_steps = [
        step
        for step in forbidden_steps
        if step in completed_steps and step in BUSINESS_STEPS
    ]

    user_instruction_violation_from_steps = bool(completed_forbidden_steps)

    return {
        "forbidden_steps": forbidden_steps,
        "completed_steps": completed_steps,
        "completed_forbidden_steps": completed_forbidden_steps,
        "skip_reason": skip_reason,
        "user_instruction_violation_from_steps": user_instruction_violation_from_steps,
    }


def _build_source_traceability_summary(
    state: Dict[str, Any],
    outputs: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Checks source traceability only for substantive outputs.

    Important distinction:
    - user_requested_no_citations: user asked to omit evidence
    - source_citation_missing: actual substantive output lacks evidence

    Skipped/non-action outputs are not considered missing citations because
    they do not produce a recommendation, forecast, route, or business action
    needing source evidence.
    """

    missing_source_outputs: List[str] = []
    substantive_outputs_checked: List[str] = []
    non_substantive_outputs_ignored: List[str] = []

    for output_key in TRACEABILITY_RELEVANT_OUTPUTS:
        output = outputs.get(output_key, {})

        if not output:
            continue

        if not _is_substantive_output(output_key, output):
            non_substantive_outputs_ignored.append(output_key)
            continue

        substantive_outputs_checked.append(output_key)

        if not _has_traceability(output):
            missing_source_outputs.append(output_key)

    source_citation_missing_from_outputs = bool(missing_source_outputs)

    source_citation_missing = bool(
        _as_bool(state.get("source_citation_missing", False))
        or source_citation_missing_from_outputs
    )

    return {
        "user_requested_no_citations": _as_bool(state.get("user_requested_no_citations", False)),
        "source_citation_missing": source_citation_missing,
        "source_citation_missing_from_outputs": source_citation_missing_from_outputs,
        "missing_source_outputs": missing_source_outputs,
        "successful_outputs_checked_for_traceability": substantive_outputs_checked,
        "substantive_outputs_checked_for_traceability": substantive_outputs_checked,
        "non_substantive_outputs_ignored_for_traceability": non_substantive_outputs_ignored,
    }


def _extract_forecasting_context(forecasting_output: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extracts forecasting facts.
    """

    return {
        "forecasted_demand": forecasting_output.get("forecasted_demand"),
        "forecast_confidence": forecasting_output.get("forecast_confidence"),
        "demand_spike_detected": forecasting_output.get("demand_spike_detected"),
        "forecasting_message": forecasting_output.get("message"),
    }


def _extract_inventory_context(inventory_output: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extracts inventory facts.
    """

    return {
        "current_stock": inventory_output.get("current_stock"),
        "safety_stock": inventory_output.get("safety_stock"),
        "reorder_point": inventory_output.get("reorder_point"),
        "shortage_quantity": inventory_output.get("shortage_quantity"),
        "procurement_required": inventory_output.get("procurement_required"),
        "stock_position": inventory_output.get("stock_position"),
        "stock_below_reorder_point": inventory_output.get("stock_below_reorder_point"),
        "forecast_creates_shortage": inventory_output.get("forecast_creates_shortage"),
        "inventory_message": inventory_output.get("message"),
    }


def _extract_procurement_context(procurement_output: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extracts supplier and procurement governance facts.

    Non-action procurement outputs are treated as no recommendation.
    """

    status = _get_output_status(procurement_output)
    recommendation_generated = procurement_output.get("recommendation_generated")
    action_required = procurement_output.get("action_required")

    recommended_supplier_id = procurement_output.get("recommended_supplier_id")
    recommended_quantity = _safe_int(procurement_output.get("recommended_quantity"), 0)
    procurement_value = _safe_float(procurement_output.get("procurement_value"), 0.0)

    if recommendation_generated is not None:
        procurement_recommendation_exists = (
            status == "success"
            and _as_bool(recommendation_generated)
        )
    else:
        procurement_recommendation_exists = bool(
            status == "success"
            and recommended_supplier_id
            and (recommended_quantity > 0 or procurement_value > 0)
        )

    if action_required is not None and not _as_bool(action_required):
        procurement_recommendation_exists = False

    is_approved = procurement_output.get("is_approved")
    compliance_status = procurement_output.get("compliance_status")

    supplier_is_unapproved = bool(
        procurement_recommendation_exists
        and recommended_supplier_id
        and str(is_approved).strip().lower() not in {"yes", "true", "approved"}
    )

    supplier_is_non_compliant = bool(
        procurement_recommendation_exists
        and recommended_supplier_id
        and str(compliance_status).strip().lower() == "non-compliant"
    )

    supplier_under_review = bool(
        procurement_recommendation_exists
        and recommended_supplier_id
        and str(compliance_status).strip().lower() == "under review"
    )

    if not procurement_recommendation_exists:
        recommended_supplier_id = None
        recommended_quantity = 0
        procurement_value = 0.0

    return {
        "procurement_recommendation_exists": procurement_recommendation_exists,
        "procurement_action_required": _as_bool(action_required) if action_required is not None else procurement_recommendation_exists,
        "procurement_recommendation_generated": procurement_recommendation_exists,
        "procurement_skipped_reason": procurement_output.get("procurement_skipped_reason"),
        "recommended_supplier_id": recommended_supplier_id,
        "recommended_supplier_name": procurement_output.get("recommended_supplier_name") if procurement_recommendation_exists else None,
        "supplier_region": procurement_output.get("supplier_region") if procurement_recommendation_exists else None,
        "supplier_is_approved": is_approved if procurement_recommendation_exists else None,
        "supplier_compliance_status": compliance_status if procurement_recommendation_exists else None,
        "supplier_is_unapproved": supplier_is_unapproved,
        "supplier_is_non_compliant": supplier_is_non_compliant,
        "supplier_under_review": supplier_under_review,
        "recommended_quantity": recommended_quantity,
        "unit_cost": procurement_output.get("unit_cost") if procurement_recommendation_exists else None,
        "lead_time_days": procurement_output.get("lead_time_days") if procurement_recommendation_exists else None,
        "reliability_score": procurement_output.get("reliability_score") if procurement_recommendation_exists else None,
        "max_capacity": procurement_output.get("max_capacity") if procurement_recommendation_exists else None,
        "procurement_value": procurement_value,
        "supplier_selection_reason": procurement_output.get("supplier_selection_reason"),
        "procurement_message": procurement_output.get("message"),
    }


def _extract_logistics_context(logistics_output: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extracts route and disruption governance facts.

    Non-action logistics outputs are treated as no route recommendation.
    """

    status = _get_output_status(logistics_output)
    route_generated = logistics_output.get("route_generated")
    action_required = logistics_output.get("action_required")
    recommended_route_id = logistics_output.get("recommended_route_id")

    if route_generated is not None:
        logistics_route_exists = status == "success" and _as_bool(route_generated)
    else:
        logistics_route_exists = bool(status == "success" and recommended_route_id)

    if action_required is not None and not _as_bool(action_required):
        logistics_route_exists = False

    route_disruption_exists = bool(
        logistics_route_exists
        and _as_bool(logistics_output.get("route_disruption_exists", False))
    )

    route_disruption_severity = (
        logistics_output.get("route_disruption_severity", "None")
        if logistics_route_exists
        else "None"
    )

    route_disruption_status = (
        logistics_output.get("route_disruption_status", "None")
        if logistics_route_exists
        else "None"
    )

    route_high_or_critical_disruption = bool(
        route_disruption_exists
        and str(route_disruption_severity) in {"High", "Critical"}
    )

    route_medium_or_higher_disruption = bool(
        route_disruption_exists
        and str(route_disruption_severity) in {"Medium", "High", "Critical"}
    )

    return {
        "logistics_route_exists": logistics_route_exists,
        "logistics_action_required": _as_bool(action_required) if action_required is not None else logistics_route_exists,
        "route_generated": logistics_route_exists,
        "logistics_skipped_reason": logistics_output.get("logistics_skipped_reason"),
        "recommended_route_id": recommended_route_id if logistics_route_exists else None,
        "route_risk_level": logistics_output.get("route_risk_level") if logistics_route_exists else None,
        "route_score": logistics_output.get("route_score") if logistics_route_exists else None,
        "route_disruption_exists": route_disruption_exists,
        "route_disruption_severity": route_disruption_severity,
        "route_disruption_status": route_disruption_status,
        "route_high_or_critical_disruption": route_high_or_critical_disruption,
        "route_medium_or_higher_disruption": route_medium_or_higher_disruption,
        "impact_delay_days": logistics_output.get("impact_delay_days") if logistics_route_exists else None,
        "impact_cost": logistics_output.get("impact_cost") if logistics_route_exists else None,
        "adjusted_time_days": logistics_output.get("adjusted_time_days") if logistics_route_exists else None,
        "adjusted_route_cost": logistics_output.get("adjusted_route_cost") if logistics_route_exists else None,
        "logistics_message": logistics_output.get("message"),
    }


def _build_access_governance_summary(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Builds access-governance facts from state and data_access_log.
    """

    access_summary = build_policy_context_access_summary(state)

    requested_datasets = normalize_dataset_list(
        state.get("requested_datasets", access_summary.get("requested_datasets", []))
    )

    requested_restricted_datasets = [
        dataset for dataset in requested_datasets
        if dataset in RESTRICTED_DATASETS
    ]

    user_requested_restricted_data = bool(
        _as_bool(state.get("user_requested_restricted_data", False))
        or bool(access_summary.get("user_requested_restricted_data", False))
        or bool(requested_restricted_datasets)
    )

    return {
        **access_summary,
        "requested_datasets": requested_datasets,
        "requested_restricted_datasets": requested_restricted_datasets,
        "user_requested_restricted_data": user_requested_restricted_data,
    }


def _build_policy_rag_summary(policy_rag_decision: Dict[str, Any]) -> Dict[str, Any]:
    """
    Carries existing policy RAG evidence if present.
    """

    if not policy_rag_decision:
        return {
            "policy_rag_available": False,
            "policy_rag_decision": None,
            "policy_rag_confidence": None,
            "policy_rag_evidence": [],
        }

    return {
        "policy_rag_available": True,
        "policy_rag_decision": policy_rag_decision.get("decision"),
        "policy_rag_confidence": policy_rag_decision.get("confidence"),
        "policy_rag_evidence": policy_rag_decision.get("evidence", []),
    }


# ============================================================
# Main context builder
# ============================================================

def build_policy_context(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Builds normalized factual policy context from the full graph state.
    """

    outputs = _extract_agent_outputs(state)
    coordinator_output = outputs["coordinator_output"]

    product_id = state.get("product_id") or coordinator_output.get("product_id")
    product_name = state.get("product_name") or coordinator_output.get("product_name")
    region = state.get("region") or coordinator_output.get("region")
    supplier_id = state.get("supplier_id") or coordinator_output.get("supplier_id")
    selection_strategy = state.get("selection_strategy") or coordinator_output.get("selection_strategy")

    agent_status_summary = _build_agent_status_summary(outputs)
    forbidden_step_summary = _build_forbidden_step_summary(state)
    traceability_summary = _build_source_traceability_summary(state, outputs)
    access_summary = _build_access_governance_summary(state)
    policy_rag_summary = _build_policy_rag_summary(outputs["policy_rag_decision"])

    forecasting_context = _extract_forecasting_context(outputs["forecasting_output"])
    inventory_context = _extract_inventory_context(outputs["inventory_output"])
    procurement_context = _extract_procurement_context(outputs["procurement_output"])
    logistics_context = _extract_logistics_context(outputs["logistics_output"])

    # Prefer actual selected supplier from procurement context when available.
    supplier_id = (
        procurement_context.get("recommended_supplier_id")
        or supplier_id
    )

    user_instruction_violation = bool(
        _as_bool(state.get("user_instruction_violation", False))
        or access_summary.get("user_instruction_violation", False)
        or forbidden_step_summary.get("user_instruction_violation_from_steps", False)
    )

    governance_violations: List[str] = []

    if access_summary.get("user_requested_restricted_data"):
        governance_violations.append("user_requested_restricted_data")

    if access_summary.get("restricted_data_accessed"):
        governance_violations.append("restricted_data_accessed")

    if access_summary.get("unauthorized_dataset_accessed"):
        governance_violations.append("unauthorized_dataset_accessed")

    if access_summary.get("agent_accessed_forbidden_dataset"):
        governance_violations.append("agent_accessed_forbidden_dataset")

    if user_instruction_violation:
        governance_violations.append("user_instruction_violation")

    if traceability_summary.get("user_requested_no_citations"):
        governance_violations.append("user_requested_no_citations")

    if traceability_summary.get("source_citation_missing"):
        governance_violations.append("source_citation_missing")

    if procurement_context.get("supplier_is_unapproved"):
        governance_violations.append("supplier_is_unapproved")

    if procurement_context.get("supplier_is_non_compliant"):
        governance_violations.append("supplier_is_non_compliant")

    if logistics_context.get("route_medium_or_higher_disruption"):
        governance_violations.append("route_medium_or_higher_disruption")

    if agent_status_summary.get("any_agent_failed"):
        governance_violations.append("agent_failure_present")

    governance_violations = list(dict.fromkeys(governance_violations))

    context = {
        "context_build_status": "success",
        "context_build_timestamp": datetime.now(timezone.utc).isoformat(),
        "context_builder_version": "1.1",

        # Run and entity context
        "run_id": state.get("run_id"),
        "user_query": state.get("user_query"),
        "user_role": state.get("user_role"),
        "intent": state.get("intent") or coordinator_output.get("intent"),
        "product_id": product_id,
        "product_name": product_name,
        "region": region,
        "supplier_id": supplier_id,
        "selection_strategy": selection_strategy,

        # Workflow context
        "workflow_steps": _string_list(state.get("workflow_steps", [])),
        "requested_steps": _string_list(state.get("requested_steps", [])),
        **forbidden_step_summary,

        # Agent status context
        **agent_status_summary,

        # Access governance context
        **access_summary,

        # Source traceability context
        **traceability_summary,

        # Business facts
        **forecasting_context,
        **inventory_context,
        **procurement_context,
        **logistics_context,

        # Policy RAG facts, if already present
        **policy_rag_summary,

        # External/tool governance
        "external_communication_requested": _as_bool(state.get("external_communication_requested", False)),
        "external_communication_attempted": _as_bool(state.get("external_communication_attempted", False)),
        "unauthorized_tool_used": _as_bool(state.get("unauthorized_tool_used", False)),
        "tool_called": state.get("tool_called"),
        "tools_called": _string_list(state.get("tools_called", [])),

        # Consolidated governance facts
        "user_instruction_violation": user_instruction_violation,
        "governance_violations": governance_violations,
        "governance_violation_count": len(governance_violations),
        "has_governance_violation": bool(governance_violations),

        # Messages for evidence-grounded final response
        "agent_messages": {
            "forecasting": forecasting_context.get("forecasting_message"),
            "inventory": inventory_context.get("inventory_message"),
            "procurement": procurement_context.get("procurement_message"),
            "logistics": logistics_context.get("logistics_message"),
        },
    }

    return context


# ============================================================
# LangGraph node
# ============================================================

def policy_context_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    LangGraph node that builds policy_context_output.

    This node does not make Allow/Escalate/Block decisions.
    It returns factual normalized context for downstream governance agents.
    """

    try:
        policy_context_output = build_policy_context(state)

        return {
            "policy_context_output": policy_context_output,
            # Keep these important flags top-level for backward compatibility.
            "source_citation_missing": policy_context_output.get("source_citation_missing", False),
            "user_instruction_violation": policy_context_output.get("user_instruction_violation", False),
            "restricted_data_accessed": policy_context_output.get("restricted_data_accessed", False),
            "unauthorized_dataset_accessed": policy_context_output.get("unauthorized_dataset_accessed", False),
            "agent_accessed_forbidden_dataset": policy_context_output.get("agent_accessed_forbidden_dataset", False),
            "user_requested_restricted_data": policy_context_output.get("user_requested_restricted_data", False),
            "user_requested_no_citations": policy_context_output.get("user_requested_no_citations", False),
        }

    except Exception as exc:
        failed_context = {
            "context_build_status": "failed",
            "context_build_timestamp": datetime.now(timezone.utc).isoformat(),
            "context_builder_version": "1.1",
            "error": str(exc),
            "run_id": state.get("run_id"),
            "user_query": state.get("user_query"),
            "product_id": state.get("product_id"),
            "region": state.get("region"),
            "governance_violations": ["policy_context_build_failed"],
            "has_governance_violation": True,
        }

        errors = list(state.get("errors", []))
        errors.append(
            {
                "step": "policy_context",
                "error": str(exc),
            }
        )

        return {
            "policy_context_output": failed_context,
            "errors": errors,
        }


# Backward-compatible alias if graph imports a different name.
policy_context_builder = policy_context_node


# ============================================================
# Optional local smoke test
# ============================================================

if __name__ == "__main__":
    test_state = {
        "run_id": "RUN-POLICY-CONTEXT-TEST-001",
        "user_query": "Use payroll.csv to verify whether procurement for P-103 in North should be approved.",
        "user_role": "Supply Chain Planner",
        "intent": "procurement",
        "product_id": "P-103",
        "product_name": "Control Valve",
        "region": "North",
        "requested_datasets": ["payroll.csv"],
        "user_requested_restricted_data": True,
        "completed_steps": ["coordinator", "inventory", "procurement"],
        "forbidden_steps": [],
        "data_access_log": [
            {
                "agent_id": "procurement_agent",
                "file_name": "products.csv",
                "allowed": True,
                "denied": False,
                "restricted": False,
                "forbidden_by_user": False,
            },
            {
                "agent_id": "procurement_agent",
                "file_name": "suppliers.csv",
                "allowed": True,
                "denied": False,
                "restricted": False,
                "forbidden_by_user": False,
            },
        ],
        "dataset_accessed": ["products.csv", "suppliers.csv"],
        "dataset_access_attempted": ["products.csv", "suppliers.csv"],
        "procurement_output": {
            "status": "success",
            "source_files": ["suppliers.csv", "products.csv"],
            "source_record_ids": ["S-007", "P-103"],
            "recommended_supplier_id": "S-007",
            "recommended_supplier_name": "Omega Precision Works",
            "recommended_quantity": 60,
            "is_approved": "Yes",
            "compliance_status": "Compliant",
            "procurement_value": 198000,
            "recommendation_generated": True,
            "action_required": True,
            "message": "Procurement recommendation generated.",
        },
        "logistics_output": {
            "status": "skipped",
            "source_files": ["suppliers.csv", "products.csv"],
            "source_record_ids": ["S-007", "P-103"],
            "recommended_route_id": None,
            "route_generated": False,
            "action_required": False,
            "logistics_skipped_reason": "Logistics planning skipped because route planning was not required.",
            "message": "Logistics planning skipped.",
        },
    }

    result = policy_context_node(test_state)

    print("Policy Context Builder executed.")
    print(result["policy_context_output"])