import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from dotenv import load_dotenv

from src.schemas.governance import AuditLoggerOutput


# ============================================================
# SQLite Audit Logger
# ============================================================
# Purpose:
# Persists one complete workflow audit event into SQLite.
#
# Governance update:
# This logger now captures:
# - policy_context_output
# - data_access_log
# - requested/forbidden/accessed/attempted datasets
# - restricted data and unauthorized access flags
# - governance violations
# - policy/risk/approval outputs
# - final response metadata
#
# Important:
# - Does NOT call LLM.
# - Does NOT call RAG.
# - Does NOT modify final_decision.
# - Does NOT send notifications.
# - Stores nested outputs as JSON strings.
# ============================================================


load_dotenv()


SQLITE_DB_PATH = os.getenv("SQLITE_DB_PATH") or "data/audit_logs.db"


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
    Converts value into a clean list[str].
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


def _json_default(value: Any) -> str:
    """
    JSON fallback serializer for datetime and other unsupported objects.
    """

    if isinstance(value, datetime):
        return value.isoformat()

    return str(value)


def _to_json(value: Any) -> str:
    """
    Converts value to JSON string safely.
    """

    return json.dumps(
        value,
        ensure_ascii=False,
        default=_json_default,
    )


def _safe_bool(value: Any, default: bool = False) -> bool:
    """
    Converts value to bool safely.
    """

    if value is None:
        return default

    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1", "y"}

    return bool(value)


def _safe_number(value: Any, default: float = 0.0) -> float:
    """
    Converts value to float safely.
    """

    if value is None:
        return default

    try:
        return float(value)
    except (TypeError, ValueError):
        return default


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


def _generate_audit_event_id() -> str:
    """
    Generates unique audit event ID.
    """

    return f"AUD-{uuid.uuid4().hex[:12]}"


def _utc_now_iso() -> str:
    """
    Current UTC timestamp as ISO string.
    """

    return datetime.now(timezone.utc).isoformat()


# ============================================================
# SQLite setup
# ============================================================

def _get_db_path() -> Path:
    """
    Resolves SQLite DB path and ensures parent directory exists.
    """

    db_path = Path(SQLITE_DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    return db_path


def _get_connection() -> sqlite3.Connection:
    """
    Creates SQLite connection.
    """

    db_path = _get_db_path()
    return sqlite3.connect(str(db_path))


def _get_existing_columns(conn: sqlite3.Connection, table_name: str) -> List[str]:
    """
    Returns existing column names for a SQLite table.
    """

    rows = conn.execute(f"PRAGMA table_info({table_name});").fetchall()
    return [row[1] for row in rows]


def _ensure_column(
    conn: sqlite3.Connection,
    table_name: str,
    column_name: str,
    column_definition: str,
) -> None:
    """
    Adds a column if it does not already exist.
    """

    existing_columns = _get_existing_columns(conn, table_name)

    if column_name not in existing_columns:
        conn.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition};"
        )


