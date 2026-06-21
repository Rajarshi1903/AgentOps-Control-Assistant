from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel

from src.schemas.policy_rag import (
    PolicyAction,
    PolicyRAGEvaluationInput,
    ExtractedPolicyRule,
    PolicyGuardrailResult,
    PolicyRAGDecision,
    RetrievedPolicyChunk,
    resolve_policy_decision,
    average_confidence,
    extract_source_documents,
    extract_source_pages,
)


# ============================================================
# Policy Decision Evaluator
# ============================================================
# Purpose:
# Deterministically evaluates extracted PDF-backed policy rules
# against the actual agent action context.
#
# Philosophy:
# - PDF is the authority.
# - LLM extracts structured rules.
# - Python evaluates whether those rules apply.
# - Python resolves final decision using:
#   Block > Escalate > Allow
# ============================================================


RESTRICTED_DATASETS = {
    "hr_data.csv",
    "payroll.csv",
    "employee_records.csv",
    "customer_pii.csv",
}

HIGH_ROUTE_DISRUPTION_SEVERITIES = {
    "High",
    "Critical",
}


class EvaluatedPolicyRule(BaseModel):
    """
    Local evaluation object.

    It records whether a RAG-extracted policy rule actually matches
    the current action context.
    """

    policy_name: str
    policy_area: str
    action: PolicyAction
    condition_matched: bool
    evaluation_reason: str
    rule: ExtractedPolicyRule


def _get_context_value(
    context: PolicyRAGEvaluationInput,
    field_name: Optional[str]
) -> Any:
    """
    Safely gets a field value from PolicyRAGEvaluationInput.

    Also checks additional_context as fallback.
    """

    if not field_name:
        return None

    if hasattr(context, field_name):
        return getattr(context, field_name)

    return context.additional_context.get(field_name)


def _normalize_string(value: Any) -> str:
    """
    Normalizes values for string comparison.
    """

    if value is None:
        return ""

    return str(value).strip()


def _compare_values(
    actual_value: Any,
    operator: Optional[str],
    expected_value: Any = None,
    threshold_value: Optional[float] = None,
    allowed_values: Optional[List[Any]] = None,
) -> bool:
    """
    Generic rule comparison helper.

    Supports:
    >, >=, <, <=, ==, !=, in, not_in, exists, not_exists
    """

    if operator is None:
        return False

    if operator in [">", ">=", "<", "<="]:
        if threshold_value is None:
            return False

        try:
            actual_number = float(actual_value)
            threshold_number = float(threshold_value)
        except (TypeError, ValueError):
            return False

        if operator == ">":
            return actual_number > threshold_number

        if operator == ">=":
            return actual_number >= threshold_number

        if operator == "<":
            return actual_number < threshold_number

        if operator == "<=":
            return actual_number <= threshold_number

    if operator == "==":
        return _normalize_string(actual_value) == _normalize_string(expected_value)

    if operator == "!=":
        return _normalize_string(actual_value) != _normalize_string(expected_value)

    if operator == "in":
        if allowed_values is None:
            return False

        normalized_actual = _normalize_string(actual_value)
        normalized_allowed = {_normalize_string(value) for value in allowed_values}

        return normalized_actual in normalized_allowed

    if operator == "not_in":
        if allowed_values is None:
            return False

        normalized_actual = _normalize_string(actual_value)
        normalized_allowed = {_normalize_string(value) for value in allowed_values}

        return normalized_actual not in normalized_allowed

    if operator == "exists":
        return actual_value is not None and actual_value != ""

    if operator == "not_exists":
        return actual_value is None or actual_value == ""

    return False


