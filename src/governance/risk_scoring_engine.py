from typing import Any, Dict, List, Tuple

from src.schemas.governance import (
    RiskFactorTriggered,
    RiskScoringOutput,
)


# ============================================================
# Risk Scoring Engine
# ============================================================
# Purpose:
# Quantifies workflow/action risk after Policy Context Builder
# and Policy Engine have run.
#
# Important:
# - Does NOT call LLM.
# - Does NOT call RAG.
# - Does NOT call Azure OpenAI.
# - Does NOT call Azure AI Search.
# - Uses only structured state already available in LangGraph.
#
# Main source of truth:
# - policy_context_output
#
# Fallback source:
# - older top-level state fields and agent outputs
# ============================================================


BASE_SCORE = 10
MAX_SCORE = 100

HIGH_VALUE_PROCUREMENT_THRESHOLD = 50000.0
LOW_FORECAST_CONFIDENCE_THRESHOLD = 0.70
LOW_POLICY_RAG_CONFIDENCE_THRESHOLD = 0.70


# ============================================================
# Risk factor points
# ============================================================

RISK_POINTS = {
    # Procurement / supplier
    "high_value_procurement": 30,
    "unapproved_vendor": 40,
    "non_compliant_supplier": 40,
    "supplier_under_review": 15,

    # Data governance
    "user_requested_restricted_data": 35,
    "restricted_data_access": 40,
    "unauthorized_dataset_access": 40,
    "user_forbidden_dataset_access": 40,

    # User instruction / audit traceability
    "user_instruction_violation": 30,
    "user_requested_no_citations": 30,
    "missing_source_citation": 25,

    # Forecasting
    "low_forecast_confidence": 20,

    # External communication / tool governance
    "external_communication_requested": 15,
    "external_communication_attempted": 25,
    "unauthorized_tool_used": 30,

    # Agent / workflow reliability
    "agent_failure_present": 25,
    "inactive_agent_action": 40,

    # Policy decision / RAG interpretation
    "policy_block_decision": 40,
    "policy_escalate_decision": 20,
    "policy_rag_evidence_missing": 20,
    "policy_rag_low_confidence": 15,
    "policy_rag_guardrail_triggered": 15,
    "policy_rag_failed": 20,
}


# Severity-aware logistics disruption scoring
ROUTE_DISRUPTION_POINTS = {
    "Low": 10,
    "Medium": 15,
    "High": 25,
    "Critical": 35,
}


# ============================================================
# Risk factor categories
# ============================================================

RISK_CATEGORIES = {
    # Procurement / supplier
    "high_value_procurement": "Financial Risk",
    "unapproved_vendor": "Supplier Compliance Risk",
    "non_compliant_supplier": "Supplier Compliance Risk",
    "supplier_under_review": "Supplier Compliance Risk",

    # Data governance
    "user_requested_restricted_data": "Data Governance Risk",
    "restricted_data_access": "Data Governance Risk",
    "unauthorized_dataset_access": "Data Access Control Risk",
    "user_forbidden_dataset_access": "User Instruction Governance Risk",

    # User instruction / audit traceability
    "user_instruction_violation": "User Instruction Governance Risk",
    "user_requested_no_citations": "Traceability Risk",
    "missing_source_citation": "Traceability Risk",

    # Forecasting
    "low_forecast_confidence": "Forecasting Risk",

    # External communication / tool governance
    "external_communication_requested": "External Communication Risk",
    "external_communication_attempted": "External Communication Risk",
    "unauthorized_tool_used": "Tool Governance Risk",

    # Agent / workflow reliability
    "agent_failure_present": "Workflow Reliability Risk",
    "inactive_agent_action": "Agent Governance Risk",

    # Policy decision / RAG interpretation
    "policy_block_decision": "Policy Enforcement Risk",
    "policy_escalate_decision": "Policy Enforcement Risk",
    "policy_rag_evidence_missing": "Policy Interpretation Risk",
    "policy_rag_low_confidence": "Policy Interpretation Risk",
    "policy_rag_guardrail_triggered": "Policy Interpretation Risk",
    "policy_rag_failed": "Policy Interpretation Risk",

    # Logistics
    "active_low_route_disruption": "Operational Risk",
    "active_medium_route_disruption": "Operational Risk",
    "active_high_route_disruption": "Operational Risk",
    "active_critical_route_disruption": "Operational Risk",
}


