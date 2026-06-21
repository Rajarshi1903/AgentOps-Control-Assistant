import pandas as pd
import numpy as np

# ============================================================
# Generate inventory.csv
# ============================================================
# Required input files:
# 1. products.csv
# 2. sales_history.csv
#
# Output:
# inventory.csv
#
# Structure:
# inventory_id, product_id, warehouse_id, region,
# current_stock, safety_stock, reorder_point, last_updated
# ============================================================

np.random.seed(42)

# -----------------------------
# File paths
# -----------------------------
PRODUCTS_FILE = "products.csv"
SALES_HISTORY_FILE = "sales_history.csv"
OUTPUT_FILE = "inventory.csv"

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

LAST_UPDATED = "2026-05-26"

# -----------------------------
# Load datasets
# -----------------------------
products_df = pd.read_csv(PRODUCTS_FILE)
sales_df = pd.read_csv(SALES_HISTORY_FILE)

# -----------------------------
# Validate required columns
# -----------------------------
required_product_columns = {"product_id", "criticality", "status"}
required_sales_columns = {"date", "product_id", "region", "units_sold"}

missing_product_columns = required_product_columns - set(products_df.columns)
missing_sales_columns = required_sales_columns - set(sales_df.columns)

if missing_product_columns:
    raise ValueError(f"products.csv is missing required columns: {missing_product_columns}")

if missing_sales_columns:
    raise ValueError(f"sales_history.csv is missing required columns: {missing_sales_columns}")

# Use only active products
products_df = products_df[products_df["status"] == "Active"].copy()

if products_df.empty:
    raise ValueError("No active products found in products.csv")

# Validate product relationship
invalid_sales_products = set(sales_df["product_id"]) - set(products_df["product_id"])

if invalid_sales_products:
    raise ValueError(f"sales_history.csv has product IDs not present in products.csv: {invalid_sales_products}")

# Validate regions
invalid_regions = set(sales_df["region"]) - set(regions)

if invalid_regions:
    raise ValueError(f"sales_history.csv has invalid regions: {invalid_regions}")

# -----------------------------
# Calculate average demand
# -----------------------------
# Average daily demand per product-region
avg_demand_df = (
    sales_df
    .groupby(["product_id", "region"], as_index=False)
    .agg(avg_daily_demand=("units_sold", "mean"))
)

# Merge criticality from product master
avg_demand_df = avg_demand_df.merge(
    products_df[["product_id", "criticality"]],
    on="product_id",
    how="left"
)

# -----------------------------
# Helper functions
# -----------------------------
def get_safety_stock_multiplier(criticality):
    """
    Higher criticality products get higher safety stock.
    """
    if criticality == "High":
        return np.random.uniform(0.45, 0.60)
    elif criticality == "Medium":
        return np.random.uniform(0.30, 0.45)
    else:
        return np.random.uniform(0.18, 0.30)


def get_lead_time_buffer(criticality):
    """
    Assumed lead time buffer in days.
    High-criticality products use slightly higher buffer.
    """
    if criticality == "High":
        return np.random.randint(4, 6)  # 4 to 5 days
    elif criticality == "Medium":
        return np.random.randint(3, 5)  # 3 to 4 days
    else:
        return np.random.randint(2, 4)  # 2 to 3 days


def generate_current_stock(product_id, region, avg_daily_demand, safety_stock, reorder_point):
    """
    Generates realistic stock levels while intentionally supporting MVP scenarios.
    """

    # --------------------------------------------------------
    # Controlled MVP scenarios
    # --------------------------------------------------------

    # Scenario 1:
    # P-101 South = main high-value procurement escalation
    # Keep stock very low.
    if product_id == "P-101" and region == "South":
        return 80

    # Scenario 2:
    # P-103 North = vendor compliance/block scenario
    # Keep stock low/moderate to force procurement.
    if product_id == "P-103" and region == "North":
        return int(max(40, avg_daily_demand * 0.9))

    # Scenario 3:
    # P-105 South = route disruption escalation scenario
    # Keep stock low to force procurement and logistics planning.
    if product_id == "P-105" and region == "South":
        return int(max(50, avg_daily_demand * 0.8))

    # Scenario 4:
    # P-104 East = no procurement needed scenario
    # Keep stock high enough despite mild demand spike.
    if product_id == "P-104" and region == "East":
        return int(reorder_point * 1.6)

    # Scenario 5:
    # P-102 West = normal allow case
    # Keep stock slightly below/around reorder point but not extremely risky.
    if product_id == "P-102" and region == "West":
        return int(reorder_point * 0.95)

    # --------------------------------------------------------
    # General realistic inventory generation
    # --------------------------------------------------------

    stock_pattern = np.random.choice(
        ["healthy", "near_reorder", "low"],
        p=[0.55, 0.30, 0.15]
    )

    if stock_pattern == "healthy":
        current_stock = np.random.uniform(1.10, 1.60) * reorder_point
    elif stock_pattern == "near_reorder":
        current_stock = np.random.uniform(0.80, 1.05) * reorder_point
    else:
        current_stock = np.random.uniform(0.45, 0.75) * reorder_point

    return int(round(current_stock))


