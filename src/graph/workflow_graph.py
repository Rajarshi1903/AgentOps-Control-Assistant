import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

try:
    from langgraph.errors import GraphInterrupt
except ImportError:
    GraphInterrupt = None

from src.schemas.state import AgentGraphState

# Business agent nodes
from src.agents.coordinator_agent import coordinator_node
from src.agents.forecasting_agent import forecasting_node
from src.agents.inventory_agent import inventory_node
from src.agents.procurement_agent import procurement_node
from src.agents.logistics_agent import logistics_node

# Governance nodes
from src.governance.policy_context_builder import policy_context_node
from src.governance.policy_engine import policy_node
from src.governance.risk_scoring_engine import risk_node

# Approval, audit, and final response nodes
from src.agents.approval_agent import approval_node
from src.storage.audit_logger import audit_node
from src.agents.final_response_agent import final_response_node


# ============================================================
# Valid workflow step names
# ============================================================

VALID_WORKFLOW_STEPS: Set[str] = {
    "forecasting",
    "inventory",
    "procurement",
    "logistics",
    "policy_context",
    "policy",
    "risk",
    "approval",
    "audit",
    "final_response",
}


# ============================================================
# Canonical workflow execution order
# ============================================================

CANONICAL_STEP_ORDER: List[str] = [
    "forecasting",
    "inventory",
    "procurement",
    "logistics",
    "policy_context",
    "policy",
    "risk",
    "approval",
    "audit",
    "final_response",
]


# ============================================================
# User-skippable versus mandatory governance steps
# ============================================================

USER_SKIPPABLE_STEPS: Set[str] = {
    "forecasting",
    "inventory",
    "procurement",
    "logistics",
}

MANDATORY_GOVERNANCE_STEPS: List[str] = [
    "policy_context",
    "policy",
    "audit",
    "final_response",
]


# ============================================================
# Intent-to-workflow fallback map
# ============================================================

INTENT_WORKFLOW_MAP: Dict[str, List[str]] = {
    "demand_spike": [
        "forecasting",
        "inventory",
        "procurement",
        "logistics",
        "policy_context",
        "policy",
        "risk",
        "approval",
        "audit",
        "final_response",
    ],
    "supply_chain_decision": [
        "forecasting",
        "inventory",
        "procurement",
        "logistics",
        "policy_context",
        "policy",
        "risk",
        "approval",
        "audit",
        "final_response",
    ],
    "forecast": [
        "forecasting",
        "policy_context",
        "policy",
        "risk",
        "audit",
        "final_response",
    ],
    "inventory": [
        "inventory",
        "policy_context",
        "policy",
        "audit",
        "final_response",
    ],
    "procurement": [
        "inventory",
        "procurement",
        "policy_context",
        "policy",
        "risk",
        "approval",
        "audit",
        "final_response",
    ],
    "supplier_lookup": [
        "procurement",
        "policy_context",
        "policy",
        "risk",
        "approval",
        "audit",
        "final_response",
    ],
    "logistics": [
        "logistics",
        "policy_context",
        "policy",
        "risk",
        "approval",
        "audit",
        "final_response",
    ],
    "route_risk": [
        "logistics",
        "policy_context",
        "policy",
        "risk",
        "approval",
        "audit",
        "final_response",
    ],
    "general": [
        "policy_context",
        "policy",
        "audit",
        "final_response",
    ],
}


# ============================================================
# Dependency groups
# ============================================================

RISK_RELEVANT_STEPS: Set[str] = {
    "forecasting",
    "procurement",
    "logistics",
}

APPROVAL_RELEVANT_STEPS: Set[str] = {
    "procurement",
    "logistics",
}

GOVERNANCE_TRIGGER_FLAGS: List[str] = [
    "user_requested_restricted_data",
    "restricted_data_accessed",
    "unauthorized_dataset_accessed",
    "agent_accessed_forbidden_dataset",
    "user_instruction_violation",
    "user_requested_no_citations",
    "source_citation_missing",
    "external_communication_requested",
    "external_communication_attempted",
    "unauthorized_tool_used",
]