RESTRICTED_DATASETS = {
    "hr_data.csv",
    "payroll.csv",
    "employee_records.csv",
    "customer_pii.csv",
}


# ============================================================
# Utility helpers
# ============================================================

def _safe_model_dump(model: Any) -> Dict[str, Any]:
    """
    Supports both Pydantic v1 and v2 serialization.
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
    Converts Pydantic object or dict-like object to plain dictionary.
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
    Safely converts a value to list.
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


def _safe_number(value: Any, default: float = 0.0) -> float:
    """
    Safely converts value to float.
    Returns default when conversion fails.
    """

    if value is None:
        return default

    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_bool(value: Any, default: bool = False) -> bool:
    """
    Safely converts value to bool.
    """

    if value is None:
        return default

    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1", "y"}

    return bool(value)


def _normalize_string(value: Any, default: str = "") -> str:
    """
    Safely converts value to stripped string.
    """

    if value is None:
        return default

    return str(value).strip()


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


def _get_policy_context(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Returns policy_context_output if available.
    """

    return _as_dict(state.get("policy_context_output"))


def _context_value(
    state: Dict[str, Any],
    context: Dict[str, Any],
    key: str,
    default: Any = None,
) -> Any:
    """
    Reads from policy_context_output first, then from top-level state.
    """

    if key in context:
        return context.get(key)

    return state.get(key, default)


def _add_risk_factor(
    factors: List[RiskFactorTriggered],
    factor: str,
    points: int,
    category: str,
) -> None:
    """
    Adds a risk factor if it has not already been added.
    Prevents accidental duplicate scoring.
    """

    existing = {item.factor for item in factors}

    if factor not in existing:
        factors.append(
            RiskFactorTriggered(
                factor=factor,
                points=points,
                category=category,
            )
        )


def _determine_risk_level(final_score: int) -> str:
    """
    Maps final risk score to risk level.

    0-30     Low
    31-60    Medium
    61-80    High
    81-100   Critical
    """

    if final_score <= 30:
        return "Low"

    if final_score <= 60:
        return "Medium"

    if final_score <= 80:
        return "High"

    return "Critical"


# ============================================================
# Source collection
# ============================================================

def _collect_source_files_and_records(
    state: Dict[str, Any]
) -> Tuple[List[str], List[str]]:
    """
    Collects source files and record IDs from all available outputs.
    """

    context = _get_policy_context(state)

    source_files: List[str] = []
    source_record_ids: List[str] = []

    for key in [
        "forecasting_output",
        "inventory_output",
        "procurement_output",
        "logistics_output",
        "policy_output",
    ]:
        output = _as_dict(state.get(key))

        files = output.get("source_files", [])
        record_ids = output.get("source_record_ids", [])

        if isinstance(files, list):
            source_files.extend(files)

        if isinstance(record_ids, list):
            source_record_ids.extend([str(item) for item in record_ids])

    dataset_accessed = context.get(
        "dataset_accessed",
        state.get("dataset_accessed", []),
    )

    dataset_attempted = context.get(
        "dataset_access_attempted",
        state.get("dataset_access_attempted", []),
    )

    source_files.extend(_string_list(dataset_accessed))
    source_files.extend(_string_list(dataset_attempted))

    policy_rag_decision = _as_dict(state.get("policy_rag_decision"))

    if policy_rag_decision:
        source_files.append("agentops_supply_chain_policy_handbook.pdf")

        for page in policy_rag_decision.get("source_pages", []):
            source_record_ids.append(f"policy_page_{page}")

    source_files = _unique_preserve_order(source_files)
    source_record_ids = _unique_preserve_order(source_record_ids)

    return source_files, source_record_ids


