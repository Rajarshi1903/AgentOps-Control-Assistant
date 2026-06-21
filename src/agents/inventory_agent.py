import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from src.schemas.agent_outputs import InventoryOutput
from src.services.data_access_guard import (
    read_governed_csv,
    merge_access_updates,
)


# ============================================================
# Inventory Agent
# ============================================================
# Purpose:
# Checks current inventory for a product-region pair and determines
# whether procurement is required.
#
# Governance update:
# This agent does not read CSV files directly using pd.read_csv.
# It reads datasets through data_access_guard.read_governed_csv so that
# every file access is logged and evaluated against dataset governance rules.
#
# Decision principle:
# Procurement is required when either:
# 1. Current stock is below the reorder point, OR
# 2. Forecasted demand plus safety stock creates a shortage.
#
# This is fully state-driven and does not hardcode any product, region,
# query text, or scenario.
# ============================================================


DATA_DIR = Path(os.getenv("DATA_DIR", "data"))


REQUIRED_INVENTORY_COLUMNS = {
    "inventory_id",
    "product_id",
    "warehouse_id",
    "region",
    "current_stock",
    "safety_stock",
    "reorder_point",
    "last_updated",
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
    Supports both Pydantic v1 and v2 serialization.
    """

    if model is None:
        return {}

    if isinstance(model, dict):
        return model

    if hasattr(model, "model_dump"):
        return model.model_dump()

    if hasattr(model, "dict"):
        return model.dict()

    return dict(model)


def _as_dict(value: Any) -> Dict[str, Any]:
    """
    Converts Pydantic object or dict-like object to dictionary.
    This keeps the agent compatible whether previous nodes return
    Pydantic objects or plain dictionaries.
    """

    if value is None:
        return {}

    if isinstance(value, dict):
        return value

    if hasattr(value, "model_dump"):
        return value.model_dump()

    if hasattr(value, "dict"):
        return value.dict()

    return {}


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


def _build_failed_inventory_output(
    run_id: str,
    product_id: Optional[str],
    region: Optional[str],
    message: str,
    source_files: Optional[List[str]] = None,
    source_record_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Builds a safe failure output.

    This is intentionally a plain dict instead of InventoryOutput because
    failure cases may not have all fields required by the success schema.
    """

    return {
        "run_id": run_id,
        "step_id": "STEP-003",
        "agent_id": "inventory_agent",
        "agent_name": "Inventory Agent",
        "status": "failed",
        "source_files": source_files or [],
        "source_record_ids": source_record_ids or [],
        "message": message,
        "product_id": product_id,
        "region": region,
        "warehouse_id": None,
        "forecasted_demand": None,
        "current_stock": None,
        "safety_stock": None,
        "reorder_point": None,
        "shortage_quantity": None,
        "procurement_required": None,
        "stock_position": None,
        "calculation": None,
    }


# ============================================================
# Dataset loading with governed access
# ============================================================

def _load_datasets(
    state: Dict[str, Any],
) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame], Dict[str, Any]]:
    """
    Loads inventory.csv and products.csv through the Data Access Guard.

    Returns:
        inventory_df, products_df, access_update

    If access is denied or a file is missing, one or both dataframes may be None.
    The access_update must still be returned by the node so policy/audit can
    reason over the attempted access.
    """

    inventory_df, inventory_access_update = read_governed_csv(
        state=state,
        agent_id="inventory_agent",
        file_name="inventory.csv",
        purpose="inventory_stock_lookup",
        data_dir=DATA_DIR,
    )

    intermediate_state = dict(state)
    intermediate_state.update(inventory_access_update)

    products_df, products_access_update = read_governed_csv(
        state=intermediate_state,
        agent_id="inventory_agent",
        file_name="products.csv",
        purpose="inventory_product_validation",
        data_dir=DATA_DIR,
    )

    access_update = merge_access_updates(
        state,
        inventory_access_update,
        products_access_update,
    )

    return inventory_df, products_df, access_update


# ============================================================
# Inventory preparation and calculations
# ============================================================

def _validate_product_exists(products_df: pd.DataFrame, product_id: str) -> str:
    """
    Validates product_id exists in products.csv and returns product_name.
    """

    product_row = products_df[products_df["product_id"] == product_id]

    if product_row.empty:
        raise ValueError(f"Product ID {product_id} not found in products.csv")

    status = str(product_row.iloc[0]["status"])

    if status != "Active":
        raise ValueError(f"Product ID {product_id} is not Active")

    return str(product_row.iloc[0]["product_name"])


def _prepare_inventory_values(inventory_row: pd.Series) -> Dict[str, Any]:
    """
    Converts inventory row values into clean numeric values.
    """

    numeric_columns = ["current_stock", "safety_stock", "reorder_point"]
    cleaned: Dict[str, Any] = {}

    for column in numeric_columns:
        value = pd.to_numeric(inventory_row[column], errors="coerce")

        if pd.isna(value):
            raise ValueError(f"Invalid numeric value found in {column}")

        if value < 0:
            raise ValueError(f"{column} cannot be negative")

        cleaned[column] = int(round(float(value)))

    cleaned["inventory_id"] = str(inventory_row["inventory_id"])
    cleaned["warehouse_id"] = str(inventory_row["warehouse_id"])
    cleaned["last_updated"] = str(inventory_row["last_updated"])

    return cleaned


