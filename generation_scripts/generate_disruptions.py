from pathlib import Path
from datetime import datetime
import pandas as pd

# ============================================================
# Generate disruptions.csv
# ============================================================
# Required input file:
# data/routes.csv
#
# Output:
# data/disruptions.csv
#
# Purpose:
# Adds temporary/current logistics disruptions on top of routes.csv
# ============================================================

# -----------------------------
# File paths
# -----------------------------
DATA_DIR = Path("data")
DATA_DIR.mkdir(parents=True, exist_ok=True)

ROUTES_FILE = DATA_DIR / "routes.csv"
OUTPUT_FILE = DATA_DIR / "disruptions.csv"

if not ROUTES_FILE.exists():
    raise FileNotFoundError(f"Could not find {ROUTES_FILE}")

# -----------------------------
# Load routes
# -----------------------------
routes_df = pd.read_csv(ROUTES_FILE)

# -----------------------------
# Required columns validation
# -----------------------------
required_route_columns = {
    "route_id",
    "supplier_id",
    "origin_region",
    "destination_region",
    "transport_mode",
    "risk_level",
    "is_active"
}

missing_route_columns = required_route_columns - set(routes_df.columns)

if missing_route_columns:
    raise ValueError(f"routes.csv is missing required columns: {missing_route_columns}")

# -----------------------------
# Constants
# -----------------------------
valid_severity = {"Low", "Medium", "High", "Critical"}
valid_status = {"Active", "Resolved", "Planned"}

# Keep disruption dates aligned with your current synthetic dataset timeline
PLANNING_DATE = datetime.strptime("2026-05-26", "%Y-%m-%d")

# -----------------------------
# Helper functions
# -----------------------------
def route_exists(route_id):
    return route_id in set(routes_df["route_id"])


def get_route(route_id):
    route = routes_df[routes_df["route_id"] == route_id]

    if route.empty:
        raise ValueError(f"Route {route_id} does not exist in routes.csv")

    return route.iloc[0]


def validate_route_mode(route_id, allowed_modes):
    route = get_route(route_id)
    mode = route["transport_mode"]

    if mode not in allowed_modes:
        raise ValueError(
            f"Disruption assigned to {route_id} is not mode-compatible. "
            f"Route mode is {mode}, allowed modes are {allowed_modes}"
        )


def make_disruption(
    disruption_id,
    route_id,
    disruption_type,
    severity,
    status,
    start_date,
    end_date,
    impact_delay_days,
    impact_cost,
    description
):
    return {
        "disruption_id": disruption_id,
        "route_id": route_id,
        "disruption_type": disruption_type,
        "severity": severity,
        "status": status,
        "start_date": start_date,
        "end_date": end_date,
        "impact_delay_days": impact_delay_days,
        "impact_cost": impact_cost,
        "description": description
    }


# ============================================================
# Curated disruption records
# ============================================================
# Exactly 15 disruptions.
#
# Design logic:
# 1. R-027 gets Active High disruption for P-105 + South demo.
# 2. Nearby West-South road routes receive similar weather-related disruptions.
# 3. Rail routes get rail-specific disruptions.
# 4. Air routes get air-specific disruptions.
# 5. Resolved disruptions provide historical context.
# 6. Planned disruptions provide future risk visibility.
# ============================================================