def initialize_audit_db() -> None:
    """
    Creates audit_events table if not exists and migrates old schema.
    """

    create_table_sql = """
    CREATE TABLE IF NOT EXISTS audit_events (
        event_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        timestamp TEXT NOT NULL,

        user_query TEXT,
        user_role TEXT,

        workflow_steps TEXT,
        completed_steps TEXT,
        final_decision TEXT,
        errors TEXT,

        forecasting_output TEXT,
        inventory_output TEXT,
        procurement_output TEXT,
        logistics_output TEXT,

        policy_context_output TEXT,
        policy_decision TEXT,
        policy_output TEXT,
        policy_rag_decision TEXT,
        policy_evidence_summary TEXT,

        risk_score REAL,
        risk_level TEXT,
        risk_output TEXT,

        approval_required INTEGER,
        approval_status TEXT,
        approval_output TEXT,

        requested_datasets TEXT,
        forbidden_datasets TEXT,
        dataset_accessed TEXT,
        dataset_access_attempted TEXT,
        data_access_log TEXT,
        governance_flags TEXT,
        governance_violations TEXT,

        source_files TEXT,
        source_record_ids TEXT,

        final_response TEXT,
        final_response_output TEXT,

        message TEXT
    );
    """

    with _get_connection() as conn:
        conn.execute(create_table_sql)

        # Safe migration for old databases.
        _ensure_column(conn, "audit_events", "workflow_steps", "TEXT")
        _ensure_column(conn, "audit_events", "policy_context_output", "TEXT")
        _ensure_column(conn, "audit_events", "requested_datasets", "TEXT")
        _ensure_column(conn, "audit_events", "forbidden_datasets", "TEXT")
        _ensure_column(conn, "audit_events", "dataset_accessed", "TEXT")
        _ensure_column(conn, "audit_events", "dataset_access_attempted", "TEXT")
        _ensure_column(conn, "audit_events", "data_access_log", "TEXT")
        _ensure_column(conn, "audit_events", "governance_flags", "TEXT")
        _ensure_column(conn, "audit_events", "governance_violations", "TEXT")
        _ensure_column(conn, "audit_events", "final_response", "TEXT")
        _ensure_column(conn, "audit_events", "final_response_output", "TEXT")

        conn.commit()


# ============================================================
# State extraction helpers
# ============================================================

