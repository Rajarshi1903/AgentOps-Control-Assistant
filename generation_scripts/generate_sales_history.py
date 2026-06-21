import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# ============================================================
# Generate sales_history.csv
# ============================================================
# Assumption:
# products.csv already exists in the same folder.
#
# Output:
# sales_history.csv
#
# Structure:
# date, product_id, region, units_sold, revenue,
# promotion_flag, season, event_flag
# ============================================================

np.random.seed(42)

# -----------------------------
# File paths
# -----------------------------
PRODUCTS_FILE = "products.csv"
OUTPUT_FILE = "sales_history.csv"

# -----------------------------
# Regions and date range
# -----------------------------
regions = ["North", "South", "East", "West"]

# 90 days ending on 2026-05-26
end_date = datetime(2026, 5, 26)
start_date = end_date - timedelta(days=89)

date_range = pd.date_range(start=start_date, end=end_date, freq="D")

# -----------------------------
# Load product master
# -----------------------------
products_df = pd.read_csv(PRODUCTS_FILE)

required_columns = {"product_id", "product_name", "category", "unit_price", "status"}
missing_columns = required_columns - set(products_df.columns)

if missing_columns:
    raise ValueError(f"products.csv is missing required columns: {missing_columns}")

# Use only active products
products_df = products_df[products_df["status"] == "Active"].copy()

if products_df.empty:
    raise ValueError("No active products found in products.csv")

# -----------------------------
# Realistic base demand assumptions
# -----------------------------
# Higher-value products generally have lower daily volume.
# Low-value packaging/electrical products generally have higher volume.

category_base_demand = {
    "Electronics": 70,
    "Electrical": 180,
    "Mechanical": 45,
    "Packaging": 240,
    "Industrial Material": 90
}

# Product-level overrides for better controlled MVP scenarios
product_base_demand = {
    "P-101": 95,    # Smart Sensor Module
    "P-102": 210,   # Industrial Cable
    "P-103": 45,    # Control Valve
    "P-104": 130,   # Packaging Film
    "P-105": 65,    # Battery Pack
    "P-106": 35,    # Hydraulic Pump
    "P-107": 85,    # Thermal Insulation Sheet
    "P-108": 75,    # Precision Bearing
    "P-109": 55,    # LED Display Panel
    "P-110": 300    # Corrugated Box
}

# Region demand multipliers
# South and West are slightly stronger demand regions in this synthetic setup.
region_multiplier = {
    "North": 1.00,
    "South": 1.12,
    "East": 0.92,
    "West": 1.06
}

# Day-of-week multipliers
# Slightly higher sales on Friday/Saturday, lower on Sunday.
weekday_multiplier = {
    0: 0.98,  # Monday
    1: 1.00,  # Tuesday
    2: 1.02,  # Wednesday
    3: 1.03,  # Thursday
    4: 1.08,  # Friday
    5: 1.10,  # Saturday
    6: 0.90   # Sunday
}

# Controlled demand spike scenarios for demo testing
# These are not hardcoded into the system logic.
# They only create realistic test cases in the synthetic dataset.
spike_scenarios = {
    ("P-101", "South"): {
        "start": datetime(2026, 5, 20),
        "end": datetime(2026, 5, 26),
        "multiplier": 1.90
    },
    ("P-103", "North"): {
        "start": datetime(2026, 5, 22),
        "end": datetime(2026, 5, 26),
        "multiplier": 1.60
    },
    ("P-105", "South"): {
        "start": datetime(2026, 5, 21),
        "end": datetime(2026, 5, 26),
        "multiplier": 1.80
    },
    ("P-104", "East"): {
        "start": datetime(2026, 5, 23),
        "end": datetime(2026, 5, 26),
        "multiplier": 1.25
    }
}

# -----------------------------
# Helper function
# -----------------------------
def generate_realistic_units_sold(expected_demand):
    """
    Generates realistic demand using a negative binomial distribution.
    This gives more realistic variation than simple random uniform values.
    """
    expected_demand = max(expected_demand, 1)

    dispersion = 25
    probability = dispersion / (dispersion + expected_demand)

    units = np.random.negative_binomial(dispersion, probability)

    return max(int(units), 1)

