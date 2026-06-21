from src.governance.risk_scoring_engine import risk_node


def test_high_value_procurement_risk():
    state = {
        "run_id": "RUN-TEST-RISK-001",
        "procurement_output": {
            "procurement_value": 387000,
            "is_approved": "Yes",
            "compliance_status": "Compliant",
        },
        "policy_output": {
            "policy_decision": "Escalate",
        },
        "policy_rag_decision": {
            "confidence": 0.95,
            "evidence_available": True,
            "guardrail_result": {
                "guardrails_triggered": []
            },
        },
    }

    result = risk_node(state)
    output = result["risk_output"]

    assert output["final_risk_score"] == 40
    assert output["risk_level"] == "Medium"
    assert output["score_cap_applied"] is False

    factors = [factor["factor"] for factor in output["risk_factors_triggered"]]

    assert "high_value_procurement" in factors


def test_active_high_route_disruption_risk():
    state = {
        "run_id": "RUN-TEST-RISK-002",
        "logistics_output": {
            "route_disruption_exists": True,
            "route_disruption_status": "Active",
            "route_disruption_severity": "High",
        },
        "policy_output": {
            "policy_decision": "Escalate",
        },
        "policy_rag_decision": {
            "confidence": 0.91,
            "evidence_available": True,
            "guardrail_result": {
                "guardrails_triggered": []
            },
        },
    }

    result = risk_node(state)
    output = result["risk_output"]

    assert output["final_risk_score"] == 35
    assert output["risk_level"] == "Medium"

    factors = [factor["factor"] for factor in output["risk_factors_triggered"]]

    assert "active_high_route_disruption" in factors


def test_critical_score_cap():
    state = {
        "run_id": "RUN-TEST-RISK-003",
        "procurement_output": {
            "procurement_value": 387000,
            "is_approved": "No",
            "compliance_status": "Non-Compliant",
        },
        "logistics_output": {
            "route_disruption_exists": True,
            "route_disruption_status": "Active",
            "route_disruption_severity": "Critical",
        },
        "policy_output": {
            "policy_decision": "Block",
        },
        "policy_rag_decision": {
            "confidence": 0.92,
            "evidence_available": True,
            "guardrail_result": {
                "guardrails_triggered": []
            },
        },
    }

    result = risk_node(state)
    output = result["risk_output"]

    assert output["final_risk_score"] == 100
    assert output["risk_level"] == "Critical"
    assert output["score_cap_applied"] is True


def test_restricted_data_and_policy_block():
    state = {
        "run_id": "RUN-TEST-RISK-004",
        "dataset_accessed": "payroll.csv",
        "restricted_data_accessed": True,
        "policy_output": {
            "policy_decision": "Block",
        },
        "policy_rag_decision": {
            "confidence": 0.88,
            "evidence_available": True,
            "guardrail_result": {
                "guardrails_triggered": []
            },
        },
    }

    result = risk_node(state)
    output = result["risk_output"]

    assert output["final_risk_score"] == 80
    assert output["risk_level"] == "High"

    factors = [factor["factor"] for factor in output["risk_factors_triggered"]]

    assert "restricted_data_access" in factors
    assert "policy_block_decision" in factors