disruptions = [
    # --------------------------------------------------------
    # ACTIVE DISRUPTIONS - South/West corridor weather cluster
    # Similar nearby road routes affected by similar natural disruption.
    # --------------------------------------------------------
    make_disruption(
        "D-001",
        "R-027",
        "Weather",
        "High",
        "Active",
        "2026-05-25",
        "2026-05-30",
        2,
        8000,
        "Heavy rainfall on the West-South highway corridor causing slow movement and diversion risk."
    ),

    make_disruption(
        "D-002",
        "R-012",
        "Weather",
        "High",
        "Active",
        "2026-05-25",
        "2026-05-29",
        3,
        10000,
        "Heavy rainfall and localized flooding affecting the West-South road corridor."
    ),

    make_disruption(
        "D-003",
        "R-042",
        "Weather",
        "High",
        "Active",
        "2026-05-25",
        "2026-05-30",
        2,
        9000,
        "Continuous rainfall causing congestion on the West-South road route."
    ),

    # --------------------------------------------------------
    # ACTIVE DISRUPTIONS - Rail corridor issues
    # Rail routes get rail-specific disruption types.
    # --------------------------------------------------------
    make_disruption(
        "D-004",
        "R-017",
        "Rail Delay",
        "Medium",
        "Active",
        "2026-05-24",
        "2026-05-28",
        1,
        4500,
        "Rail congestion on the North-South corridor causing moderate shipment delay."
    ),

    make_disruption(
        "D-005",
        "R-054",
        "Infrastructure Maintenance",
        "Medium",
        "Active",
        "2026-05-26",
        "2026-05-31",
        2,
        6000,
        "Scheduled track maintenance on the North-East rail corridor causing slower transit."
    ),

    # --------------------------------------------------------
    # ACTIVE DISRUPTIONS - Road / artificial operational issue
    # Manmade disruptions can differ even if routes are nearby.
    # --------------------------------------------------------
    make_disruption(
        "D-006",
        "R-020",
        "Road Closure",
        "Medium",
        "Active",
        "2026-05-26",
        "2026-05-29",
        1,
        5000,
        "Temporary road closure on the East-South route requiring partial diversion."
    ),

    make_disruption(
        "D-007",
        "R-048",
        "Capacity Constraint",
        "High",
        "Active",
        "2026-05-25",
        "2026-05-29",
        2,
        12000,
        "Limited air cargo capacity on the North-South lane due to high shipment backlog."
    ),

    # --------------------------------------------------------
    # RESOLVED DISRUPTIONS - Historical issues, no current escalation
    # --------------------------------------------------------
    make_disruption(
        "D-008",
        "R-002",
        "Rail Delay",
        "Medium",
        "Resolved",
        "2026-05-18",
        "2026-05-22",
        0,
        0,
        "Previous rail delay on the South-West route has been resolved."
    ),

    make_disruption(
        "D-009",
        "R-033",
        "Capacity Constraint",
        "Low",
        "Resolved",
        "2026-05-20",
        "2026-05-21",
        0,
        0,
        "Temporary air cargo capacity constraint in the East region has been resolved."
    ),

    make_disruption(
        "D-010",
        "R-039",
        "Capacity Constraint",
        "Low",
        "Resolved",
        "2026-05-19",
        "2026-05-21",
        0,
        0,
        "Short-duration air freight capacity constraint in the West region has been resolved."
    ),

    make_disruption(
        "D-011",
        "R-026",
        "Rail Delay",
        "Medium",
        "Resolved",
        "2026-05-16",
        "2026-05-20",
        0,
        0,
        "Earlier rail congestion on the South-East corridor is no longer active."
    ),

    make_disruption(
        "D-012",
        "R-005",
        "Rail Delay",
        "Medium",
        "Resolved",
        "2026-05-17",
        "2026-05-23",
        0,
        0,
        "Previous rail congestion on the South-North corridor has been cleared."
    ),

    # --------------------------------------------------------
    # PLANNED DISRUPTIONS - Future visibility
    # --------------------------------------------------------
    make_disruption(
        "D-013",
        "R-036",
        "Infrastructure Maintenance",
        "Medium",
        "Planned",
        "2026-05-30",
        "2026-06-02",
        2,
        6500,
        "Planned rail infrastructure maintenance on the East-North route may increase delivery time."
    ),

    make_disruption(
        "D-014",
        "R-040",
        "Road Closure",
        "Medium",
        "Planned",
        "2026-05-31",
        "2026-06-03",
        2,
        7000,
        "Planned roadwork on the West-North route may require alternate routing."
    ),

    make_disruption(
        "D-015",
        "R-015",
        "Air Traffic Delay",
        "High",
        "Planned",
        "2026-05-30",
        "2026-06-01",
        1,
        15000,
        "Expected air traffic congestion on the West-East lane may increase cargo handling cost."
    )
]

disruptions_df = pd.DataFrame(disruptions)

# -----------------------------
# Mode compatibility validation
# -----------------------------
road_types = {"Weather", "Road Closure", "Accident", "Fuel Shortage"}
rail_types = {"Rail Delay", "Strike", "Infrastructure Maintenance"}
air_types = {"Weather", "Capacity Constraint", "Air Traffic Delay"}

for _, row in disruptions_df.iterrows():
    route = get_route(row["route_id"])
    mode = route["transport_mode"]
    disruption_type = row["disruption_type"]

    if mode == "Road":
        allowed = road_types
    elif mode == "Rail":
        allowed = rail_types
    elif mode == "Air":
        allowed = air_types
    else:
        raise ValueError(f"Invalid transport mode found in routes.csv for route {row['route_id']}: {mode}")

    if disruption_type not in allowed:
        raise ValueError(
            f"Mode mismatch for disruption {row['disruption_id']} on route {row['route_id']}. "
            f"Route mode is {mode}, but disruption type is {disruption_type}."
        )