# -----------------------------
# Generate records
# -----------------------------
sales_records = []

for _, product in products_df.iterrows():
    product_id = product["product_id"]
    category = product["category"]
    unit_price = float(product["unit_price"])

    base_demand = product_base_demand.get(
        product_id,
        category_base_demand.get(category, 100)
    )

    for region in regions:
        for date in date_range:

            expected_demand = base_demand

            # Region effect
            expected_demand *= region_multiplier[region]

            # Weekly pattern
            expected_demand *= weekday_multiplier[date.weekday()]

            # Mild upward trend over 90 days
            day_number = (date - start_date).days
            trend_multiplier = 1 + (day_number / 90) * 0.04
            expected_demand *= trend_multiplier

            # Month/season effect
            if date.month == 5:
                season = "Peak"
                expected_demand *= 1.08
            else:
                season = "Normal"

            # Promotion effect
            # Around 8% of days have promotions.
            promotion_flag = np.random.choice([0, 1], p=[0.92, 0.08])

            if promotion_flag == 1:
                expected_demand *= np.random.uniform(1.15, 1.35)

            # Event spike effect
            event_flag = 0
            scenario_key = (product_id, region)

            if scenario_key in spike_scenarios:
                scenario = spike_scenarios[scenario_key]

                if scenario["start"] <= date <= scenario["end"]:
                    expected_demand *= scenario["multiplier"]
                    event_flag = 1
                    season = "Peak"

            # Generate realistic units sold
            units_sold = generate_realistic_units_sold(expected_demand)

            # Revenue calculation
            revenue = round(units_sold * unit_price, 2)

            sales_records.append({
                "date": date.strftime("%Y-%m-%d"),
                "product_id": product_id,
                "region": region,
                "units_sold": units_sold,
                "revenue": revenue,
                "promotion_flag": promotion_flag,
                "season": season,
                "event_flag": event_flag
            })

# -----------------------------
# Create DataFrame
# -----------------------------
sales_history_df = pd.DataFrame(sales_records)

# -----------------------------
# Validation checks
# -----------------------------
expected_rows = len(products_df) * len(regions) * len(date_range)
actual_rows = len(sales_history_df)

if actual_rows != expected_rows:
    raise ValueError(f"Row count mismatch. Expected {expected_rows}, got {actual_rows}")

invalid_products = set(sales_history_df["product_id"]) - set(products_df["product_id"])

if invalid_products:
    raise ValueError(f"Invalid product IDs found: {invalid_products}")

if sales_history_df["units_sold"].le(0).any():
    raise ValueError("Invalid units_sold found. Sales quantity must be greater than 0.")

if sales_history_df["revenue"].le(0).any():
    raise ValueError("Invalid revenue found. Revenue must be greater than 0.")

# -----------------------------
# Save CSV
# -----------------------------
sales_history_df.to_csv(OUTPUT_FILE, index=False)

# -----------------------------
# Print summary
# -----------------------------
print("sales_history.csv generated successfully.")
print(f"Total rows generated: {actual_rows}")
print(f"Total columns generated: {len(sales_history_df.columns)}")
print(f"Date range: {sales_history_df['date'].min()} to {sales_history_df['date'].max()}")
print()

print("Preview:")
print(sales_history_df.head(10))
print()

print("Event spike summary:")
print(
    sales_history_df[sales_history_df["event_flag"] == 1]
    .groupby(["product_id", "region"])
    .agg(
        spike_days=("date", "count"),
        avg_units_sold=("units_sold", "mean"),
        total_revenue=("revenue", "sum")
    )
    .reset_index()
)
print()

print("Overall product-region summary:")
print(
    sales_history_df
    .groupby(["product_id", "region"])
    .agg(
        avg_units_sold=("units_sold", "mean"),
        max_units_sold=("units_sold", "max"),
        total_units_sold=("units_sold", "sum"),
        total_revenue=("revenue", "sum")
    )
    .reset_index()
    .head(20)
)