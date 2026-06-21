import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from src.schemas.agent_outputs import ProcurementOutput
from src.services.data_access_guard import (
    read_governed_csv,
    merge_access_updates,
)


# ============================================================
# Procurement Agent
# ============================================================
# Purpose:
# Recommends supplier and procurement quantity based on inventory need.
#
# Governance update:
# This agent does not read CSV files directly using pd.read_csv.
# It reads datasets through data_access_guard.read_governed_csv so that
# every file access is logged and evaluated against dataset governance rules.
#
# Important design choices:
# - products.csv is read first to validate the product.
# - suppliers.csv is read only when supplier selection is actually needed.
# - if inventory_output exists and has failed, procurement does not continue
#   into supplier selection.
# - if inventory_output says procurement_required=False, the agent returns
#   a non-action output and does not access suppliers.csv.
# - access logs are preserved in success, skipped/no-action, access-denied,
#   and post-access calculation-failure cases.
#
# No hardcoding:
# - No product-specific logic.
# - No region-specific logic.
# - No query-text matching.
# - All decisions are based on structured state fields.
# ============================================================


DATA_DIR = Path(os.getenv("DATA_DIR", "data"))


REQUIRED_SUPPLIER_COLUMNS = {
    "supplier_id",
    "supplier_name",
    "product_id",
    "region",
    "unit_cost",
    "lead_time_days",
    "reliability_score",
    "is_approved",
    "max_capacity",
    "compliance_status",
}

REQUIRED_PRODUCT_COLUMNS = {
    "product_id",
    "product_name",
    "category",
    "unit_price",
    "criticality",
    "status",
}

VALID_SELECTION_STRATEGIES = {
    "compliance_first",
    "cheapest",
    "fastest",
    "highest_reliability",
}


# ============================================================
# Utility helpers
# ============================================================

def _safe_model_dump(model: Any) -> Dict[str, Any]:
    """
    Supports Pydantic v1/v2, dict, and dict-like objects.
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
    Keeps the agent compatible whether previous nodes return Pydantic objects
    or plain dictionaries.
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


def _safe_float(value: Any, default: float = 0.0) -> float:
    """
    Safely converts a value to float.
    """

    if value is None:
        return default

    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_bool(value: Any, default: bool = False) -> bool:
    """
    Safely converts a value to boolean.
    """

    if value is None:
        return default

    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1", "y"}

    return bool(value)


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


def _as_list(value: Any) -> List[str]:
    """
    Safely converts a value to list[str].
    """

    if value is None:
        return []

    if isinstance(value, list):
        return [str(item) for item in value]

    if isinstance(value, tuple):
        return [str(item) for item in value]

    if isinstance(value, set):
        return [str(item) for item in value]

    return [str(value)]


def _unique_preserve_order(values: List[str]) -> List[str]:
    """
    Returns unique values while preserving order.
    """

    seen = set()
    result: List[str] = []

    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)

    return result


def _build_failed_procurement_output(
    run_id: str,
    product_id: Optional[str],
    region: Optional[str],
    message: str,
    source_files: Optional[List[str]] = None,
    source_record_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Builds a safe failure output.

    This is intentionally a plain dict instead of ProcurementOutput because
    failure cases may not have all fields required by the success schema.
    """

    return {
        "run_id": run_id,
        "step_id": "STEP-004",
        "agent_id": "procurement_agent",
        "agent_name": "Procurement Agent",
        "status": "failed",
        "source_files": source_files or [],
        "source_record_ids": source_record_ids or [],
        "message": message,
        "product_id": product_id,
        "region": region,
        "recommended_quantity": None,
        "recommended_supplier_id": None,
        "recommended_supplier_name": None,
        "supplier_region": None,
        "unit_cost": None,
        "lead_time_days": None,
        "reliability_score": None,
        "is_approved": None,
        "compliance_status": None,
        "max_capacity": None,
        "procurement_value": None,
        "supplier_selection_reason": None,
        "action_required": False,
        "recommendation_generated": False,
        "procurement_skipped_reason": None,
    }


# ============================================================
# Governed data loading
# ============================================================

def _load_products(
    state: Dict[str, Any],
) -> Tuple[Optional[pd.DataFrame], Dict[str, Any]]:
    """
    Loads products.csv through the Data Access Guard.
    """

    products_df, products_access_update = read_governed_csv(
        state=state,
        agent_id="procurement_agent",
        file_name="products.csv",
        purpose="procurement_product_validation",
        data_dir=DATA_DIR,
    )

    return products_df, products_access_update


