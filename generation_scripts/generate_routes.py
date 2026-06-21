from pathlib import Path
import pandas as pd
import numpy as np

# ============================================================
# Generate routes.csv
# ============================================================
# Required input files:
# data/suppliers.csv
# data/inventory.csv
#
# Output:
# data/routes.csv
#
# Route model:
# Supplier node -> Warehouse node
#
# Graph-compatible direct logistics lane structure.
# ============================================================

np.random.seed(42)

# -----------------------------
# File paths
# -----------------------------
DATA_DIR = Path("data")
DATA_DIR.mkdir(parents=True, exist_ok=True)

SUPPLIERS_FILE = DATA_DIR / "suppliers.csv"
INVENTORY_FILE = DATA_DIR / "inventory.csv"
OUTPUT_FILE = DATA_DIR / "routes.csv"

if not SUPPLIERS_FILE.exists():
    raise FileNotFoundError(f"Could not find {SUPPLIERS_FILE}")

if not INVENTORY_FILE.exists():
    raise FileNotFoundError(f"Could not find {INVENTORY_FILE}")

# -----------------------------
# Constants
# -----------------------------
regions = ["North", "South", "East", "West"]

warehouse_map = {
    "North": "WH-NORTH-01",
    "South": "WH-SOUTH-01",
    "East": "WH-EAST-01",
    "West": "WH-WEST-01"
}

valid_transport_modes = ["Road", "Rail", "Air"]
valid_risk_levels = ["Low", "Medium", "High"]

# Important scenario suppliers get 3 routes instead of 2
important_scenario_suppliers = {
    "S-001",  # P-101 main approved supplier, South
    "S-004",  # P-102 normal West case
    "S-005",  # P-102 normal West case
    "S-007",  # P-103 approved North supplier
    "S-012",  # P-105 route disruption scenario
    "S-013"   # P-105 alternate approved supplier
}

# Required scenario destination mapping
scenario_destination_map = {
    "S-001": "South",  # P-101 + South
    "S-004": "West",   # P-102 + West
    "S-005": "West",   # P-102 + West
    "S-007": "North",  # P-103 + North
    "S-012": "South",  # P-105 + South route risk case
    "S-013": "South"   # P-105 + South alternate
}

# Synthetic but realistic region-to-region distance ranges in km
distance_matrix = {
    ("North", "North"): (80, 300),
    ("South", "South"): (80, 320),
    ("East", "East"): (80, 280),
    ("West", "West"): (80, 300),

    ("North", "South"): (1400, 1900),
    ("South", "North"): (1400, 1900),

    ("North", "East"): (700, 1200),
    ("East", "North"): (700, 1200),

    ("North", "West"): (800, 1300),
    ("West", "North"): (800, 1300),

    ("South", "East"): (900, 1500),
    ("East", "South"): (900, 1500),

    ("South", "West"): (600, 1100),
    ("West", "South"): (600, 1100),

    ("East", "West"): (1300, 1800),
    ("West", "East"): (1300, 1800)
}

# -----------------------------
# Load input datasets
# -----------------------------
suppliers_df = pd.read_csv(SUPPLIERS_FILE)
inventory_df = pd.read_csv(INVENTORY_FILE)

# -----------------------------
# Validate required columns
# -----------------------------
required_supplier_columns = {
    "supplier_id",
    "supplier_name",
    "product_id",
    "region"
}

required_inventory_columns = {
    "warehouse_id",
    "region"
}

missing_supplier_columns = required_supplier_columns - set(suppliers_df.columns)
missing_inventory_columns = required_inventory_columns - set(inventory_df.columns)

if missing_supplier_columns:
    raise ValueError(f"suppliers.csv is missing required columns: {missing_supplier_columns}")

if missing_inventory_columns:
    raise ValueError(f"inventory.csv is missing required columns: {missing_inventory_columns}")

# -----------------------------
# Validate regions
# -----------------------------
invalid_supplier_regions = set(suppliers_df["region"]) - set(regions)

if invalid_supplier_regions:
    raise ValueError(f"Invalid supplier regions found: {invalid_supplier_regions}")

invalid_inventory_regions = set(inventory_df["region"]) - set(regions)

if invalid_inventory_regions:
    raise ValueError(f"Invalid inventory regions found: {invalid_inventory_regions}")

# -----------------------------
# Build warehouse map from inventory.csv
# -----------------------------
inventory_warehouse_map = (
    inventory_df[["region", "warehouse_id"]]
    .drop_duplicates()
    .set_index("region")["warehouse_id"]
    .to_dict()
)

