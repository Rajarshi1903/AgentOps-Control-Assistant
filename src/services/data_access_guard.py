"""
src/services/data_access_guard.py

Governed data access service for the AgentOps Supply Chain Control Tower.

Purpose
-------
This module centralizes and audits dataset access across all agents.

Agents should NOT directly call:

    pd.read_csv(...)

Instead, agents should call:

    dataframe, access_update = read_governed_csv(
        state=state,
        agent_id="inventory_agent",
        file_name="inventory.csv",
        purpose="inventory_check",
    )

The returned access_update should be merged into the LangGraph node return.

This module records factual runtime evidence:
- which files were attempted
- which files were successfully accessed
- whether a restricted dataset was requested or accessed
- whether an agent attempted a dataset not allowlisted for that agent
- whether the user explicitly forbade a dataset and it was still attempted
- whether user instructions were violated

Important design principle
--------------------------
This module is deterministic by design.

The LLM may understand intent in the Coordinator Agent, but file-access control
must not be probabilistic. Restricted data and allowlisted dataset access should
be enforced through clear Python rules.
"""

from __future__ import annotations

import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import pandas as pd


# =============================================================================
# Paths
# =============================================================================

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))


# =============================================================================
# Dataset Access Policy
# =============================================================================
# Agent IDs should match the agent_id values used in your agent outputs.
#
# This is not "bad hardcoding"; this is governance configuration.
# Later, this can be moved to config/data_governance.yaml if needed.
# =============================================================================

ALLOWED_DATASETS_BY_AGENT: Dict[str, Set[str]] = {
    "coordinator_agent": {
        "products.csv",
        "suppliers.csv",
    },
    "forecasting_agent": {
        "sales_history.csv",
        "products.csv",
    },
    "inventory_agent": {
        "inventory.csv",
        "products.csv",
    },
    "procurement_agent": {
        "inventory.csv",
        "products.csv",
        "suppliers.csv",
    },
    "logistics_agent": {
        "routes.csv",
        "disruptions.csv",
        "suppliers.csv",
        "products.csv",
    },
    "policy_engine": {
        "agentops_supply_chain_policy_handbook.pdf",
        "inventory.csv",
        "products.csv",
        "suppliers.csv",
        "routes.csv",
        "disruptions.csv",
        "sales_history.csv",
    },
    "risk_scoring_engine": {
        "inventory.csv",
        "products.csv",
        "suppliers.csv",
        "routes.csv",
        "disruptions.csv",
        "agentops_supply_chain_policy_handbook.pdf",
    },
    "approval_agent": {
        "inventory.csv",
        "products.csv",
        "suppliers.csv",
        "routes.csv",
        "disruptions.csv",
        "agentops_supply_chain_policy_handbook.pdf",
    },
    "audit_logger": {
        "audit_logs.db",
    },
    "final_response_agent": set(),
}


# Datasets that must never be used for supply-chain operational decisions.
RESTRICTED_DATASETS: Set[str] = {
    "payroll.csv",
    "employee_records.csv",
    "salary_data.csv",
    "hr_master.csv",
    "personnel.csv",
    "compensation.csv",
}


# Keyword-to-file mappings for deterministic query parsing support.
# This is a supplement to the Coordinator LLM, not a replacement.
RESTRICTED_DATASET_PATTERNS: Dict[str, str] = {
    "payroll": "payroll.csv",
    "salary": "salary_data.csv",
    "employee record": "employee_records.csv",
    "employee records": "employee_records.csv",
    "employee_records": "employee_records.csv",
    "hr master": "hr_master.csv",
    "hr_master": "hr_master.csv",
    "personnel": "personnel.csv",
    "compensation": "compensation.csv",
}


# =============================================================================
# Exceptions
# =============================================================================