# ============================================================
# Risk factor evaluation
# ============================================================

def _evaluate_forecasting_risk(
    state: Dict[str, Any],
    context: Dict[str, Any],
    factors: List[RiskFactorTriggered],
) -> None:
    """
    Evaluates forecasting-related risk.
    """

    forecasting_output = _as_dict(state.get("forecasting_output"))

    forecast_confidence = _safe_number(
        context.get(
            "forecast_confidence",
            forecasting_output.get("forecast_confidence", 1.0),
        ),
        default=1.0,
    )

    if forecast_confidence < LOW_FORECAST_CONFIDENCE_THRESHOLD:
        _add_risk_factor(
            factors=factors,
            factor="low_forecast_confidence",
            points=RISK_POINTS["low_forecast_confidence"],
            category=RISK_CATEGORIES["low_forecast_confidence"],
        )


def _evaluate_procurement_risk(
    state: Dict[str, Any],
    context: Dict[str, Any],
    factors: List[RiskFactorTriggered],
) -> None:
    """
    Evaluates procurement and supplier compliance risk.
    """

    procurement_output = _as_dict(state.get("procurement_output"))

    procurement_value = _safe_number(
        context.get(
            "procurement_value",
            procurement_output.get("procurement_value", 0),
        ),
        default=0,
    )

    supplier_is_unapproved = _safe_bool(
        context.get("supplier_is_unapproved", False),
        default=False,
    )

    supplier_is_non_compliant = _safe_bool(
        context.get("supplier_is_non_compliant", False),
        default=False,
    )

    supplier_under_review = _safe_bool(
        context.get("supplier_under_review", False),
        default=False,
    )

    # Fallback to old procurement output if policy_context_output is absent.
    if not context:
        is_approved = _normalize_string(
            procurement_output.get("is_approved", "Yes"),
            default="Yes",
        )

        compliance_status = _normalize_string(
            procurement_output.get("compliance_status", "Compliant"),
            default="Compliant",
        )

        supplier_is_unapproved = is_approved == "No"
        supplier_is_non_compliant = compliance_status == "Non-Compliant"
        supplier_under_review = compliance_status == "Under Review"

    if procurement_value > HIGH_VALUE_PROCUREMENT_THRESHOLD:
        _add_risk_factor(
            factors=factors,
            factor="high_value_procurement",
            points=RISK_POINTS["high_value_procurement"],
            category=RISK_CATEGORIES["high_value_procurement"],
        )

    if supplier_is_unapproved:
        _add_risk_factor(
            factors=factors,
            factor="unapproved_vendor",
            points=RISK_POINTS["unapproved_vendor"],
            category=RISK_CATEGORIES["unapproved_vendor"],
        )

    if supplier_is_non_compliant:
        _add_risk_factor(
            factors=factors,
            factor="non_compliant_supplier",
            points=RISK_POINTS["non_compliant_supplier"],
            category=RISK_CATEGORIES["non_compliant_supplier"],
        )

    if supplier_under_review:
        _add_risk_factor(
            factors=factors,
            factor="supplier_under_review",
            points=RISK_POINTS["supplier_under_review"],
            category=RISK_CATEGORIES["supplier_under_review"],
        )


def _evaluate_logistics_risk(
    state: Dict[str, Any],
    context: Dict[str, Any],
    factors: List[RiskFactorTriggered],
) -> None:
    """
    Evaluates logistics route disruption risk using severity-aware scoring.
    """

    logistics_output = _as_dict(state.get("logistics_output"))

    route_disruption_exists = _safe_bool(
        context.get(
            "route_disruption_exists",
            logistics_output.get("route_disruption_exists", False),
        ),
        default=False,
    )

    route_disruption_status = _normalize_string(
        context.get(
            "route_disruption_status",
            logistics_output.get("route_disruption_status", "None"),
        ),
        default="None",
    )

    route_disruption_severity = _normalize_string(
        context.get(
            "route_disruption_severity",
            logistics_output.get("route_disruption_severity", "None"),
        ),
        default="None",
    )

    if route_disruption_exists and route_disruption_status == "Active":
        points = ROUTE_DISRUPTION_POINTS.get(route_disruption_severity, 0)

        if points > 0:
            factor_name = (
                f"active_{route_disruption_severity.lower()}_route_disruption"
            )

            _add_risk_factor(
                factors=factors,
                factor=factor_name,
                points=points,
                category=RISK_CATEGORIES.get(factor_name, "Operational Risk"),
            )