# ============================================================
# Small helpers
# ============================================================

def _unique_preserve_order(values: List[str]) -> List[str]:
    """Returns unique values while preserving order."""

    seen = set()
    result: List[str] = []

    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)

    return result


def _valid_unique_steps(steps: List[str]) -> List[str]:
    """Keeps only valid workflow steps and removes duplicates."""

    return _unique_preserve_order(
        [step for step in steps if step in VALID_WORKFLOW_STEPS]
    )


def _canonical_order(steps: List[str]) -> List[str]:
    """Orders steps according to CANONICAL_STEP_ORDER."""

    step_set = set(steps)
    return [step for step in CANONICAL_STEP_ORDER if step in step_set]


def _as_bool(value: Any) -> bool:
    """Safely converts common bool-like values to bool."""

    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "y", "1"}

    if isinstance(value, (int, float)):
        return bool(value)

    return False


def _governance_triggered(state: AgentGraphState) -> bool:
    """Returns True if the state already contains governance-risk flags."""

    return any(_as_bool(state.get(flag)) for flag in GOVERNANCE_TRIGGER_FLAGS)


def _build_forbidden_step_skip_reasons(forbidden_steps: List[str]) -> Dict[str, str]:
    """
    Builds skip reasons for all user-forbidden steps.
    """

    skip_reason: Dict[str, str] = {}

    for step in forbidden_steps:
        if step in USER_SKIPPABLE_STEPS:
            skip_reason[step] = "Skipped because user explicitly forbade this workflow step."
        elif step in VALID_WORKFLOW_STEPS:
            skip_reason[step] = (
                "User requested this governance step to be skipped, but governance "
                "steps may still run if required by policy or risk controls."
            )

    return skip_reason


def _is_graph_interrupt(exc: Exception) -> bool:
    """
    Returns True if the caught exception is a LangGraph interrupt signal.

    Important:
    Node wrappers must re-raise GraphInterrupt. If wrappers catch it as a normal
    exception, LangGraph HITL interrupt will not pause/resume correctly.
    """

    return GraphInterrupt is not None and isinstance(exc, GraphInterrupt)


# ============================================================
# Timing helpers
# ============================================================

def _utc_now_iso() -> str:
    """
    Returns current UTC timestamp in ISO format.
    """

    return datetime.now(timezone.utc).isoformat()


