import pytest

from src.agents.procurement_agent import procurement_node


def test_procurement_agent_shortage_case_p101_south():
    state = {
        "run_id": "RUN-TEST-PROC-001",
        "product_id": "P-101",
        "region": "South",
        "inventory_output": {
            "procurement_required": True,
            "shortage_quantity": 215,
            "warehouse_id": "WH-SOUTH-01",
            "stock_position": "Below Reorder Point",
            "source_record_ids": ["INV-003"],
        },
        "selection_strategy": "compliance_first",
    }

    result = procurement_node(state)

    assert "procurement_output" in result
    assert "supplier_id" in result

    output = result["procurement_output"]

    assert output["agent_id"] == "procurement_agent"
    assert output["product_id"] == "P-101"
    assert output["region"] == "South"
    assert output["recommended_quantity"] == 215
    assert output["recommended_supplier_id"] is not None
    assert output["procurement_value"] > 50000
    assert output["is_approved"] == "Yes"
    assert output["compliance_status"] in ["Compliant", "Under Review"]
    assert "suppliers.csv" in output["source_files"]


def test_procurement_agent_no_procurement_required():
    state = {
        "run_id": "RUN-TEST-PROC-002",
        "product_id": "P-104",
        "region": "East",
        "inventory_output": {
            "procurement_required": False,
            "shortage_quantity": 0,
            "warehouse_id": "WH-EAST-01",
            "stock_position": "Healthy",
            "source_record_ids": ["INV-014"],
        },
    }

    result = procurement_node(state)

    output = result["procurement_output"]

    assert output["recommended_quantity"] == 0
    assert output["recommended_supplier_id"] is None
    assert output["procurement_value"] == 0
    assert output["is_approved"] == "Yes"
    assert output["compliance_status"] == "Compliant"


def test_procurement_agent_supplier_lookup_without_inventory():
    state = {
        "run_id": "RUN-TEST-PROC-003",
        "product_id": "P-103",
        "region": "North",
        "selection_strategy": "compliance_first",
    }

    result = procurement_node(state)

    output = result["procurement_output"]

    assert output["recommended_quantity"] == 0
    assert output["procurement_value"] == 0
    assert output["recommended_supplier_id"] is not None
    assert output["product_id"] == "P-103"


def test_procurement_agent_cheapest_strategy_red_team_ready():
    state = {
        "run_id": "RUN-TEST-PROC-004",
        "product_id": "P-101",
        "region": "South",
        "inventory_output": {
            "procurement_required": True,
            "shortage_quantity": 215,
            "warehouse_id": "WH-SOUTH-01",
            "stock_position": "Below Reorder Point",
            "source_record_ids": ["INV-003"],
        },
        "selection_strategy": "cheapest",
    }

    result = procurement_node(state)

    output = result["procurement_output"]

    assert output["recommended_quantity"] == 215
    assert output["recommended_supplier_id"] is not None
    assert output["procurement_value"] > 0


def test_procurement_agent_invalid_product_raises_error():
    state = {
        "run_id": "RUN-TEST-PROC-005",
        "product_id": "P-999",
        "region": "South",
    }

    with pytest.raises(ValueError):
        procurement_node(state)


def test_procurement_agent_invalid_strategy_raises_error():
    state = {
        "run_id": "RUN-TEST-PROC-006",
        "product_id": "P-101",
        "region": "South",
        "selection_strategy": "invalid_strategy",
    }

    with pytest.raises(ValueError):
        procurement_node(state)