for region in regions:
    expected_warehouse = warehouse_map[region]

    if region not in inventory_warehouse_map:
        raise ValueError(f"No warehouse found for region: {region}")

    if inventory_warehouse_map[region] != expected_warehouse:
        raise ValueError(
            f"Warehouse mismatch for {region}. "
            f"Expected {expected_warehouse}, found {inventory_warehouse_map[region]}"
        )

# -----------------------------
# Helper functions
# -----------------------------
def get_distance(origin_region, destination_region):
    """
    Returns realistic synthetic distance based on origin-destination region pair.
    """
    low, high = distance_matrix[(origin_region, destination_region)]
    return int(np.random.randint(low, high + 1))


def choose_transport_mode(distance_km):
    """
    Chooses transport mode probabilities based on distance.
    """
    if distance_km <= 350:
        return np.random.choice(["Road", "Rail", "Air"], p=[0.75, 0.20, 0.05])
    elif distance_km <= 900:
        return np.random.choice(["Road", "Rail", "Air"], p=[0.55, 0.35, 0.10])
    else:
        return np.random.choice(["Road", "Rail", "Air"], p=[0.35, 0.45, 0.20])


def estimate_time_days(distance_km, transport_mode):
    """
    Estimates delivery time based on distance and mode.
    """
    if transport_mode == "Road":
        if distance_km <= 350:
            return int(np.random.randint(1, 3))
        elif distance_km <= 900:
            return int(np.random.randint(2, 5))
        else:
            return int(np.random.randint(4, 7))

    if transport_mode == "Rail":
        if distance_km <= 350:
            return int(np.random.randint(2, 4))
        elif distance_km <= 900:
            return int(np.random.randint(3, 6))
        else:
            return int(np.random.randint(5, 9))

    if transport_mode == "Air":
        return int(np.random.randint(1, 3))


def calculate_base_cost(distance_km, transport_mode):
    """
    Calculates logistics base cost using distance and transport mode.
    """
    if transport_mode == "Road":
        fixed_cost = 4000
        cost_per_km = np.random.uniform(22, 32)

    elif transport_mode == "Rail":
        fixed_cost = 6000
        cost_per_km = np.random.uniform(14, 22)

    elif transport_mode == "Air":
        fixed_cost = 18000
        cost_per_km = np.random.uniform(45, 70)

    cost = fixed_cost + (distance_km * cost_per_km)

    # Add mild random variation
    cost *= np.random.uniform(0.92, 1.08)

    # Round to nearest 100
    return int(round(cost / 100) * 100)


def assign_risk_level(distance_km, transport_mode, origin_region, destination_region):
    """
    Assigns baseline route risk.
    Longer routes and cross-region routes have higher risk.
    """
    risk_score = 0

    if distance_km > 1200:
        risk_score += 2
    elif distance_km > 700:
        risk_score += 1

    if transport_mode in ["Road", "Rail"]:
        risk_score += 1

    if origin_region != destination_region:
        risk_score += 1

    if risk_score <= 1:
        return np.random.choice(["Low", "Medium"], p=[0.85, 0.15])
    elif risk_score == 2:
        return np.random.choice(["Low", "Medium", "High"], p=[0.35, 0.55, 0.10])
    else:
        return np.random.choice(["Medium", "High"], p=[0.70, 0.30])


def choose_route_destinations(supplier_id, origin_region, route_count):
    """
    Chooses destination regions for a supplier.
    Ensures important scenario suppliers have routes to required demo destination.
    """
    destinations = []

    if supplier_id in scenario_destination_map:
        destinations.append(scenario_destination_map[supplier_id])

    # Add same-region route if not already included
    if origin_region not in destinations:
        destinations.append(origin_region)

    # Add random remaining regions
    remaining_regions = [r for r in regions if r not in destinations]

    while len(destinations) < route_count:
        if remaining_regions:
            chosen_region = np.random.choice(remaining_regions)
            destinations.append(chosen_region)
            remaining_regions.remove(chosen_region)
        else:
            destinations.append(np.random.choice(regions))

    return destinations[:route_count]


def route_score(base_cost, estimated_time_days, risk_level):
    """
    Preview scoring logic for Logistics Agent.
    Not saved in final CSV.
    """
    risk_penalty_map = {
        "Low": 0,
        "Medium": 5000,
        "High": 15000
    }

    return base_cost + (estimated_time_days * 1000) + risk_penalty_map[risk_level]


# -----------------------------
# Generate route records
# -----------------------------
routes = []
route_counter = 1