class DataAccessDeniedError(PermissionError):
    """
    Raised when a caller explicitly asks read_governed_csv(..., raise_on_denied=True).

    The exception carries access_update so the caller can still return governance
    evidence to LangGraph state.
    """

    def __init__(self, message: str, access_update: Dict[str, Any]):
        super().__init__(message)
        self.access_update = access_update


# =============================================================================
# Normalization Helpers
# =============================================================================

def normalize_dataset_name(file_name: Any) -> str:
    """
    Normalizes a dataset name to a lowercase basename.

    Examples:
        data/inventory.csv -> inventory.csv
        C:\\x\\payroll.csv -> payroll.csv
        PAYROLL.CSV -> payroll.csv
    """

    if file_name is None:
        return ""

    name = str(file_name).strip().replace("\\", "/")
    name = Path(name).name

    return name.lower()


def unique_preserve_order(values: Iterable[Any]) -> List[Any]:
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


def as_list(value: Any) -> List[Any]:
    """
    Converts a value to list safely.
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


def normalize_dataset_list(values: Any) -> List[str]:
    """
    Normalizes a state field that may contain one or many dataset names.
    """

    normalized = [
        normalize_dataset_name(value)
        for value in as_list(values)
        if normalize_dataset_name(value)
    ]

    return unique_preserve_order(normalized)


# =============================================================================
# Query / Dataset Detection Helpers
# =============================================================================

def extract_dataset_mentions_from_text(text: str) -> List[str]:
    """
    Extracts dataset filenames mentioned in a user query or free text.

    Detects:
    - explicit filenames like payroll.csv, inventory.csv, policy.pdf
    - restricted-data keywords like payroll, salary, HR master, etc.

    This is useful for the Coordinator Agent to set:
        requested_datasets
        user_requested_restricted_data
    """

    if not text:
        return []

    text_lower = text.lower()

    explicit_file_matches = re.findall(
        r"\b[a-zA-Z0-9_\-]+\.(?:csv|xlsx|xls|pdf|db|sqlite)\b",
        text_lower,
    )

    inferred_files = []

    for keyword, canonical_file in RESTRICTED_DATASET_PATTERNS.items():
        if keyword in text_lower:
            inferred_files.append(canonical_file)

    return unique_preserve_order(
        [
            normalize_dataset_name(value)
            for value in explicit_file_matches + inferred_files
        ]
    )


def detect_forbidden_steps_from_text(text: str) -> List[str]:
    """
    Deterministically detects user instructions that forbid workflow steps.

    This is a supplement to the Coordinator LLM. The Coordinator can merge
    these results with LLM-extracted forbidden_steps.

    Examples:
        "Do not check inventory" -> ["inventory"]
        "Do not select a supplier" -> ["procurement"]
        "Do not create a logistics route" -> ["logistics"]
    """

    if not text:
        return []

    text_lower = text.lower()
    forbidden_steps: List[str] = []

    patterns = {
        "forecasting": [
            "do not forecast",
            "don't forecast",
            "no forecast",
        ],
        "inventory": [
            "do not check inventory",
            "don't check inventory",
            "do not run inventory",
            "no inventory",
            "do not check stock",
            "don't check stock",
        ],
        "procurement": [
            "do not procure",
            "don't procure",
            "do not select a supplier",
            "don't select a supplier",
            "do not recommend a supplier",
            "don't recommend a supplier",
            "do not create procurement",
            "no procurement",
        ],
        "logistics": [
            "do not create a logistics route",
            "do not create logistics",
            "do not route",
            "don't route",
            "do not evaluate route",
            "don't evaluate route",
            "no logistics",
            "no route",
        ],
        "approval": [
            "do not create an approval request",
            "do not request approval",
            "no approval request",
        ],
    }

    for step, step_patterns in patterns.items():
        if any(pattern in text_lower for pattern in step_patterns):
            forbidden_steps.append(step)

    return unique_preserve_order(forbidden_steps)


def detect_no_citation_instruction(text: str) -> bool:
    """
    Detects if the user explicitly asks to omit source files, source records,
    citations, or policy evidence.

    This should set:
        user_requested_no_citations = True

    Important:
    This does not itself prove that citations are missing.
    Actual missing citation should be computed later by checking agent outputs.
    """

    if not text:
        return False

    text_lower = text.lower()

    no_citation_patterns = [
        "do not cite",
        "don't cite",
        "without citation",
        "without citations",
        "do not include source",
        "don't include source",
        "without source files",
        "without source records",
        "without policy evidence",
        "do not cite source files",
        "do not cite source records",
        "do not cite policy evidence",
    ]

    return any(pattern in text_lower for pattern in no_citation_patterns)


# =============================================================================
# Access Policy Checks
# =============================================================================

def is_restricted_dataset(file_name: str) -> bool:
    """
    Returns True if file_name is a restricted dataset.
    """

    return normalize_dataset_name(file_name) in RESTRICTED_DATASETS


def is_dataset_allowed_for_agent(agent_id: str, file_name: str) -> bool:
    """
    Checks whether a dataset is allowlisted for an agent.
    """

    normalized_file = normalize_dataset_name(file_name)
    allowed = ALLOWED_DATASETS_BY_AGENT.get(agent_id, set())

    return normalized_file in allowed


def is_forbidden_by_user(state: Dict[str, Any], file_name: str) -> bool:
    """
    Checks whether the user explicitly forbade access to this dataset.
    """

    normalized_file = normalize_dataset_name(file_name)

    forbidden_datasets = normalize_dataset_list(
        state.get("forbidden_datasets", [])
    )

    return normalized_file in forbidden_datasets


def build_access_decision(
    state: Dict[str, Any],
    agent_id: str,
    file_name: str,
) -> Dict[str, Any]:
    """
    Builds a deterministic access decision for a file access attempt.

    Access is allowed only if:
    - dataset is not restricted
    - dataset is allowlisted for the agent
    - dataset was not forbidden by the user
    """

    normalized_file = normalize_dataset_name(file_name)

    restricted = is_restricted_dataset(normalized_file)

    allowed_for_agent = is_dataset_allowed_for_agent(
        agent_id=agent_id,
        file_name=normalized_file,
    )

    forbidden_by_user = is_forbidden_by_user(
        state=state,
        file_name=normalized_file,
    )

    reasons: List[str] = []

    if restricted:
        reasons.append("Dataset is restricted for supply-chain workflows.")

    if not allowed_for_agent:
        reasons.append(f"Dataset is not allowlisted for agent_id={agent_id}.")

    if forbidden_by_user:
        reasons.append("User explicitly forbade access to this dataset.")

    allowed = (not restricted) and allowed_for_agent and (not forbidden_by_user)

    if allowed:
        reasons.append("Access allowed by dataset governance policy.")

    return {
        "file_name": normalized_file,
        "allowed": allowed,
        "restricted": restricted,
        "allowed_for_agent": allowed_for_agent,
        "forbidden_by_user": forbidden_by_user,
        "reason": " ".join(reasons),
    }


# =============================================================================
# State Update Builders
# =============================================================================

def build_access_entry(
    state: Dict[str, Any],
    agent_id: str,
    file_name: str,
    purpose: str,
    access_type: str,
    access_decision: Dict[str, Any],
    file_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Builds one access log entry.

    This becomes part of:
        state["data_access_log"]
    """

    return {
        "access_id": f"ACC-{uuid.uuid4().hex[:12]}",
        "run_id": state.get("run_id", "RUN-UNKNOWN"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent_id": agent_id,
        "file_name": access_decision["file_name"],
        "file_path": str(file_path) if file_path else None,
        "access_type": access_type,
        "purpose": purpose,
        "allowed": access_decision["allowed"],
        "denied": not access_decision["allowed"],
        "restricted": access_decision["restricted"],
        "allowed_for_agent": access_decision["allowed_for_agent"],
        "forbidden_by_user": access_decision["forbidden_by_user"],
        "reason": access_decision["reason"],
    }


def build_access_update(
    state: Dict[str, Any],
    access_entry: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Builds a LangGraph-compatible state update from one access log entry.
    """

    existing_log = list(state.get("data_access_log", []))
    merged_log = existing_log + [access_entry]

    existing_accessed = normalize_dataset_list(
        state.get("dataset_accessed", [])
    )

    existing_attempted = normalize_dataset_list(
        state.get("dataset_access_attempted", [])
    )

    attempted_file = access_entry["file_name"]

    dataset_access_attempted = unique_preserve_order(
        existing_attempted + [attempted_file]
    )

    if access_entry.get("allowed"):
        dataset_accessed = unique_preserve_order(
            existing_accessed + [attempted_file]
        )
    else:
        dataset_accessed = existing_accessed

    restricted_data_accessed = bool(
        state.get("restricted_data_accessed", False)
    ) or bool(access_entry.get("restricted"))

    unauthorized_dataset_accessed = bool(
        state.get("unauthorized_dataset_accessed", False)
    ) or bool(access_entry.get("denied"))

    agent_accessed_forbidden_dataset = bool(
        state.get("agent_accessed_forbidden_dataset", False)
    ) or bool(access_entry.get("forbidden_by_user"))

    user_instruction_violation = bool(
        state.get("user_instruction_violation", False)
    ) or bool(access_entry.get("forbidden_by_user"))

    return {
        "data_access_log": merged_log,
        "dataset_accessed": dataset_accessed,
        "dataset_access_attempted": dataset_access_attempted,
        "restricted_data_accessed": restricted_data_accessed,
        "unauthorized_dataset_accessed": unauthorized_dataset_accessed,
        "agent_accessed_forbidden_dataset": agent_accessed_forbidden_dataset,
        "user_instruction_violation": user_instruction_violation,
    }


def merge_access_updates(
    state: Dict[str, Any],
    *updates: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Merges multiple access updates into a single state update.

    Use this when an agent reads multiple files in one node.

    Example:
        sales_df, access_1 = read_governed_csv(...)
        products_df, access_2 = read_governed_csv(...)

        access_update = merge_access_updates(state, access_1, access_2)
    """

    merged_log = list(state.get("data_access_log", []))
    merged_accessed = normalize_dataset_list(state.get("dataset_accessed", []))
    merged_attempted = normalize_dataset_list(
        state.get("dataset_access_attempted", [])
    )

    restricted_data_accessed = bool(state.get("restricted_data_accessed", False))
    unauthorized_dataset_accessed = bool(
        state.get("unauthorized_dataset_accessed", False)
    )
    agent_accessed_forbidden_dataset = bool(
        state.get("agent_accessed_forbidden_dataset", False)
    )
    user_instruction_violation = bool(
        state.get("user_instruction_violation", False)
    )

    for update in updates:
        if not update:
            continue

        merged_log = list(update.get("data_access_log", merged_log))

        merged_accessed = normalize_dataset_list(
            update.get("dataset_accessed", merged_accessed)
        )

        merged_attempted = normalize_dataset_list(
            update.get("dataset_access_attempted", merged_attempted)
        )

        restricted_data_accessed = restricted_data_accessed or bool(
            update.get("restricted_data_accessed", False)
        )

        unauthorized_dataset_accessed = unauthorized_dataset_accessed or bool(
            update.get("unauthorized_dataset_accessed", False)
        )

        agent_accessed_forbidden_dataset = agent_accessed_forbidden_dataset or bool(
            update.get("agent_accessed_forbidden_dataset", False)
        )

        user_instruction_violation = user_instruction_violation or bool(
            update.get("user_instruction_violation", False)
        )

    return {
        "data_access_log": merged_log,
        "dataset_accessed": merged_accessed,
        "dataset_access_attempted": merged_attempted,
        "restricted_data_accessed": restricted_data_accessed,
        "unauthorized_dataset_accessed": unauthorized_dataset_accessed,
        "agent_accessed_forbidden_dataset": agent_accessed_forbidden_dataset,
        "user_instruction_violation": user_instruction_violation,
    }


# =============================================================================
# Governed File Readers
# =============================================================================

def read_governed_csv(
    state: Dict[str, Any],
    agent_id: str,
    file_name: str,
    purpose: str,
    data_dir: Optional[Path] = None,
    raise_on_denied: bool = False,
    **read_csv_kwargs: Any,
) -> Tuple[Optional[pd.DataFrame], Dict[str, Any]]:
    """
    Governed replacement for pd.read_csv.

    Returns:
        (dataframe_or_none, access_update)

    If access is denied:
        - dataframe_or_none is None
        - access_update contains denial evidence and governance flags
        - if raise_on_denied=True, raises DataAccessDeniedError
    """

    active_data_dir = data_dir or DATA_DIR
    normalized_file = normalize_dataset_name(file_name)
    file_path = active_data_dir / normalized_file

    access_decision = build_access_decision(
        state=state,
        agent_id=agent_id,
        file_name=normalized_file,
    )

    access_entry = build_access_entry(
        state=state,
        agent_id=agent_id,
        file_name=normalized_file,
        purpose=purpose,
        access_type="read",
        access_decision=access_decision,
        file_path=file_path,
    )

    access_update = build_access_update(
        state=state,
        access_entry=access_entry,
    )

    if not access_decision["allowed"]:
        message = (
            f"Data access denied for agent_id={agent_id}, "
            f"file_name={normalized_file}. "
            f"Reason: {access_decision['reason']}"
        )

        if raise_on_denied:
            raise DataAccessDeniedError(
                message,
                access_update=access_update,
            )

        return None, access_update

    if not file_path.exists():
        access_entry["allowed"] = False
        access_entry["denied"] = True
        access_entry["reason"] = (
            f"File was allowed but not found at path: {file_path}"
        )

        access_update = build_access_update(
            state=state,
            access_entry=access_entry,
        )

        if raise_on_denied:
            raise FileNotFoundError(access_entry["reason"])

        return None, access_update

    dataframe = pd.read_csv(file_path, **read_csv_kwargs)

    return dataframe, access_update


def require_governed_csv(
    state: Dict[str, Any],
    agent_id: str,
    file_name: str,
    purpose: str,
    data_dir: Optional[Path] = None,
    **read_csv_kwargs: Any,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Strict governed CSV reader.

    Raises DataAccessDeniedError or FileNotFoundError if the CSV cannot be read.
    """

    dataframe, access_update = read_governed_csv(
        state=state,
        agent_id=agent_id,
        file_name=file_name,
        purpose=purpose,
        data_dir=data_dir,
        raise_on_denied=True,
        **read_csv_kwargs,
    )

    if dataframe is None:
        raise DataAccessDeniedError(
            f"Data access failed for file_name={file_name}",
            access_update=access_update,
        )

    return dataframe, access_update


# =============================================================================
# Coordinator / Policy Context Helpers
# =============================================================================

def build_query_governance_flags(user_query: str) -> Dict[str, Any]:
    """
    Deterministically derives basic governance flags from user query text.

    This should be called by the Coordinator Agent and merged with LLM output.

    It detects:
    - requested datasets
    - user-requested restricted data
    - forbidden workflow steps
    - user instruction to omit citations
    """

    requested_datasets = extract_dataset_mentions_from_text(user_query)

    restricted_requested = any(
        dataset in RESTRICTED_DATASETS
        for dataset in requested_datasets
    )

    return {
        "requested_datasets": requested_datasets,
        "user_requested_restricted_data": restricted_requested,
        "forbidden_steps": detect_forbidden_steps_from_text(user_query),
        "user_requested_no_citations": detect_no_citation_instruction(user_query),
    }


def build_policy_context_access_summary(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Builds compact access-governance facts from state.

    This can be used by:
    - policy_context_builder.py
    - policy_engine.py
    - risk_scoring_engine.py
    - audit_logger.py
    - final_response_agent.py
    """

    data_access_log = list(state.get("data_access_log", []))

    requested_datasets = normalize_dataset_list(
        state.get("requested_datasets", [])
    )

    forbidden_datasets = normalize_dataset_list(
        state.get("forbidden_datasets", [])
    )

    dataset_accessed = normalize_dataset_list(
        state.get("dataset_accessed", [])
    )

    dataset_access_attempted = normalize_dataset_list(
        state.get("dataset_access_attempted", [])
    )

    requested_restricted_datasets = [
        dataset
        for dataset in requested_datasets
        if dataset in RESTRICTED_DATASETS
    ]

    accessed_restricted_datasets = [
        dataset
        for dataset in dataset_access_attempted
        if dataset in RESTRICTED_DATASETS
    ]

    denied_accesses = [
        entry
        for entry in data_access_log
        if entry.get("denied")
    ]

    forbidden_accesses = [
        entry
        for entry in data_access_log
        if entry.get("forbidden_by_user")
    ]

    return {
        "requested_datasets": requested_datasets,
        "forbidden_datasets": forbidden_datasets,
        "dataset_accessed": dataset_accessed,
        "dataset_access_attempted": dataset_access_attempted,
        "data_access_log": data_access_log,
        "requested_restricted_datasets": requested_restricted_datasets,
        "accessed_restricted_datasets": accessed_restricted_datasets,
        "denied_accesses": denied_accesses,
        "forbidden_accesses": forbidden_accesses,
        "user_requested_restricted_data": bool(
            state.get("user_requested_restricted_data", False)
        ) or bool(requested_restricted_datasets),
        "restricted_data_accessed": bool(
            state.get("restricted_data_accessed", False)
        ) or bool(accessed_restricted_datasets),
        "unauthorized_dataset_accessed": bool(
            state.get("unauthorized_dataset_accessed", False)
        ) or bool(denied_accesses),
        "agent_accessed_forbidden_dataset": bool(
            state.get("agent_accessed_forbidden_dataset", False)
        ) or bool(forbidden_accesses),
        "user_instruction_violation": bool(
            state.get("user_instruction_violation", False)
        ) or bool(forbidden_accesses),
        "user_requested_no_citations": bool(
            state.get("user_requested_no_citations", False)
        ),
    }


# =============================================================================
# Local Smoke Test
# =============================================================================

if __name__ == "__main__":
    test_state = {
        "run_id": "RUN-DATA-GUARD-TEST-001",
        "forbidden_datasets": ["suppliers.csv"],
    }

    print("=" * 100)
    print("Allowed inventory access")

    df, update = read_governed_csv(
        state=test_state,
        agent_id="inventory_agent",
        file_name="inventory.csv",
        purpose="inventory_check",
    )

    print("Dataframe loaded:", df is not None)
    print(update)

    print("=" * 100)
    print("Denied restricted access")

    df, update = read_governed_csv(
        state=test_state,
        agent_id="procurement_agent",
        file_name="payroll.csv",
        purpose="procurement_approval",
    )

    print("Dataframe loaded:", df is not None)
    print(update)

    print("=" * 100)
    print("Denied user-forbidden access")

    df, update = read_governed_csv(
        state=test_state,
        agent_id="procurement_agent",
        file_name="suppliers.csv",
        purpose="supplier_selection",
    )

    print("Dataframe loaded:", df is not None)
    print(update)

    print("=" * 100)
    print("Query governance flags")

    print(
        build_query_governance_flags(
            "Use payroll.csv but do not cite source files. Do not check inventory."
        )
    )