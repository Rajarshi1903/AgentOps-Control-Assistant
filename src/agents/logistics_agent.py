import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from src.schemas.agent_outputs import LogisticsOutput
from src.services.data_access_guard import (
    read_governed_csv,
    merge_access_updates,
)


# ============================================================
# Logistics Agent
# ============================================================
# Purpose:
# Recommends the best active logistics route for a selected supplier
# and destination region, while accounting for active disruptions.
#
# Governance update:
# This agent does not read CSV files directly using pd.read_csv.
# It reads datasets through data_access_guard.read_governed_csv so that
# every file access is logged and evaluated against dataset governance rules.
#
# Important design choices:
# - If procurement says no procurement is required, logistics does not access
#   suppliers.csv, routes.csv, or disruptions.csv.
# - If procurement_output failed, logistics does not continue into route planning.
# - If procurement did not generate a real supplier recommendation, logistics
#   returns a skipped/non-action output.
# - If a required dataset is denied/unavailable, the agent returns a failed
#   logistics_output while preserving data access evidence.
#
# No hardcoding:
# - No product-specific logic.
# - No region-specific logic.
# - No query-text matching.
# - Route planning is driven only by structured state facts.
# ============================================================


DATA_DIR = Path(os.getenv("DATA_DIR", "data"))


REQUIRED_ROUTE_COLUMNS = {
    "route_id",
    "source_node",
    "source_type",
    "destination_node",
    "destination_type",
    "supplier_id",
    "origin_region",
    "destination_region",
    "warehouse_id",
    "distance_km",
    "transport_mode",
    "base_cost",
    "estimated_time_days",
    "risk_level",
    "is_active",
}

REQUIRED_DISRUPTION_COLUMNS = {
    "disruption_id",
    "route_id",
    "disruption_type",
    "severity",
    "status",
    "start_date",
    "end_date",
    "impact_delay_days",
    "impact_cost",
    "description",
}

REQUIRED_SUPPLIER_COLUMNS = {
    "supplier_id",
    "supplier_name",
    "product_id",
    "region",
}


RISK_PENALTY_MAP = {
    "Low": 0,
    "Medium": 5000,
    "High": 15000,
}

DISRUPTION_PENALTY_MAP = {
    "None": 0,
    "Low": 2000,
    "Medium": 5000,
    "High": 15000,
    "Critical": 30000,
}