def _evaluate_access_governance_risk(
    state: Dict[str, Any],
    context: Dict[str, Any],
    factors: List[RiskFactorTriggered],
) -> None:
    """
    Evaluates restricted data, unauthorized access, and forbidden dataset risks.
    """

    user_requested_restricted_data = _safe_bool(
        _context_value(state, context, "user_requested_restricted_data", False),
        default=False,
    )

    restricted_data_accessed = _safe_bool(
        _context_value(state, context, "restricted_data_accessed", False),
        default=False,
    )

    unauthorized_dataset_accessed = _safe_bool(
        _context_value(state, context, "unauthorized_dataset_accessed", False),
        default=False,
    )

    agent_accessed_forbidden_dataset = _safe_bool(
        _context_value(state, context, "agent_accessed_forbidden_dataset", False),
        default=False,
    )

    dataset_accessed = _string_list(
        context.get("dataset_accessed", state.get("dataset_accessed", []))
    )

    accessed_restricted_dataset = any(
        dataset in RESTRICTED_DATASETS
        for dataset in dataset_accessed
    )

    if user_requested_restricted_data:
        _add_risk_factor(
            factors=factors,
            factor="user_requested_restricted_data",
            points=RISK_POINTS["user_requested_restricted_data"],
            category=RISK_CATEGORIES["user_requested_restricted_data"],
        )

    if restricted_data_accessed or accessed_restricted_dataset:
        _add_risk_factor(
            factors=factors,
            factor="restricted_data_access",
            points=RISK_POINTS["restricted_data_access"],
            category=RISK_CATEGORIES["restricted_data_access"],
        )

    if unauthorized_dataset_accessed:
        _add_risk_factor(
            factors=factors,
            factor="unauthorized_dataset_access",
            points=RISK_POINTS["unauthorized_dataset_access"],
            category=RISK_CATEGORIES["unauthorized_dataset_access"],
        )

    if agent_accessed_forbidden_dataset:
        _add_risk_factor(
            factors=factors,
            factor="user_forbidden_dataset_access",
            points=RISK_POINTS["user_forbidden_dataset_access"],
            category=RISK_CATEGORIES["user_forbidden_dataset_access"],
        )


def _evaluate_traceability_and_instruction_risk(
    state: Dict[str, Any],
    context: Dict[str, Any],
    factors: List[RiskFactorTriggered],
) -> None:
    """
    Evaluates user instruction and traceability risks.
    """

    user_instruction_violation = _safe_bool(
        _context_value(state, context, "user_instruction_violation", False),
        default=False,
    )

    user_requested_no_citations = _safe_bool(
        _context_value(state, context, "user_requested_no_citations", False),
        default=False,
    )

    source_citation_missing = _safe_bool(
        _context_value(state, context, "source_citation_missing", False),
        default=False,
    )

    if user_instruction_violation:
        _add_risk_factor(
            factors=factors,
            factor="user_instruction_violation",
            points=RISK_POINTS["user_instruction_violation"],
            category=RISK_CATEGORIES["user_instruction_violation"],
        )

    if user_requested_no_citations:
        _add_risk_factor(
            factors=factors,
            factor="user_requested_no_citations",
            points=RISK_POINTS["user_requested_no_citations"],
            category=RISK_CATEGORIES["user_requested_no_citations"],
        )

    if source_citation_missing:
        _add_risk_factor(
            factors=factors,
            factor="missing_source_citation",
            points=RISK_POINTS["missing_source_citation"],
            category=RISK_CATEGORIES["missing_source_citation"],
        )