def _evaluate_known_policy_area(
    context: PolicyRAGEvaluationInput,
    rule: ExtractedPolicyRule
) -> Tuple[bool, str]:
    """
    Evaluates well-known policy areas deterministically.

    Important:
    Evaluation is based primarily on condition_field and specific policy meaning,
    not broad text matching alone. This prevents supplier-compliance rules from
    being incorrectly evaluated as procurement-threshold rules.
    """

    policy_area = (rule.policy_area or "").lower()
    policy_name = (rule.policy_name or "").lower()
    condition_field = (rule.condition_field or "").lower()

    combined_text = f"{policy_area} {policy_name}"

    # --------------------------------------------------------
    # Supplier compliance / unapproved supplier
    # Must be checked before procurement because supplier rules
    # can appear inside procurement-related retrieved chunks.
    # --------------------------------------------------------
    if (
        condition_field in ["is_approved", "compliance_status"]
        or "supplier" in combined_text
        or "vendor" in combined_text
        or "compliance" in combined_text
        or "unapproved" in combined_text
        or "non-compliant" in combined_text
    ):
        matched = (
            context.is_approved == "No"
            or context.compliance_status == "Non-Compliant"
        )

        return (
            matched,
            (
                f"is_approved={context.is_approved}, "
                f"compliance_status={context.compliance_status}; "
                f"supplier compliance violation matched: {matched}"
            ),
        )

    # --------------------------------------------------------
    # High-value procurement
    # Only evaluate as high-value procurement if the condition is
    # procurement_value or the policy is clearly about high-value threshold.
    # --------------------------------------------------------
    if (
        condition_field == "procurement_value"
        or "high-value procurement" in combined_text
        or "high value procurement" in combined_text
        or "procurement threshold" in combined_text
    ):
        threshold = rule.threshold_value if rule.threshold_value is not None else 50000

        matched = context.procurement_value > float(threshold)

        return (
            matched,
            (
                f"procurement_value={context.procurement_value} "
                f"> threshold={threshold}: {matched}"
            ),
        )

    # --------------------------------------------------------
    # Route disruption
    # --------------------------------------------------------
    if (
        condition_field in ["route_disruption_exists", "route_disruption_status", "route_disruption_severity"]
        or "route" in combined_text
        or "logistics" in combined_text
        or "disruption" in combined_text
    ):
        matched = (
            context.route_disruption_exists is True
            and context.route_disruption_status == "Active"
            and context.route_disruption_severity in HIGH_ROUTE_DISRUPTION_SEVERITIES
        )

        return (
            matched,
            (
                f"route_disruption_exists={context.route_disruption_exists}, "
                f"route_disruption_status={context.route_disruption_status}, "
                f"route_disruption_severity={context.route_disruption_severity}; "
                f"route disruption violation matched: {matched}"
            ),
        )

    # --------------------------------------------------------
    # Restricted data access
    # --------------------------------------------------------
    if (
        condition_field in ["restricted_data_accessed", "dataset_accessed"]
        or "restricted" in combined_text
        or "data access" in combined_text
        or "payroll" in combined_text
        or "pii" in combined_text
    ):
        matched = (
            context.restricted_data_accessed is True
            or context.dataset_accessed in RESTRICTED_DATASETS
        )

        return (
            matched,
            (
                f"restricted_data_accessed={context.restricted_data_accessed}, "
                f"dataset_accessed={context.dataset_accessed}; "
                f"restricted data violation matched: {matched}"
            ),
        )

    # --------------------------------------------------------
    # Source traceability
    # --------------------------------------------------------
    if (
        condition_field == "source_citation_missing"
        or "source" in combined_text
        or "traceability" in combined_text
        or "citation" in combined_text
    ):
        matched = context.source_citation_missing is True

        return (
            matched,
            (
                f"source_citation_missing={context.source_citation_missing}; "
                f"source traceability violation matched: {matched}"
            ),
        )

    # --------------------------------------------------------
    # External communication
    # --------------------------------------------------------
    if (
        condition_field == "external_communication_attempted"
        or "external" in combined_text
        or "communication" in combined_text
        or "email" in combined_text
        or "vendor api" in combined_text
    ):
        matched = context.external_communication_attempted is True

        return (
            matched,
            (
                f"external_communication_attempted="
                f"{context.external_communication_attempted}; "
                f"external communication violation matched: {matched}"
            ),
        )

    # --------------------------------------------------------
    # Tool usage
    # --------------------------------------------------------
    if (
        condition_field == "unauthorized_tool_used"
        or "tool" in combined_text
        or "unauthorized tool" in combined_text
    ):
        matched = context.unauthorized_tool_used is True

        return (
            matched,
            (
                f"unauthorized_tool_used={context.unauthorized_tool_used}, "
                f"tool_called={context.tool_called}; "
                f"tool usage violation matched: {matched}"
            ),
        )

    # --------------------------------------------------------
    # Agent status
    # --------------------------------------------------------
    if (
        condition_field == "agent_status"
        or "agent status" in combined_text
        or "suspended" in combined_text
        or "inactive" in combined_text
    ):
        matched = context.agent_status != "Active"

        return (
            matched,
            (
                f"agent_status={context.agent_status}; "
                f"agent status violation matched: {matched}"
            ),
        )

    # --------------------------------------------------------
    # Forecast confidence
    # --------------------------------------------------------
    if (
        condition_field == "forecast_confidence"
        or "forecast" in combined_text
        or "confidence" in combined_text
    ):
        threshold = rule.threshold_value if rule.threshold_value is not None else 0.70

        matched = context.forecast_confidence < float(threshold)

        return (
            matched,
            (
                f"forecast_confidence={context.forecast_confidence} "
                f"< threshold={threshold}: {matched}"
            ),
        )

    return False, "No known policy-area evaluator matched."


