from src.agents.approval_agent import approval_node


def test_escalated_procurement_requires_approval():
    state = {
        "run_id": "RUN-TEST-APPROVAL-001",
        "policy_output": {
            "agent_id": "policy_engine",
            "policy_decision": "Escalate",
            "triggered_policies": [
                {
                    "policy_name": "High-Value Procurement Policy",
                    "action": "Escalate",
                    "severity": "High",
                }
            ],
        },
        "risk_output": {
            "final_risk_score": 40,
            "risk_level": "Medium",
        },
        "procurement_output": {
            "recommended_quantity": 215,
            "recommended_supplier_id": "S-001",
            "recommended_supplier_name": "Alpha Components Pvt Ltd",
            "procurement_value": 387000,
        },
    }

    result = approval_node(state)
    output = result["approval_output"]

    assert output["approval_required"] is True
    assert output["approval_status"] == "Pending"
    assert output["reviewer_role"] == "Supply Chain Manager"


def test_high_risk_requires_risk_manager_approval():
    state = {
        "run_id": "RUN-TEST-APPROVAL-002",
        "policy_output": {
            "agent_id": "policy_engine",
            "policy_decision": "Allow",
            "triggered_policies": [],
        },
        "risk_output": {
            "final_risk_score": 70,
            "risk_level": "High",
        },
    }

    result = approval_node(state)
    output = result["approval_output"]

    assert output["approval_required"] is True
    assert output["approval_status"] == "Pending"
    assert output["reviewer_role"] == "Risk Manager"


def test_blocked_action_does_not_create_approval():
    state = {
        "run_id": "RUN-TEST-APPROVAL-003",
        "policy_output": {
            "agent_id": "policy_engine",
            "policy_decision": "Block",
            "triggered_policies": [
                {
                    "policy_name": "Unapproved Supplier Policy",
                    "action": "Block",
                    "severity": "Critical",
                }
            ],
        },
        "risk_output": {
            "final_risk_score": 80,
            "risk_level": "High",
        },
    }

    result = approval_node(state)
    output = result["approval_output"]

    assert output["approval_required"] is False
    assert output["approval_status"] == "Blocked"
    assert output["reviewer_role"] == "Governance Officer"


def test_safe_action_no_approval_required():
    state = {
        "run_id": "RUN-TEST-APPROVAL-004",
        "policy_output": {
            "agent_id": "policy_engine",
            "policy_decision": "Allow",
            "triggered_policies": [],
        },
        "risk_output": {
            "final_risk_score": 10,
            "risk_level": "Low",
        },
    }

    result = approval_node(state)
    output = result["approval_output"]

    assert output["approval_required"] is False
    assert output["approval_status"] == "Not Required"


def test_missing_policy_output_requires_approval():
    state = {
        "run_id": "RUN-TEST-APPROVAL-005",
    }

    result = approval_node(state)
    output = result["approval_output"]

    assert output["approval_required"] is True
    assert output["approval_status"] == "Pending"