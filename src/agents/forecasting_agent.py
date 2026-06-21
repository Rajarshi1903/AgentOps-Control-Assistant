import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from src.schemas.agent_outputs import ForecastingOutput
from src.agents.forecasting_visualizations import generate_forecasting_visualizations
from src.services.data_access_guard import (
    read_governed_csv,
    merge_access_updates,
)


# ============================================================
# Forecasting Agent
# ============================================================
# Purpose:
# Predict near-term demand for a product-region pair using
# historical sales data.
#
# Governance update:
# This agent no longer reads CSV files directly using pd.read_csv.
# It reads datasets through data_access_guard.read_governed_csv so that
# every file access is logged and evaluated against dataset governance rules.
# ============================================================


DATA_DIR = Path(os.getenv("DATA_DIR", "data"))


REQUIRED_SALES_COLUMNS = {
    "date",
    "product_id",
    "region",
    "units_sold",
    "revenue",
    "promotion_flag",
    "season",
    "event_flag",
}

REQUIRED_PRODUCT_COLUMNS = {
    "product_id",
    "product_name",
    "category",
    "unit_price",
    "criticality",
    "status",
}


# ============================================================
# Utility helpers
# ============================================================

def _safe_model_dump(model: Any) -> Dict[str, Any]:
    """
    Supports both Pydantic v1 and v2 style serialization.
    """

    if hasattr(model, "model_dump"):
        return model.model_dump()

    return model.dict()