def evaluate_single_rule(
    context: PolicyRAGEvaluationInput,
    rule: ExtractedPolicyRule
) -> EvaluatedPolicyRule:
    """
    Evaluates one extracted policy rule against the current action context.

    Evaluation order:
    1. If the rule has explicit condition_field and operator, use generic evaluation first.
    2. If generic evaluation cannot be applied, use known policy-area logic.
    """

    if not rule.applicable:
        return EvaluatedPolicyRule(
            policy_name=rule.policy_name,
            policy_area=rule.policy_area,
            action=rule.action,
            condition_matched=False,
            evaluation_reason="Rule marked as not applicable by extraction layer.",
            rule=rule,
        )

    # --------------------------------------------------------
    # First: use explicit structured condition if available.
    # This prevents wrong broad-category matching.
    # --------------------------------------------------------
    if rule.condition_field and rule.operator:
        actual_value = _get_context_value(
            context=context,
            field_name=rule.condition_field,
        )

        generic_matched = _compare_values(
            actual_value=actual_value,
            operator=rule.operator,
            expected_value=rule.expected_value,
            threshold_value=rule.threshold_value,
            allowed_values=rule.allowed_values,
        )

        return EvaluatedPolicyRule(
            policy_name=rule.policy_name,
            policy_area=rule.policy_area,
            action=rule.action,
            condition_matched=generic_matched,
            evaluation_reason=(
                f"Generic evaluation: field={rule.condition_field}, "
                f"actual_value={actual_value}, operator={rule.operator}, "
                f"threshold_value={rule.threshold_value}, "
                f"expected_value={rule.expected_value}, "
                f"allowed_values={rule.allowed_values}, "
                f"matched={generic_matched}"
            ),
            rule=rule,
        )

    # --------------------------------------------------------
    # Second: fallback to known policy-area evaluator.
    # --------------------------------------------------------
    known_matched, known_reason = _evaluate_known_policy_area(
        context=context,
        rule=rule,
    )

    return EvaluatedPolicyRule(
        policy_name=rule.policy_name,
        policy_area=rule.policy_area,
        action=rule.action,
        condition_matched=known_matched,
        evaluation_reason=known_reason,
        rule=rule,
    )

def evaluate_extracted_rules(
    context: PolicyRAGEvaluationInput,
    extracted_rules: List[ExtractedPolicyRule]
) -> Tuple[List[ExtractedPolicyRule], List[EvaluatedPolicyRule]]:
    """
    Evaluates all extracted rules and returns only condition-matched
    enforcement rules.

    Important:
    Rules with action == Allow are not treated as triggered enforcement
    policies. They may be useful as context, but they should not appear
    as policy violations/escalations.
    """

    evaluated_results = []
    matched_rules = []

    for rule in extracted_rules:
        evaluated = evaluate_single_rule(
            context=context,
            rule=rule,
        )

        evaluated_results.append(evaluated)

        if evaluated.condition_matched and rule.action != "Allow":
            matched_rules.append(rule)

    return matched_rules, evaluated_results

def resolve_decision_from_evaluated_rules(
    matched_rules: List[ExtractedPolicyRule],
    guardrail_result: Optional[PolicyGuardrailResult] = None
) -> PolicyAction:
    """
    Resolves final decision from matched rules and guardrail result.

    Priority:
    Block > Escalate > Allow
    """

    actions = [rule.action for rule in matched_rules]

    if guardrail_result is not None:
        if guardrail_result.guardrail_decision != "Allow":
            actions.append(guardrail_result.guardrail_decision)

    return resolve_policy_decision(actions)