def _build_timing_record(
    step_name: str,
    started_at: str,
    ended_at: str,
    duration_seconds: float,
    status: str,
    error: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Builds a normalized timing record for one workflow node.
    """

    record = {
        "step": step_name,
        "status": status,
        "duration_seconds": round(float(duration_seconds), 3),
        "started_at": started_at,
        "ended_at": ended_at,
    }

    if error:
        record["error"] = error

    return record


def _append_node_timing(
    state: AgentGraphState,
    timing_record: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Appends one timing record to state-level node_timings.
    """

    node_timings = list(state.get("node_timings", []))
    node_timings.append(timing_record)

    workflow_duration_seconds = round(
        sum(
            float(item.get("duration_seconds", 0.0))
            for item in node_timings
            if isinstance(item, dict)
        ),
        3,
    )

    return {
        "node_timings": node_timings,
        "workflow_duration_seconds": workflow_duration_seconds,
        "last_completed_step_timing": timing_record,
    }


# ============================================================
# Workflow normalization
# ============================================================

def normalize_workflow_steps(state: AgentGraphState) -> Dict[str, Any]:
    """
    Creates a clean workflow plan.
    """

    raw_steps = list(state.get("workflow_steps", []))

    if not raw_steps:
        intent = state.get("intent", "general")
        raw_steps = INTENT_WORKFLOW_MAP.get(
            intent,
            INTENT_WORKFLOW_MAP["general"],
        )

    cleaned_steps = _valid_unique_steps(raw_steps)
    forbidden_steps = _valid_unique_steps(list(state.get("forbidden_steps", [])))
    forbidden_set = set(forbidden_steps)

    skip_reason = dict(state.get("skip_reason", {}))
    skip_reason.update(_build_forbidden_step_skip_reasons(forbidden_steps))

    # Procurement generally requires inventory context.
    if "procurement" in cleaned_steps:
        if "inventory" not in cleaned_steps and "inventory" not in forbidden_set:
            cleaned_steps.append("inventory")

    # Procurement/logistics require governance, risk, approval, audit, final response.
    if any(step in cleaned_steps for step in APPROVAL_RELEVANT_STEPS):
        for required_step in [
            "policy_context",
            "policy",
            "risk",
            "approval",
            "audit",
            "final_response",
        ]:
            if required_step not in cleaned_steps:
                cleaned_steps.append(required_step)

    # Forecasting should include governance/risk/audit/final response.
    if "forecasting" in cleaned_steps:
        for required_step in [
            "policy_context",
            "policy",
            "risk",
            "audit",
            "final_response",
        ]:
            if required_step not in cleaned_steps:
                cleaned_steps.append(required_step)

    # Inventory-only checks require basic governance/audit/final response.
    if "inventory" in cleaned_steps:
        for required_step in ["policy_context", "policy", "audit", "final_response"]:
            if required_step not in cleaned_steps:
                cleaned_steps.append(required_step)

    # If policy is present, policy_context must run before policy.
    if "policy" in cleaned_steps and "policy_context" not in cleaned_steps:
        cleaned_steps.append("policy_context")

    # Any governance-triggering flag should force governance path.
    if _governance_triggered(state):
        for required_step in [
            "policy_context",
            "policy",
            "risk",
            "approval",
            "audit",
            "final_response",
        ]:
            if required_step not in cleaned_steps:
                cleaned_steps.append(required_step)

    # Always ensure minimum governance traceability.
    for required_step in MANDATORY_GOVERNANCE_STEPS:
        if required_step not in cleaned_steps:
            cleaned_steps.append(required_step)

    # Enforce user-forbidden business steps.
    filtered_steps: List[str] = []

    for step in cleaned_steps:
        if step in forbidden_set and step in USER_SKIPPABLE_STEPS:
            skip_reason[step] = "Skipped because user explicitly forbade this workflow step."
            continue

        if step not in filtered_steps:
            filtered_steps.append(step)

    ordered_steps = _canonical_order(filtered_steps)

    if "final_response" in ordered_steps:
        ordered_steps = [step for step in ordered_steps if step != "final_response"]
        ordered_steps.append("final_response")

    return {
        "workflow_steps": ordered_steps,
        "skip_reason": skip_reason,
    }


# ============================================================
# Step completion helper
# ============================================================

def mark_step_complete(
    state: AgentGraphState,
    step_name: str,
) -> List[str]:
    """
    Returns updated completed_steps list.
    Does not mutate state directly.
    """

    completed_steps = list(state.get("completed_steps", []))

    if step_name not in completed_steps:
        completed_steps.append(step_name)

    return completed_steps


# ============================================================
# Generic node wrapper
# ============================================================

def wrap_node(step_name: str, node_func: Callable[[AgentGraphState], Dict[str, Any]]):
    """
    Wraps a LangGraph node while preserving node state updates.

    HITL-specific behavior:
    - If LangGraph interrupt is raised, re-raise it.
    - Do not mark the node complete.
    - Do not log it as failed.
    - Let LangGraph checkpoint and pause execution.
    """

    def wrapped_node(state: AgentGraphState) -> Dict[str, Any]:
        started_at = _utc_now_iso()
        start_time = time.perf_counter()

        try:
            node_result = node_func(state)

            if node_result is None:
                node_result = {}

            if not isinstance(node_result, dict):
                raise TypeError(
                    f"{step_name} node must return dict, got {type(node_result)}"
                )

            duration_seconds = time.perf_counter() - start_time
            ended_at = _utc_now_iso()

            timing_record = _build_timing_record(
                step_name=step_name,
                started_at=started_at,
                ended_at=ended_at,
                duration_seconds=duration_seconds,
                status="success",
            )

            timing_update = _append_node_timing(
                state=state,
                timing_record=timing_record,
            )

            completed_steps = mark_step_complete(
                state=state,
                step_name=step_name,
            )

            return {
                **node_result,
                **timing_update,
                "completed_steps": completed_steps,
            }

        except Exception as exc:
            if _is_graph_interrupt(exc):
                raise

            duration_seconds = time.perf_counter() - start_time
            ended_at = _utc_now_iso()

            error_message = str(exc)

            timing_record = _build_timing_record(
                step_name=step_name,
                started_at=started_at,
                ended_at=ended_at,
                duration_seconds=duration_seconds,
                status="failed",
                error=error_message,
            )

            timing_update = _append_node_timing(
                state=state,
                timing_record=timing_record,
            )

            completed_steps = mark_step_complete(
                state=state,
                step_name=step_name,
            )

            errors = list(state.get("errors", []))
            errors.append(
                {
                    "step": step_name,
                    "error": error_message,
                }
            )

            return {
                **timing_update,
                "completed_steps": completed_steps,
                "errors": errors,
            }

    return wrapped_node


# ============================================================
# Coordinator wrapper
# ============================================================

def coordinator_wrapper(state: AgentGraphState) -> Dict[str, Any]:
    """
    Coordinator wrapper with workflow normalization and timing.

    HITL-specific behavior:
    - Re-raises GraphInterrupt if ever surfaced here.
    """

    step_name = "coordinator"
    started_at = _utc_now_iso()
    start_time = time.perf_counter()

    try:
        result = coordinator_node(state)

        if result is None:
            result = {}

        if not isinstance(result, dict):
            raise TypeError(
                f"coordinator_node must return dict, got {type(result)}"
            )

        temp_state = dict(state)
        temp_state.update(result)

        normalization = normalize_workflow_steps(temp_state)
        normalized_steps = normalization["workflow_steps"]

        existing_skip_reason = dict(state.get("skip_reason", {}))
        result_skip_reason = dict(result.get("skip_reason", {}))
        normalized_skip_reason = dict(normalization.get("skip_reason", {}))

        merged_skip_reason = {}
        merged_skip_reason.update(existing_skip_reason)
        merged_skip_reason.update(result_skip_reason)
        merged_skip_reason.update(normalized_skip_reason)

        completed_steps = mark_step_complete(
            state=state,
            step_name=step_name,
        )

        errors = list(state.get("errors", []))
        result_errors = result.get("errors", [])

        if result_errors:
            errors = list(result_errors)

        coordinator_output = dict(result.get("coordinator_output", {}))

        if coordinator_output:
            coordinator_output["workflow_steps"] = normalized_steps
            coordinator_output["skip_reason"] = merged_skip_reason

        duration_seconds = time.perf_counter() - start_time
        ended_at = _utc_now_iso()

        timing_record = _build_timing_record(
            step_name=step_name,
            started_at=started_at,
            ended_at=ended_at,
            duration_seconds=duration_seconds,
            status="success",
        )

        timing_update = _append_node_timing(
            state=state,
            timing_record=timing_record,
        )

        return {
            **result,
            **timing_update,
            "coordinator_output": coordinator_output or result.get("coordinator_output"),
            "workflow_steps": normalized_steps,
            "skip_reason": merged_skip_reason,
            "completed_steps": completed_steps,
            "errors": errors,
        }

    except Exception as exc:
        if _is_graph_interrupt(exc):
            raise

        duration_seconds = time.perf_counter() - start_time
        ended_at = _utc_now_iso()

        error_message = str(exc)

        timing_record = _build_timing_record(
            step_name=step_name,
            started_at=started_at,
            ended_at=ended_at,
            duration_seconds=duration_seconds,
            status="failed",
            error=error_message,
        )

        timing_update = _append_node_timing(
            state=state,
            timing_record=timing_record,
        )

        completed_steps = mark_step_complete(
            state=state,
            step_name=step_name,
        )

        errors = list(state.get("errors", []))
        errors.append(
            {
                "step": step_name,
                "error": error_message,
            }
        )

        return {
            **timing_update,
            "completed_steps": completed_steps,
            "errors": errors,
        }


# ============================================================
# Router
# ============================================================

def route_next_step(state: AgentGraphState) -> str:
    """
    Routes to the next incomplete workflow step.

    If all workflow steps are completed, routes to END.
    """

    workflow_steps = list(state.get("workflow_steps", []))
    completed_steps = set(state.get("completed_steps", []))
    forbidden_steps = set(state.get("forbidden_steps", []))

    for step in workflow_steps:
        if step in completed_steps:
            continue

        if step in forbidden_steps and step in USER_SKIPPABLE_STEPS:
            continue

        return step

    return "end"


# ============================================================
# Graph builder
# ============================================================

def build_workflow_graph():
    """
    Builds a generalized LangGraph workflow.

    HITL update:
    - Compiles with MemorySaver checkpointer.
    - Required for LangGraph interrupt/resume in Approval Agent.

    Important:
    Callers must invoke the compiled graph with config:
        {"configurable": {"thread_id": run_id}}
    """

    graph = StateGraph(AgentGraphState)

    # Coordinator uses special wrapper
    graph.add_node("coordinator", coordinator_wrapper)

    # Business nodes
    graph.add_node("forecasting", wrap_node("forecasting", forecasting_node))
    graph.add_node("inventory", wrap_node("inventory", inventory_node))
    graph.add_node("procurement", wrap_node("procurement", procurement_node))
    graph.add_node("logistics", wrap_node("logistics", logistics_node))

    # Governance nodes
    graph.add_node("policy_context", wrap_node("policy_context", policy_context_node))
    graph.add_node("policy", wrap_node("policy", policy_node))
    graph.add_node("risk", wrap_node("risk", risk_node))

    # Approval, audit, and final response nodes
    graph.add_node("approval", wrap_node("approval", approval_node))
    graph.add_node("audit", wrap_node("audit", audit_node))
    graph.add_node("final_response", wrap_node("final_response", final_response_node))

    # Start with coordinator
    graph.add_edge(START, "coordinator")

    route_map = {
        "forecasting": "forecasting",
        "inventory": "inventory",
        "procurement": "procurement",
        "logistics": "logistics",
        "policy_context": "policy_context",
        "policy": "policy",
        "risk": "risk",
        "approval": "approval",
        "audit": "audit",
        "final_response": "final_response",
        "end": END,
    }

    # Coordinator routes to first selected step
    graph.add_conditional_edges(
        "coordinator",
        route_next_step,
        route_map,
    )

    # Every workflow node routes to the next incomplete step
    for node_name in [
        "forecasting",
        "inventory",
        "procurement",
        "logistics",
        "policy_context",
        "policy",
        "risk",
        "approval",
        "audit",
        "final_response",
    ]:
        graph.add_conditional_edges(
            node_name,
            route_next_step,
            route_map,
        )

    checkpointer = MemorySaver()

    return graph.compile(checkpointer=checkpointer)


# ============================================================
# Optional local test runner
# ============================================================

if __name__ == "__main__":
    app = build_workflow_graph()

    test_queries = [
        "Check whether supplier S-999 can deliver P-105 to South safely."
    ]

    for index, query in enumerate(test_queries, start=1):
        run_id = f"RUN-GRAPH-VALIDATION-{index:03d}"

        initial_state = {
            "run_id": run_id,
            "user_query": query,
            "user_role": "Supply Chain Planner",
            "completed_steps": [],
            "errors": [],
            # Disable HITL for direct CLI validation.
            # True HITL should be tested through dashboard/service resume flow.
            "disable_hitl": True,
        }

        config = {
            "configurable": {
                "thread_id": run_id,
            }
        }

        result = app.invoke(initial_state, config=config)

        print("=" * 100)
        print("Query:", query)
        print("Workflow completed.")

        # --------------------------------------------------------
        # High-level workflow status
        # --------------------------------------------------------
        print("Final decision:", result.get("final_decision"))
        print("Completed steps:", result.get("completed_steps"))
        print("Workflow steps:", result.get("workflow_steps"))
        print("Forbidden steps:", result.get("forbidden_steps"))
        print("Skip reason:", result.get("skip_reason"))
        print("Errors:", result.get("errors"))

        print("Workflow duration seconds:", result.get("workflow_duration_seconds"))
        print("Node timings:")
        for timing in result.get("node_timings", []):
            print(timing)

        # --------------------------------------------------------
        # Governance/access flags
        # --------------------------------------------------------
        print("-" * 100)
        print("Governance and data-access flags:")
        print("Requested datasets:", result.get("requested_datasets"))
        print("Forbidden datasets:", result.get("forbidden_datasets"))
        print("Dataset accessed:", result.get("dataset_accessed"))
        print("Dataset access attempted:", result.get("dataset_access_attempted"))
        print("User requested restricted data:", result.get("user_requested_restricted_data"))
        print("Restricted data accessed:", result.get("restricted_data_accessed"))
        print("Unauthorized dataset accessed:", result.get("unauthorized_dataset_accessed"))
        print("Agent accessed forbidden dataset:", result.get("agent_accessed_forbidden_dataset"))
        print("User instruction violation:", result.get("user_instruction_violation"))
        print("User requested no citations:", result.get("user_requested_no_citations"))
        print("Source citation missing:", result.get("source_citation_missing"))
        print("External communication requested:", result.get("external_communication_requested"))
        print("External communication attempted:", result.get("external_communication_attempted"))
        print("Unauthorized tool used:", result.get("unauthorized_tool_used"))

        # --------------------------------------------------------
        # Coordinator output
        # --------------------------------------------------------
        print("-" * 100)
        print("Coordinator output:")
        print(result.get("coordinator_output"))

        # --------------------------------------------------------
        # Business agent outputs
        # --------------------------------------------------------
        print("-" * 100)
        print("Forecasting output:")
        print(result.get("forecasting_output"))

        print("-" * 100)
        print("Inventory output:")
        print(result.get("inventory_output"))

        print("-" * 100)
        print("Procurement output:")
        print(result.get("procurement_output"))

        print("-" * 100)
        print("Logistics output:")
        print(result.get("logistics_output"))

        # --------------------------------------------------------
        # Governance outputs
        # --------------------------------------------------------
        print("-" * 100)
        print("Policy context output:")
        print(result.get("policy_context_output"))

        print("-" * 100)
        print("Policy output:")
        print(result.get("policy_output"))

        print("-" * 100)
        print("Policy RAG decision:")
        print(result.get("policy_rag_decision"))

        print("-" * 100)
        print("Risk output:")
        print(result.get("risk_output"))

        print("-" * 100)
        print("Approval output:")
        print(result.get("approval_output"))

        print("-" * 100)
        print("Human review output:")
        print(result.get("human_review_output"))

        print("-" * 100)
        print("Audit output:")
        print(result.get("audit_output"))

        # --------------------------------------------------------
        # Final response outputs
        # --------------------------------------------------------
        print("-" * 100)
        print("Final response output:")
        print(result.get("final_response_output"))

        print("-" * 100)
        print("Final natural language explanation:")
        final_response_output = result.get("final_response_output") or {}
        print(final_response_output.get("natural_language_explanation"))

        print("-" * 100)
        print("Final response markdown:")
        print(result.get("final_response"))

        print("=" * 100)
        print("\n")