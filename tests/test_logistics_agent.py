import pytest

from src.agents.logistics_agent import logistics_node


def test_logistics_agent_normal_route_s001_south():
    state = {
        "run_id": "RUN-TEST-LOG-001",
        "supplier_id": "S-001",
        "region": "South",
    }

    result = logistics_node(state)

    output = result["logistics_output"]

    assert output["agent_id"] == "logistics_agent"
    assert output["supplier_id"] == "S-001"
    assert output["destination_region"] == "South"
    assert output["recommended_route_id"] == "R-001"
    assert output["route_disruption_exists"] is False
    assert output["route_disruption_severity"] == "None"
    assert output["route_disruption_status"] == "None"
    assert output["adjusted_route_cost"] == output["base_cost"]


def test_logistics_agent_route_disruption_s012_south():
    state = {
        "run_id": "RUN-TEST-LOG-002",
        "supplier_id": "S-012",
        "region": "South",
    }

    result = logistics_node(state)

    output = result["logistics_output"]

    assert output["supplier_id"] == "S-012"
    assert output["destination_region"] == "South"
    assert output["recommended_route_id"] == "R-027"
    assert output["route_disruption_exists"] is True
    assert output["route_disruption_severity"] == "High"
    assert output["route_disruption_status"] == "Active"
    assert output["adjusted_time_days"] > output["estimated_time_days"]
    assert output["adjusted_route_cost"] > output["base_cost"]
    assert "D-001" in output["source_record_ids"]


def test_logistics_agent_no_procurement_required():
    state = {
        "run_id": "RUN-TEST-LOG-003",
        "region": "East",
        "procurement_output": {
            "recommended_supplier_id": None,
            "recommended_quantity": 0,
            "procurement_value": 0,
        }
    }

    result = logistics_node(state)

    output = result["logistics_output"]

    assert output["recommended_route_id"] is None
    assert output["route_disruption_exists"] is False
    assert output["adjusted_route_cost"] == 0
    assert output["adjusted_time_days"] == 0


def test_logistics_agent_invalid_supplier_raises_error():
    state = {
        "run_id": "RUN-TEST-LOG-004",
        "supplier_id": "S-999",
        "region": "South",
    }

    with pytest.raises(ValueError):
        logistics_node(state)


def test_logistics_agent_invalid_region_raises_error():
    state = {
        "run_id": "RUN-TEST-LOG-005",
        "supplier_id": "S-001",
        "region": "Central",
    }

    with pytest.raises(ValueError):
        logistics_node(state)