def _evaluate_external_and_tool_risk(
    state: Dict[str, Any],
    context: Dict[str, Any],
    factors: List[RiskFactorTriggered],
) -> None:
    """
    Evaluates external communication and tool-governance risks.
    """

    external_communication_requested = _safe_bool(
        _context_value(state, context, "external_communication_requested", False),
        default=False,
    )

    external_communication_attempted = _safe_bool(
        _context_value(state, context, "external_communication_attempted", False),
        default=False,
    )

    unauthorized_tool_used = _safe_bool(
        _context_value(state, context, "unauthorized_tool_used", False),
        default=False,
    )

    if external_communication_requested:
        _add_risk_factor(
            factors=factors,
            factor="external_communication_requested",
            points=RISK_POINTS["external_communication_requested"],
            category=RISK_CATEGORIES["external_communication_requested"],
        )

    if external_communication_attempted:
        _add_risk_factor(
            factors=factors,
            factor="external_communication_attempted",
            points=RISK_POINTS["external_communication_attempted"],
            category=RISK_CATEGORIES["external_communication_attempted"],
        )

    if unauthorized_tool_used:
        _add_risk_factor(
            factors=factors,
            factor="unauthorized_tool_used",
            points=RISK_POINTS["unauthorized_tool_used"],
            category=RISK_CATEGORIES["unauthorized_tool_used"],
        )


def _evaluate_workflow_reliability_risk(
    state: Dict[str, Any],
    context: Dict[str, Any],
    factors: List[RiskFactorTriggered],
) -> None:
    """
    Evaluates agent failure and inactive-agent risks.
    """

    any_agent_failed = _safe_bool(
        context.get("any_agent_failed", False),
        default=False,
    )

    agent_status = _normalize_string(
        state.get("agent_status", "Active"),
        default="Active",
    )

    if any_agent_failed:
        _add_risk_factor(
            factors=factors,
            factor="agent_failure_present",
            points=RISK_POINTS["agent_failure_present"],
            category=RISK_CATEGORIES["agent_failure_present"],
        )

    if agent_status != "Active":
        _add_risk_factor(
            factors=factors,
            factor="inactive_agent_action",
            points=RISK_POINTS["inactive_agent_action"],
            category=RISK_CATEGORIES["inactive_agent_action"],
        )


def _evaluate_policy_risk(
    state: Dict[str, Any],
    factors: List[RiskFactorTriggered],
) -> None:
    """
    Evaluates risk from policy output and PDF-first RAG decision.
    """

    policy_output = _as_dict(state.get("policy_output"))
    policy_rag_decision = _as_dict(state.get("policy_rag_decision"))

    policy_decision = _normalize_string(
        policy_output.get("policy_decision", state.get("final_decision", "Allow")),
        default="Allow",
    )

    if policy_decision == "Block":
        _add_risk_factor(
            factors=factors,
            factor="policy_block_decision",
            points=RISK_POINTS["policy_block_decision"],
            category=RISK_CATEGORIES["policy_block_decision"],
        )

    elif policy_decision == "Escalate":
        _add_risk_factor(
            factors=factors,
            factor="policy_escalate_decision",
            points=RISK_POINTS["policy_escalate_decision"],
            category=RISK_CATEGORIES["policy_escalate_decision"],
        )

    if policy_rag_decision:
        rag_confidence = _safe_number(
            policy_rag_decision.get("confidence", 1.0),
            default=1.0,
        )

        evidence_available = _safe_bool(
            policy_rag_decision.get("evidence_available", True),
            default=True,
        )

        rag_error = policy_rag_decision.get("error")

        if rag_error:
            _add_risk_factor(
                factors=factors,
                factor="policy_rag_failed",
                points=RISK_POINTS["policy_rag_failed"],
                category=RISK_CATEGORIES["policy_rag_failed"],
            )

        if not evidence_available:
            _add_risk_factor(
                factors=factors,
                factor="policy_rag_evidence_missing",
                points=RISK_POINTS["policy_rag_evidence_missing"],
                category=RISK_CATEGORIES["policy_rag_evidence_missing"],
            )

        if rag_confidence < LOW_POLICY_RAG_CONFIDENCE_THRESHOLD:
            _add_risk_factor(
                factors=factors,
                factor="policy_rag_low_confidence",
                points=RISK_POINTS["policy_rag_low_confidence"],
                category=RISK_CATEGORIES["policy_rag_low_confidence"],
            )

        guardrail_result = _as_dict(
            policy_rag_decision.get("guardrail_result")
        )

        guardrails_triggered = guardrail_result.get("guardrails_triggered", [])

        if isinstance(guardrails_triggered, list) and guardrails_triggered:
            _add_risk_factor(
                factors=factors,
                factor="policy_rag_guardrail_triggered",
                points=RISK_POINTS["policy_rag_guardrail_triggered"],
                category=RISK_CATEGORIES["policy_rag_guardrail_triggered"],
            )


