import os
from typing import Any, Dict, List, Optional, Tuple

from src.schemas.governance import (
    TriggeredPolicy,
    PolicyEngineOutput,
)

from src.rag.policy_rag_agent import evaluate_policy_with_rag_from_state


# ============================================================
# Policy Engine
# ============================================================
# Purpose:
# Evaluates normalized policy_context_output and optionally combines it with
# PDF-first policy RAG evidence.
#
# Design principle:
# - Policy Context Builder provides factual normalized context.
# - Data Access Guard provides deterministic file-access evidence.
# - Policy RAG provides handbook-based policy evidence when enabled/needed.
# - This Policy Engine applies deterministic priority:
#       Block > Escalate > Allow
#
# Latency optimization:
# - Deterministic context rules are evaluated first.
# - If the context already produces a clear Block decision, PDF RAG can be
#   skipped because the final decision is already known.
# - RAG can also be disabled using ENABLE_POLICY_RAG=false.
#
# Important:
# - Restricted-data and unauthorized-access controls are deterministic.
# - RAG is used for policy evidence and handbook-backed rules when enabled.
# - If RAG fails but deterministic context contains a Block/Escalate trigger,
#   the deterministic decision still stands.
# - If RAG fails and no deterministic trigger exists, fail closed as Escalate.
# ============================================================


ENABLE_POLICY_RAG = (
    os.getenv("ENABLE_POLICY_RAG", "true").strip().lower() == "true"
)

# If true, RAG will still run even when context already has a deterministic Block.
# Keep false for latency. Set true only when you specifically want PDF evidence
# even for obvious governance blocks.
RUN_RAG_ON_CLEAR_CONTEXT_BLOCK = (
    os.getenv("RUN_RAG_ON_CLEAR_CONTEXT_BLOCK", "false").strip().lower() == "true"
)


DECISION_PRIORITY = {
    "Allow": 1,
    "Escalate": 2,
    "Block": 3,
}

HIGH_VALUE_PROCUREMENT_THRESHOLD = 50000.0