def _build_failed_forecasting_output(
    run_id: str,
    product_id: Optional[str],
    region: Optional[str],
    message: str,
    source_files: Optional[List[str]] = None,
    source_record_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Builds a safe failure output.

    This is intentionally a plain dict instead of ForecastingOutput because
    failure cases may not have all fields required by the success schema.
    """

    return {
        "run_id": run_id,
        "step_id": "STEP-002",
        "agent_id": "forecasting_agent",
        "agent_name": "Forecasting Agent",
        "status": "failed",
        "source_files": source_files or [],
        "source_record_ids": source_record_ids or [],
        "message": message,
        "product_id": product_id,
        "region": region,
        "forecast_horizon_days": 1,
        "forecasted_demand": None,
        "historical_avg_demand": None,
        "recent_avg_demand": None,
        "demand_spike_detected": None,
        "forecast_confidence": None,
        "method_used": None,
        "visualization_files": [],
    }


def _validate_required_columns(
    dataframe: pd.DataFrame,
    required_columns: set,
    file_name: str,
) -> None:
    """
    Validates that a dataframe contains all required columns.
    """

    missing_columns = required_columns - set(dataframe.columns)

    if missing_columns:
        raise ValueError(
            f"{file_name} is missing required columns: {missing_columns}"
        )


# ============================================================
# Dataset loading with governed access
# ============================================================

def _load_datasets(
    state: Dict[str, Any],
) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame], Dict[str, Any]]:
    """
    Loads sales_history.csv and products.csv through the Data Access Guard.

    Returns:
        sales_df, products_df, access_update

    If access is denied or a file is missing, one or both dataframes may be None.
    The access_update must still be returned by the node so policy/audit can
    reason over the attempted access.
    """

    sales_df, sales_access_update = read_governed_csv(
        state=state,
        agent_id="forecasting_agent",
        file_name="sales_history.csv",
        purpose="forecasting_sales_history_load",
        data_dir=DATA_DIR,
    )

    intermediate_state = dict(state)
    intermediate_state.update(sales_access_update)

    products_df, products_access_update = read_governed_csv(
        state=intermediate_state,
        agent_id="forecasting_agent",
        file_name="products.csv",
        purpose="forecasting_product_lookup",
        data_dir=DATA_DIR,
    )

    access_update = merge_access_updates(
        state,
        sales_access_update,
        products_access_update,
    )

    return sales_df, products_df, access_update


# ============================================================
# Forecast preparation and calculations
# ============================================================

def _prepare_product_region_series(
    sales_df: pd.DataFrame,
    product_id: str,
    region: str,
) -> pd.DataFrame:
    """
    Filters sales history for a product-region combination, validates dates and
    numeric demand, sorts by date, and ensures daily continuity.
    """

    filtered_df = sales_df[
        (sales_df["product_id"] == product_id)
        & (sales_df["region"] == region)
    ].copy()

    if filtered_df.empty:
        raise ValueError(
            f"No sales history found for product_id={product_id}, region={region}"
        )

    filtered_df["date"] = pd.to_datetime(filtered_df["date"], errors="coerce")

    if filtered_df["date"].isna().any():
        raise ValueError(
            f"Invalid date values found for product_id={product_id}, region={region}"
        )

    filtered_df["units_sold"] = pd.to_numeric(
        filtered_df["units_sold"],
        errors="coerce",
    )

    if filtered_df["units_sold"].isna().any():
        raise ValueError(
            f"Non-numeric units_sold values found for product_id={product_id}, region={region}"
        )

    if (filtered_df["units_sold"] < 0).any():
        raise ValueError(
            f"Negative units_sold values found for product_id={product_id}, region={region}"
        )

    filtered_df = filtered_df.sort_values("date").reset_index(drop=True)

    if filtered_df["date"].duplicated().any():
        raise ValueError(
            f"Duplicate dates found for product_id={product_id}, region={region}"
        )

    if len(filtered_df) < 14:
        raise ValueError(
            f"Insufficient historical data. At least 14 records required, found {len(filtered_df)}"
        )

    date_range = pd.date_range(
        start=filtered_df["date"].min(),
        end=filtered_df["date"].max(),
        freq="D",
    )

    if len(date_range) != len(filtered_df):
        filtered_df = (
            filtered_df
            .set_index("date")
            .reindex(date_range)
            .rename_axis("date")
            .reset_index()
        )

        filtered_df["product_id"] = product_id
        filtered_df["region"] = region

        filtered_df["units_sold"] = (
            filtered_df["units_sold"]
            .interpolate(method="linear")
            .bfill()
            .ffill()
        )

        filtered_df["promotion_flag"] = (
            filtered_df["promotion_flag"]
            .fillna(0)
            .astype(int)
        )

        filtered_df["event_flag"] = (
            filtered_df["event_flag"]
            .fillna(0)
            .astype(int)
        )

        filtered_df["season"] = (
            filtered_df["season"]
            .ffill()
            .bfill()
            .fillna("Normal")
        )

        filtered_df["revenue"] = filtered_df["revenue"].fillna(0)

    return filtered_df


def _calculate_weighted_forecast(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Calculates weighted moving average forecast using:
    - historical average
    - recent 7-day average
    - recent 14-day average
    - event/promotion/season awareness
    """

    historical_avg = float(df["units_sold"].mean())

    recent_7_df = df.tail(7)
    recent_14_df = df.tail(14)

    recent_7_avg = float(recent_7_df["units_sold"].mean())
    recent_14_avg = float(recent_14_df["units_sold"].mean())

    recent_event_rate = float(recent_7_df["event_flag"].mean())
    recent_promotion_rate = float(recent_7_df["promotion_flag"].mean())

    current_season = str(df.iloc[-1]["season"])

    spike_threshold = historical_avg * 1.30

    demand_spike_detected = bool(
        recent_7_avg > spike_threshold
        or (
            recent_event_rate >= 0.40
            and recent_7_avg > historical_avg * 1.15
        )
    )

    weight_recent_7 = 0.60
    weight_recent_14 = 0.25
    weight_historical = 0.15

    if recent_event_rate >= 0.40:
        weight_recent_7 = 0.70
        weight_recent_14 = 0.20
        weight_historical = 0.10
    elif recent_promotion_rate >= 0.40:
        weight_recent_7 = 0.50
        weight_recent_14 = 0.30
        weight_historical = 0.20

    forecast = (
        weight_recent_7 * recent_7_avg
        + weight_recent_14 * recent_14_avg
        + weight_historical * historical_avg
    )

    if current_season == "Peak" and not demand_spike_detected:
        forecast *= 1.03

    if recent_event_rate >= 0.40:
        forecast *= 1.05

    forecasted_demand = int(round(max(forecast, 0)))

    return {
        "historical_avg_demand": historical_avg,
        "recent_avg_demand": recent_7_avg,
        "recent_14_avg_demand": recent_14_avg,
        "recent_event_rate": recent_event_rate,
        "recent_promotion_rate": recent_promotion_rate,
        "current_season": current_season,
        "demand_spike_detected": demand_spike_detected,
        "forecasted_demand": forecasted_demand,
        "weights": {
            "recent_7": weight_recent_7,
            "recent_14": weight_recent_14,
            "historical": weight_historical,
        },
    }


def _one_step_forecast_for_backtest(train_df: pd.DataFrame) -> int:
    """
    Computes one-step-ahead forecast using same weighted logic.
    Used for backtesting on the last few days.
    """

    result = _calculate_weighted_forecast(train_df)
    return int(result["forecasted_demand"])


def _calculate_backtest_mae(df: pd.DataFrame, validation_days: int = 7) -> float:
    """
    Uses last N days as validation and computes one-step-ahead MAE.
    """

    if len(df) <= validation_days + 14:
        return 0.0

    errors = []
    start_idx = len(df) - validation_days

    for idx in range(start_idx, len(df)):
        train_df = df.iloc[:idx].copy()
        actual = float(df.iloc[idx]["units_sold"])
        forecast = float(_one_step_forecast_for_backtest(train_df))
        errors.append(abs(actual - forecast))

    if not errors:
        return 0.0

    return float(np.mean(errors))


def _calculate_forecast_confidence(
    df: pd.DataFrame,
    forecast_details: Dict[str, Any],
    backtest_mae: float,
) -> float:
    """
    Calculates forecast confidence between 0 and 1.

    Confidence decreases when:
    - demand volatility is high
    - recent event rate is high
    - recent promotion rate is high
    - backtest error is high
    - data length is small
    """

    demand_mean = float(df["units_sold"].mean())
    demand_std = float(df["units_sold"].std(ddof=0))

    if demand_mean <= 0:
        coefficient_of_variation = 1.0
    else:
        coefficient_of_variation = demand_std / demand_mean

    recent_event_rate = forecast_details["recent_event_rate"]
    recent_promotion_rate = forecast_details["recent_promotion_rate"]
    recent_avg = max(forecast_details["recent_avg_demand"], 1)

    error_rate = backtest_mae / recent_avg if recent_avg > 0 else 1.0

    confidence = 0.95

    volatility_penalty = min(0.25, coefficient_of_variation * 0.35)
    error_penalty = min(0.25, error_rate * 0.60)
    event_penalty = 0.07 if recent_event_rate >= 0.40 else 0.0
    promotion_penalty = 0.03 if recent_promotion_rate >= 0.40 else 0.0

    if len(df) >= 60:
        data_penalty = 0.0
    elif len(df) >= 30:
        data_penalty = 0.05
    else:
        data_penalty = 0.10

    confidence -= (
        volatility_penalty
        + error_penalty
        + event_penalty
        + promotion_penalty
        + data_penalty
    )

    confidence = float(np.clip(confidence, 0.50, 0.95))

    return round(confidence, 2)


def _validate_product_exists(products_df: pd.DataFrame, product_id: str) -> str:
    """
    Validates product_id exists in products.csv and returns product_name.
    """

    product_row = products_df[products_df["product_id"] == product_id]

    if product_row.empty:
        raise ValueError(f"Product ID {product_id} not found in products.csv")

    return str(product_row.iloc[0]["product_name"])


# ============================================================
# Main LangGraph node
# ============================================================

def forecasting_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Forecasting Agent node.

    Reads sales_history.csv and products.csv through the Data Access Guard,
    filters by product_id and region, generates forecasted demand, detects
    demand spike, estimates confidence, generates visualizations, and returns
    schema-compatible output plus data-access governance updates.
    """

    run_id = state.get("run_id", "RUN-UNKNOWN")
    product_id = state.get("product_id")
    region = state.get("region")

    if not product_id:
        raise ValueError("product_id is required in state for Forecasting Agent")

    if not region:
        raise ValueError("region is required in state for Forecasting Agent")

    sales_df, products_df, access_update = _load_datasets(state)

    if sales_df is None or products_df is None:
        message = (
            "Forecasting could not proceed because required dataset access was "
            "denied or a required dataset was unavailable. Review data_access_log "
            "for the exact access decision."
        )

        return {
            "forecasting_output": _build_failed_forecasting_output(
                run_id=run_id,
                product_id=product_id,
                region=region,
                message=message,
                source_files=[],
                source_record_ids=[],
            ),
            **access_update,
        }

    try:
        _validate_required_columns(
            dataframe=sales_df,
            required_columns=REQUIRED_SALES_COLUMNS,
            file_name="sales_history.csv",
        )

        _validate_required_columns(
            dataframe=products_df,
            required_columns=REQUIRED_PRODUCT_COLUMNS,
            file_name="products.csv",
        )

        product_name = _validate_product_exists(
            products_df=products_df,
            product_id=product_id,
        )

        product_region_df = _prepare_product_region_series(
            sales_df=sales_df,
            product_id=product_id,
            region=region,
        )

        forecast_details = _calculate_weighted_forecast(product_region_df)

        backtest_mae = _calculate_backtest_mae(
            product_region_df,
            validation_days=7,
        )

        forecast_confidence = _calculate_forecast_confidence(
            df=product_region_df,
            forecast_details=forecast_details,
            backtest_mae=backtest_mae,
        )

        visualization_files = generate_forecasting_visualizations(
            df=product_region_df,
            product_id=product_id,
            region=region,
            run_id=run_id,
            forecast_details=forecast_details,
            forecast_confidence=forecast_confidence,
        )

        min_date = product_region_df["date"].min().date()
        max_date = product_region_df["date"].max().date()
        record_count = len(product_region_df)

        source_record_id = (
            f"{product_id}|{region}|{min_date}_to_{max_date}|rows={record_count}"
        )

        message = (
            f"Forecast generated for {product_id} ({product_name}) in {region}. "
            f"Forecasted demand: {forecast_details['forecasted_demand']} units. "
            f"Recent 7-day average: {forecast_details['recent_avg_demand']:.2f}. "
            f"Historical average: {forecast_details['historical_avg_demand']:.2f}. "
            f"Demand spike detected: {forecast_details['demand_spike_detected']}."
        )

        output = ForecastingOutput(
            run_id=run_id,
            step_id="STEP-002",
            agent_id="forecasting_agent",
            agent_name="Forecasting Agent",
            status="success",
            source_files=["sales_history.csv", "products.csv"],
            source_record_ids=[source_record_id],
            message=message,
            product_id=product_id,
            region=region,
            forecast_horizon_days=1,
            forecasted_demand=forecast_details["forecasted_demand"],
            historical_avg_demand=round(
                forecast_details["historical_avg_demand"],
                2,
            ),
            recent_avg_demand=round(
                forecast_details["recent_avg_demand"],
                2,
            ),
            demand_spike_detected=forecast_details["demand_spike_detected"],
            forecast_confidence=forecast_confidence,
            method_used=(
                "weighted_moving_average_with_spike_detection_"
                "event_promotion_season_adjustment_and_backtest_mae"
            ),
            visualization_files=visualization_files,
        )

        return {
            "forecasting_output": _safe_model_dump(output),
            **access_update,
        }

    except Exception as exc:
        message = (
            "Forecasting failed after governed dataset access completed. "
            f"Reason: {exc}"
        )

        return {
            "forecasting_output": _build_failed_forecasting_output(
                run_id=run_id,
                product_id=product_id,
                region=region,
                message=message,
                source_files=["sales_history.csv", "products.csv"],
                source_record_ids=[],
            ),
            **access_update,
        }


# ============================================================
# Optional local test
# ============================================================

if __name__ == "__main__":
    test_state = {
        "run_id": "RUN-FORECAST-TEST-001",
        "product_id": "P-101",
        "region": "East",
        "completed_steps": [],
        "errors": [],
    }

    result = forecasting_node(test_state)

    print("Forecasting Agent executed successfully.")
    print("Forecasting output:")
    print(result.get("forecasting_output"))

    print("Data access log:")
    print(result.get("data_access_log"))

    print("Dataset accessed:")
    print(result.get("dataset_accessed"))

    print("Dataset access attempted:")
    print(result.get("dataset_access_attempted"))