# ============================================================
# Main risk node
# ============================================================

def risk_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    LangGraph Risk Scoring node.

    Reads workflow state and policy_context_output, then returns RiskScoringOutput.

    Returns:
        {
            "risk_output": {...}
        }
    """

    context = _get_policy_context(state)
    risk_factors: List[RiskFactorTriggered] = []

    _evaluate_forecasting_risk(state, context, risk_factors)
    _evaluate_procurement_risk(state, context, risk_factors)
    _evaluate_logistics_risk(state, context, risk_factors)
    _evaluate_access_governance_risk(state, context, risk_factors)
    _evaluate_traceability_and_instruction_risk(state, context, risk_factors)
    _evaluate_external_and_tool_risk(state, context, risk_factors)
    _evaluate_workflow_reliability_risk(state, context, risk_factors)
    _evaluate_policy_risk(state, risk_factors)

    total_factor_points = sum(factor.points for factor in risk_factors)

    calculated_score = BASE_SCORE + total_factor_points
    final_risk_score = min(calculated_score, MAX_SCORE)
    score_cap_applied = calculated_score > MAX_SCORE

    risk_level = _determine_risk_level(final_risk_score)

    source_files, source_record_ids = _collect_source_files_and_records(state)

    factor_names = [factor.factor for factor in risk_factors]

    if factor_names:
        message = (
            f"Risk score calculated as {final_risk_score} from base score "
            f"{BASE_SCORE} and {len(factor_names)} triggered factor(s): "
            f"{', '.join(factor_names)}. Final risk level: {risk_level}. "
            f"Score cap applied: {score_cap_applied}."
        )
    else:
        message = (
            f"Risk score calculated as {final_risk_score} from base score "
            f"{BASE_SCORE}. No additional risk factors were triggered. "
            f"Final risk level: {risk_level}. Score cap applied: {score_cap_applied}."
        )

    output = RiskScoringOutput(
        run_id=state.get("run_id", "RUN-UNKNOWN"),
        step_id="STEP-007",
        agent_id="risk_scoring_engine",
        agent_name="Risk Scoring Engine",
        status="success",
        source_files=source_files,
        source_record_ids=source_record_ids,
        message=message,
        base_score=BASE_SCORE,
        risk_factors_triggered=risk_factors,
        calculated_score=int(calculated_score),
        final_risk_score=int(final_risk_score),
        risk_level=risk_level,
        score_cap_applied=score_cap_applied,
    )

    return {
        "risk_output": _safe_model_dump(output)
    }


# ============================================================
# Optional local manual tests
# ============================================================

if __name__ == "__main__":
    test_cases = [
        {
            "name": "Restricted dataset requested",
            "state": {
                "run_id": "RUN-RISK-TEST-001",
                "policy_context_output": {
                    "user_requested_restricted_data": True,
                    "requested_restricted_datasets": ["payroll.csv"],
                    "restricted_data_accessed": False,
                    "unauthorized_dataset_accessed": False,
                    "agent_accessed_forbidden_dataset": False,
                    "source_citation_missing": False,
                    "user_requested_no_citations": False,
                    "procurement_value": 198000,
                    "supplier_is_unapproved": False,
                    "supplier_is_non_compliant": False,
                    "supplier_under_review": False,
                    "route_disruption_exists": False,
                    "route_disruption_status": "None",
                    "route_disruption_severity": "None",
                    "any_agent_failed": False,
                    "dataset_accessed": ["products.csv", "suppliers.csv"],
                    "dataset_access_attempted": ["products.csv", "suppliers.csv"],
                },
                "policy_output": {
                    "policy_decision": "Block",
                    "source_files": ["agentops_supply_chain_policy_handbook.pdf"],
                    "source_record_ids": ["policy_page_6"],
                },
                "policy_rag_decision": {
                    "decision": "Allow",
                    "confidence": 0.95,
                    "evidence_available": True,
                    "source_pages": [6],
                    "guardrail_result": {
                        "guardrails_triggered": []
                    },
                },
            },
        },
        {
            "name": "Forbidden dataset access",
            "state": {
                "run_id": "RUN-RISK-TEST-002",
                "policy_context_output": {
                    "user_requested_restricted_data": False,
                    "restricted_data_accessed": False,
                    "unauthorized_dataset_accessed": True,
                    "agent_accessed_forbidden_dataset": True,
                    "forbidden_accesses": [
                        {
                            "agent_id": "procurement_agent",
                            "file_name": "suppliers.csv",
                        }
                    ],
                    "source_citation_missing": False,
                    "user_requested_no_citations": False,
                    "procurement_value": 0,
                    "any_agent_failed": True,
                    "failed_agents": ["procurement_agent"],
                    "dataset_accessed": ["products.csv"],
                    "dataset_access_attempted": ["products.csv", "suppliers.csv"],
                },
                "policy_output": {
                    "policy_decision": "Block",
                    "source_files": ["agentops_supply_chain_policy_handbook.pdf"],
                    "source_record_ids": ["policy_page_6"],
                },
                "policy_rag_decision": {
                    "decision": "Escalate",
                    "confidence": 0.88,
                    "evidence_available": True,
                    "source_pages": [6],
                    "guardrail_result": {
                        "guardrails_triggered": []
                    },
                },
            },
        },
        {
            "name": "High-value procurement and critical route disruption",
            "state": {
                "run_id": "RUN-RISK-TEST-003",
                "policy_context_output": {
                    "procurement_value": 387000,
                    "supplier_is_unapproved": False,
                    "supplier_is_non_compliant": False,
                    "supplier_under_review": False,
                    "route_disruption_exists": True,
                    "route_disruption_status": "Active",
                    "route_disruption_severity": "Critical",
                    "source_citation_missing": False,
                    "user_requested_no_citations": False,
                    "any_agent_failed": False,
                    "dataset_accessed": ["products.csv", "suppliers.csv", "routes.csv"],
                    "dataset_access_attempted": ["products.csv", "suppliers.csv", "routes.csv"],
                },
                "policy_output": {
                    "policy_decision": "Escalate",
                    "source_files": ["agentops_supply_chain_policy_handbook.pdf"],
                    "source_record_ids": ["policy_page_8", "policy_page_10"],
                },
                "policy_rag_decision": {
                    "decision": "Escalate",
                    "confidence": 0.92,
                    "evidence_available": True,
                    "source_pages": [8, 10],
                    "guardrail_result": {
                        "guardrails_triggered": []
                    },
                },
            },
        },
    ]

    for case in test_cases:
        print("=" * 100)
        print("CASE:", case["name"])

        result = risk_node(case["state"])
        risk_output = result["risk_output"]

        print("Risk score:", risk_output["final_risk_score"])
        print("Risk level:", risk_output["risk_level"])
        print("Calculated score:", risk_output["calculated_score"])
        print("Score cap applied:", risk_output["score_cap_applied"])
        print("Factors:")

        for factor in risk_output["risk_factors_triggered"]:
            print(
                f"- {factor['factor']} "
                f"+{factor['points']} "
                f"({factor['category']})"
            )

        print("Message:", risk_output["message"])