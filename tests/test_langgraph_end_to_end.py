from src.graph.workflow_graph import build_workflow_graph


def run_graph(initial_state):
    app = build_workflow_graph()
    return app.invoke(initial_state)


def test_full_demand_spike_workflow_pdf_policy_escalates():
    initial_state = {
        "run_id": "RUN-E2E-DEMAND-SPIKE-001",
        "user_query": "Demand for P-101 has increased in South region.",
        "user_role": "Supply Chain Planner",
        "completed_steps": [],
        "errors": [],
    }

    result = run_graph(initial_state)

    assert result.get("errors", []) == []

    completed_steps = result["completed_steps"]

    assert "coordinator" in completed_steps
    assert "forecasting" in completed_steps
    assert "inventory" in completed_steps
    assert "procurement" in completed_steps
    assert "logistics" in completed_steps
    assert "policy" in completed_steps
    assert "risk" in completed_steps
    assert "approval" in completed_steps
    assert "audit" in completed_steps
    assert "final_response" in completed_steps

    assert result["final_decision"] == "Escalate"

    assert "forecasting_output" in result
    assert "inventory_output" in result
    assert "procurement_output" in result
    assert "logistics_output" in result
    assert "policy_output" in result
    assert "policy_rag_decision" in result

    procurement_output = result["procurement_output"]
    policy_output = result["policy_output"]
    policy_rag_decision = result["policy_rag_decision"]

    assert procurement_output["procurement_value"] > 50000

    assert policy_output["policy_decision"] == "Escalate"
    assert policy_rag_decision["decision"] == "Escalate"
    assert policy_rag_decision["evidence_available"] is True
    assert len(policy_rag_decision["triggered_rules"]) >= 1


def test_route_disruption_workflow_pdf_policy_escalates():
    initial_state = {
        "run_id": "RUN-E2E-ROUTE-RISK-001",
        "user_query": "Check route risk for supplier S-012 to South.",
        "user_role": "Supply Chain Planner",
        "supplier_id": "S-012",
        "region": "South",
        "completed_steps": [],
        "errors": [],
    }

    result = run_graph(initial_state)

    assert result.get("errors", []) == []

    completed_steps = result["completed_steps"]

    assert "coordinator" in completed_steps
    assert "logistics" in completed_steps
    assert "policy" in completed_steps
    assert "risk" in completed_steps
    assert "audit" in completed_steps
    assert "final_response" in completed_steps

    assert result["final_decision"] == "Escalate"

    logistics_output = result["logistics_output"]
    policy_rag_decision = result["policy_rag_decision"]

    assert logistics_output["route_disruption_exists"] is True
    assert logistics_output["route_disruption_status"] == "Active"
    assert logistics_output["route_disruption_severity"] in ["High", "Critical"]

    assert policy_rag_decision["decision"] == "Escalate"
    assert policy_rag_decision["evidence_available"] is True


def test_inventory_only_workflow_routes_correctly():
    initial_state = {
        "run_id": "RUN-E2E-INVENTORY-001",
        "user_query": "Check inventory for P-101 in South.",
        "user_role": "Supply Chain Planner",
        "completed_steps": [],
        "errors": [],
    }

    result = run_graph(initial_state)

    assert result.get("errors", []) == []

    completed_steps = result["completed_steps"]

    assert "coordinator" in completed_steps
    assert "inventory" in completed_steps
    assert "policy" in completed_steps
    assert "audit" in completed_steps
    assert "final_response" in completed_steps

    assert "forecasting" not in completed_steps
    assert "procurement" not in completed_steps
    assert "logistics" not in completed_steps

    assert "inventory_output" in result
    assert "policy_output" in result