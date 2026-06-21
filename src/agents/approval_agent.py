import os
from datetime import datetime, timezone
from typing import Any, Dict, List

from langgraph.types import interrupt

from src.schemas.governance import HumanApprovalOutput


# ============================================================
# Approval Agent
# ============================================================
# Purpose:
# Converts policy/risk decisions into a human-in-the-loop approval
# workflow decision.
#
# Governance update:
# - Consumes policy_context_output as the primary governance context.
# - Does not override final_decision.
# - Blocks when Policy Engine blocks.
# - Escalates to the right reviewer when human review is required.
# - Allows auto-approval only when policy allows and risk is acceptable.
#
# HITL update:
# - Uses LangGraph interrupt() only when approval is genuinely pending.
# - Does not interrupt for Allow / Not Required cases.
# - Does not allow human override for Block cases.
# - Human decision is captured after graph resume.
#
# Important:
# - Does NOT call LLM.
# - Does NOT call RAG.
# - Does NOT write to SQLite directly.
# - Does NOT send emails or notifications.
# - Does NOT change final_decision.
# ============================================================


ENABLE_LANGGRAPH_HITL_APPROVAL = (
    os.getenv("ENABLE_LANGGRAPH_HITL_APPROVAL", "true").strip().lower() == "true"
)


APPROVAL_STATUSES = {
    "Pending",
    "Not Required",
    "Blocked",
    "Approved",
    "Rejected",
    "Revision Requested",
}


HUMAN_REVIEW_DECISIONS = {
    "Approve",
    "Reject",
    "Request Revision",
}


