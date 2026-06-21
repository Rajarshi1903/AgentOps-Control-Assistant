"""
dashboard/utils/state_helpers.py

Helpers for reading workflow state safely.
"""

import json
from typing import Any, Dict, List


def as_dict(value: Any) -> Dict[str, Any]:
    """
    Safely converts Pydantic/dict-like objects into dictionaries.
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


def as_list(value: Any) -> List[Any]:
    """
    Safely converts a value into a list.
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


def safe_get_nested(
    data: Dict[str, Any],
    path: List[str],
    default: Any = None,
) -> Any:
    """
    Safely gets nested dictionary values.
    """

    current = data

    for key in path:
        if not isinstance(current, dict):
            return default

        current = current.get(key)

        if current is None:
            return default

    return current


def pretty_json(value: Any) -> str:
    """
    Converts objects into readable JSON string.
    """

    try:
        return json.dumps(value, indent=2, default=str, ensure_ascii=False)
    except Exception:
        return str(value)


def extract_outputs(result: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    Extracts major workflow outputs into a normalized dictionary.
    """

    return {
        "coordinator_output": as_dict(result.get("coordinator_output")),
        "forecasting_output": as_dict(result.get("forecasting_output")),
        "inventory_output": as_dict(result.get("inventory_output")),
        "procurement_output": as_dict(result.get("procurement_output")),
        "logistics_output": as_dict(result.get("logistics_output")),
        "policy_context_output": as_dict(result.get("policy_context_output")),
        "policy_output": as_dict(result.get("policy_output")),
        "policy_rag_decision": as_dict(result.get("policy_rag_decision")),
        "risk_output": as_dict(result.get("risk_output")),
        "approval_output": as_dict(result.get("approval_output")),
        "audit_output": as_dict(result.get("audit_output")),
        "final_response_output": as_dict(result.get("final_response_output")),
    }