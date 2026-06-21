from src.schemas.agent_outputs import (
    CoordinatorOutput,
    ForecastingOutput,
    InventoryOutput,
    ProcurementOutput,
    LogisticsOutput,
)


def test_coordinator_output_schema():
    output = CoordinatorOutput(
        run_id="RUN-001",
        step_id="STEP-001",
        agent_id="coordinator_agent",
        agent_name="Coordinator Agent",
        status="success",
        source_files=["products.csv"],
        source_record_ids=[],
        message="Workflow planned.",
        intent="demand_spike_response",
        product_input="P-101",
        resolved_product_id="P-101",
        resolved_product_name="Smart Sensor Module",
        region="South",
        workflow=[
            "forecasting",
            "inventory",
            "procurement",
            "logistics",
            "policy",
            "risk",
            "approval",
            "audit",
            "final_response",
        ],
    )

    assert output.intent == "demand_spike_response"
    assert output.resolved_product_id == "P-101"


def test_forecasting_output_schema():
    output = ForecastingOutput(
        run_id="RUN-001",
        step_id="STEP-002",
        agent_id="forecasting_agent",
        agent_name="Forecasting Agent",
        status="success",
        source_files=["sales_history.csv"],
        source_record_ids=[],
        message="Forecast generated.",
        product_id="P-101",
        region="South",
        forecast_horizon_days=1,
        forecasted_demand=223,
        historical_avg_demand=124.73,
        recent_avg_demand=222.86,
        demand_spike_detected=True,
        forecast_confidence=0.78,
        method_used="moving_average_with_recent_spike_adjustment",
    )

    assert output.forecasted_demand == 223
    assert 0 <= output.forecast_confidence <= 1


def test_inventory_output_schema():
    output = InventoryOutput(
        run_id="RUN-001",
        step_id="STEP-003",
        agent_id="inventory_agent",
        agent_name="Inventory Agent",
        status="success",
        source_files=["inventory.csv"],
        source_record_ids=["INV-003"],
        message="Inventory shortage detected.",
        product_id="P-101",
        region="South",
        warehouse_id="WH-SOUTH-01",
        forecasted_demand=223,
        current_stock=80,
        safety_stock=72,
        reorder_point=696,
        stock_position="Below Reorder Point",
        shortage_quantity=215,
        procurement_required=True,
        calculation="shortage_quantity = forecasted_demand + safety_stock - current_stock",
    )

    assert output.shortage_quantity == 215
    assert output.procurement_required is True


def test_procurement_output_schema():
    output = ProcurementOutput(
        run_id="RUN-001",
        step_id="STEP-004",
        agent_id="procurement_agent",
        agent_name="Procurement Agent",
        status="success",
        source_files=["suppliers.csv", "inventory.csv", "products.csv"],
        source_record_ids=["S-001"],
        message="Supplier recommendation generated.",
        product_id="P-101",
        region="South",
        recommended_quantity=215,
        recommended_supplier_id="S-001",
        recommended_supplier_name="Alpha Components Pvt Ltd",
        supplier_region="South",
        unit_cost=1800,
        lead_time_days=5,
        reliability_score=92,
        is_approved="Yes",
        compliance_status="Compliant",
        max_capacity=700,
        procurement_value=387000,
        supplier_selection_reason="Approved supplier with sufficient capacity.",
    )

    assert output.procurement_value == 387000
    assert output.is_approved == "Yes"


def test_logistics_output_schema():
    output = LogisticsOutput(
        run_id="RUN-001",
        step_id="STEP-005",
        agent_id="logistics_agent",
        agent_name="Logistics Agent",
        status="success",
        source_files=["routes.csv", "disruptions.csv"],
        source_record_ids=["R-001"],
        message="Route recommendation generated.",
        supplier_id="S-001",
        destination_region="South",
        warehouse_id="WH-SOUTH-01",
        recommended_route_id="R-001",
        origin_region="South",
        destination_node="WH-SOUTH-01",
        transport_mode="Road",
        distance_km=172,
        base_cost=8300,
        estimated_time_days=2,
        route_risk_level="Low",
        route_score=10300,
        route_disruption_exists=False,
        route_disruption_severity="None",
        route_disruption_status="None",
        impact_delay_days=0,
        impact_cost=0,
        adjusted_time_days=2,
        adjusted_route_cost=8300,
    )

    assert output.recommended_route_id == "R-001"
    assert output.adjusted_route_cost == 8300