HIGH_RISK_LEVELS = {
    "High",
    "Critical",
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
    Converts dict-like or Pydantic object to plain dictionary.
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
    Converts value to a clean list[str].
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


def _get_triggered_policy_names(policy_output: Dict[str, Any]) -> List[str]:
    """
    Extracts triggered policy names from policy_output.
    """

    triggered_policies = policy_output.get("triggered_policies", [])
    policy_names: List[str] = []

    if isinstance(triggered_policies, list):
        for policy in triggered_policies:
            policy_dict = _as_dict(policy)
            policy_name = policy_dict.get("policy_name")

            if policy_name:
                policy_names.append(str(policy_name))

    return _unique_preserve_order(policy_names)


def _get_policy_decision(
    state: Dict[str, Any],
    policy_output: Dict[str, Any],
) -> str:
    """
    Determines policy decision from policy_output or final_decision.
    """

    return _normalize_string(
        policy_output.get("policy_decision", state.get("final_decision", "Escalate")),
        default="Escalate",
    )


def _get_risk_level(risk_output: Dict[str, Any]) -> str:
    """
    Extracts risk level from risk_output.
    """

    return _normalize_string(
        risk_output.get("risk_level", "Unknown"),
        default="Unknown",
    )


def _get_risk_score(risk_output: Dict[str, Any]) -> float:
    """
    Extracts risk score from risk_output.
    """

    return _safe_number(
        risk_output.get("final_risk_score", 0),
        default=0,
    )


# ============================================================
# Reviewer routing
# ============================================================

def _determine_reviewer_role(
    policy_decision: str,
    risk_level: str,
    policy_context: Dict[str, Any],
    state: Dict[str, Any],
) -> str:
    """
    Determines reviewer role based on policy context and risk context.

    Priority:
    1. Restricted/unauthorized data governance issue
    2. Source/citation issue
    3. Supplier governance issue
    4. Route disruption issue
    5. High-value procurement
    6. Agent failure / system reliability
    7. External communication/tool issue
    8. Policy block
    9. High/Critical risk
    10. Default supply chain approval
    """

    if (
        _safe_bool(policy_context.get("user_requested_restricted_data"))
        or _safe_bool(policy_context.get("restricted_data_accessed"))
        or _safe_bool(policy_context.get("unauthorized_dataset_accessed"))
        or _safe_bool(policy_context.get("agent_accessed_forbidden_dataset"))
    ):
        return "Data Governance / Compliance Team"

    if (
        _safe_bool(policy_context.get("user_requested_no_citations"))
        or _safe_bool(policy_context.get("source_citation_missing"))
    ):
        return "Audit Compliance Team"

    if (
        _safe_bool(policy_context.get("supplier_is_unapproved"))
        or _safe_bool(policy_context.get("supplier_is_non_compliant"))
        or _safe_bool(policy_context.get("supplier_under_review"))
    ):
        return "Supplier Governance Team"

    if _safe_bool(policy_context.get("route_medium_or_higher_disruption")):
        return "Logistics Manager"

    procurement_value = _safe_number(policy_context.get("procurement_value"), 0)

    if procurement_value > 50000:
        return "Procurement Manager"

    if _safe_bool(policy_context.get("any_agent_failed")):
        return "Operations Review Team"

    if (
        _safe_bool(policy_context.get("external_communication_requested"))
        or _safe_bool(policy_context.get("external_communication_attempted"))
        or _safe_bool(policy_context.get("unauthorized_tool_used"))
        or _safe_bool(state.get("external_communication_attempted", False))
    ):
        return "Business Approver"

    if policy_decision == "Block":
        return "Governance Officer"

    if risk_level in HIGH_RISK_LEVELS:
        return "Risk Manager"

    return "Supply Chain Manager"


# ============================================================
# Approval decision logic
# ============================================================

def _determine_approval_decision(
    policy_output: Dict[str, Any],
    risk_output: Dict[str, Any],
    policy_context: Dict[str, Any],
    state: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Determines whether approval is required.

    Rules:
    - Missing policy output -> Pending
    - Missing risk output -> Pending
    - Block -> Blocked, no approval workflow
    - Escalate -> Pending human review
    - Allow + High/Critical risk -> Pending human review
    - Allow + Low/Medium risk -> Approved without manual approval
    """

    policy_missing = not bool(policy_output)
    risk_missing = not bool(risk_output)

    if policy_missing:
        return {
            "approval_required": True,
            "approval_status": "Pending",
            "reason": (
                "Policy output is missing. Human review is required before proceeding."
            ),
        }

    if risk_missing:
        return {
            "approval_required": True,
            "approval_status": "Pending",
            "reason": (
                "Risk output is missing. Human review is required before proceeding."
            ),
        }

    policy_decision = _get_policy_decision(
        state=state,
        policy_output=policy_output,
    )

    risk_level = _get_risk_level(risk_output)

    if policy_decision == "Block":
        return {
            "approval_required": False,
            "approval_status": "Blocked",
            "reason": (
                "Action was blocked by Policy Engine. A normal approval workflow "
                "was not created because the workflow must be corrected before it can proceed."
            ),
        }

    if policy_decision == "Escalate":
        return {
            "approval_required": True,
            "approval_status": "Pending",
            "reason": (
                "Policy Engine returned Escalate. Human review is required."
            ),
        }

    if risk_level in HIGH_RISK_LEVELS:
        return {
            "approval_required": True,
            "approval_status": "Pending",
            "reason": (
                f"Policy decision is Allow, but risk level is {risk_level}. "
                "Human review is required before proceeding."
            ),
        }

    return {
        "approval_required": False,
        "approval_status": "Approved",
        "reason": (
            "Policy decision is Allow and risk level does not require manual review. "
            "The action is approved without additional human approval."
        ),
    }


# ============================================================
# Action and reason builders
# ============================================================

def _build_action_under_review(
    state: Dict[str, Any],
    policy_context: Dict[str, Any],
    policy_decision: str,
    risk_level: str,
    risk_score: float,
) -> str:
    """
    Builds human-readable action under review.
    """

    procurement_output = _as_dict(state.get("procurement_output"))
    logistics_output = _as_dict(state.get("logistics_output"))

    governance_violations = _string_list(
        policy_context.get("governance_violations", [])
    )

    if policy_decision == "Block":
        if governance_violations:
            return (
                "Action blocked due to governance violation(s): "
                + ", ".join(governance_violations)
                + "."
            )

        return (
            "Action blocked by Policy Engine. Review policy output, policy context, "
            "and policy evidence for details."
        )

    if policy_context.get("procurement_recommendation_exists"):
        quantity = policy_context.get(
            "recommended_quantity",
            procurement_output.get("recommended_quantity"),
        )
        supplier_id = policy_context.get(
            "recommended_supplier_id",
            procurement_output.get("recommended_supplier_id"),
        )
        supplier_name = policy_context.get(
            "recommended_supplier_name",
            procurement_output.get("recommended_supplier_name"),
        )
        procurement_value = policy_context.get(
            "procurement_value",
            procurement_output.get("procurement_value"),
        )

        return (
            f"Procurement recommendation for {quantity} units from supplier "
            f"{supplier_id} ({supplier_name}) with value INR {procurement_value}."
        )

    if policy_context.get("recommended_route_id"):
        route_id = policy_context.get("recommended_route_id")
        severity = policy_context.get("route_disruption_severity", "None")
        status = policy_context.get("route_disruption_status", "None")

        if _safe_bool(policy_context.get("route_disruption_exists")):
            return (
                f"Logistics route {route_id} has disruption status {status} "
                f"with severity {severity} and requires review."
            )

        return f"Logistics route recommendation {route_id} is under review."

    if logistics_output and logistics_output.get("recommended_route_id"):
        route_id = logistics_output.get("recommended_route_id")
        severity = logistics_output.get("route_disruption_severity", "None")
        status = logistics_output.get("route_disruption_status", "None")

        if logistics_output.get("route_disruption_exists"):
            return (
                f"Logistics route {route_id} has disruption status {status} "
                f"with severity {severity} and requires review."
            )

        return f"Logistics route recommendation {route_id} is under review."

    if risk_level in HIGH_RISK_LEVELS:
        return (
            f"Workflow risk level is {risk_level} with final risk score {risk_score}."
        )

    return "Workflow action reviewed by Approval Agent."


def _build_approval_reason(
    approval_decision: Dict[str, Any],
    policy_context: Dict[str, Any],
    policy_output: Dict[str, Any],
    policy_rag_decision: Dict[str, Any],
    risk_output: Dict[str, Any],
    reviewer_role: str,
) -> str:
    """
    Builds approval reason using policy context, policy output, RAG, and risk output.
    """

    policy_decision = _normalize_string(
        policy_output.get("policy_decision", "Unknown"),
        default="Unknown",
    )

    risk_level = _normalize_string(
        risk_output.get("risk_level", "Unknown"),
        default="Unknown",
    )

    risk_score = _safe_number(
        risk_output.get("final_risk_score", 0),
        default=0,
    )

    triggered_policy_names = _get_triggered_policy_names(policy_output)
    governance_violations = _string_list(
        policy_context.get("governance_violations", [])
    )

    rag_reason = policy_rag_decision.get("final_reason", "")

    reason_parts = [
        approval_decision["reason"],
        f"Policy decision: {policy_decision}.",
        f"Risk score: {risk_score}, risk level: {risk_level}.",
        f"Reviewer role: {reviewer_role}.",
    ]

    if governance_violations:
        reason_parts.append(
            "Governance signals: " + ", ".join(governance_violations) + "."
        )

    if triggered_policy_names:
        reason_parts.append(
            "Triggered policies: " + ", ".join(triggered_policy_names) + "."
        )

    if rag_reason:
        reason_parts.append("PDF policy reason: " + str(rag_reason))

    return " ".join(reason_parts)


# ============================================================
# Source collection
# ============================================================

def _collect_source_files_and_records(
    state: Dict[str, Any],
    policy_context: Dict[str, Any],
) -> Dict[str, List[str]]:
    """
    Collects source files and record IDs from governance outputs and business outputs.
    """

    source_files: List[str] = []
    source_record_ids: List[str] = []

    for key in [
        "policy_output",
        "risk_output",
        "procurement_output",
        "logistics_output",
        "inventory_output",
        "forecasting_output",
    ]:
        output = _as_dict(state.get(key))

        files = output.get("source_files", [])
        record_ids = output.get("source_record_ids", [])

        if isinstance(files, list):
            source_files.extend(files)

        if isinstance(record_ids, list):
            source_record_ids.extend([str(item) for item in record_ids])

    source_files.extend(
        _string_list(policy_context.get("dataset_accessed", []))
    )

    source_files.extend(
        _string_list(policy_context.get("dataset_access_attempted", []))
    )

    policy_rag_decision = _as_dict(state.get("policy_rag_decision"))

    if policy_rag_decision and not policy_rag_decision.get("rag_skipped"):
        source_files.append("agentops_supply_chain_policy_handbook.pdf")

        for page in policy_rag_decision.get("source_pages", []):
            source_record_ids.append(f"policy_page_{page}")

    return {
        "source_files": _unique_preserve_order(source_files),
        "source_record_ids": _unique_preserve_order(source_record_ids),
    }


# ============================================================
# HITL helpers
# ============================================================

def _should_interrupt_for_human_review(
    state: Dict[str, Any],
    approval_output: Dict[str, Any],
) -> bool:
    """
    Returns True when LangGraph should pause for human approval.

    HITL is intentionally limited to genuine Pending approval cases.
    It does not run for Block because Block must not be overridden.
    """

    if not ENABLE_LANGGRAPH_HITL_APPROVAL:
        return False

    if _safe_bool(state.get("disable_hitl", False)):
        return False

    approval_required = _safe_bool(
        approval_output.get("approval_required"),
        default=False,
    )

    approval_status = _normalize_string(
        approval_output.get("approval_status"),
        default="",
    )

    policy_decision = _normalize_string(
        state.get("final_decision")
        or _as_dict(state.get("policy_output")).get("policy_decision"),
        default="",
    )

    return bool(
        approval_required
        and approval_status == "Pending"
        and policy_decision != "Block"
    )


def _build_human_review_request(
    state: Dict[str, Any],
    approval_output: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Builds JSON-serializable interrupt payload for dashboard/HITL UI.
    """

    policy_output = _as_dict(state.get("policy_output"))
    risk_output = _as_dict(state.get("risk_output"))
    policy_context = _get_policy_context(state)

    return {
        "type": "human_approval_required",
        "message": "Human approval is required before the workflow can continue.",
        "run_id": state.get("run_id"),
        "approval_id": approval_output.get("approval_id"),
        "reviewer_role": approval_output.get("reviewer_role"),
        "approval_status": approval_output.get("approval_status"),
        "approval_required": approval_output.get("approval_required"),
        "action_under_review": approval_output.get("action_under_review"),
        "approval_options": ["Approve", "Reject", "Request Revision"],
        "policy_decision": policy_output.get("policy_decision"),
        "risk_score": risk_output.get("final_risk_score"),
        "risk_level": risk_output.get("risk_level"),
        "triggered_policies": _get_triggered_policy_names(policy_output),
        "governance_violations": policy_context.get("governance_violations", []),
    }


def _normalize_human_review_input(human_review: Any) -> Dict[str, Any]:
    """
    Normalizes human review input received from Command(resume=...).
    """

    review = _as_dict(human_review)

    decision = _normalize_string(review.get("decision"))
    comment = _normalize_string(review.get("comment"))
    reviewed_by = _normalize_string(review.get("reviewed_by"), "Human Reviewer")

    if decision not in HUMAN_REVIEW_DECISIONS:
        decision = "Request Revision"

        if not comment:
            comment = (
                "Invalid or missing human review decision. "
                "Defaulted to revision request."
            )

    return {
        "decision": decision,
        "comment": comment,
        "reviewed_by": reviewed_by,
    }


def _apply_human_review_to_approval_output(
    approval_output: Dict[str, Any],
    human_review: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Applies human reviewer decision to approval_output.

    This does not change final_decision. It only updates approval state.
    """

    updated_output = dict(approval_output)

    decision = human_review["decision"]
    comment = human_review["comment"]
    reviewed_by = human_review["reviewed_by"]

    if decision == "Approve":
        updated_output["approval_status"] = "Approved"
        updated_output["approval_required"] = False
        updated_output["message"] = (
            "Human reviewer approved the escalated action. "
            "The workflow may proceed only within the reviewed and approved scope."
        )

    elif decision == "Reject":
        updated_output["approval_status"] = "Rejected"
        updated_output["approval_required"] = False
        updated_output["message"] = (
            "Human reviewer rejected the escalated action. "
            "The workflow must not proceed."
        )

    elif decision == "Request Revision":
        updated_output["approval_status"] = "Revision Requested"
        updated_output["approval_required"] = False
        updated_output["message"] = (
            "Human reviewer requested revision. "
            "The workflow should be corrected and rerun before execution."
        )

    human_review_output = {
        "human_review_completed": True,
        "decision": decision,
        "comment": comment,
        "reviewed_by": reviewed_by,
        "reviewer_role": approval_output.get("reviewer_role"),
        "approval_id": approval_output.get("approval_id"),
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
    }

    updated_output["human_review_output"] = human_review_output

    if comment:
        updated_output["message"] = (
            updated_output.get("message", "")
            + f" Reviewer comment: {comment}"
        )

    return updated_output


# ============================================================
# Main LangGraph node
# ============================================================

def approval_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    LangGraph Approval Agent node.

    Converts governance decision and risk score into approval workflow state.

    HITL behavior:
    - If approval is Pending, this node pauses using LangGraph interrupt().
    - On resume, the human decision is applied to approval_output.
    - Blocked workflows are not interrupt-approved.
    """

    run_id = state.get("run_id", "RUN-UNKNOWN")

    policy_context = _get_policy_context(state)
    policy_output = _as_dict(state.get("policy_output"))
    policy_rag_decision = _as_dict(state.get("policy_rag_decision"))
    risk_output = _as_dict(state.get("risk_output"))

    approval_decision = _determine_approval_decision(
        policy_output=policy_output,
        risk_output=risk_output,
        policy_context=policy_context,
        state=state,
    )

    policy_decision = _get_policy_decision(
        state=state,
        policy_output=policy_output,
    )

    risk_level = _get_risk_level(risk_output)
    risk_score = _get_risk_score(risk_output)

    reviewer_role = _determine_reviewer_role(
        policy_decision=policy_decision,
        risk_level=risk_level,
        policy_context=policy_context,
        state=state,
    )

    action_under_review = _build_action_under_review(
        state=state,
        policy_context=policy_context,
        policy_decision=policy_decision,
        risk_level=risk_level,
        risk_score=risk_score,
    )

    approval_reason = _build_approval_reason(
        approval_decision=approval_decision,
        policy_context=policy_context,
        policy_output=policy_output,
        policy_rag_decision=policy_rag_decision,
        risk_output=risk_output,
        reviewer_role=reviewer_role,
    )

    source_context = _collect_source_files_and_records(
        state=state,
        policy_context=policy_context,
    )

    output = HumanApprovalOutput(
        run_id=run_id,
        step_id="STEP-008",
        agent_id="approval_agent",
        agent_name="Approval Agent",
        status="success",
        source_files=source_context["source_files"],
        source_record_ids=source_context["source_record_ids"],
        message=approval_reason,
        approval_id=f"APR-{run_id}",
        approval_required=approval_decision["approval_required"],
        approval_status=approval_decision["approval_status"],
        requested_by_agent=policy_output.get("agent_id", "policy_engine"),
        reviewer_role=reviewer_role,
        action_under_review=action_under_review,
    )

    approval_output = _safe_model_dump(output)

    # --------------------------------------------------------
    # True LangGraph HITL interrupt.
    # This pauses graph execution only for Pending approval cases.
    # --------------------------------------------------------
    if _should_interrupt_for_human_review(
        state=state,
        approval_output=approval_output,
    ):
        review_request = _build_human_review_request(
            state=state,
            approval_output=approval_output,
        )

        human_review_raw = interrupt(review_request)

        human_review = _normalize_human_review_input(human_review_raw)

        approval_output = _apply_human_review_to_approval_output(
            approval_output=approval_output,
            human_review=human_review,
        )

        return {
            "approval_output": approval_output,
            "human_review_output": approval_output.get("human_review_output"),
            "human_review_completed": True,
        }

    return {
        "approval_output": approval_output,
        "human_review_completed": False,
    }


# Backward-compatible alias if workflow_graph imports a different name.
approval_agent = approval_node


# ============================================================
# Optional local manual tests
# ============================================================
# Note:
# Direct local tests disable HITL because interrupt() requires LangGraph
# checkpoint/resume context. True HITL should be tested through workflow_graph.
# ============================================================

if __name__ == "__main__":
    test_cases = [
        {
            "name": "Restricted data block",
            "state": {
                "run_id": "RUN-APPROVAL-TEST-001",
                "disable_hitl": True,
                "policy_context_output": {
                    "user_requested_restricted_data": True,
                    "requested_restricted_datasets": ["payroll.csv"],
                    "governance_violations": ["user_requested_restricted_data"],
                    "dataset_accessed": ["products.csv", "suppliers.csv"],
                    "dataset_access_attempted": ["products.csv", "suppliers.csv"],
                },
                "policy_output": {
                    "agent_id": "policy_engine",
                    "policy_decision": "Block",
                    "triggered_policies": [
                        {
                            "policy_name": "Restricted Dataset Request Block",
                            "action": "Block",
                            "severity": "Critical",
                        }
                    ],
                    "source_files": ["agentops_supply_chain_policy_handbook.pdf"],
                    "source_record_ids": ["policy_page_6"],
                },
                "policy_rag_decision": {
                    "decision": "Allow",
                    "final_reason": "RAG did not override deterministic restricted-data block.",
                    "source_pages": [6],
                },
                "risk_output": {
                    "final_risk_score": 85,
                    "risk_level": "Critical",
                    "source_files": ["products.csv", "suppliers.csv"],
                    "source_record_ids": ["S-007"],
                },
            },
        },
        {
            "name": "High-value procurement escalation",
            "state": {
                "run_id": "RUN-APPROVAL-TEST-002",
                "disable_hitl": True,
                "policy_context_output": {
                    "procurement_recommendation_exists": True,
                    "recommended_quantity": 215,
                    "recommended_supplier_id": "S-001",
                    "recommended_supplier_name": "Alpha Components Pvt Ltd",
                    "procurement_value": 387000,
                    "governance_violations": [],
                    "dataset_accessed": ["products.csv", "suppliers.csv"],
                    "dataset_access_attempted": ["products.csv", "suppliers.csv"],
                },
                "policy_output": {
                    "agent_id": "policy_engine",
                    "policy_decision": "Escalate",
                    "triggered_policies": [
                        {
                            "policy_name": "High-Value Procurement Escalation",
                            "action": "Escalate",
                            "severity": "Medium",
                        }
                    ],
                    "source_files": ["agentops_supply_chain_policy_handbook.pdf"],
                    "source_record_ids": ["policy_page_8"],
                },
                "policy_rag_decision": {
                    "decision": "Escalate",
                    "final_reason": "Procurement value exceeds approval threshold.",
                    "source_pages": [8],
                },
                "risk_output": {
                    "final_risk_score": 60,
                    "risk_level": "Medium",
                },
            },
        },
        {
            "name": "High risk even if policy allows",
            "state": {
                "run_id": "RUN-APPROVAL-TEST-003",
                "disable_hitl": True,
                "policy_context_output": {},
                "policy_output": {
                    "agent_id": "policy_engine",
                    "policy_decision": "Allow",
                    "triggered_policies": [],
                },
                "risk_output": {
                    "final_risk_score": 72,
                    "risk_level": "High",
                },
            },
        },
        {
            "name": "Safe low-risk action",
            "state": {
                "run_id": "RUN-APPROVAL-TEST-004",
                "disable_hitl": True,
                "policy_context_output": {},
                "policy_output": {
                    "agent_id": "policy_engine",
                    "policy_decision": "Allow",
                    "triggered_policies": [],
                },
                "risk_output": {
                    "final_risk_score": 20,
                    "risk_level": "Low",
                },
            },
        },
        {
            "name": "Missing policy output",
            "state": {
                "run_id": "RUN-APPROVAL-TEST-005",
                "disable_hitl": True,
                "risk_output": {
                    "final_risk_score": 20,
                    "risk_level": "Low",
                },
            },
        },
    ]

    for case in test_cases:
        print("=" * 100)
        print("CASE:", case["name"])

        result = approval_node(case["state"])
        approval_output = result["approval_output"]

        print("Approval required:", approval_output["approval_required"])
        print("Approval status:", approval_output["approval_status"])
        print("Reviewer role:", approval_output["reviewer_role"])
        print("Action under review:", approval_output["action_under_review"])
        print("Human review completed:", result.get("human_review_completed"))
        print("Message:", approval_output["message"])