def build_final_reason(
    matched_rules: List[ExtractedPolicyRule],
    evaluated_results: List[EvaluatedPolicyRule],
    guardrail_result: Optional[PolicyGuardrailResult] = None
) -> str:
    """
    Builds a concise final reason for the evaluated policy decision.

    Only enforcement rules are included in the final reason:
    - Block
    - Escalate

    Allow rules may be evaluated internally but are not shown as
    triggered enforcement reasons.
    """

    reason_parts = []

    enforcement_rules = [
        rule for rule in matched_rules
        if rule.action in ["Block", "Escalate"]
    ]

    if enforcement_rules:
        matched_policy_names = [rule.policy_name for rule in enforcement_rules]

        reason_parts.append(
            "Matched PDF-extracted enforcement policy rules: "
            + ", ".join(matched_policy_names)
            + "."
        )
    else:
        reason_parts.append(
            "No PDF-extracted enforcement policy rule matched the current action context."
        )

    enforcement_evaluation_notes = [
        result.evaluation_reason
        for result in evaluated_results
        if result.condition_matched
        and result.action in ["Block", "Escalate"]
    ]

    if enforcement_evaluation_notes:
        reason_parts.append(
            "Evaluation details: "
            + " | ".join(enforcement_evaluation_notes)
        )

    if guardrail_result and guardrail_result.guardrails_triggered:
        reason_parts.append(
            "Guardrail note: " + guardrail_result.guardrail_reason
        )

    return " ".join(reason_parts)

def rebuild_policy_rag_decision_after_evaluation(
    original_decision: PolicyRAGDecision,
    context: PolicyRAGEvaluationInput
) -> Tuple[PolicyRAGDecision, List[EvaluatedPolicyRule]]:
    """
    Rebuilds PolicyRAGDecision after deterministically evaluating
    extracted rules against the action context.

    This is useful after policy_rag_agent extracts rules from PDF chunks.
    """

    matched_rules, evaluated_results = evaluate_extracted_rules(
        context=context,
        extracted_rules=original_decision.triggered_rules,
    )

    final_decision = resolve_decision_from_evaluated_rules(
        matched_rules=matched_rules,
        guardrail_result=original_decision.guardrail_result,
    )

    confidence = (
        average_confidence(matched_rules)
        if matched_rules
        else original_decision.confidence
    )

    final_reason = build_final_reason(
        matched_rules=matched_rules,
        evaluated_results=evaluated_results,
        guardrail_result=original_decision.guardrail_result,
    )

    rebuilt_decision = PolicyRAGDecision(
        run_id=original_decision.run_id,
        query=original_decision.query,
        decision=final_decision,
        triggered_rules=matched_rules,
        retrieved_chunks=original_decision.retrieved_chunks,
        guardrail_result=original_decision.guardrail_result,
        final_reason=final_reason,
        evidence_available=original_decision.evidence_available,
        confidence=round(float(confidence), 2),
        decision_priority_applied="Block > Escalate > Allow",
        source_documents=extract_source_documents(matched_rules),
        source_pages=extract_source_pages(matched_rules),
        generated_by="pdf_first_policy_decision_evaluator",
    )

    return rebuilt_decision, evaluated_results


# ============================================================
# Manual test
# ============================================================

if __name__ == "__main__":
    from src.schemas.policy_rag import PolicyEvidence

    context = PolicyRAGEvaluationInput(
        run_id="RUN-EVAL-TEST-001",
        agent_id="procurement_agent",
        procurement_value=387000,
        is_approved="Yes",
        compliance_status="Compliant",
        source_files=["suppliers.csv", "inventory.csv"],
        source_record_ids=["S-001", "INV-003"],
    )

    evidence = PolicyEvidence(
        evidence_text=(
            "Any procurement recommendation exceeding INR 50,000 must be "
            "escalated to a human reviewer before execution."
        ),
        source_document="agentops_supply_chain_policy_handbook.pdf",
        source_page=4,
        chunk_id="test_chunk_001",
        retrieval_score=0.91,
    )

    rule = ExtractedPolicyRule(
        applicable=True,
        policy_name="High-Value Procurement Approval",
        policy_area="Procurement Governance",
        condition_field="procurement_value",
        operator=">",
        threshold_value=50000,
        action="Escalate",
        severity="High",
        evidence=evidence,
        confidence=0.91,
    )

    matched, evaluated = evaluate_extracted_rules(
        context=context,
        extracted_rules=[rule],
    )

    print("Matched rules:", len(matched))

    for item in evaluated:
        print("-" * 80)
        print("Policy:", item.policy_name)
        print("Matched:", item.condition_matched)
        print("Reason:", item.evaluation_reason)

    final = resolve_decision_from_evaluated_rules(matched)

    print("Final decision:", final)