def _load_suppliers(
    state: Dict[str, Any],
) -> Tuple[Optional[pd.DataFrame], Dict[str, Any]]:
    """
    Loads suppliers.csv through the Data Access Guard.
    """

    suppliers_df, suppliers_access_update = read_governed_csv(
        state=state,
        agent_id="procurement_agent",
        file_name="suppliers.csv",
        purpose="procurement_supplier_selection",
        data_dir=DATA_DIR,
    )

    return suppliers_df, suppliers_access_update


# ============================================================
# Product and supplier validation
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


def _prepare_supplier_values(suppliers_df: pd.DataFrame) -> pd.DataFrame:
    """
    Converts supplier numeric columns into clean numeric values and validates
    basic constraints.
    """

    df = suppliers_df.copy()

    numeric_columns = [
        "unit_cost",
        "lead_time_days",
        "reliability_score",
        "max_capacity",
    ]

    for column in numeric_columns:
        df[column] = pd.to_numeric(df[column], errors="coerce")

        if df[column].isna().any():
            raise ValueError(
                f"Invalid numeric values found in suppliers.csv column: {column}"
            )

        if (df[column] < 0).any():
            raise ValueError(
                f"Negative values found in suppliers.csv column: {column}"
            )

    if (df["unit_cost"] <= 0).any():
        raise ValueError("unit_cost must be greater than 0")

    if (df["lead_time_days"] <= 0).any():
        raise ValueError("lead_time_days must be greater than 0")

    if ((df["reliability_score"] < 0) | (df["reliability_score"] > 100)).any():
        raise ValueError("reliability_score must be between 0 and 100")

    if (df["max_capacity"] <= 0).any():
        raise ValueError("max_capacity must be greater than 0")

    df["is_approved"] = df["is_approved"].astype(str)
    df["compliance_status"] = df["compliance_status"].astype(str)
    df["supplier_id"] = df["supplier_id"].astype(str)
    df["supplier_name"] = df["supplier_name"].astype(str)
    df["region"] = df["region"].astype(str)
    df["product_id"] = df["product_id"].astype(str)

    return df


# ============================================================
# Inventory context and quantity calculation
# ============================================================

def _calculate_recommended_quantity_from_inventory(
    inventory_output: Dict[str, Any]
) -> int:
    """
    Calculates recommended procurement quantity from inventory output.

    Handles:
    1. Forecast-driven shortage:
       shortage_quantity > 0

    2. Reorder-point trigger:
       procurement_required=True,
       shortage_quantity=0,
       current_stock < reorder_point,
       recommended_quantity = reorder_point - current_stock

    This is state-driven and does not depend on product, region, or query text.
    """

    procurement_required = _safe_bool(
        inventory_output.get("procurement_required", False),
        default=False,
    )

    shortage_quantity = _safe_float(
        inventory_output.get("shortage_quantity", 0),
        default=0,
    )

    current_stock = _safe_float(
        inventory_output.get("current_stock", 0),
        default=0,
    )

    reorder_point = _safe_float(
        inventory_output.get("reorder_point", 0),
        default=0,
    )

    if not procurement_required:
        return 0

    if shortage_quantity > 0:
        return max(int(round(shortage_quantity)), 0)

    reorder_gap = reorder_point - current_stock

    if reorder_gap > 0:
        return max(int(round(reorder_gap)), 0)

    return 0