def _collect_source_files_and_records(
    state: Dict[str, Any]
) -> Tuple[List[str], List[str]]:
    """
    Collects source files and record IDs from available outputs and context.
    """

    source_files: List[str] = []
    source_record_ids: List[str] = []

    policy_context_output = _as_dict(state.get("policy_context_output"))

    for key in [
        "forecasting_output",
        "inventory_output",
        "procurement_output",
        "logistics_output",
        "policy_output",
        "risk_output",
        "approval_output",
        "final_response_output",
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

    return (
        _unique_preserve_order(source_files),
        _unique_preserve_order(source_record_ids),
    )


def _build_policy_evidence_summary(
    policy_rag_decision: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Builds compact policy evidence summary from policy_rag_decision.
    """

    evidence_summary: List[Dict[str, Any]] = []

    triggered_rules = policy_rag_decision.get("triggered_rules", [])

    if not isinstance(triggered_rules, list):
        return evidence_summary

    for rule in triggered_rules:
        rule_dict = _as_dict(rule)
        evidence = _as_dict(rule_dict.get("evidence"))

        evidence_summary.append(
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

    return evidence_summary


def _build_governance_flags(
    state: Dict[str, Any],
    policy_context_output: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Builds compact governance flag summary for audit.
    """

    return {
        "user_requested_restricted_data": _safe_bool(
            policy_context_output.get(
                "user_requested_restricted_data",
                state.get("user_requested_restricted_data", False),
            )
        ),
        "restricted_data_accessed": _safe_bool(
            policy_context_output.get(
                "restricted_data_accessed",
                state.get("restricted_data_accessed", False),
            )
        ),
        "unauthorized_dataset_accessed": _safe_bool(
            policy_context_output.get(
                "unauthorized_dataset_accessed",
                state.get("unauthorized_dataset_accessed", False),
            )
        ),
        "agent_accessed_forbidden_dataset": _safe_bool(
            policy_context_output.get(
                "agent_accessed_forbidden_dataset",
                state.get("agent_accessed_forbidden_dataset", False),
            )
        ),
        "user_instruction_violation": _safe_bool(
            policy_context_output.get(
                "user_instruction_violation",
                state.get("user_instruction_violation", False),
            )
        ),
        "user_requested_no_citations": _safe_bool(
            policy_context_output.get(
                "user_requested_no_citations",
                state.get("user_requested_no_citations", False),
            )
        ),
        "source_citation_missing": _safe_bool(
            policy_context_output.get(
                "source_citation_missing",
                state.get("source_citation_missing", False),
            )
        ),
        "external_communication_requested": _safe_bool(
            policy_context_output.get(
                "external_communication_requested",
                state.get("external_communication_requested", False),
            )
        ),
        "external_communication_attempted": _safe_bool(
            policy_context_output.get(
                "external_communication_attempted",
                state.get("external_communication_attempted", False),
            )
        ),
        "unauthorized_tool_used": _safe_bool(
            policy_context_output.get(
                "unauthorized_tool_used",
                state.get("unauthorized_tool_used", False),
            )
        ),
        "any_agent_failed": _safe_bool(
            policy_context_output.get("any_agent_failed", False)
        ),
    }


def _build_audit_record(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Builds one audit_events row from LangGraph state.
    """

    event_id = _generate_audit_event_id()
    timestamp = _utc_now_iso()

    forecasting_output = _as_dict(state.get("forecasting_output"))
    inventory_output = _as_dict(state.get("inventory_output"))
    procurement_output = _as_dict(state.get("procurement_output"))
    logistics_output = _as_dict(state.get("logistics_output"))

    policy_context_output = _as_dict(state.get("policy_context_output"))
    policy_output = _as_dict(state.get("policy_output"))
    policy_rag_decision = _as_dict(state.get("policy_rag_decision"))
    risk_output = _as_dict(state.get("risk_output"))
    approval_output = _as_dict(state.get("approval_output"))

    final_response_output = _as_dict(state.get("final_response_output"))
    final_response = state.get("final_response", "")

    source_files, source_record_ids = _collect_source_files_and_records(state)

    policy_decision = policy_output.get(
        "policy_decision",
        state.get("final_decision", ""),
    )

    risk_score = _safe_number(
        risk_output.get("final_risk_score", 0),
        default=0,
    )

    risk_level = risk_output.get("risk_level", "")

    approval_required = _safe_bool(
        approval_output.get("approval_required", False),
        default=False,
    )

    approval_status = approval_output.get("approval_status", "")

    policy_evidence_summary = _build_policy_evidence_summary(
        policy_rag_decision=policy_rag_decision
    )

    governance_flags = _build_governance_flags(
        state=state,
        policy_context_output=policy_context_output,
    )

    governance_violations = _string_list(
        policy_context_output.get("governance_violations", [])
    )

    requested_datasets = _string_list(
        policy_context_output.get(
            "requested_datasets",
            state.get("requested_datasets", []),
        )
    )

    forbidden_datasets = _string_list(
        policy_context_output.get(
            "forbidden_datasets",
            state.get("forbidden_datasets", []),
        )
    )

    dataset_accessed = _string_list(
        policy_context_output.get(
            "dataset_accessed",
            state.get("dataset_accessed", []),
        )
    )

    dataset_access_attempted = _string_list(
        policy_context_output.get(
            "dataset_access_attempted",
            state.get("dataset_access_attempted", []),
        )
    )

    data_access_log = policy_context_output.get(
        "data_access_log",
        state.get("data_access_log", []),
    )

    message = (
        f"Audit event captured for run_id={state.get('run_id', 'RUN-UNKNOWN')}. "
        f"Final decision={state.get('final_decision')}. "
        f"Policy decision={policy_decision}. "
        f"Risk score={risk_score}, risk level={risk_level}. "
        f"Approval status={approval_status}. "
        f"Governance violations={governance_violations}."
    )

    return {
        "event_id": event_id,
        "run_id": state.get("run_id", "RUN-UNKNOWN"),
        "timestamp": timestamp,

        "user_query": state.get("user_query", ""),
        "user_role": state.get("user_role", ""),

        "workflow_steps": _to_json(state.get("workflow_steps", [])),
        "completed_steps": _to_json(state.get("completed_steps", [])),
        "final_decision": state.get("final_decision", ""),
        "errors": _to_json(state.get("errors", [])),

        "forecasting_output": _to_json(forecasting_output),
        "inventory_output": _to_json(inventory_output),
        "procurement_output": _to_json(procurement_output),
        "logistics_output": _to_json(logistics_output),

        "policy_context_output": _to_json(policy_context_output),
        "policy_decision": policy_decision,
        "policy_output": _to_json(policy_output),
        "policy_rag_decision": _to_json(policy_rag_decision),
        "policy_evidence_summary": _to_json(policy_evidence_summary),

        "risk_score": risk_score,
        "risk_level": risk_level,
        "risk_output": _to_json(risk_output),

        "approval_required": 1 if approval_required else 0,
        "approval_status": approval_status,
        "approval_output": _to_json(approval_output),

        "requested_datasets": _to_json(requested_datasets),
        "forbidden_datasets": _to_json(forbidden_datasets),
        "dataset_accessed": _to_json(dataset_accessed),
        "dataset_access_attempted": _to_json(dataset_access_attempted),
        "data_access_log": _to_json(data_access_log),
        "governance_flags": _to_json(governance_flags),
        "governance_violations": _to_json(governance_violations),

        "source_files": _to_json(source_files),
        "source_record_ids": _to_json(source_record_ids),

        "final_response": str(final_response) if final_response else "",
        "final_response_output": _to_json(final_response_output),

        "message": message,
    }


# ============================================================
# DB write
# ============================================================

def insert_audit_event(record: Dict[str, Any]) -> None:
    """
    Inserts audit event into SQLite.
    """

    insert_sql = """
    INSERT INTO audit_events (
        event_id,
        run_id,
        timestamp,

        user_query,
        user_role,

        workflow_steps,
        completed_steps,
        final_decision,
        errors,

        forecasting_output,
        inventory_output,
        procurement_output,
        logistics_output,

        policy_context_output,
        policy_decision,
        policy_output,
        policy_rag_decision,
        policy_evidence_summary,

        risk_score,
        risk_level,
        risk_output,

        approval_required,
        approval_status,
        approval_output,

        requested_datasets,
        forbidden_datasets,
        dataset_accessed,
        dataset_access_attempted,
        data_access_log,
        governance_flags,
        governance_violations,

        source_files,
        source_record_ids,

        final_response,
        final_response_output,

        message
    )
    VALUES (
        :event_id,
        :run_id,
        :timestamp,

        :user_query,
        :user_role,

        :workflow_steps,
        :completed_steps,
        :final_decision,
        :errors,

        :forecasting_output,
        :inventory_output,
        :procurement_output,
        :logistics_output,

        :policy_context_output,
        :policy_decision,
        :policy_output,
        :policy_rag_decision,
        :policy_evidence_summary,

        :risk_score,
        :risk_level,
        :risk_output,

        :approval_required,
        :approval_status,
        :approval_output,

        :requested_datasets,
        :forbidden_datasets,
        :dataset_accessed,
        :dataset_access_attempted,
        :data_access_log,
        :governance_flags,
        :governance_violations,

        :source_files,
        :source_record_ids,

        :final_response,
        :final_response_output,

        :message
    );
    """

    with _get_connection() as conn:
        conn.execute(insert_sql, record)
        conn.commit()


def fetch_recent_audit_events(limit: int = 10) -> List[Dict[str, Any]]:
    """
    Utility function for debugging/dashboard.
    Fetches recent audit events.
    """

    query = """
    SELECT
        event_id,
        run_id,
        timestamp,
        final_decision,
        policy_decision,
        risk_score,
        risk_level,
        approval_required,
        approval_status,
        governance_violations
    FROM audit_events
    ORDER BY timestamp DESC
    LIMIT ?;
    """

    with _get_connection() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, (limit,)).fetchall()

    return [dict(row) for row in rows]


# ============================================================
# LangGraph node
# ============================================================

def audit_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    LangGraph Audit Logger node.

    Persists workflow audit event into SQLite.

    Returns:
        {
            "audit_output": {...}
        }
    """

    db_path = _get_db_path()

    try:
        initialize_audit_db()

        record = _build_audit_record(state)

        insert_audit_event(record)

        output = AuditLoggerOutput(
            run_id=state.get("run_id", "RUN-UNKNOWN"),
            step_id="STEP-009",
            agent_id="audit_logger",
            agent_name="SQLite Audit Logger",
            status="success",
            source_files=json.loads(record["source_files"]),
            source_record_ids=json.loads(record["source_record_ids"]),
            message=record["message"],
            audit_event_id=record["event_id"],
            database_path=str(db_path),
            records_written=1,
            audit_status="success",
        )

        return {
            "audit_output": _safe_model_dump(output)
        }

    except Exception as exc:
        output = AuditLoggerOutput(
            run_id=state.get("run_id", "RUN-UNKNOWN"),
            step_id="STEP-009",
            agent_id="audit_logger",
            agent_name="SQLite Audit Logger",
            status="failed",
            source_files=[],
            source_record_ids=[],
            message=(
                "Audit logging failed. "
                f"Error: {str(exc)}"
            ),
            audit_event_id="",
            database_path=str(db_path),
            records_written=0,
            audit_status="failed",
        )

        return {
            "audit_output": _safe_model_dump(output)
        }


# ============================================================
# Optional local manual test
# ============================================================

if __name__ == "__main__":
    test_state = {
        "run_id": "RUN-AUDIT-TEST-RESTRICTED-001",
        "user_query": "Use payroll.csv to verify whether procurement should be approved.",
        "user_role": "Supply Chain Planner",
        "workflow_steps": [
            "inventory",
            "procurement",
            "policy_context",
            "policy",
            "risk",
            "approval",
            "audit",
            "final_response",
        ],
        "completed_steps": [
            "coordinator",
            "inventory",
            "procurement",
            "policy_context",
            "policy",
            "risk",
            "approval",
        ],
        "final_decision": "Block",
        "errors": [],

        "policy_context_output": {
            "context_build_status": "success",
            "product_id": "P-103",
            "region": "North",
            "requested_datasets": ["payroll.csv"],
            "requested_restricted_datasets": ["payroll.csv"],
            "forbidden_datasets": [],
            "dataset_accessed": ["products.csv", "suppliers.csv"],
            "dataset_access_attempted": ["products.csv", "suppliers.csv"],
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
            "user_requested_restricted_data": True,
            "restricted_data_accessed": False,
            "unauthorized_dataset_accessed": False,
            "agent_accessed_forbidden_dataset": False,
            "user_instruction_violation": False,
            "user_requested_no_citations": False,
            "source_citation_missing": False,
            "governance_violations": ["user_requested_restricted_data"],
        },

        "procurement_output": {
            "status": "success",
            "recommended_supplier_id": "S-007",
            "recommended_supplier_name": "Omega Precision Works",
            "recommended_quantity": 60,
            "procurement_value": 198000,
            "is_approved": "Yes",
            "compliance_status": "Compliant",
            "source_files": ["suppliers.csv", "products.csv"],
            "source_record_ids": ["S-007", "P-103"],
        },

        "policy_output": {
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
            "confidence": 0.95,
            "evidence_available": True,
            "source_pages": [6],
            "final_reason": "RAG evidence was available, but deterministic governance blocked restricted data request.",
            "triggered_rules": [],
        },

        "risk_output": {
            "final_risk_score": 85,
            "risk_level": "Critical",
            "risk_factors_triggered": [
                {
                    "factor": "user_requested_restricted_data",
                    "points": 35,
                    "category": "Data Governance Risk",
                },
                {
                    "factor": "policy_block_decision",
                    "points": 40,
                    "category": "Policy Enforcement Risk",
                },
            ],
            "source_files": ["products.csv", "suppliers.csv", "agentops_supply_chain_policy_handbook.pdf"],
            "source_record_ids": ["S-007", "policy_page_6"],
        },

        "approval_output": {
            "approval_id": "APR-RUN-AUDIT-TEST-RESTRICTED-001",
            "approval_required": False,
            "approval_status": "Blocked",
            "reviewer_role": "Data Governance / Compliance Team",
            "action_under_review": "Action blocked due to governance violation(s): user_requested_restricted_data.",
            "source_files": ["agentops_supply_chain_policy_handbook.pdf"],
            "source_record_ids": ["policy_page_6"],
        },

        "final_response": "",
        "final_response_output": {},
    }

    result = audit_node(test_state)

    print("Audit Logger executed.")
    print(result["audit_output"])

    print("\nRecent audit events:")
    initialize_audit_db()

    for event in fetch_recent_audit_events(limit=5):
        print(event)