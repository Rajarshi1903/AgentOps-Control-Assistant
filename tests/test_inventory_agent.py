import pytest

from src.agents.inventory_agent import inventory_node


def test_inventory_agent_with_forecast_p101_south():
    state = {
        "run_id": "RUN-TEST-INVENTORY-001",
        "product_id": "P-101",
        "region": "South",
        "forecasting_output": {
            "forecasted_demand": 223,
            "forecast_confidence": 0.78,
            "demand_spike_detected": True,
        }
    }

    result = inventory_node(state)

    assert "inventory_output" in result

    output = result["inventory_output"]

    assert output["agent_id"] == "inventory_agent"
    assert output["product_id"] == "P-101"
    assert output["region"] == "South"
    assert output["warehouse_id"] == "WH-SOUTH-01"
    assert output["forecasted_demand"] == 223
    assert output["current_stock"] >= 0
    assert output["safety_stock"] >= 0
    assert output["reorder_point"] >= 0
    assert output["shortage_quantity"] >= 0
    assert output["procurement_required"] is True
    assert output["stock_position"] in [
        "Below Safety Stock",
        "Below Reorder Point",
        "Healthy",
    ]
    assert "inventory.csv" in output["source_files"]


def test_inventory_agent_inventory_only_mode():
    state = {
        "run_id": "RUN-TEST-INVENTORY-002",
        "product_id": "P-101",
        "region": "South",
    }

    result = inventory_node(state)

    output = result["inventory_output"]

    assert output["forecasted_demand"] == 0
    assert output["shortage_quantity"] == 0
    assert output["stock_position"] in [
        "Below Safety Stock",
        "Below Reorder Point",
        "Healthy",
    ]
    assert "reorder point" in output["message"].lower()


def test_inventory_agent_healthy_case_p104_east():
    state = {
        "run_id": "RUN-TEST-INVENTORY-003",
        "product_id": "P-104",
        "region": "East",
        "forecasting_output": {
            "forecasted_demand": 160,
            "forecast_confidence": 0.80,
            "demand_spike_detected": True,
        }
    }

    result = inventory_node(state)

    output = result["inventory_output"]

    assert output["product_id"] == "P-104"
    assert output["region"] == "East"
    assert output["current_stock"] >= 0
    assert output["stock_position"] in [
        "Below Safety Stock",
        "Below Reorder Point",
        "Healthy",
    ]


def test_inventory_agent_invalid_product_raises_error():
    state = {
        "run_id": "RUN-TEST-INVENTORY-004",
        "product_id": "P-999",
        "region": "South",
    }

    with pytest.raises(ValueError):
        inventory_node(state)


def test_inventory_agent_invalid_region_raises_error():
    state = {
        "run_id": "RUN-TEST-INVENTORY-005",
        "product_id": "P-101",
        "region": "Central",
    }

    with pytest.raises(ValueError):
        inventory_node(state)