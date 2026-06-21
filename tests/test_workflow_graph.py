from src.graph.workflow_graph import build_workflow_graph


def test_demand_spike_workflow_runs():
    app = build_workflow_graph()

    initial_state = {
        "run_id": "RUN-TEST-001",
        "user_query": "Demand for P-101 has increased in South region.",
        "user_role": "Supply Chain Planner",
        "completed_steps": [],
        "errors": [],
    }

    result = app.invoke(initial_state)

    assert "coordinator" in result["completed_steps"]
    assert "forecasting" in result["completed_steps"]
    assert "inventory" in result["completed_steps"]
    assert "procurement" in result["completed_steps"]
    assert "logistics" in result["completed_steps"]
    assert "policy" in result["completed_steps"]
    assert "risk" in result["completed_steps"]
    assert "approval" in result["completed_steps"]
    assert "audit" in result["completed_steps"]
    assert "final_response" in result["completed_steps"]
    assert result.get("errors", []) == []


def test_inventory_only_workflow_runs():
    app = build_workflow_graph()

    initial_state = {
        "run_id": "RUN-TEST-002",
        "user_query": "Check inventory for P-101 in South.",
        "user_role": "Supply Chain Planner",
        "completed_steps": [],
        "errors": [],
    }

    result = app.invoke(initial_state)

    assert "coordinator" in result["completed_steps"]
    assert "inventory" in result["completed_steps"]
    assert "policy" in result["completed_steps"]
    assert "audit" in result["completed_steps"]
    assert "final_response" in result["completed_steps"]

    assert "forecasting" not in result["completed_steps"]
    assert "procurement" not in result["completed_steps"]
    assert "logistics" not in result["completed_steps"]

    assert result.get("errors", []) == []


def test_forecast_only_workflow_runs():
    app = build_workflow_graph()

    initial_state = {
        "run_id": "RUN-TEST-003",
        "user_query": "Forecast demand for P-101 in South.",
        "user_role": "Supply Chain Planner",
        "completed_steps": [],
        "errors": [],
    }

    result = app.invoke(initial_state)

    assert "coordinator" in result["completed_steps"]
    assert "forecasting" in result["completed_steps"]
    assert "policy" in result["completed_steps"]
    assert "risk" in result["completed_steps"]
    assert "audit" in result["completed_steps"]
    assert "final_response" in result["completed_steps"]

    assert "inventory" not in result["completed_steps"]
    assert "procurement" not in result["completed_steps"]
    assert "logistics" not in result["completed_steps"]

    assert result.get("errors", []) == []