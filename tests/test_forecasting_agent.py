from src.agents.forecasting_agent import forecasting_node


def test_forecasting_agent_runs_for_valid_product_region():
    state = {
        "run_id": "RUN-TEST-FORECAST-001",
        "product_id": "P-101",
        "region": "South"
    }

    result = forecasting_node(state)

    assert "forecasting_output" in result

    output = result["forecasting_output"]

    assert output["agent_id"] == "forecasting_agent"
    assert output["product_id"] == "P-101"
    assert output["region"] == "South"
    assert output["forecasted_demand"] > 0
    assert 0 <= output["forecast_confidence"] <= 1
    assert output["demand_spike_detected"] in [True, False]
    assert "sales_history.csv" in output["source_files"]
    assert "visualization_files" in output
    assert len(output["visualization_files"])