# -----------------------------
# Generate inventory records
# -----------------------------
inventory_records = []

inventory_counter = 1

for _, row in avg_demand_df.iterrows():
    product_id = row["product_id"]
    region = row["region"]
    criticality = row["criticality"]
    avg_daily_demand = row["avg_daily_demand"]

    warehouse_id = warehouse_map[region]

    # Safety stock
    safety_multiplier = get_safety_stock_multiplier(criticality)
    safety_stock = int(round(avg_daily_demand * safety_multiplier))

    # Reorder point
    lead_time_buffer = get_lead_time_buffer(criticality)
    reorder_point = int(round(safety_stock + (avg_daily_demand * lead_time_buffer)))

    # Current stock
    current_stock = generate_current_stock(
        product_id=product_id,
        region=region,
        avg_daily_demand=avg_daily_demand,
        safety_stock=safety_stock,
        reorder_point=reorder_point
    )

    inventory_records.append({
        "inventory_id": f"INV-{inventory_counter:03d}",
        "product_id": product_id,
        "warehouse_id": warehouse_id,
        "region": region,
        "current_stock": current_stock,
        "safety_stock": safety_stock,
        "reorder_point": reorder_point,
        "last_updated": LAST_UPDATED
    })

    inventory_counter += 1

# -----------------------------
# Create DataFrame
# -----------------------------
inventory_df = pd.DataFrame(inventory_records)

# Sort for readability
inventory_df = inventory_df.sort_values(
    by=["product_id", "region"]
).reset_index(drop=True)

# Reassign inventory_id after sorting
inventory_df["inventory_id"] = [
    f"INV-{i+1:03d}" for i in range(len(inventory_df))
]

# -----------------------------
# Validation checks
# -----------------------------
expected_rows = len(products_df) * len(regions)
actual_rows = len(inventory_df)

if actual_rows != expected_rows:
    raise ValueError(f"Row count mismatch. Expected {expected_rows}, got {actual_rows}")

invalid_inventory_products = set(inventory_df["product_id"]) - set(products_df["product_id"])

if invalid_inventory_products:
    raise ValueError(f"inventory.csv has product IDs not present in products.csv: {invalid_inventory_products}")

invalid_inventory_regions = set(inventory_df["region"]) - set(regions)

if invalid_inventory_regions:
    raise ValueError(f"inventory.csv has invalid regions: {invalid_inventory_regions}")

if inventory_df["current_stock"].lt(0).any():
    raise ValueError("current_stock cannot be negative.")

if inventory_df["safety_stock"].lt(0).any():
    raise ValueError("safety_stock cannot be negative.")

if inventory_df["reorder_point"].lt(inventory_df["safety_stock"]).any():
    raise ValueError("reorder_point should not be less than safety_stock.")

# -----------------------------
# Save CSV
# -----------------------------
inventory_df.to_csv(OUTPUT_FILE, index=False)

# -----------------------------
# Print summary
# -----------------------------
print("inventory.csv generated successfully.")
print(f"Total rows generated: {actual_rows}")
print(f"Total columns generated: {len(inventory_df.columns)}")
print()

print("Preview:")
print(inventory_df.head(12))
print()

print("Scenario rows:")
scenario_rows = inventory_df[
    ((inventory_df["product_id"] == "P-101") & (inventory_df["region"] == "South")) |
    ((inventory_df["product_id"] == "P-103") & (inventory_df["region"] == "North")) |
    ((inventory_df["product_id"] == "P-105") & (inventory_df["region"] == "South")) |
    ((inventory_df["product_id"] == "P-104") & (inventory_df["region"] == "East")) |
    ((inventory_df["product_id"] == "P-102") & (inventory_df["region"] == "West"))
]

print(scenario_rows)