# -----------------------------
# Validation checks
# -----------------------------
if len(disruptions_df) != 15:
    raise ValueError(f"Expected exactly 15 disruption records, got {len(disruptions_df)}")

if disruptions_df["disruption_id"].duplicated().any():
    raise ValueError("Duplicate disruption_id found.")

invalid_routes = set(disruptions_df["route_id"]) - set(routes_df["route_id"])

if invalid_routes:
    raise ValueError(f"Invalid route_id values found in disruptions.csv: {invalid_routes}")

invalid_severity = set(disruptions_df["severity"]) - valid_severity

if invalid_severity:
    raise ValueError(f"Invalid severity values found: {invalid_severity}")

invalid_status = set(disruptions_df["status"]) - valid_status

if invalid_status:
    raise ValueError(f"Invalid status values found: {invalid_status}")

# Date validation
disruptions_df["start_date_dt"] = pd.to_datetime(disruptions_df["start_date"], errors="coerce")
disruptions_df["end_date_dt"] = pd.to_datetime(disruptions_df["end_date"], errors="coerce")

if disruptions_df["start_date_dt"].isna().any():
    raise ValueError("Invalid start_date found.")

if disruptions_df["end_date_dt"].isna().any():
    raise ValueError("Invalid end_date found.")

if (disruptions_df["start_date_dt"] > disruptions_df["end_date_dt"]).any():
    raise ValueError("Some disruptions have start_date greater than end_date.")

if (disruptions_df["impact_delay_days"] < 0).any():
    raise ValueError("impact_delay_days cannot be negative.")

if (disruptions_df["impact_cost"] < 0).any():
    raise ValueError("impact_cost cannot be negative.")

# Active disruptions should have positive impact
active_disruptions = disruptions_df[disruptions_df["status"] == "Active"]

if (active_disruptions["impact_delay_days"] <= 0).any():
    raise ValueError("All Active disruptions must have impact_delay_days > 0.")

if (active_disruptions["impact_cost"] <= 0).any():
    raise ValueError("All Active disruptions must have impact_cost > 0.")

# Planned disruptions should also have positive impact
planned_disruptions = disruptions_df[disruptions_df["status"] == "Planned"]

if (planned_disruptions["impact_delay_days"] <= 0).any():
    raise ValueError("All Planned disruptions must have impact_delay_days > 0.")

if (planned_disruptions["impact_cost"] <= 0).any():
    raise ValueError("All Planned disruptions must have impact_cost > 0.")

# Ensure R-027 has Active High disruption
r027_check = disruptions_df[
    (disruptions_df["route_id"] == "R-027") &
    (disruptions_df["status"] == "Active") &
    (disruptions_df["severity"].isin(["High", "Critical"]))
]

if r027_check.empty:
    raise ValueError("R-027 must have an Active High/Critical disruption for the route-risk scenario.")

# Ensure at least one Active High/Critical disruption exists
active_high_critical = disruptions_df[
    (disruptions_df["status"] == "Active") &
    (disruptions_df["severity"].isin(["High", "Critical"]))
]

if active_high_critical.empty:
    raise ValueError("At least one Active High/Critical disruption is required.")

# Ensure not every route has disruption
if disruptions_df["route_id"].nunique() >= routes_df["route_id"].nunique():
    raise ValueError("Too many disrupted routes. disruptions.csv should not cover every route.")

# Drop internal datetime columns before saving
disruptions_df = disruptions_df.drop(columns=["start_date_dt", "end_date_dt"])

# -----------------------------
# Save disruptions.csv
# -----------------------------
disruptions_df.to_csv(OUTPUT_FILE, index=False)

# -----------------------------
# Print summary
# -----------------------------
print("disruptions.csv generated successfully.")
print(f"Saved to: {OUTPUT_FILE}")
print(f"Total rows generated: {len(disruptions_df)}")
print(f"Total columns generated: {len(disruptions_df.columns)}")
print()

print("Status distribution:")
print(disruptions_df["status"].value_counts())
print()

print("Severity distribution:")
print(disruptions_df["severity"].value_counts())
print()

print("Disruption type distribution:")
print(disruptions_df["disruption_type"].value_counts())
print()

print("Active High/Critical disruptions:")
print(
    disruptions_df[
        (disruptions_df["status"] == "Active") &
        (disruptions_df["severity"].isin(["High", "Critical"]))
    ][[
        "disruption_id",
        "route_id",
        "disruption_type",
        "severity",
        "status",
        "impact_delay_days",
        "impact_cost",
        "description"
    ]]
)
print()

print("Preview:")
print(disruptions_df)