for _, supplier in suppliers_df.iterrows():
    supplier_id = supplier["supplier_id"]
    origin_region = supplier["region"]

    route_count = 3 if supplier_id in important_scenario_suppliers else 2
    destinations = choose_route_destinations(supplier_id, origin_region, route_count)

    used_destination_mode_pairs = set()

    for destination_region in destinations:
        warehouse_id = warehouse_map[destination_region]

        distance_km = get_distance(origin_region, destination_region)
        transport_mode = choose_transport_mode(distance_km)

        # Avoid duplicate destination + mode for same supplier where possible
        attempts = 0
        while (destination_region, transport_mode) in used_destination_mode_pairs and attempts < 5:
            transport_mode = choose_transport_mode(distance_km)
            attempts += 1

        used_destination_mode_pairs.add((destination_region, transport_mode))

        estimated_days = estimate_time_days(distance_km, transport_mode)
        base_cost = calculate_base_cost(distance_km, transport_mode)
        risk_level = assign_risk_level(
            distance_km,
            transport_mode,
            origin_region,
            destination_region
        )

        # Controlled scenario:
        # S-012 to South should be high-risk for later disruption escalation.
        if supplier_id == "S-012" and destination_region == "South":
            risk_level = "High"
            transport_mode = "Road"
            estimated_days = max(estimated_days, 5)

        # Controlled scenario:
        # S-001 to South should be stable for main P-101 demo.
        if supplier_id == "S-001" and destination_region == "South":
            risk_level = "Low"
            is_active = "Yes"
        else:
            is_active = np.random.choice(["Yes", "No"], p=[0.93, 0.07])

        routes.append({
            "route_id": f"R-{route_counter:03d}",
            "source_node": supplier_id,
            "source_type": "Supplier",
            "destination_node": warehouse_id,
            "destination_type": "Warehouse",
            "supplier_id": supplier_id,
            "origin_region": origin_region,
            "destination_region": destination_region,
            "warehouse_id": warehouse_id,
            "distance_km": distance_km,
            "transport_mode": transport_mode,
            "base_cost": base_cost,
            "estimated_time_days": estimated_days,
            "risk_level": risk_level,
            "is_active": is_active
        })

        route_counter += 1

routes_df = pd.DataFrame(routes)

# -----------------------------
# Ensure every supplier has at least one active route
# -----------------------------
for supplier_id in suppliers_df["supplier_id"]:
    supplier_routes = routes_df[routes_df["supplier_id"] == supplier_id]

    if not (supplier_routes["is_active"] == "Yes").any():
        first_index = supplier_routes.index[0]
        routes_df.loc[first_index, "is_active"] = "Yes"

# -----------------------------
# Ensure at least one inactive route exists
# -----------------------------
if "No" not in routes_df["is_active"].values:
    non_critical_routes = routes_df[
        ~routes_df["supplier_id"].isin(important_scenario_suppliers)
    ]

    if not non_critical_routes.empty:
        routes_df.loc[non_critical_routes.index[0], "is_active"] = "No"

# -----------------------------
# Ensure at least one High risk route exists
# -----------------------------
if "High" not in routes_df["risk_level"].values:
    s012_south = routes_df[
        (routes_df["supplier_id"] == "S-012") &
        (routes_df["destination_region"] == "South")
    ]

    if not s012_south.empty:
        routes_df.loc[s012_south.index[0], "risk_level"] = "High"

# -----------------------------
# Validation checks
# -----------------------------
expected_min_rows = len(suppliers_df) * 2
actual_rows = len(routes_df)

if actual_rows < expected_min_rows:
    raise ValueError(f"Too few routes generated. Expected at least {expected_min_rows}, got {actual_rows}")

if routes_df["route_id"].duplicated().any():
    raise ValueError("Duplicate route_id found.")

invalid_supplier_ids = set(routes_df["supplier_id"]) - set(suppliers_df["supplier_id"])

if invalid_supplier_ids:
    raise ValueError(f"Invalid supplier IDs found in routes.csv: {invalid_supplier_ids}")

if not (routes_df["source_node"] == routes_df["supplier_id"]).all():
    raise ValueError("source_node must always equal supplier_id.")

if not (routes_df["source_type"] == "Supplier").all():
    raise ValueError("source_type must always be Supplier.")

if not (routes_df["destination_node"] == routes_df["warehouse_id"]).all():
    raise ValueError("destination_node must always equal warehouse_id.")

if not (routes_df["destination_type"] == "Warehouse").all():
    raise ValueError("destination_type must always be Warehouse.")

invalid_dest_regions = set(routes_df["destination_region"]) - set(regions)

if invalid_dest_regions:
    raise ValueError(f"Invalid destination regions found: {invalid_dest_regions}")

invalid_origin_regions = set(routes_df["origin_region"]) - set(regions)

if invalid_origin_regions:
    raise ValueError(f"Invalid origin regions found: {invalid_origin_regions}")