SEVERITY_RANK = {
    "None": 0,
    "Low": 1,
    "Medium": 2,
    "High": 3,
    "Critical": 4,
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


def _safe_bool(value: Any, default: bool = False) -> bool:
    """
    Safely converts a value to bool.
    """

    if value is None:
        return default

    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1", "y"}

    return bool(value)


def _safe_int(value: Any, default: int = 0) -> int:
    """
    Safely converts a value to int.
    """

    if value is None:
        return default

    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return default


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


def _build_failed_logistics_output(
    run_id: str,
    supplier_id: Optional[str],
    destination_region: Optional[str],
    message: str,
    source_files: Optional[List[str]] = None,
    source_record_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Builds a safe failed logistics output.

    This is intentionally a plain dict instead of LogisticsOutput because
    failure cases may not have all fields required by the success schema.
    """

    return {
        "run_id": run_id,
        "step_id": "STEP-005",
        "agent_id": "logistics_agent",
        "agent_name": "Logistics Agent",
        "status": "failed",
        "source_files": source_files or [],
        "source_record_ids": source_record_ids or [],
        "message": message,
        "supplier_id": supplier_id,
        "destination_region": destination_region,
        "warehouse_id": "",
        "recommended_route_id": None,
        "origin_region": None,
        "destination_node": None,
        "transport_mode": None,
        "distance_km": None,
        "base_cost": 0,
        "estimated_time_days": 0,
        "route_risk_level": "None",
        "route_score": 0,
        "route_disruption_exists": False,
        "route_disruption_severity": "None",
        "route_disruption_status": "None",
        "impact_delay_days": 0,
        "impact_cost": 0,
        "adjusted_time_days": 0,
        "adjusted_route_cost": 0,
        "action_required": False,
        "route_generated": False,
        "logistics_skipped_reason": None,
    }


# ============================================================
# Governed data loading
# ============================================================

def _load_suppliers(
    state: Dict[str, Any],
) -> Tuple[Optional[pd.DataFrame], Dict[str, Any]]:
    """
    Loads suppliers.csv through the Data Access Guard.
    """

    suppliers_df, suppliers_access_update = read_governed_csv(
        state=state,
        agent_id="logistics_agent",
        file_name="suppliers.csv",
        purpose="logistics_supplier_validation",
        data_dir=DATA_DIR,
    )

    return suppliers_df, suppliers_access_update


def _load_routes(
    state: Dict[str, Any],
) -> Tuple[Optional[pd.DataFrame], Dict[str, Any]]:
    """
    Loads routes.csv through the Data Access Guard.
    """

    routes_df, routes_access_update = read_governed_csv(
        state=state,
        agent_id="logistics_agent",
        file_name="routes.csv",
        purpose="logistics_route_selection",
        data_dir=DATA_DIR,
    )

    return routes_df, routes_access_update


def _load_disruptions(
    state: Dict[str, Any],
) -> Tuple[Optional[pd.DataFrame], Dict[str, Any]]:
    """
    Loads disruptions.csv through the Data Access Guard.
    """

    disruptions_df, disruptions_access_update = read_governed_csv(
        state=state,
        agent_id="logistics_agent",
        file_name="disruptions.csv",
        purpose="logistics_disruption_check",
        data_dir=DATA_DIR,
    )

    return disruptions_df, disruptions_access_update


# ============================================================
# Dataset preparation and validation
# ============================================================

def _prepare_routes_df(routes_df: pd.DataFrame) -> pd.DataFrame:
    """
    Cleans and validates route numeric columns.
    """

    df = routes_df.copy()

    numeric_columns = [
        "distance_km",
        "base_cost",
        "estimated_time_days",
    ]

    for column in numeric_columns:
        df[column] = pd.to_numeric(df[column], errors="coerce")

        if df[column].isna().any():
            raise ValueError(
                f"Invalid numeric values found in routes.csv column: {column}"
            )

        if (df[column] < 0).any():
            raise ValueError(
                f"Negative values found in routes.csv column: {column}"
            )

    if (df["distance_km"] <= 0).any():
        raise ValueError("distance_km must be greater than 0")

    if (df["base_cost"] <= 0).any():
        raise ValueError("base_cost must be greater than 0")

    if (df["estimated_time_days"] <= 0).any():
        raise ValueError("estimated_time_days must be greater than 0")

    invalid_risk_levels = set(df["risk_level"]) - set(RISK_PENALTY_MAP.keys())

    if invalid_risk_levels:
        raise ValueError(f"Invalid route risk levels found: {invalid_risk_levels}")

    invalid_active_values = set(df["is_active"]) - {"Yes", "No"}

    if invalid_active_values:
        raise ValueError(f"Invalid is_active values found: {invalid_active_values}")

    df["supplier_id"] = df["supplier_id"].astype(str)
    df["route_id"] = df["route_id"].astype(str)
    df["destination_region"] = df["destination_region"].astype(str)

    return df


def _prepare_disruptions_df(disruptions_df: pd.DataFrame) -> pd.DataFrame:
    """
    Cleans and validates disruption numeric/date columns.
    """

    df = disruptions_df.copy()

    df["impact_delay_days"] = pd.to_numeric(
        df["impact_delay_days"],
        errors="coerce",
    )

    df["impact_cost"] = pd.to_numeric(
        df["impact_cost"],
        errors="coerce",
    )

    if df["impact_delay_days"].isna().any():
        raise ValueError("Invalid impact_delay_days values found in disruptions.csv")

    if df["impact_cost"].isna().any():
        raise ValueError("Invalid impact_cost values found in disruptions.csv")

    if (df["impact_delay_days"] < 0).any():
        raise ValueError("impact_delay_days cannot be negative")

    if (df["impact_cost"] < 0).any():
        raise ValueError("impact_cost cannot be negative")

    invalid_severity = set(df["severity"]) - set(SEVERITY_RANK.keys())

    if invalid_severity:
        raise ValueError(f"Invalid disruption severity values found: {invalid_severity}")

    invalid_status = set(df["status"]) - {"Active", "Resolved", "Planned"}

    if invalid_status:
        raise ValueError(f"Invalid disruption status values found: {invalid_status}")

    df["route_id"] = df["route_id"].astype(str)
    df["disruption_id"] = df["disruption_id"].astype(str)

    return df


def _prepare_suppliers_df(suppliers_df: pd.DataFrame) -> pd.DataFrame:
    """
    Cleans suppliers dataframe for logistics validation.
    """

    df = suppliers_df.copy()

    df["supplier_id"] = df["supplier_id"].astype(str)
    df["supplier_name"] = df["supplier_name"].astype(str)
    df["product_id"] = df["product_id"].astype(str)
    df["region"] = df["region"].astype(str)

    return df


def _validate_supplier_exists(
    suppliers_df: pd.DataFrame,
    supplier_id: str,
) -> None:
    """
    Validates supplier_id exists in suppliers.csv.
    """

    supplier_row = suppliers_df[suppliers_df["supplier_id"] == supplier_id]

    if supplier_row.empty:
        raise ValueError(f"Supplier ID {supplier_id} not found in suppliers.csv")


# ============================================================
# Procurement context
# ============================================================

def _extract_procurement_context(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extracts procurement context from state.

    Route planning is required only when procurement produced a substantive
    supplier recommendation.
    """

    procurement_output = _as_dict(state.get("procurement_output"))

    if not procurement_output:
        return {
            "procurement_available": False,
            "procurement_failed": False,
            "route_planning_required": False,
            "supplier_id_from_procurement": None,
            "recommended_quantity": 0,
            "procurement_failure_message": None,
            "procurement_source_files": [],
            "procurement_source_record_ids": [],
            "skip_reason": "No procurement_output found in state.",
        }

    procurement_status = str(procurement_output.get("status", "")).lower()

    if procurement_status == "failed":
        return {
            "procurement_available": True,
            "procurement_failed": True,
            "route_planning_required": False,
            "supplier_id_from_procurement": None,
            "recommended_quantity": 0,
            "procurement_failure_message": procurement_output.get("message"),
            "procurement_source_files": _as_list(procurement_output.get("source_files", [])),
            "procurement_source_record_ids": _as_list(procurement_output.get("source_record_ids", [])),
            "skip_reason": None,
        }

    recommended_supplier_id = procurement_output.get("recommended_supplier_id")
    recommended_quantity = _safe_int(
        procurement_output.get("recommended_quantity", 0),
        default=0,
    )

    recommendation_generated = _safe_bool(
        procurement_output.get("recommendation_generated", False),
        default=False,
    )

    action_required = _safe_bool(
        procurement_output.get("action_required", False),
        default=False,
    )

    # Backward-compatible substantive check:
    # If older procurement output does not include action_required or
    # recommendation_generated but has a supplier and positive quantity,
    # route planning is still considered required.
    has_substantive_supplier_recommendation = (
        recommended_supplier_id is not None
        and str(recommended_supplier_id).strip() != ""
        and recommended_quantity > 0
    )

    route_planning_required = (
        (recommendation_generated and action_required)
        or has_substantive_supplier_recommendation
    )

    skip_reason = procurement_output.get("procurement_skipped_reason")

    if not route_planning_required and not skip_reason:
        skip_reason = (
            "Procurement did not generate a supplier recommendation requiring route planning."
        )

    return {
        "procurement_available": True,
        "procurement_failed": False,
        "route_planning_required": bool(route_planning_required),
        "supplier_id_from_procurement": (
            str(recommended_supplier_id)
            if recommended_supplier_id is not None
            else None
        ),
        "recommended_quantity": recommended_quantity,
        "procurement_failure_message": None,
        "procurement_source_files": _as_list(procurement_output.get("source_files", [])),
        "procurement_source_record_ids": _as_list(procurement_output.get("source_record_ids", [])),
        "skip_reason": skip_reason,
    }


# ============================================================
# Output builders
# ============================================================

def _build_no_route_needed_output(
    run_id: str,
    destination_region: str,
    procurement_context: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Builds no-route-needed logistics response.

    Plain dict is used instead of LogisticsOutput so that status can be
    represented as skipped without risking schema incompatibility.
    """

    reason = (
        procurement_context.get("skip_reason")
        or "Logistics planning skipped because no procurement route was required."
    )

    source_files = _unique_preserve_order(
        procurement_context.get("procurement_source_files", [])
    )

    source_record_ids = _unique_preserve_order(
        procurement_context.get("procurement_source_record_ids", [])
    )

    return {
        "logistics_output": {
            "run_id": run_id,
            "step_id": "STEP-005",
            "agent_id": "logistics_agent",
            "agent_name": "Logistics Agent",
            "status": "skipped",
            "source_files": source_files,
            "source_record_ids": source_record_ids,
            "message": reason,
            "supplier_id": None,
            "destination_region": destination_region,
            "warehouse_id": "",
            "recommended_route_id": None,
            "origin_region": None,
            "destination_node": None,
            "transport_mode": None,
            "distance_km": None,
            "base_cost": 0,
            "estimated_time_days": 0,
            "route_risk_level": "None",
            "route_score": 0,
            "route_disruption_exists": False,
            "route_disruption_severity": "None",
            "route_disruption_status": "None",
            "impact_delay_days": 0,
            "impact_cost": 0,
            "adjusted_time_days": 0,
            "adjusted_route_cost": 0,
            "action_required": False,
            "route_generated": False,
            "logistics_skipped_reason": reason,
        }
    }


# ============================================================
# Route logic
# ============================================================

def _filter_active_routes(
    routes_df: pd.DataFrame,
    supplier_id: str,
    destination_region: str,
) -> pd.DataFrame:
    """
    Filters routes by supplier, destination region, and active status.
    """

    supplier_routes = routes_df[
        (routes_df["supplier_id"] == supplier_id)
        & (routes_df["destination_region"] == destination_region)
    ].copy()

    if supplier_routes.empty:
        raise ValueError(
            f"No routes found for supplier_id={supplier_id}, "
            f"destination_region={destination_region}"
        )

    active_routes = supplier_routes[supplier_routes["is_active"] == "Yes"].copy()

    if active_routes.empty:
        raise ValueError(
            f"No active routes found for supplier_id={supplier_id}, "
            f"destination_region={destination_region}"
        )

    return active_routes


def _get_active_disruption_summary(
    disruptions_df: pd.DataFrame,
    route_id: str,
) -> Dict[str, Any]:
    """
    Gets active disruption summary for a route.

    If multiple active disruptions exist:
    - delay is summed
    - cost is summed
    - highest severity is used
    """

    active_disruptions = disruptions_df[
        (disruptions_df["route_id"] == route_id)
        & (disruptions_df["status"] == "Active")
    ].copy()

    if active_disruptions.empty:
        return {
            "route_disruption_exists": False,
            "route_disruption_severity": "None",
            "route_disruption_status": "None",
            "impact_delay_days": 0,
            "impact_cost": 0,
            "active_disruption_ids": [],
        }

    impact_delay_days = int(active_disruptions["impact_delay_days"].sum())
    impact_cost = float(active_disruptions["impact_cost"].sum())

    highest_severity = max(
        active_disruptions["severity"],
        key=lambda severity: SEVERITY_RANK[severity],
    )

    active_disruption_ids = active_disruptions["disruption_id"].astype(str).tolist()

    return {
        "route_disruption_exists": True,
        "route_disruption_severity": highest_severity,
        "route_disruption_status": "Active",
        "impact_delay_days": impact_delay_days,
        "impact_cost": impact_cost,
        "active_disruption_ids": active_disruption_ids,
    }


def _score_routes(
    active_routes: pd.DataFrame,
    disruptions_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Adds disruption-adjusted fields and route_score to active routes.
    """

    scored_routes = []

    for _, route in active_routes.iterrows():
        route_id = str(route["route_id"])

        disruption_summary = _get_active_disruption_summary(
            disruptions_df=disruptions_df,
            route_id=route_id,
        )

        baseline_risk_penalty = RISK_PENALTY_MAP[str(route["risk_level"])]
        disruption_severity = disruption_summary["route_disruption_severity"]
        disruption_penalty = DISRUPTION_PENALTY_MAP[disruption_severity]

        adjusted_time_days = int(route["estimated_time_days"]) + int(
            disruption_summary["impact_delay_days"]
        )

        adjusted_route_cost = float(route["base_cost"]) + float(
            disruption_summary["impact_cost"]
        )

        time_penalty = adjusted_time_days * 1000

        route_score = (
            adjusted_route_cost
            + time_penalty
            + baseline_risk_penalty
            + disruption_penalty
        )

        route_dict = route.to_dict()
        route_dict.update(disruption_summary)
        route_dict["adjusted_time_days"] = adjusted_time_days
        route_dict["adjusted_route_cost"] = adjusted_route_cost
        route_dict["route_score"] = float(route_score)

        scored_routes.append(route_dict)

    return pd.DataFrame(scored_routes)


def _select_best_route(scored_routes: pd.DataFrame) -> pd.Series:
    """
    Selects lowest score route.
    Ties are resolved by lower adjusted cost, lower adjusted time, and lower distance.
    """

    selected_routes = scored_routes.sort_values(
        by=[
            "route_score",
            "adjusted_route_cost",
            "adjusted_time_days",
            "distance_km",
        ],
        ascending=[True, True, True, True],
    )

    return selected_routes.iloc[0]


# ============================================================
# Main LangGraph node
# ============================================================

def logistics_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Logistics Agent node.

    Selects best active route for supplier + destination region and accounts
    for active disruptions. All dataset reads go through the Data Access Guard.
    """

    run_id = state.get("run_id", "RUN-UNKNOWN")
    destination_region = state.get("region")

    if not destination_region:
        raise ValueError("region is required in state for Logistics Agent")

    procurement_context = _extract_procurement_context(state)

    if procurement_context["procurement_failed"]:
        message = (
            "Logistics planning could not proceed because Procurement Agent output failed. "
            f"Procurement failure reason: {procurement_context.get('procurement_failure_message')}"
        )

        return {
            "logistics_output": _build_failed_logistics_output(
                run_id=run_id,
                supplier_id=None,
                destination_region=destination_region,
                message=message,
                source_files=procurement_context.get("procurement_source_files", []),
                source_record_ids=procurement_context.get("procurement_source_record_ids", []),
            )
        }

    if procurement_context["procurement_available"] and not procurement_context["route_planning_required"]:
        return _build_no_route_needed_output(
            run_id=run_id,
            destination_region=destination_region,
            procurement_context=procurement_context,
        )

    supplier_id = (
        procurement_context["supplier_id_from_procurement"]
        or state.get("supplier_id")
    )

    if not supplier_id:
        raise ValueError(
            "supplier_id is required for Logistics Agent unless procurement output "
            "indicates that route planning is not required"
        )

    supplier_id = str(supplier_id)

    # --------------------------------------------------------
    # Governed dataset loading.
    # Supplier validation is done first. If suppliers.csv is denied,
    # route/disruption files are not unnecessarily accessed.
    # --------------------------------------------------------
    suppliers_df, suppliers_access_update = _load_suppliers(state)

    if suppliers_df is None:
        message = (
            "Logistics planning could not proceed because suppliers.csv access was "
            "denied or suppliers.csv was unavailable. Review data_access_log for "
            "the exact access decision."
        )

        return {
            "logistics_output": _build_failed_logistics_output(
                run_id=run_id,
                supplier_id=supplier_id,
                destination_region=destination_region,
                message=message,
                source_files=[],
                source_record_ids=[],
            ),
            **suppliers_access_update,
        }

    intermediate_state = dict(state)
    intermediate_state.update(suppliers_access_update)

    routes_df, routes_access_update = _load_routes(intermediate_state)

    route_state = dict(intermediate_state)
    route_state.update(routes_access_update)

    access_update_after_routes = merge_access_updates(
        state,
        suppliers_access_update,
        routes_access_update,
    )

    if routes_df is None:
        message = (
            "Logistics planning could not proceed because routes.csv access was "
            "denied or routes.csv was unavailable. Review data_access_log for "
            "the exact access decision."
        )

        return {
            "logistics_output": _build_failed_logistics_output(
                run_id=run_id,
                supplier_id=supplier_id,
                destination_region=destination_region,
                message=message,
                source_files=["suppliers.csv"],
                source_record_ids=[supplier_id],
            ),
            **access_update_after_routes,
        }

    disruptions_df, disruptions_access_update = _load_disruptions(route_state)

    access_update = merge_access_updates(
        state,
        suppliers_access_update,
        routes_access_update,
        disruptions_access_update,
    )

    if disruptions_df is None:
        message = (
            "Logistics planning could not proceed because disruptions.csv access was "
            "denied or disruptions.csv was unavailable. Review data_access_log for "
            "the exact access decision."
        )

        return {
            "logistics_output": _build_failed_logistics_output(
                run_id=run_id,
                supplier_id=supplier_id,
                destination_region=destination_region,
                message=message,
                source_files=["suppliers.csv", "routes.csv"],
                source_record_ids=[supplier_id],
            ),
            **access_update,
        }

    try:
        _validate_required_columns(
            dataframe=suppliers_df,
            required_columns=REQUIRED_SUPPLIER_COLUMNS,
            file_name="suppliers.csv",
        )

        _validate_required_columns(
            dataframe=routes_df,
            required_columns=REQUIRED_ROUTE_COLUMNS,
            file_name="routes.csv",
        )

        _validate_required_columns(
            dataframe=disruptions_df,
            required_columns=REQUIRED_DISRUPTION_COLUMNS,
            file_name="disruptions.csv",
        )

        suppliers_df = _prepare_suppliers_df(suppliers_df)
        routes_df = _prepare_routes_df(routes_df)
        disruptions_df = _prepare_disruptions_df(disruptions_df)

        _validate_supplier_exists(
            suppliers_df=suppliers_df,
            supplier_id=supplier_id,
        )

        active_routes = _filter_active_routes(
            routes_df=routes_df,
            supplier_id=supplier_id,
            destination_region=destination_region,
        )

        scored_routes = _score_routes(
            active_routes=active_routes,
            disruptions_df=disruptions_df,
        )

        selected_route = _select_best_route(scored_routes)

        active_disruption_ids = selected_route.get("active_disruption_ids", [])

        source_record_ids: List[str] = [
            supplier_id,
            str(selected_route["route_id"]),
        ]

        if isinstance(active_disruption_ids, list):
            source_record_ids.extend([str(item) for item in active_disruption_ids])

        source_files = [
            "suppliers.csv",
            "routes.csv",
            "disruptions.csv",
        ]

        message = (
            f"Selected route {selected_route['route_id']} for supplier {supplier_id} "
            f"to {destination_region}. "
            f"Route score: {round(float(selected_route['route_score']), 2)}. "
            f"Base cost: INR {round(float(selected_route['base_cost']), 2)}, "
            f"adjusted cost: INR {round(float(selected_route['adjusted_route_cost']), 2)}, "
            f"estimated time: {int(selected_route['estimated_time_days'])} days, "
            f"adjusted time: {int(selected_route['adjusted_time_days'])} days. "
            f"Active disruption: {selected_route['route_disruption_exists']}."
        )

        output = LogisticsOutput(
            run_id=run_id,
            step_id="STEP-005",
            agent_id="logistics_agent",
            agent_name="Logistics Agent",
            status="success",
            source_files=source_files,
            source_record_ids=source_record_ids,
            message=message,
            supplier_id=supplier_id,
            destination_region=str(selected_route["destination_region"]),
            warehouse_id=str(selected_route["warehouse_id"]),
            recommended_route_id=str(selected_route["route_id"]),
            origin_region=str(selected_route["origin_region"]),
            destination_node=str(selected_route["destination_node"]),
            transport_mode=str(selected_route["transport_mode"]),
            distance_km=int(selected_route["distance_km"]),
            base_cost=float(selected_route["base_cost"]),
            estimated_time_days=int(selected_route["estimated_time_days"]),
            route_risk_level=str(selected_route["risk_level"]),
            route_score=round(float(selected_route["route_score"]), 2),
            route_disruption_exists=bool(selected_route["route_disruption_exists"]),
            route_disruption_severity=str(selected_route["route_disruption_severity"]),
            route_disruption_status=str(selected_route["route_disruption_status"]),
            impact_delay_days=int(selected_route["impact_delay_days"]),
            impact_cost=float(selected_route["impact_cost"]),
            adjusted_time_days=int(selected_route["adjusted_time_days"]),
            adjusted_route_cost=round(float(selected_route["adjusted_route_cost"]), 2),
        )

        logistics_output = _safe_model_dump(output)

        logistics_output["action_required"] = True
        logistics_output["route_generated"] = True
        logistics_output["logistics_skipped_reason"] = None

        return {
            "logistics_output": logistics_output,
            **access_update,
        }

    except Exception as exc:
        message = (
            "Logistics planning failed after governed dataset access completed. "
            f"Reason: {exc}"
        )

        return {
            "logistics_output": _build_failed_logistics_output(
                run_id=run_id,
                supplier_id=supplier_id,
                destination_region=destination_region,
                message=message,
                source_files=["suppliers.csv", "routes.csv", "disruptions.csv"],
                source_record_ids=[supplier_id],
            ),
            **access_update,
        }


# Backward-compatible alias if workflow_graph imports a different name.
logistics_agent = logistics_node


# ============================================================
# Optional local tests
# ============================================================

if __name__ == "__main__":
    test_cases = [
        {
            "name": "Direct route risk with supplier_id",
            "state": {
                "run_id": "RUN-LOGISTICS-TEST-001",
                "supplier_id": "S-012",
                "region": "South",
                "completed_steps": [],
                "errors": [],
            },
        },
        {
            "name": "No procurement required",
            "state": {
                "run_id": "RUN-LOGISTICS-TEST-002",
                "region": "East",
                "procurement_output": {
                    "status": "skipped",
                    "recommended_supplier_id": None,
                    "recommended_quantity": 0,
                    "message": "Procurement not required.",
                    "action_required": False,
                    "recommendation_generated": False,
                    "procurement_skipped_reason": "Inventory output indicates procurement_required=False.",
                    "source_files": ["inventory.csv", "products.csv"],
                    "source_record_ids": ["INV-013", "P-104"],
                },
                "completed_steps": [],
                "errors": [],
            },
        },
        {
            "name": "User-forbidden routes.csv access",
            "state": {
                "run_id": "RUN-LOGISTICS-TEST-003",
                "supplier_id": "S-012",
                "region": "South",
                "forbidden_datasets": ["routes.csv"],
                "completed_steps": [],
                "errors": [],
            },
        },
    ]

    for case in test_cases:
        print("=" * 100)
        print("CASE:", case["name"])

        result = logistics_node(case["state"])

        print("Logistics output:")
        print(result.get("logistics_output"))

        print("Data access log:")
        print(result.get("data_access_log"))

        print("Dataset accessed:")
        print(result.get("dataset_accessed"))

        print("Dataset access attempted:")
        print(result.get("dataset_access_attempted"))