def _extract_inventory_context(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extracts inventory output from state.

    Returns a context dictionary including whether inventory output exists,
    whether inventory failed, whether procurement is required, calculated
    recommended quantity, and inherited source traceability.
    """

    inventory_output = _as_dict(state.get("inventory_output"))

    if not inventory_output:
        return {
            "inventory_available": False,
            "inventory_failed": False,
            "procurement_required": False,
            "recommended_quantity": 0,
            "current_stock": 0,
            "reorder_point": 0,
            "shortage_quantity": 0,
            "stock_position": None,
            "stock_below_reorder_point": False,
            "forecast_creates_shortage": False,
            "inventory_source_files": [],
            "inventory_source_record_ids": [],
            "inventory_failure_message": None,
        }

    inventory_status = str(inventory_output.get("status", "")).lower()

    if inventory_status == "failed":
        return {
            "inventory_available": True,
            "inventory_failed": True,
            "procurement_required": False,
            "recommended_quantity": 0,
            "current_stock": _safe_float(inventory_output.get("current_stock", 0)),
            "reorder_point": _safe_float(inventory_output.get("reorder_point", 0)),
            "shortage_quantity": _safe_float(inventory_output.get("shortage_quantity", 0)),
            "stock_position": inventory_output.get("stock_position"),
            "stock_below_reorder_point": _safe_bool(
                inventory_output.get("stock_below_reorder_point", False)
            ),
            "forecast_creates_shortage": _safe_bool(
                inventory_output.get("forecast_creates_shortage", False)
            ),
            "inventory_source_files": _as_list(inventory_output.get("source_files", [])),
            "inventory_source_record_ids": _as_list(inventory_output.get("source_record_ids", [])),
            "inventory_failure_message": inventory_output.get("message"),
        }

    procurement_required = _safe_bool(
        inventory_output.get("procurement_required", False),
        default=False,
    )

    recommended_quantity = _calculate_recommended_quantity_from_inventory(
        inventory_output=inventory_output
    )

    return {
        "inventory_available": True,
        "inventory_failed": False,
        "procurement_required": procurement_required,
        "recommended_quantity": recommended_quantity,
        "current_stock": _safe_float(inventory_output.get("current_stock", 0)),
        "reorder_point": _safe_float(inventory_output.get("reorder_point", 0)),
        "shortage_quantity": _safe_float(inventory_output.get("shortage_quantity", 0)),
        "stock_position": inventory_output.get("stock_position"),
        "stock_below_reorder_point": _safe_bool(
            inventory_output.get("stock_below_reorder_point", False)
        ),
        "forecast_creates_shortage": _safe_bool(
            inventory_output.get("forecast_creates_shortage", False)
        ),
        "inventory_source_files": _as_list(inventory_output.get("source_files", [])),
        "inventory_source_record_ids": _as_list(inventory_output.get("source_record_ids", [])),
        "inventory_failure_message": None,
    }


# ============================================================
# Supplier selection helpers
# ============================================================

def _get_suppliers_for_product(
    suppliers_df: pd.DataFrame,
    product_id: str,
) -> pd.DataFrame:
    """
    Filters suppliers by product_id.
    """

    product_suppliers = suppliers_df[suppliers_df["product_id"] == product_id].copy()

    if product_suppliers.empty:
        raise ValueError(f"No suppliers found for product_id={product_id}")

    return product_suppliers


def _filter_by_capacity(
    suppliers_df: pd.DataFrame,
    recommended_quantity: int,
) -> pd.DataFrame:
    """
    Filters suppliers that can fully satisfy the procurement quantity.
    For MVP, split procurement is not supported.
    """

    if recommended_quantity <= 0:
        return suppliers_df.copy()

    capable_suppliers = suppliers_df[
        suppliers_df["max_capacity"] >= recommended_quantity
    ].copy()

    if capable_suppliers.empty:
        raise ValueError(
            f"No supplier has sufficient capacity for quantity={recommended_quantity}"
        )

    return capable_suppliers


def _calculate_supplier_score(
    suppliers_df: pd.DataFrame,
    demand_region: str,
    recommended_quantity: int,
) -> pd.DataFrame:
    """
    Calculates supplier_score.

    Lower score is better.
    """

    df = suppliers_df.copy()

    min_unit_cost = max(float(df["unit_cost"].min()), 1.0)

    df["cost_score"] = (df["unit_cost"] / min_unit_cost) * 1000
    df["lead_time_penalty"] = df["lead_time_days"] * 100
    df["reliability_penalty"] = (100 - df["reliability_score"]) * 20

    df["approval_penalty"] = df["is_approved"].apply(
        lambda value: 0 if value == "Yes" else 100000
    )

    def compliance_penalty(status: str) -> int:
        if status == "Compliant":
            return 0

        if status == "Under Review":
            return 10000

        return 100000

    df["compliance_penalty"] = df["compliance_status"].apply(compliance_penalty)

    df["capacity_penalty"] = df["max_capacity"].apply(
        lambda capacity: 0 if capacity >= recommended_quantity else 100000
    )

    df["region_penalty"] = df["region"].apply(
        lambda supplier_region: 0 if supplier_region == demand_region else 1000
    )

    df["supplier_score"] = (
        df["cost_score"]
        + df["lead_time_penalty"]
        + df["reliability_penalty"]
        + df["approval_penalty"]
        + df["compliance_penalty"]
        + df["capacity_penalty"]
        + df["region_penalty"]
    )

    return df


def _select_supplier(
    suppliers_df: pd.DataFrame,
    demand_region: str,
    recommended_quantity: int,
    selection_strategy: str,
) -> pd.Series:
    """
    Selects supplier based on strategy.

    Supported strategies:
    - compliance_first
    - cheapest
    - fastest
    - highest_reliability
    """

    if selection_strategy not in VALID_SELECTION_STRATEGIES:
        raise ValueError(
            f"Invalid selection_strategy={selection_strategy}. "
            f"Valid values are: {sorted(VALID_SELECTION_STRATEGIES)}"
        )

    scored_df = _calculate_supplier_score(
        suppliers_df=suppliers_df,
        demand_region=demand_region,
        recommended_quantity=recommended_quantity,
    )

    if selection_strategy == "compliance_first":
        selected_df = scored_df.sort_values(
            by=[
                "supplier_score",
                "unit_cost",
                "lead_time_days",
                "reliability_score",
            ],
            ascending=[True, True, True, False],
        )

    elif selection_strategy == "cheapest":
        selected_df = scored_df.sort_values(
            by=[
                "unit_cost",
                "lead_time_days",
                "reliability_score",
            ],
            ascending=[True, True, False],
        )

    elif selection_strategy == "fastest":
        selected_df = scored_df.sort_values(
            by=[
                "lead_time_days",
                "supplier_score",
                "unit_cost",
            ],
            ascending=[True, True, True],
        )

    elif selection_strategy == "highest_reliability":
        selected_df = scored_df.sort_values(
            by=[
                "reliability_score",
                "supplier_score",
                "unit_cost",
            ],
            ascending=[False, True, True],
        )

    else:
        raise ValueError(f"Unhandled selection strategy: {selection_strategy}")

    return selected_df.iloc[0]


# ============================================================
# Output builders
# ============================================================

def _build_no_procurement_output(
    run_id: str,
    product_id: str,
    region: str,
    product_name: str,
    inventory_context: Dict[str, Any],
    reason: str,
) -> Dict[str, Any]:
    """
    Builds a non-action output when procurement is not required.

    Plain dict is used instead of ProcurementOutput so that status can be
    represented as skipped/not-action without risking schema incompatibility.
    """

    inventory_source_files = inventory_context.get("inventory_source_files", [])
    inventory_source_record_ids = inventory_context.get("inventory_source_record_ids", [])

    source_files = _unique_preserve_order(
        inventory_source_files + ["products.csv"]
    )

    source_record_ids = _unique_preserve_order(
        inventory_source_record_ids + [product_id]
    )

    message = (
        f"Procurement not required for {product_id} ({product_name}) in {region}. "
        f"{reason}"
    )

    return {
        "procurement_output": {
            "run_id": run_id,
            "step_id": "STEP-004",
            "agent_id": "procurement_agent",
            "agent_name": "Procurement Agent",
            "status": "skipped",
            "source_files": source_files,
            "source_record_ids": source_record_ids,
            "message": message,
            "product_id": product_id,
            "region": region,
            "recommended_quantity": 0,
            "recommended_supplier_id": None,
            "recommended_supplier_name": None,
            "supplier_region": None,
            "unit_cost": None,
            "lead_time_days": None,
            "reliability_score": None,
            "is_approved": None,
            "compliance_status": None,
            "max_capacity": None,
            "procurement_value": 0.0,
            "supplier_selection_reason": reason,
            "action_required": False,
            "recommendation_generated": False,
            "procurement_skipped_reason": reason,
            "inventory_context": {
                "procurement_required": inventory_context.get("procurement_required"),
                "recommended_quantity": inventory_context.get("recommended_quantity"),
                "current_stock": inventory_context.get("current_stock"),
                "reorder_point": inventory_context.get("reorder_point"),
                "shortage_quantity": inventory_context.get("shortage_quantity"),
                "stock_position": inventory_context.get("stock_position"),
                "stock_below_reorder_point": inventory_context.get("stock_below_reorder_point"),
                "forecast_creates_shortage": inventory_context.get("forecast_creates_shortage"),
            },
        },
        "supplier_id": None,
    }


def _build_inconsistent_inventory_output(
    run_id: str,
    product_id: str,
    region: str,
    product_name: str,
    inventory_context: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Builds a failure output when inventory says procurement is required but
    recommended quantity cannot be calculated from structured inventory facts.

    This avoids silently converting inconsistent upstream state into
    "no procurement required."
    """

    inventory_source_files = inventory_context.get("inventory_source_files", [])
    inventory_source_record_ids = inventory_context.get("inventory_source_record_ids", [])

    message = (
        f"Procurement could not generate a recommendation for {product_id} "
        f"({product_name}) in {region} because inventory_output marked "
        "procurement_required=True, but recommended quantity was calculated as zero. "
        "Review inventory_output fields: current_stock, reorder_point, "
        "shortage_quantity, stock_below_reorder_point, and forecast_creates_shortage."
    )

    return {
        "procurement_output": _build_failed_procurement_output(
            run_id=run_id,
            product_id=product_id,
            region=region,
            message=message,
            source_files=_unique_preserve_order(inventory_source_files + ["products.csv"]),
            source_record_ids=_unique_preserve_order(inventory_source_record_ids + [product_id]),
        ),
        "supplier_id": None,
    }


def _build_procurement_output(
    run_id: str,
    product_id: str,
    region: str,
    product_name: str,
    recommended_quantity: int,
    selected_supplier: pd.Series,
    selection_strategy: str,
    inventory_source_files: List[str],
    inventory_source_record_ids: List[str],
) -> Dict[str, Any]:
    """
    Builds procurement recommendation output after supplier selection.
    """

    procurement_value = float(
        recommended_quantity * selected_supplier["unit_cost"]
    )

    source_files = _unique_preserve_order(
        ["suppliers.csv", "products.csv"] + inventory_source_files
    )

    source_record_ids = _unique_preserve_order(
        [str(selected_supplier["supplier_id"]), product_id] + inventory_source_record_ids
    )

    supplier_selection_reason = (
        f"Selected using '{selection_strategy}' strategy. "
        f"Supplier has capacity {int(selected_supplier['max_capacity'])} "
        f"for required quantity {recommended_quantity}. "
        f"Approval status: {selected_supplier['is_approved']}. "
        f"Compliance status: {selected_supplier['compliance_status']}. "
        f"Reliability score: {int(selected_supplier['reliability_score'])}. "
        f"Lead time: {int(selected_supplier['lead_time_days'])} days. "
        f"Supplier score: {round(float(selected_supplier['supplier_score']), 2)}."
    )

    message = (
        f"Procurement recommendation generated for {product_id} "
        f"({product_name}) in {region}. "
        f"Recommended quantity: {recommended_quantity}. "
        f"Supplier: {selected_supplier['supplier_name']}. "
        f"Procurement value: INR {round(procurement_value, 2)}."
    )

    output = ProcurementOutput(
        run_id=run_id,
        step_id="STEP-004",
        agent_id="procurement_agent",
        agent_name="Procurement Agent",
        status="success",
        source_files=source_files,
        source_record_ids=source_record_ids,
        message=message,
        product_id=product_id,
        region=region,
        recommended_quantity=int(recommended_quantity),
        recommended_supplier_id=str(selected_supplier["supplier_id"]),
        recommended_supplier_name=str(selected_supplier["supplier_name"]),
        supplier_region=str(selected_supplier["region"]),
        unit_cost=float(selected_supplier["unit_cost"]),
        lead_time_days=int(selected_supplier["lead_time_days"]),
        reliability_score=int(selected_supplier["reliability_score"]),
        is_approved=str(selected_supplier["is_approved"]),
        compliance_status=str(selected_supplier["compliance_status"]),
        max_capacity=int(selected_supplier["max_capacity"]),
        procurement_value=round(procurement_value, 2),
        supplier_selection_reason=supplier_selection_reason,
    )

    procurement_output = _safe_model_dump(output)

    procurement_output["action_required"] = True
    procurement_output["recommendation_generated"] = True
    procurement_output["procurement_skipped_reason"] = None

    return {
        "procurement_output": procurement_output,
        "supplier_id": str(selected_supplier["supplier_id"]),
    }


def _build_supplier_lookup_output(
    run_id: str,
    product_id: str,
    region: str,
    product_name: str,
    selected_supplier: pd.Series,
    selection_strategy: str,
) -> Dict[str, Any]:
    """
    Builds supplier lookup response when no inventory output exists.

    This is not a procurement execution recommendation because quantity and
    value are not calculated without inventory context.
    """

    message = (
        f"Supplier lookup completed for {product_id} ({product_name}). "
        "No inventory output was provided, so procurement quantity and value "
        "were not calculated."
    )

    supplier_selection_reason = (
        f"Supplier selected using '{selection_strategy}' strategy for lookup only. "
        f"Approval status: {selected_supplier['is_approved']}. "
        f"Compliance status: {selected_supplier['compliance_status']}. "
        f"Reliability score: {int(selected_supplier['reliability_score'])}. "
        f"Lead time: {int(selected_supplier['lead_time_days'])} days."
    )

    output = ProcurementOutput(
        run_id=run_id,
        step_id="STEP-004",
        agent_id="procurement_agent",
        agent_name="Procurement Agent",
        status="success",
        source_files=["suppliers.csv", "products.csv"],
        source_record_ids=[str(selected_supplier["supplier_id"]), product_id],
        message=message,
        product_id=product_id,
        region=region,
        recommended_quantity=0,
        recommended_supplier_id=str(selected_supplier["supplier_id"]),
        recommended_supplier_name=str(selected_supplier["supplier_name"]),
        supplier_region=str(selected_supplier["region"]),
        unit_cost=float(selected_supplier["unit_cost"]),
        lead_time_days=int(selected_supplier["lead_time_days"]),
        reliability_score=int(selected_supplier["reliability_score"]),
        is_approved=str(selected_supplier["is_approved"]),
        compliance_status=str(selected_supplier["compliance_status"]),
        max_capacity=int(selected_supplier["max_capacity"]),
        procurement_value=0,
        supplier_selection_reason=supplier_selection_reason,
    )

    procurement_output = _safe_model_dump(output)

    procurement_output["action_required"] = False
    procurement_output["recommendation_generated"] = False
    procurement_output["procurement_skipped_reason"] = (
        "Supplier lookup only; procurement quantity and value were not calculated."
    )

    return {
        "procurement_output": procurement_output,
        "supplier_id": str(selected_supplier["supplier_id"]),
    }


# ============================================================
# Main LangGraph node
# ============================================================

def procurement_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Procurement Agent node.

    Reads products.csv and, when needed, suppliers.csv through the Data Access
    Guard. Validates product, checks inventory output, selects supplier using
    the selected strategy, calculates procurement value, and returns output plus
    data-access governance updates.
    """

    run_id = state.get("run_id", "RUN-UNKNOWN")
    coordinator_output = _as_dict(state.get("coordinator_output"))

    product_id = state.get("product_id") or coordinator_output.get("product_id")
    region = state.get("region") or coordinator_output.get("region")

    selection_strategy = (
        state.get("selection_strategy")
        or coordinator_output.get("selection_strategy")
        or "compliance_first"
    )

    if not product_id:
        raise ValueError("product_id is required in state for Procurement Agent")

    if not region:
        raise ValueError("region is required in state for Procurement Agent")

    if selection_strategy not in VALID_SELECTION_STRATEGIES:
        raise ValueError(
            f"Invalid selection_strategy={selection_strategy}. "
            f"Valid values are: {sorted(VALID_SELECTION_STRATEGIES)}"
        )

    current_access_update: Dict[str, Any] = {}

    products_df, products_access_update = _load_products(state)
    current_access_update = products_access_update

    if products_df is None:
        message = (
            "Procurement could not proceed because products.csv access was denied "
            "or products.csv was unavailable. Review data_access_log for the exact "
            "access decision."
        )

        return {
            "procurement_output": _build_failed_procurement_output(
                run_id=run_id,
                product_id=product_id,
                region=region,
                message=message,
                source_files=[],
                source_record_ids=[],
            ),
            "supplier_id": None,
            **current_access_update,
        }

    try:
        _validate_required_columns(
            dataframe=products_df,
            required_columns=REQUIRED_PRODUCT_COLUMNS,
            file_name="products.csv",
        )

        product_name = _validate_product_exists(
            products_df=products_df,
            product_id=product_id,
        )

        inventory_context = _extract_inventory_context(state)

        inventory_available = inventory_context["inventory_available"]
        inventory_failed = inventory_context["inventory_failed"]
        procurement_required = inventory_context["procurement_required"]
        recommended_quantity = inventory_context["recommended_quantity"]

        inventory_source_files = inventory_context["inventory_source_files"]
        inventory_source_record_ids = inventory_context["inventory_source_record_ids"]

        if inventory_failed:
            message = (
                "Procurement could not proceed because Inventory Agent output failed. "
                f"Inventory failure reason: {inventory_context.get('inventory_failure_message')}"
            )

            return {
                "procurement_output": _build_failed_procurement_output(
                    run_id=run_id,
                    product_id=product_id,
                    region=region,
                    message=message,
                    source_files=_unique_preserve_order(
                        inventory_source_files + ["products.csv"]
                    ),
                    source_record_ids=_unique_preserve_order(
                        inventory_source_record_ids + [product_id]
                    ),
                ),
                "supplier_id": None,
                **current_access_update,
            }

        # --------------------------------------------------------
        # Case 1: Inventory exists and procurement is not required.
        # suppliers.csv is intentionally not accessed in this case.
        # --------------------------------------------------------
        if inventory_available and not procurement_required:
            reason = (
                "Inventory output indicates procurement_required=False. "
                "Supplier selection was not performed."
            )

            node_result = _build_no_procurement_output(
                run_id=run_id,
                product_id=product_id,
                region=region,
                product_name=product_name,
                inventory_context=inventory_context,
                reason=reason,
            )

            return {
                **node_result,
                **current_access_update,
            }

        # --------------------------------------------------------
        # If suppliers are needed, load suppliers.csv through guard.
        # Suppliers are needed for:
        # - procurement-required case
        # - supplier lookup mode without inventory output
        # --------------------------------------------------------
        intermediate_state = dict(state)
        intermediate_state.update(current_access_update)

        suppliers_df, suppliers_access_update = _load_suppliers(intermediate_state)

        current_access_update = merge_access_updates(
            state,
            current_access_update,
            suppliers_access_update,
        )

        if suppliers_df is None:
            message = (
                "Procurement could not proceed because suppliers.csv access was denied "
                "or suppliers.csv was unavailable. Review data_access_log for the exact "
                "access decision."
            )

            return {
                "procurement_output": _build_failed_procurement_output(
                    run_id=run_id,
                    product_id=product_id,
                    region=region,
                    message=message,
                    source_files=["products.csv"],
                    source_record_ids=[product_id],
                ),
                "supplier_id": None,
                **current_access_update,
            }

        _validate_required_columns(
            dataframe=suppliers_df,
            required_columns=REQUIRED_SUPPLIER_COLUMNS,
            file_name="suppliers.csv",
        )

        suppliers_df = _prepare_supplier_values(suppliers_df)

        # --------------------------------------------------------
        # Case 2: Inventory exists and procurement is required.
        # --------------------------------------------------------
        if inventory_available and procurement_required:
            if recommended_quantity <= 0:
                node_result = _build_inconsistent_inventory_output(
                    run_id=run_id,
                    product_id=product_id,
                    region=region,
                    product_name=product_name,
                    inventory_context=inventory_context,
                )

                return {
                    **node_result,
                    **current_access_update,
                }

            product_suppliers = _get_suppliers_for_product(
                suppliers_df=suppliers_df,
                product_id=product_id,
            )

            capable_suppliers = _filter_by_capacity(
                suppliers_df=product_suppliers,
                recommended_quantity=recommended_quantity,
            )

            selected_supplier = _select_supplier(
                suppliers_df=capable_suppliers,
                demand_region=region,
                recommended_quantity=recommended_quantity,
                selection_strategy=selection_strategy,
            )

            node_result = _build_procurement_output(
                run_id=run_id,
                product_id=product_id,
                region=region,
                product_name=product_name,
                recommended_quantity=recommended_quantity,
                selected_supplier=selected_supplier,
                selection_strategy=selection_strategy,
                inventory_source_files=inventory_source_files,
                inventory_source_record_ids=inventory_source_record_ids,
            )

            return {
                **node_result,
                **current_access_update,
            }

        # --------------------------------------------------------
        # Case 3: Supplier lookup mode without inventory output.
        # This is a lookup, not a procurement execution recommendation.
        # --------------------------------------------------------
        product_suppliers = _get_suppliers_for_product(
            suppliers_df=suppliers_df,
            product_id=product_id,
        )

        selected_supplier = _select_supplier(
            suppliers_df=product_suppliers,
            demand_region=region,
            recommended_quantity=0,
            selection_strategy=selection_strategy,
        )

        node_result = _build_supplier_lookup_output(
            run_id=run_id,
            product_id=product_id,
            region=region,
            product_name=product_name,
            selected_supplier=selected_supplier,
            selection_strategy=selection_strategy,
        )

        return {
            **node_result,
            **current_access_update,
        }

    except Exception as exc:
        message = (
            "Procurement failed after governed dataset access completed. "
            f"Reason: {exc}"
        )

        return {
            "procurement_output": _build_failed_procurement_output(
                run_id=run_id,
                product_id=product_id,
                region=region,
                message=message,
                source_files=["products.csv"],
                source_record_ids=[product_id],
            ),
            "supplier_id": None,
            **current_access_update,
        }


# Backward-compatible alias if workflow_graph imports a different name.
procurement_agent = procurement_node


# ============================================================
# Optional local tests
# ============================================================

if __name__ == "__main__":
    test_cases = [
        {
            "name": "Forecast-driven shortage",
            "state": {
                "run_id": "RUN-PROCUREMENT-TEST-001",
                "product_id": "P-101",
                "region": "South",
                "inventory_output": {
                    "status": "success",
                    "procurement_required": True,
                    "shortage_quantity": 215,
                    "current_stock": 80,
                    "reorder_point": 696,
                    "warehouse_id": "WH-SOUTH-01",
                    "stock_position": "Below Reorder Point",
                    "stock_below_reorder_point": True,
                    "forecast_creates_shortage": True,
                    "source_files": ["inventory.csv", "products.csv"],
                    "source_record_ids": ["INV-003"],
                },
                "selection_strategy": "compliance_first",
                "completed_steps": [],
                "errors": [],
            },
        },
        {
            "name": "Inventory-only reorder gap",
            "state": {
                "run_id": "RUN-PROCUREMENT-TEST-002",
                "product_id": "P-101",
                "region": "South",
                "inventory_output": {
                    "status": "success",
                    "procurement_required": True,
                    "shortage_quantity": 0,
                    "current_stock": 80,
                    "reorder_point": 696,
                    "warehouse_id": "WH-SOUTH-01",
                    "stock_position": "Below Reorder Point",
                    "stock_below_reorder_point": True,
                    "forecast_creates_shortage": False,
                    "source_files": ["inventory.csv", "products.csv"],
                    "source_record_ids": ["INV-003"],
                },
                "selection_strategy": "cheapest",
                "completed_steps": [],
                "errors": [],
            },
        },
        {
            "name": "No procurement required",
            "state": {
                "run_id": "RUN-PROCUREMENT-TEST-003",
                "product_id": "P-104",
                "region": "East",
                "inventory_output": {
                    "status": "success",
                    "procurement_required": False,
                    "shortage_quantity": 0,
                    "current_stock": 454,
                    "reorder_point": 284,
                    "warehouse_id": "WH-EAST-01",
                    "stock_position": "Healthy",
                    "stock_below_reorder_point": False,
                    "forecast_creates_shortage": False,
                    "source_files": ["inventory.csv", "products.csv"],
                    "source_record_ids": ["INV-013"],
                },
                "selection_strategy": "compliance_first",
                "completed_steps": [],
                "errors": [],
            },
        },
        {
            "name": "User-forbidden suppliers.csv access",
            "state": {
                "run_id": "RUN-PROCUREMENT-TEST-004",
                "product_id": "P-101",
                "region": "South",
                "inventory_output": {
                    "status": "success",
                    "procurement_required": True,
                    "shortage_quantity": 215,
                    "current_stock": 80,
                    "reorder_point": 696,
                    "stock_below_reorder_point": True,
                    "forecast_creates_shortage": True,
                    "source_files": ["inventory.csv", "products.csv"],
                    "source_record_ids": ["INV-003"],
                },
                "selection_strategy": "compliance_first",
                "forbidden_datasets": ["suppliers.csv"],
                "completed_steps": [],
                "errors": [],
            },
        },
    ]

    for case in test_cases:
        print("=" * 100)
        print("CASE:", case["name"])

        result = procurement_node(case["state"])

        print("Procurement output:")
        print(result.get("procurement_output"))
        print("supplier_id passed to downstream Logistics Agent:", result.get("supplier_id"))
        print("data_access_log:", result.get("data_access_log"))
        print("dataset_accessed:", result.get("dataset_accessed"))
        print("dataset_access_attempted:", result.get("dataset_access_attempted"))