def _get_inventory_row(
    inventory_df: pd.DataFrame,
    product_id: str,
    region: str,
) -> pd.Series:
    """
    Finds the inventory record for product_id + region.
    MVP assumption: one warehouse per region.
    """

    filtered = inventory_df[
        (inventory_df["product_id"] == product_id)
        & (inventory_df["region"] == region)
    ]

    if filtered.empty:
        raise ValueError(
            f"No inventory record found for product_id={product_id}, region={region}"
        )

    if len(filtered) > 1:
        raise ValueError(
            f"Multiple inventory records found for product_id={product_id}, region={region}. "
            "MVP expects one inventory row per product-region."
        )

    return filtered.iloc[0]


def _classify_stock_position(
    current_stock: int,
    safety_stock: int,
    reorder_point: int,
) -> str:
    """
    Classifies inventory health using inventory thresholds.
    """

    if current_stock < safety_stock:
        return "Below Safety Stock"

    if current_stock < reorder_point:
        return "Below Reorder Point"

    return "Healthy"


def _extract_forecasted_demand(state: Dict[str, Any]) -> Tuple[int, bool]:
    """
    Extracts forecasted_demand from forecasting_output if available.

    Returns:
    - forecasted_demand
    - forecast_available
    """

    forecasting_output = _as_dict(state.get("forecasting_output"))

    if not forecasting_output:
        return 0, False

    if forecasting_output.get("status") == "failed":
        return 0, False

    forecasted_demand = forecasting_output.get("forecasted_demand")

    if forecasted_demand is None:
        return 0, False

    forecasted_demand = pd.to_numeric(forecasted_demand, errors="coerce")

    if pd.isna(forecasted_demand):
        raise ValueError("forecasted_demand in forecasting_output is not numeric")

    if forecasted_demand < 0:
        raise ValueError("forecasted_demand cannot be negative")

    return int(round(float(forecasted_demand))), True


def _calculate_inventory_decision(
    forecasted_demand: int,
    forecast_available: bool,
    current_stock: int,
    safety_stock: int,
    reorder_point: int,
) -> Dict[str, Any]:
    """
    Calculates shortage and procurement requirement.

    General decision logic:
    - stock_below_reorder_point = current_stock < reorder_point
    - forecast_creates_shortage = shortage_quantity > 0
    - procurement_required = stock_below_reorder_point OR forecast_creates_shortage

    This avoids treating inventory as sufficient when it is below reorder point,
    even if forecast-based shortage_quantity is zero.
    """

    stock_position = _classify_stock_position(
        current_stock=current_stock,
        safety_stock=safety_stock,
        reorder_point=reorder_point,
    )

    stock_below_reorder_point = current_stock < reorder_point

    if forecast_available:
        shortage_quantity = max(
            forecasted_demand + safety_stock - current_stock,
            0,
        )

        forecast_creates_shortage = shortage_quantity > 0

        procurement_required = (
            stock_below_reorder_point
            or forecast_creates_shortage
        )

        calculation = (
            "shortage_quantity = max(forecasted_demand + safety_stock - current_stock, 0); "
            "stock_below_reorder_point = current_stock < reorder_point; "
            "forecast_creates_shortage = shortage_quantity > 0; "
            "procurement_required = stock_below_reorder_point OR forecast_creates_shortage"
        )

    else:
        shortage_quantity = 0
        forecast_creates_shortage = False

        procurement_required = stock_below_reorder_point

        calculation = (
            "No forecasting_output available. "
            "stock_below_reorder_point = current_stock < reorder_point; "
            "procurement_required = stock_below_reorder_point"
        )

    return {
        "shortage_quantity": int(shortage_quantity),
        "procurement_required": bool(procurement_required),
        "stock_position": stock_position,
        "stock_below_reorder_point": bool(stock_below_reorder_point),
        "forecast_creates_shortage": bool(forecast_creates_shortage),
        "calculation": calculation,
    }


def _build_inventory_message(
    product_id: str,
    product_name: str,
    region: str,
    forecast_available: bool,
    forecasted_demand: int,
    inventory_values: Dict[str, Any],
    decision: Dict[str, Any],
) -> str:
    """
    Builds a business-readable inventory message without contradicting
    procurement_required or stock_position.
    """

    base_message = (
        f"Inventory checked for {product_id} ({product_name}) in {region}. "
        f"Current stock: {inventory_values['current_stock']}, "
        f"safety stock: {inventory_values['safety_stock']}, "
        f"reorder point: {inventory_values['reorder_point']}, "
        f"stock position: {decision['stock_position']}, "
        f"shortage quantity: {decision['shortage_quantity']}, "
        f"procurement required: {decision['procurement_required']}."
    )

    if forecast_available:
        base_message += (
            f" Forecasted demand used: {forecasted_demand}. "
        )
    else:
        base_message += (
            " No forecast was available, so procurement requirement was evaluated using reorder point. "
        )

    if decision["stock_below_reorder_point"] and not decision["forecast_creates_shortage"]:
        base_message += (
            "Stock is below the reorder point even though forecast-based shortage is zero."
        )
    elif decision["forecast_creates_shortage"]:
        base_message += (
            "Forecasted demand plus safety stock creates a replenishment shortage."
        )
    elif not decision["procurement_required"]:
        base_message += (
            "Inventory is healthy against the reorder threshold and no forecast-based shortage was created."
        )

    return base_message


