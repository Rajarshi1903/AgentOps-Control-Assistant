import sqlite3

from src.storage.audit_logger import audit_node, _get_db_path


def test_audit_logger_writes_event():
    state = {
        "run_id": "RUN-TEST-AUDIT-001",
        "user_query": "Demand for P-101 has increased in South region.",
        "user_role": "Supply Chain Planner",
        "completed_steps": ["forecasting", "inventory", "policy", "risk", "approval"],
        "final_decision": "Escalate",
        "errors": [],
        "policy_output": {
            "policy_decision": "Escalate",
            "source_files": ["agentops_supply_chain_policy_handbook.pdf"],
            "source_record_ids": ["policy_page_8"],
        },
        "risk_output": {
            "final_risk_score": 40,
            "risk_level": "Medium",
        },
        "approval_output": {
            "approval_required": True,
            "approval_status": "Pending",
        },
    }

    result = audit_node(state)
    output = result["audit_output"]

    assert output["audit_status"] == "success"
    assert output["records_written"] == 1
    assert output["audit_event_id"]

    db_path = _get_db_path()

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    row = conn.execute(
        """
        SELECT
            run_id,
            final_decision,
            policy_decision,
            risk_score,
            risk_level,
            approval_status
        FROM audit_events
        WHERE event_id = ?;
        """,
        (output["audit_event_id"],),
    ).fetchone()

    conn.close()

    assert row is not None
    assert row["run_id"] == "RUN-TEST-AUDIT-001"
    assert row["final_decision"] == "Escalate"
    assert row["policy_decision"] == "Escalate"
    assert row["risk_score"] == 40
    assert row["risk_level"] == "Medium"
    assert row["approval_status"] == "Pending"