invalid_modes = set(routes_df["transport_mode"]) - set(valid_transport_modes)

if invalid_modes:
    raise ValueError(f"Invalid transport modes found: {invalid_modes}")

invalid_risks = set(routes_df["risk_level"]) - set(valid_risk_levels)

if invalid_risks:
    raise ValueError(f"Invalid risk levels found: {invalid_risks}")

invalid_active_values = set(routes_df["is_active"]) - {"Yes", "No"}

if invalid_active_values:
    raise ValueError(f"Invalid is_active values found: {invalid_active_values}")

# origin_region should match supplier region
supplier_region_map = suppliers_df.set_index("supplier_id")["region"].to_dict()
routes_df["expected_origin_region"] = routes_df["supplier_id"].map(supplier_region_map)

origin_mismatch = routes_df[
    routes_df["origin_region"] != routes_df["expected_origin_region"]
]

if not origin_mismatch.empty:
    raise ValueError("Some route origin_region values do not match supplier region.")

routes_df = routes_df.drop(columns=["expected_origin_region"])

# warehouse_id should match destination_region
routes_df["expected_warehouse_id"] = routes_df["destination_region"].map(warehouse_map)

warehouse_mismatch = routes_df[
    routes_df["warehouse_id"] != routes_df["expected_warehouse_id"]
]

if not warehouse_mismatch.empty:
    raise ValueError("Some warehouse_id values do not match destination_region.")

routes_df = routes_df.drop(columns=["expected_warehouse_id"])

if (routes_df["distance_km"] <= 0).any():
    raise ValueError("distance_km must be positive.")

if (routes_df["base_cost"] <= 0).any():
    raise ValueError("base_cost must be positive.")

if (routes_df["estimated_time_days"] <= 0).any():
    raise ValueError("estimated_time_days must be positive.")

# Every supplier should have at least one active route
active_route_check = (
    routes_df[routes_df["is_active"] == "Yes"]
    .groupby("supplier_id")["route_id"]
    .count()
)

suppliers_without_active_route = set(suppliers_df["supplier_id"]) - set(active_route_check.index)

if suppliers_without_active_route:
    raise ValueError(f"Suppliers without active routes: {suppliers_without_active_route}")

# Important scenario route checks
required_routes = {
    "S-001": "South",
    "S-004": "West",
    "S-005": "West",
    "S-007": "North",
    "S-012": "South",
    "S-013": "South"
}

for supplier_id, required_destination in required_routes.items():
    required_route_exists = not routes_df[
        (routes_df["supplier_id"] == supplier_id) &
        (routes_df["destination_region"] == required_destination)
    ].empty

    if not required_route_exists:
        raise ValueError(
            f"Required scenario route missing: {supplier_id} -> {required_destination}"
        )

# -----------------------------
# Save final CSV
# -----------------------------
routes_df.to_csv(OUTPUT_FILE, index=False)

# -----------------------------
# Print useful summary
# -----------------------------
routes_df["route_score_preview"] = routes_df.apply(
    lambda row: route_score(
        row["base_cost"],
        row["estimated_time_days"],
        row["risk_level"]
    ),
    axis=1
)

print("routes.csv generated successfully.")
print(f"Saved to: {OUTPUT_FILE}")
print(f"Total rows generated: {len(routes_df)}")
print(f"Total columns generated: {len(routes_df.drop(columns=['route_score_preview']).columns)}")
print()

print("Routes per supplier summary:")
print(routes_df.groupby("supplier_id")["route_id"].count())
print()

print("Transport mode distribution:")
print(routes_df["transport_mode"].value_counts())
print()

print("Risk level distribution:")
print(routes_df["risk_level"].value_counts())
print()

print("Active route distribution:")
print(routes_df["is_active"].value_counts())
print()

print("Important scenario routes:")
scenario_routes = routes_df[
    (
        (routes_df["supplier_id"] == "S-001") &
        (routes_df["destination_region"] == "South")
    ) |
    (
        (routes_df["supplier_id"] == "S-012") &
        (routes_df["destination_region"] == "South")
    ) |
    (
        (routes_df["supplier_id"] == "S-013") &
        (routes_df["destination_region"] == "South")
    ) |
    (
        (routes_df["supplier_id"] == "S-004") &
        (routes_df["destination_region"] == "West")
    ) |
    (
        (routes_df["supplier_id"] == "S-005") &
        (routes_df["destination_region"] == "West")
    ) |
    (
        (routes_df["supplier_id"] == "S-007") &
        (routes_df["destination_region"] == "North")
    )
]

print(
    scenario_routes[[
        "route_id",
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
        "route_score_preview"
    ]]
)