CLEAR_CONTEXT_BLOCK_POLICY_IDS = {
    "CTX-BLOCK-001",  # Restricted Dataset Request Block
    "CTX-BLOCK-002",  # Restricted Dataset Access Block
    "CTX-BLOCK-003",  # Unauthorized Dataset Access Block
    "CTX-BLOCK-004",  # User-Forbidden Dataset Access Block
    "CTX-BLOCK-005",  # No-Citation Request Block
    "CTX-BLOCK-006",  # Missing Source Traceability Block
    "CTX-BLOCK-007",  # Non-Compliant Supplier Block
    "CTX-BLOCK-008",  # Unapproved Supplier Block
    "CTX-BLOCK-009",  # Policy Context Build Failure
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


def _as_bool(value: Any) -> bool:
    """
    Safely converts common bool-like values to bool.
    """

    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1", "y"}

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


def _normalize_decision(value: Any) -> str:
    """
    Normalizes decision into Allow, Escalate, or Block.
    """

    if value is None:
        return "Allow"

    value_str = str(value).strip().lower()

    if value_str == "block":
        return "Block"

    if value_str == "escalate":
        return "Escalate"

    if value_str == "allow":
        return "Allow"

    return "Escalate"


def _highest_priority_decision(decisions: List[str]) -> str:
    """
    Applies Block > Escalate > Allow priority.
    """

    if not decisions:
        return "Allow"

    normalized_decisions = [
        _normalize_decision(decision)
        for decision in decisions
    ]

    return max(
        normalized_decisions,
        key=lambda decision: DECISION_PRIORITY.get(decision, 0),
    )


def _unique_preserve_order(values: List[Any]) -> List[Any]:
    """
    Returns unique values while preserving order.
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
# Context helpers
# ============================================================

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


def _infer_evaluated_agent_id(state: Dict[str, Any]) -> str:
    """
    Infers which agent/action is mainly being evaluated.
    """

    context = _get_policy_context(state)

    if context.get("procurement_recommendation_exists"):
        return "procurement_agent"

    if context.get("recommended_route_id") is not None:
        return "logistics_agent"

    if context.get("procurement_status") == "success":
        return "procurement_agent"

    if context.get("logistics_status") == "success":
        return "logistics_agent"

    if context.get("inventory_status") == "success":
        return "inventory_agent"

    if context.get("forecasting_status") == "success":
        return "forecasting_agent"

    procurement_output = _as_dict(state.get("procurement_output"))
    logistics_output = _as_dict(state.get("logistics_output"))
    inventory_output = _as_dict(state.get("inventory_output"))
    forecasting_output = _as_dict(state.get("forecasting_output"))

    if procurement_output.get("recommended_supplier_id") is not None:
        return "procurement_agent"

    if logistics_output.get("recommended_route_id") is not None:
        return "logistics_agent"

    if inventory_output:
        return "inventory_agent"

    if forecasting_output:
        return "forecasting_agent"

    return state.get("evaluated_agent_id", "multi_agent_workflow")


def _collect_policy_source_files(
    state: Dict[str, Any],
    include_policy_handbook: bool,
) -> List[str]:
    """
    Collects source files from policy context and business agent outputs.

    The policy handbook is included only if PDF RAG actually ran.
    """

    context = _get_policy_context(state)
    source_files: List[str] = []

    for key in [
        "forecasting_output",
        "inventory_output",
        "procurement_output",
        "logistics_output",
    ]:
        output = _as_dict(state.get(key))
        files = output.get("source_files", [])

        if isinstance(files, list):
            source_files.extend(files)

    data_accessed = context.get(
        "dataset_accessed",
        state.get("dataset_accessed", []),
    )

    if isinstance(data_accessed, list):
        source_files.extend(data_accessed)
    elif data_accessed:
        source_files.append(str(data_accessed))

    if include_policy_handbook:
        source_files.append("agentops_supply_chain_policy_handbook.pdf")

    return _unique_preserve_order(source_files)


def _stringify_for_rag(value: Any) -> str:
    """
    Converts list/dict/scalar values into a RAG-input-safe string.
    """

    if value is None:
        return ""

    if isinstance(value, list):
        return ", ".join(str(item) for item in value)

    if isinstance(value, tuple):
        return ", ".join(str(item) for item in value)

    if isinstance(value, set):
        return ", ".join(str(item) for item in value)

    if isinstance(value, dict):
        return str(value)

    return str(value)


def _build_rag_safe_state(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Builds a copy of state that is compatible with Policy RAG input schema.

    Important:
    - This does not mutate the real LangGraph state.
    - It only converts list-based governance fields into strings for RAG.
    """

    rag_state = dict(state)

    fields_to_stringify = [
        "dataset_accessed",
        "dataset_access_attempted",
        "requested_datasets",
        "forbidden_datasets",
    ]

    for field in fields_to_stringify:
        if field in rag_state:
            rag_state[field] = _stringify_for_rag(rag_state.get(field))

    policy_context_output = _as_dict(state.get("policy_context_output"))

    if policy_context_output:
        for field in fields_to_stringify:
            if not rag_state.get(field) and field in policy_context_output:
                rag_state[field] = _stringify_for_rag(
                    policy_context_output.get(field)
                )

        rag_state["user_requested_restricted_data"] = policy_context_output.get(
            "user_requested_restricted_data",
            state.get("user_requested_restricted_data", False),
        )

        rag_state["restricted_data_accessed"] = policy_context_output.get(
            "restricted_data_accessed",
            state.get("restricted_data_accessed", False),
        )

        rag_state["unauthorized_dataset_accessed"] = policy_context_output.get(
            "unauthorized_dataset_accessed",
            state.get("unauthorized_dataset_accessed", False),
        )

        rag_state["agent_accessed_forbidden_dataset"] = policy_context_output.get(
            "agent_accessed_forbidden_dataset",
            state.get("agent_accessed_forbidden_dataset", False),
        )

        rag_state["user_requested_no_citations"] = policy_context_output.get(
            "user_requested_no_citations",
            state.get("user_requested_no_citations", False),
        )

        rag_state["source_citation_missing"] = policy_context_output.get(
            "source_citation_missing",
            state.get("source_citation_missing", False),
        )

    return rag_state


# ============================================================
# RAG skip helpers
# ============================================================

def _has_clear_context_block(
    context_decision: str,
    context_triggered_policies: List[TriggeredPolicy],
) -> bool:
    """
    Returns True when deterministic context already produced a clear Block.

    This is used to skip expensive RAG calls for obvious governance violations.
    """

    if _normalize_decision(context_decision) != "Block":
        return False

    for policy in context_triggered_policies:
        policy_dict = _safe_model_dump(policy)
        policy_id = policy_dict.get("policy_id")
        action = _normalize_decision(policy_dict.get("action"))

        if action == "Block" and policy_id in CLEAR_CONTEXT_BLOCK_POLICY_IDS:
            return True

    return False


def _build_policy_rag_skipped_decision(
    reason: str,
    context_decision: str,
    skipped_due_to: str,
) -> Dict[str, Any]:
    """
    Builds serializable metadata when RAG is intentionally skipped.
    """

    return {
        "decision": "Skipped",
        "context_decision": context_decision,
        "final_reason": reason,
        "evidence_available": False,
        "confidence": None,
        "source_documents": [],
        "source_pages": [],
        "triggered_rules": [],
        "retrieved_chunks": [],
        "guardrail_result": {
            "guardrail_decision": "Skipped",
            "guardrail_reason": reason,
            "guardrails_triggered": [],
        },
        "rag_skipped": True,
        "skipped_due_to": skipped_due_to,
        "generated_by": "policy_engine_rag_bypass",
    }


# ============================================================
# Triggered policy builders
# ============================================================

def _make_triggered_policy(
    policy_id: str,
    policy_name: str,
    category: str,
    action: str,
    severity: str,
    message: str,
) -> TriggeredPolicy:
    """
    Convenience builder for TriggeredPolicy.
    """

    return TriggeredPolicy(
        policy_id=policy_id,
        policy_name=policy_name,
        category=category,
        action=action,
        severity=severity,
        message=message,
    )


def _build_context_triggered_policies(
    state: Dict[str, Any],
    context: Dict[str, Any],
) -> Tuple[List[TriggeredPolicy], List[str]]:
    """
    Builds deterministic policies from policy_context_output.

    Returns:
        triggered_policies, candidate_decisions
    """

    triggered_policies: List[TriggeredPolicy] = []
    candidate_decisions: List[str] = []

    # --------------------------------------------------------
    # BLOCK rules
    # --------------------------------------------------------

    if _as_bool(_context_value(state, context, "user_requested_restricted_data", False)):
        requested_restricted = context.get("requested_restricted_datasets", [])
        dataset_text = (
            ", ".join(requested_restricted)
            if requested_restricted
            else "restricted data"
        )

        triggered_policies.append(
            _make_triggered_policy(
                policy_id="CTX-BLOCK-001",
                policy_name="Restricted Dataset Request Block",
                category="Data Governance",
                action="Block",
                severity="Critical",
                message=(
                    f"The user requested restricted dataset usage ({dataset_text}). "
                    "Restricted datasets cannot be used for supply-chain procurement, "
                    "routing, or approval decisions."
                ),
            )
        )
        candidate_decisions.append("Block")

    if _as_bool(_context_value(state, context, "restricted_data_accessed", False)):
        accessed_restricted = context.get("accessed_restricted_datasets", [])
        dataset_text = (
            ", ".join(accessed_restricted)
            if accessed_restricted
            else "restricted dataset"
        )

        triggered_policies.append(
            _make_triggered_policy(
                policy_id="CTX-BLOCK-002",
                policy_name="Restricted Dataset Access Block",
                category="Data Governance",
                action="Block",
                severity="Critical",
                message=(
                    f"Restricted data access was detected for {dataset_text}. "
                    "The workflow must be blocked and reviewed."
                ),
            )
        )
        candidate_decisions.append("Block")

    if _as_bool(_context_value(state, context, "unauthorized_dataset_accessed", False)):
        denied_accesses = context.get("denied_accesses", [])
        denied_files = [
            str(entry.get("file_name"))
            for entry in denied_accesses
            if isinstance(entry, dict) and entry.get("file_name")
        ]

        denied_text = (
            ", ".join(_unique_preserve_order(denied_files))
            if denied_files
            else "one or more datasets"
        )

        triggered_policies.append(
            _make_triggered_policy(
                policy_id="CTX-BLOCK-003",
                policy_name="Unauthorized Dataset Access Block",
                category="Data Access Control",
                action="Block",
                severity="Critical",
                message=(
                    f"Unauthorized or denied dataset access was detected for {denied_text}. "
                    "The workflow cannot proceed based on unauthorized access attempts."
                ),
            )
        )
        candidate_decisions.append("Block")

    if _as_bool(_context_value(state, context, "agent_accessed_forbidden_dataset", False)):
        forbidden_accesses = context.get("forbidden_accesses", [])
        forbidden_files = [
            str(entry.get("file_name"))
            for entry in forbidden_accesses
            if isinstance(entry, dict) and entry.get("file_name")
        ]

        forbidden_text = (
            ", ".join(_unique_preserve_order(forbidden_files))
            if forbidden_files
            else "a user-forbidden dataset"
        )

        triggered_policies.append(
            _make_triggered_policy(
                policy_id="CTX-BLOCK-004",
                policy_name="User-Forbidden Dataset Access Block",
                category="User Instruction Governance",
                action="Block",
                severity="Critical",
                message=(
                    f"An agent attempted to access {forbidden_text}, which the user explicitly forbade. "
                    "This is a user-instruction violation and must be blocked."
                ),
            )
        )
        candidate_decisions.append("Block")

    if _as_bool(_context_value(state, context, "user_requested_no_citations", False)):
        triggered_policies.append(
            _make_triggered_policy(
                policy_id="CTX-BLOCK-005",
                policy_name="No-Citation Request Block",
                category="Audit Traceability",
                action="Block",
                severity="High",
                message=(
                    "The user requested omission of source files, source records, "
                    "or policy evidence. Audit-ready recommendations require source "
                    "traceability and policy evidence."
                ),
            )
        )
        candidate_decisions.append("Block")

    if _as_bool(_context_value(state, context, "source_citation_missing", False)):
        missing_outputs = context.get("missing_source_outputs", [])
        missing_text = (
            ", ".join(missing_outputs)
            if missing_outputs
            else "one or more successful outputs"
        )

        triggered_policies.append(
            _make_triggered_policy(
                policy_id="CTX-BLOCK-006",
                policy_name="Missing Source Traceability Block",
                category="Audit Traceability",
                action="Block",
                severity="High",
                message=(
                    f"Source traceability is missing for {missing_text}. "
                    "The workflow cannot be approved without source files and source record identifiers."
                ),
            )
        )
        candidate_decisions.append("Block")

    if _as_bool(context.get("supplier_is_non_compliant", False)):
        supplier_id = context.get("recommended_supplier_id")

        triggered_policies.append(
            _make_triggered_policy(
                policy_id="CTX-BLOCK-007",
                policy_name="Non-Compliant Supplier Block",
                category="Supplier Governance",
                action="Block",
                severity="Critical",
                message=(
                    f"Recommended supplier {supplier_id} is marked Non-Compliant. "
                    "Procurement recommendations using non-compliant suppliers must be blocked."
                ),
            )
        )
        candidate_decisions.append("Block")

    if _as_bool(context.get("supplier_is_unapproved", False)):
        supplier_id = context.get("recommended_supplier_id")

        triggered_policies.append(
            _make_triggered_policy(
                policy_id="CTX-BLOCK-008",
                policy_name="Unapproved Supplier Block",
                category="Supplier Governance",
                action="Block",
                severity="High",
                message=(
                    f"Recommended supplier {supplier_id} is not approved. "
                    "Procurement recommendations using unapproved suppliers must be blocked."
                ),
            )
        )
        candidate_decisions.append("Block")

    if context.get("context_build_status") == "failed":
        triggered_policies.append(
            _make_triggered_policy(
                policy_id="CTX-BLOCK-009",
                policy_name="Policy Context Build Failure",
                category="Policy Engine System Guardrail",
                action="Block",
                severity="High",
                message=(
                    "Policy context could not be built successfully. "
                    "The workflow cannot be safely evaluated without normalized governance context."
                ),
            )
        )
        candidate_decisions.append("Block")

    # --------------------------------------------------------
    # ESCALATE rules
    # --------------------------------------------------------

    if _as_bool(_context_value(state, context, "user_instruction_violation", False)):
        completed_forbidden_steps = context.get("completed_forbidden_steps", [])
        step_text = (
            ", ".join(completed_forbidden_steps)
            if completed_forbidden_steps
            else "a user instruction"
        )

        triggered_policies.append(
            _make_triggered_policy(
                policy_id="CTX-ESC-001",
                policy_name="User Instruction Violation Escalation",
                category="User Instruction Governance",
                action="Escalate",
                severity="High",
                message=(
                    f"The workflow appears to have violated {step_text}. "
                    "Human review is required before proceeding."
                ),
            )
        )
        candidate_decisions.append("Escalate")

    procurement_value = _safe_float(context.get("procurement_value"), 0.0)

    if procurement_value > HIGH_VALUE_PROCUREMENT_THRESHOLD:
        triggered_policies.append(
            _make_triggered_policy(
                policy_id="CTX-ESC-002",
                policy_name="High-Value Procurement Escalation",
                category="Procurement Governance",
                action="Escalate",
                severity="Medium",
                message=(
                    f"Procurement value INR {round(procurement_value, 2)} exceeds the threshold "
                    f"of INR {round(HIGH_VALUE_PROCUREMENT_THRESHOLD, 2)}. "
                    "Human approval is required."
                ),
            )
        )
        candidate_decisions.append("Escalate")

    if _as_bool(context.get("supplier_under_review", False)):
        supplier_id = context.get("recommended_supplier_id")

        triggered_policies.append(
            _make_triggered_policy(
                policy_id="CTX-ESC-003",
                policy_name="Supplier Under Review Escalation",
                category="Supplier Governance",
                action="Escalate",
                severity="Medium",
                message=(
                    f"Recommended supplier {supplier_id} is under review. "
                    "Human review is required before procurement execution."
                ),
            )
        )
        candidate_decisions.append("Escalate")

    if _as_bool(context.get("route_medium_or_higher_disruption", False)):
        route_id = context.get("recommended_route_id")
        severity = context.get("route_disruption_severity")

        triggered_policies.append(
            _make_triggered_policy(
                policy_id="CTX-ESC-004",
                policy_name="Active Route Disruption Escalation",
                category="Logistics Governance",
                action="Escalate",
                severity="High" if severity in {"High", "Critical"} else "Medium",
                message=(
                    f"Recommended route {route_id} has an active disruption with severity {severity}. "
                    "Logistics review is required before execution."
                ),
            )
        )
        candidate_decisions.append("Escalate")

    if _as_bool(context.get("any_agent_failed", False)):
        failed_agents = context.get("failed_agents", [])
        failed_text = (
            ", ".join(failed_agents)
            if failed_agents
            else "one or more agents"
        )

        triggered_policies.append(
            _make_triggered_policy(
                policy_id="CTX-ESC-005",
                policy_name="Agent Failure Escalation",
                category="Workflow Reliability",
                action="Escalate",
                severity="High",
                message=(
                    f"The workflow contains failed agent outputs: {failed_text}. "
                    "Human review is required before relying on the recommendation."
                ),
            )
        )
        candidate_decisions.append("Escalate")

    if _as_bool(context.get("external_communication_requested", False)):
        triggered_policies.append(
            _make_triggered_policy(
                policy_id="CTX-ESC-006",
                policy_name="External Communication Request Escalation",
                category="External Communication Governance",
                action="Escalate",
                severity="Medium",
                message=(
                    "The user requested external communication, such as sending an email "
                    "or purchase order. Human approval is required before external communication."
                ),
            )
        )
        candidate_decisions.append("Escalate")

    if _as_bool(context.get("external_communication_attempted", False)):
        triggered_policies.append(
            _make_triggered_policy(
                policy_id="CTX-ESC-007",
                policy_name="External Communication Attempt Escalation",
                category="External Communication Governance",
                action="Escalate",
                severity="High",
                message=(
                    "An external communication attempt was detected. "
                    "Human review is required before proceeding."
                ),
            )
        )
        candidate_decisions.append("Escalate")

    if _as_bool(context.get("unauthorized_tool_used", False)):
        triggered_policies.append(
            _make_triggered_policy(
                policy_id="CTX-ESC-008",
                policy_name="Unauthorized Tool Use Escalation",
                category="Tool Governance",
                action="Escalate",
                severity="High",
                message=(
                    "Unauthorized tool usage was detected. "
                    "Human review is required before proceeding."
                ),
            )
        )
        candidate_decisions.append("Escalate")

    return triggered_policies, candidate_decisions


def _convert_rag_rules_to_triggered_policies(rag_decision: Any) -> List[TriggeredPolicy]:
    """
    Converts PDF-extracted RAG rules into existing TriggeredPolicy schema.
    """

    if rag_decision is None:
        return []

    triggered_policies: List[TriggeredPolicy] = []

    for index, rule in enumerate(getattr(rag_decision, "triggered_rules", []), start=1):
        evidence_text = ""

        if getattr(rule, "evidence", None) and getattr(rule.evidence, "evidence_text", None):
            evidence_text = rule.evidence.evidence_text

        message = (
            evidence_text
            if evidence_text
            else f"PDF-extracted policy rule triggered: {rule.policy_name}"
        )

        triggered_policy = TriggeredPolicy(
            policy_id=f"PDF-POL-{index:03d}",
            policy_name=rule.policy_name,
            category=rule.policy_area,
            action=rule.action,
            severity=rule.severity,
            message=message,
        )

        triggered_policies.append(triggered_policy)

    if (
        not triggered_policies
        and getattr(rag_decision, "decision", "Allow") != "Allow"
        and getattr(rag_decision, "guardrail_result", None)
    ):
        triggered_policies.append(
            TriggeredPolicy(
                policy_id="PDF-GUARDRAIL-001",
                policy_name="PDF Policy RAG Guardrail",
                category="Policy Interpretation Guardrail",
                action=rag_decision.decision,
                severity="High",
                message=rag_decision.guardrail_result.guardrail_reason,
            )
        )

    return triggered_policies


# ============================================================
# Policy output builders
# ============================================================

def _build_policy_message(
    final_decision: str,
    context_decision: str,
    rag_decision_value: Optional[str],
    triggered_policy_count: int,
) -> str:
    """
    Builds a concise policy output message.
    """

    rag_text = rag_decision_value if rag_decision_value else "Unavailable"

    return (
        "Policy evaluation completed using normalized policy context "
        "and conditional PDF-first RAG evidence. "
        f"Final decision: {final_decision}. "
        f"Context decision: {context_decision}. "
        f"RAG decision: {rag_text}. "
        f"Triggered policies: {triggered_policy_count}."
    )


def _build_policy_output(
    state: Dict[str, Any],
    final_decision: str,
    context_decision: str,
    rag_decision_value: Optional[str],
    triggered_policies: List[TriggeredPolicy],
    rag_decision: Any = None,
    status: str = "success",
    include_policy_handbook: bool = False,
) -> PolicyEngineOutput:
    """
    Builds PolicyEngineOutput from context + RAG results.
    """

    source_files = _collect_policy_source_files(
        state=state,
        include_policy_handbook=include_policy_handbook,
    )

    source_record_ids: List[str] = []

    if rag_decision is not None:
        source_record_ids = [
            f"policy_page_{page}"
            for page in getattr(rag_decision, "source_pages", [])
        ]

    return PolicyEngineOutput(
        run_id=state.get("run_id", "RUN-UNKNOWN"),
        step_id="STEP-006",
        agent_id="policy_engine",
        agent_name="Policy Engine",
        status=status,
        source_files=source_files,
        source_record_ids=source_record_ids,
        message=_build_policy_message(
            final_decision=final_decision,
            context_decision=context_decision,
            rag_decision_value=rag_decision_value,
            triggered_policy_count=len(triggered_policies),
        ),
        evaluated_agent_id=_infer_evaluated_agent_id(state),
        triggered_policies=triggered_policies,
        policy_decision=final_decision,
        decision_priority_applied="Block > Escalate > Allow",
    )


def _build_policy_rag_error_decision(error: Exception) -> Dict[str, Any]:
    """
    Builds a serializable RAG error object.
    """

    error_message = str(error)

    return {
        "decision": "Escalate",
        "final_reason": (
            "Policy RAG evaluation failed. Human review required before action can proceed."
        ),
        "error": error_message,
        "generated_by": "policy_engine_rag_safe_fallback",
    }


# ============================================================
# Main LangGraph node
# ============================================================

def policy_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    LangGraph policy node.

    This node:
    1. Reads policy_context_output generated by Policy Context Builder.
    2. Applies deterministic governance rules for restricted data, unauthorized
       access, source traceability, supplier governance, route disruption, and
       workflow failures.
    3. Conditionally calls the PDF-first Policy RAG Agent.
    4. Combines decisions using priority: Block > Escalate > Allow.
    5. Returns PolicyEngineOutput, policy_rag_decision, and final_decision.
    """

    context = _get_policy_context(state)

    context_triggered_policies, context_candidate_decisions = (
        _build_context_triggered_policies(
            state=state,
            context=context,
        )
    )

    context_decision = _highest_priority_decision(context_candidate_decisions)

    rag_decision = None
    rag_decision_dict: Dict[str, Any]
    rag_triggered_policies: List[TriggeredPolicy] = []
    rag_candidate_decision = "Allow"
    rag_decision_value_for_message: Optional[str] = None
    include_policy_handbook = False

    context_block_exists = _normalize_decision(context_decision) == "Block"

    should_run_rag = ENABLE_POLICY_RAG

    if context_block_exists and not RUN_RAG_ON_CLEAR_CONTEXT_BLOCK:
        should_run_rag = False
        rag_candidate_decision = "Allow"
        rag_decision_dict = _build_policy_rag_skipped_decision(
            reason=(
                "PDF RAG was skipped because deterministic policy context already "
                "produced a Block decision. Since policy priority is Block > Escalate > Allow, "
                "RAG evidence is not required to determine the final decision."
            ),
            context_decision=context_decision,
            skipped_due_to="context_block_decision",
        )
        rag_decision_value_for_message = "Skipped"

    elif not ENABLE_POLICY_RAG:
        should_run_rag = False
        rag_decision_dict = _build_policy_rag_skipped_decision(
            reason=(
                "PDF RAG was skipped because ENABLE_POLICY_RAG is set to false."
            ),
            context_decision=context_decision,
            skipped_due_to="rag_disabled_by_config",
        )
        rag_decision_value_for_message = "Skipped"
        rag_candidate_decision = "Allow"

    else:
        rag_decision_dict = {}

    if should_run_rag:
        try:
            rag_safe_state = _build_rag_safe_state(state)

            rag_decision = evaluate_policy_with_rag_from_state(rag_safe_state)

            rag_decision_dict = _safe_model_dump(rag_decision)

            rag_candidate_decision = _normalize_decision(
                getattr(rag_decision, "decision", "Allow")
            )

            rag_decision_value_for_message = rag_candidate_decision

            rag_triggered_policies = _convert_rag_rules_to_triggered_policies(
                rag_decision
            )

            include_policy_handbook = True

        except Exception as exc:
            rag_decision_dict = _build_policy_rag_error_decision(exc)
            rag_candidate_decision = "Escalate"
            rag_decision_value_for_message = "Escalate"

            rag_triggered_policies = [
                _make_triggered_policy(
                    policy_id="PDF-RAG-ERROR-001",
                    policy_name="Policy RAG Evaluation Failure",
                    category="Policy Engine System Guardrail",
                    action="Escalate",
                    severity="High",
                    message=(
                        "Policy RAG evaluation failed. Human review is required before proceeding. "
                        f"Error: {str(exc)}"
                    ),
                )
            ]

            include_policy_handbook = False

    all_triggered_policies = context_triggered_policies + rag_triggered_policies

    final_decision = _highest_priority_decision(
        [
            context_decision,
            rag_candidate_decision,
        ]
    )

    policy_output = _build_policy_output(
        state=state,
        final_decision=final_decision,
        context_decision=context_decision,
        rag_decision_value=rag_decision_value_for_message,
        triggered_policies=all_triggered_policies,
        rag_decision=rag_decision,
        status="success",
        include_policy_handbook=include_policy_handbook,
    )

    return {
        "policy_output": _safe_model_dump(policy_output),
        "policy_rag_decision": rag_decision_dict,
        "final_decision": final_decision,
    }


# ============================================================
# Optional local manual test
# ============================================================

if __name__ == "__main__":
    test_state = {
        "run_id": "RUN-POLICY-TEST-RESTRICTED-DATA-001",
        "user_query": (
            "Use payroll.csv to verify whether procurement for P-103 "
            "in North should be approved."
        ),
        "policy_context_output": {
            "context_build_status": "success",
            "product_id": "P-103",
            "region": "North",
            "requested_datasets": ["payroll.csv"],
            "requested_restricted_datasets": ["payroll.csv"],
            "user_requested_restricted_data": True,
            "restricted_data_accessed": False,
            "unauthorized_dataset_accessed": False,
            "source_citation_missing": False,
            "user_requested_no_citations": False,
            "procurement_recommendation_exists": True,
            "recommended_supplier_id": "S-007",
            "supplier_is_approved": "Yes",
            "supplier_compliance_status": "Compliant",
            "supplier_is_unapproved": False,
            "supplier_is_non_compliant": False,
            "procurement_value": 198000,
            "route_disruption_exists": False,
            "route_medium_or_higher_disruption": False,
            "any_agent_failed": False,
            "dataset_accessed": ["products.csv", "suppliers.csv"],
            "dataset_access_attempted": ["products.csv", "suppliers.csv"],
        },
    }

    result = policy_node(test_state)

    print("Policy Engine executed.")
    print("Final decision:", result["final_decision"])

    print("Policy output:")
    print(result["policy_output"])

    print("Policy RAG decision summary:")
    print(result["policy_rag_decision"])
