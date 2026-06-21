"""
dashboard/services/workflow_service.py

Service layer for invoking and resuming the backend LangGraph workflow.

This service supports:
- normal workflow execution
- LangGraph interrupt-based Human-in-the-Loop approval
- graph checkpoint persistence during Streamlit session
"""

import sys
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

import streamlit as st
from langgraph.types import Command

from dashboard.config import DEFAULT_USER_ROLE


# ============================================================
# Project path setup
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from src.graph.workflow_graph import build_workflow_graph


# ============================================================
# Cached graph loader
# ============================================================

@st.cache_resource
def get_workflow_graph():
    """
    Builds and caches the compiled LangGraph workflow.

    Important:
    - The workflow graph now uses MemorySaver checkpointing.
    - Caching keeps the graph and in-memory checkpoints alive across
      Streamlit reruns during the same app session.
    - This is required for interrupt/resume HITL behavior.
    """

    return build_workflow_graph()


# ============================================================
# Config helpers
# ============================================================

def _build_thread_config(run_id: str) -> Dict[str, Any]:
    """
    Builds LangGraph config with thread_id.

    The thread_id is required so LangGraph can resume the same paused
    checkpoint after an interrupt.
    """

    return {
        "configurable": {
            "thread_id": run_id,
        }
    }


def _generate_run_id() -> str:
    """
    Generates a unique dashboard run ID.
    """

    return f"RUN-DASHBOARD-{uuid.uuid4().hex[:12]}"


# ============================================================
# Workflow execution
# ============================================================

def run_workflow(
    user_query: str,
    user_role: str = DEFAULT_USER_ROLE,
    run_id: Optional[str] = None,
    disable_hitl: bool = False,
) -> Dict[str, Any]:
    """
    Starts a new workflow run.

    Args:
        user_query: User's natural language query.
        user_role: Role of the user executing the workflow.
        run_id: Optional run ID. If not provided, a unique ID is generated.
        disable_hitl: If True, disables approval interrupt for this run.

    Returns:
        LangGraph result state. If an approval interrupt occurs, the result
        may contain "__interrupt__".
    """

    app = get_workflow_graph()

    effective_run_id = run_id or _generate_run_id()

    initial_state = {
        "run_id": effective_run_id,
        "user_query": user_query,
        "user_role": user_role,
        "completed_steps": [],
        "errors": [],
        "disable_hitl": disable_hitl,
    }

    config = _build_thread_config(effective_run_id)

    result = app.invoke(
        initial_state,
        config=config,
    )

    # Ensure dashboard can always recover the run_id from result.
    if isinstance(result, dict):
        result["run_id"] = effective_run_id

    return result


# ============================================================
# Workflow resume after HITL interrupt
# ============================================================

def resume_workflow(
    run_id: str,
    human_review: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Resumes a paused LangGraph workflow after human approval input.

    Args:
        run_id: Same run_id/thread_id used during the original workflow run.
        human_review: Human reviewer decision payload.

    Example human_review:
        {
            "decision": "Approve",
            "comment": "Approved for execution.",
            "reviewed_by": "Supply Chain Manager"
        }

    Returns:
        Final workflow result after graph resumes.
    """

    app = get_workflow_graph()

    config = _build_thread_config(run_id)

    result = app.invoke(
        Command(resume=human_review),
        config=config,
    )

    if isinstance(result, dict):
        result["run_id"] = run_id

    return result


# ============================================================
# Interrupt helpers
# ============================================================

def has_interrupt(result: Dict[str, Any]) -> bool:
    """
    Returns True if LangGraph result contains an interrupt payload.
    """

    if not isinstance(result, dict):
        return False

    return "__interrupt__" in result and bool(result.get("__interrupt__"))


def get_interrupt_payload(result: Dict[str, Any]) -> Any:
    """
    Safely returns LangGraph interrupt payload from result.
    """

    if not isinstance(result, dict):
        return None

    return result.get("__interrupt__")