# ============================================================
# Main LangGraph node
# ============================================================

def inventory_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Inventory Agent node.

    Reads inventory.csv and products.csv through the Data Access Guard,
    validates product-region inventory, uses forecasted demand when available,
    calculates shortage, classifies stock position, and returns schema-compatible
    output plus data-access governance updates.
    """

    run_id = state.get("run_id", "RUN-UNKNOWN")
    product_id = state.get("product_id")
    region = state.get("region")

    if not product_id:
        raise ValueError("product_id is required in state for Inventory Agent")

    if not region:
        raise ValueError("region is required in state for Inventory Agent")

    inventory_df, products_df, access_update = _load_datasets(state)

    if inventory_df is None or products_df is None:
        message = (
            "Inventory check could not proceed because required dataset access was "
            "denied or a required dataset was unavailable. Review data_access_log "
            "for the exact access decision."
        )

        return {
            "inventory_output": _build_failed_inventory_output(
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
            dataframe=inventory_df,
            required_columns=REQUIRED_INVENTORY_COLUMNS,
            file_name="inventory.csv",
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

        inventory_row = _get_inventory_row(
            inventory_df=inventory_df,
            product_id=product_id,
            region=region,
        )

        inventory_values = _prepare_inventory_values(inventory_row)

        forecasted_demand, forecast_available = _extract_forecasted_demand(state)

        decision = _calculate_inventory_decision(
            forecasted_demand=forecasted_demand,
            forecast_available=forecast_available,
            current_stock=inventory_values["current_stock"],
            safety_stock=inventory_values["safety_stock"],
            reorder_point=inventory_values["reorder_point"],
        )

        message = _build_inventory_message(
            product_id=product_id,
            product_name=product_name,
            region=region,
            forecast_available=forecast_available,
            forecasted_demand=forecasted_demand,
            inventory_values=inventory_values,
            decision=decision,
        )

        output = InventoryOutput(
            run_id=run_id,
            step_id="STEP-003",
            agent_id="inventory_agent",
            agent_name="Inventory Agent",
            status="success",
            source_files=["inventory.csv", "products.csv"],
            source_record_ids=[inventory_values["inventory_id"]],
            message=message,
            product_id=product_id,
            region=region,
            warehouse_id=inventory_values["warehouse_id"],
            forecasted_demand=forecasted_demand,
            current_stock=inventory_values["current_stock"],
            safety_stock=inventory_values["safety_stock"],
            reorder_point=inventory_values["reorder_point"],
            shortage_quantity=decision["shortage_quantity"],
            procurement_required=decision["procurement_required"],
            stock_position=decision["stock_position"],
            calculation=decision["calculation"],
        )

        inventory_output = _safe_model_dump(output)

        # Add non-schema diagnostic fields only after model serialization.
        # This keeps InventoryOutput schema compatibility while still giving
        # downstream agents structured, general-purpose decision facts.
        inventory_output["stock_below_reorder_point"] = decision["stock_below_reorder_point"]
        inventory_output["forecast_creates_shortage"] = decision["forecast_creates_shortage"]

        return {
            "inventory_output": inventory_output,
            **access_update,
        }

    except Exception as exc:
        message = (
            "Inventory check failed after governed dataset access completed. "
            f"Reason: {exc}"
        )

        return {
            "inventory_output": _build_failed_inventory_output(
                run_id=run_id,
                product_id=product_id,
                region=region,
                message=message,
                source_files=["inventory.csv", "products.csv"],
                source_record_ids=[],
            ),
            **access_update,
        }


# ============================================================
# Optional local test
# ============================================================

if __name__ == "__main__":
    test_state = {
        "run_id": "RUN-INVENTORY-TEST-001",
        "product_id": "P-101",
        "region": "South",
        "forecasting_output": {
            "forecasted_demand": 223,
            "forecast_confidence": 0.78,
            "demand_spike_detected": True,
        },
        "completed_steps": [],
        "errors": [],
    }

    result = inventory_node(test_state)

    print("Inventory Agent executed successfully.")
    print("Inventory output:")
    print(result.get("inventory_output"))

    print("Data access log:")
    print(result.get("data_access_log"))

    print("Dataset accessed:")
    print(result.get("dataset_accessed"))

    print("Dataset access attempted:")
    print(result.get("dataset_access_attempted"))