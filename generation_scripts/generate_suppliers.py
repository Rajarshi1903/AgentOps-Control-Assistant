import pandas as pd
import numpy as np

# ============================================================
# Generate suppliers.csv
# ============================================================
# Required input:
# products.csv
#
# Output:
# suppliers.csv
#
# Structure:
# supplier_id, supplier_name, product_id, region, unit_cost,
# lead_time_days, reliability_score, is_approved,
# max_capacity, compliance_status
# ============================================================

np.random.seed(42)

PRODUCTS_FILE = "products.csv"
OUTPUT_FILE = "suppliers.csv"

regions = ["North", "South", "East", "West"]

# ------------------------------------------------------------
# Load products
# ------------------------------------------------------------
products_df = pd.read_csv(PRODUCTS_FILE)

required_columns = {
    "product_id",
    "product_name",
    "category",
    "unit_price",
    "status"
}

missing_columns = required_columns - set(products_df.columns)

if missing_columns:
    raise ValueError(f"products.csv is missing required columns: {missing_columns}")

products_df = products_df[products_df["status"] == "Active"].copy()

if products_df.empty:
    raise ValueError("No active products found in products.csv")

product_lookup = products_df.set_index("product_id").to_dict("index")

# ------------------------------------------------------------
# Supplier count per product
# Total = 25 supplier rows
# ------------------------------------------------------------
supplier_count_map = {
    "P-101": 3,
    "P-102": 3,
    "P-103": 3,
    "P-104": 2,
    "P-105": 3,
    "P-106": 2,
    "P-107": 2,
    "P-108": 2,
    "P-109": 3,
    "P-110": 2
}

# ------------------------------------------------------------
# Category-based rules
# ------------------------------------------------------------
lead_time_ranges = {
    "Packaging": (2, 5),
    "Electrical": (3, 7),
    "Electronics": (5, 10),
    "Mechanical": (6, 14),
    "Industrial Material": (4, 8)
}

capacity_ranges = {
    "Packaging": (1000, 5000),
    "Electrical": (800, 3000),
    "Electronics": (200, 1000),
    "Mechanical": (100, 800),
    "Industrial Material": (500, 2000)
}

supplier_name_pool = [
    "Alpha Components Pvt Ltd",
    "Beta Industrial Traders",
    "Nova Electronics Supply Co",
    "Omega Precision Works",
    "Prime Motion Systems",
    "Vertex Supply Chain Solutions",
    "Delta Engineering Supplies",
    "Apex Packaging Materials",
    "Zenith Industrial Components",
    "Orion Electrical Distributors",
    "Summit Techno Supplies",
    "Metro Manufacturing Partners",
    "Reliable Components India",
    "Evergreen Packaging Co",
    "Trident Mechanical Systems",
    "Sapphire Industrial Traders",
    "Pioneer Electronics Hub",
    "Global Material Source",
    "Rapid Logistics Suppliers",
    "CoreTech Component Works",
    "Bharat Industrial Supply Co",
    "Eastern Precision Traders",
    "Southern Tech Components",
    "Western Engineering Supply",
    "Northstar Vendor Services"
]

# ------------------------------------------------------------
# Helper functions
# ------------------------------------------------------------
def get_unit_cost(unit_price, supplier_type):
    """
    Supplier cost is usually 60% to 85% of product selling price.
    Approved suppliers are slightly costlier.
    Unapproved suppliers are cheaper but riskier.
    """
    if supplier_type == "approved_compliant":
        multiplier = np.random.uniform(0.70, 0.85)
    elif supplier_type == "approved_under_review":
        multiplier = np.random.uniform(0.65, 0.78)
    else:
        multiplier = np.random.uniform(0.60, 0.70)

    return int(round(unit_price * multiplier))


def get_lead_time(category, supplier_type):
    """
    Lead time depends on product category and supplier quality.
    """
    low, high = lead_time_ranges.get(category, (4, 8))

    lead_time = np.random.randint(low, high + 1)

    if supplier_type == "approved_compliant":
        lead_time = max(low, lead_time - 1)
    elif supplier_type == "unapproved":
        lead_time = min(high + 2, lead_time + 1)

    return int(lead_time)


def get_reliability(supplier_type):
    """
    Reliability score depends on approval and compliance status.
    """
    if supplier_type == "approved_compliant":
        return int(np.random.randint(86, 99))
    elif supplier_type == "approved_under_review":
        return int(np.random.randint(75, 86))
    else:
        return int(np.random.randint(55, 75))


def get_capacity(category, supplier_type):
    """
    Capacity depends on product category and supplier maturity.
    """
    low, high = capacity_ranges.get(category, (300, 1000))

    capacity = np.random.randint(low, high + 1)

    if supplier_type == "approved_compliant":
        capacity = int(capacity * np.random.uniform(1.0, 1.2))
    elif supplier_type == "unapproved":
        capacity = int(capacity * np.random.uniform(0.6, 0.9))

    return int(capacity)


def get_supplier_type(index, total_suppliers):
    """
    Creates a realistic mix:
    - Mostly approved and compliant
    - Some approved but under review
    - Some unapproved/non-compliant
    """
    if total_suppliers == 2:
        if index == 0:
            return "approved_compliant"
        else:
            return np.random.choice(
                ["approved_compliant", "approved_under_review", "unapproved"],
                p=[0.50, 0.30, 0.20]
            )

    if total_suppliers == 3:
        if index == 0:
            return "approved_compliant"
        elif index == 1:
            return np.random.choice(
                ["approved_compliant", "approved_under_review"],
                p=[0.65, 0.35]
            )
        else:
            return np.random.choice(
                ["approved_under_review", "unapproved"],
                p=[0.35, 0.65]
            )


def type_to_status(supplier_type):
    if supplier_type == "approved_compliant":
        return "Yes", "Compliant"
    elif supplier_type == "approved_under_review":
        return "Yes", "Under Review"
    else:
        return "No", "Non-Compliant"


# ------------------------------------------------------------
# Controlled MVP scenario overrides
# ------------------------------------------------------------
# These ensure the demo cases work properly.
# They do not make the framework hardcoded.
# They only shape the synthetic data.

controlled_suppliers = {
    "P-101": [
        {
            "supplier_name": "Alpha Components Pvt Ltd",
            "region": "South",
            "unit_cost": 1800,
            "lead_time_days": 5,
            "reliability_score": 92,
            "is_approved": "Yes",
            "max_capacity": 700,
            "compliance_status": "Compliant"
        },
        {
            "supplier_name": "Beta Industrial Traders",
            "region": "South",
            "unit_cost": 1550,
            "lead_time_days": 4,
            "reliability_score": 68,
            "is_approved": "No",
            "max_capacity": 450,
            "compliance_status": "Non-Compliant"
        },
        {
            "supplier_name": "Nova Electronics Supply Co",
            "region": "West",
            "unit_cost": 1950,
            "lead_time_days": 7,
            "reliability_score": 88,
            "is_approved": "Yes",
            "max_capacity": 600,
            "compliance_status": "Compliant"
        }
    ],

    "P-103": [
        {
            "supplier_name": "Omega Precision Works",
            "region": "North",
            "unit_cost": 3300,
            "lead_time_days": 8,
            "reliability_score": 90,
            "is_approved": "Yes",
            "max_capacity": 350,
            "compliance_status": "Compliant"
        },
        {
            "supplier_name": "Beta Industrial Traders",
            "region": "East",
            "unit_cost": 2600,
            "lead_time_days": 9,
            "reliability_score": 62,
            "is_approved": "No",
            "max_capacity": 250,
            "compliance_status": "Non-Compliant"
        },
        {
            "supplier_name": "Trident Mechanical Systems",
            "region": "West",
            "unit_cost": 3500,
            "lead_time_days": 11,
            "reliability_score": 82,
            "is_approved": "Yes",
            "max_capacity": 300,
            "compliance_status": "Under Review"
        }
    ],

    "P-105": [
        {
            "supplier_name": "Pioneer Electronics Hub",
            "region": "West",
            "unit_cost": 2300,
            "lead_time_days": 6,
            "reliability_score": 91,
            "is_approved": "Yes",
            "max_capacity": 500,
            "compliance_status": "Compliant"
        },
        {
            "supplier_name": "Southern Tech Components",
            "region": "South",
            "unit_cost": 2450,
            "lead_time_days": 5,
            "reliability_score": 87,
            "is_approved": "Yes",
            "max_capacity": 450,
            "compliance_status": "Compliant"
        },
        {
            "supplier_name": "Rapid Logistics Suppliers",
            "region": "East",
            "unit_cost": 2050,
            "lead_time_days": 8,
            "reliability_score": 70,
            "is_approved": "No",
            "max_capacity": 300,
            "compliance_status": "Non-Compliant"
        }
    ]
}

# ------------------------------------------------------------
# Generate supplier records
# ------------------------------------------------------------
supplier_records = []
supplier_counter = 1
used_names = set()

for product_id, supplier_count in supplier_count_map.items():

    if product_id not in product_lookup:
        raise ValueError(f"{product_id} not found in products.csv")

    product_info = product_lookup[product_id]
    category = product_info["category"]
    unit_price = product_info["unit_price"]

    # Use controlled scenario suppliers if available
    if product_id in controlled_suppliers:
        supplier_list = controlled_suppliers[product_id]

        for supplier in supplier_list:
            supplier_records.append({
                "supplier_id": f"S-{supplier_counter:03d}",
                "supplier_name": supplier["supplier_name"],
                "product_id": product_id,
                "region": supplier["region"],
                "unit_cost": supplier["unit_cost"],
                "lead_time_days": supplier["lead_time_days"],
                "reliability_score": supplier["reliability_score"],
                "is_approved": supplier["is_approved"],
                "max_capacity": supplier["max_capacity"],
                "compliance_status": supplier["compliance_status"]
            })

            supplier_counter += 1

        continue

    # Generate general suppliers for other products
    for i in range(supplier_count):

        supplier_type = get_supplier_type(i, supplier_count)
        is_approved, compliance_status = type_to_status(supplier_type)

        # Pick supplier name
        available_names = [name for name in supplier_name_pool if name not in used_names]

        if not available_names:
            supplier_name = f"Regional Supplier {supplier_counter}"
        else:
            supplier_name = np.random.choice(available_names)
            used_names.add(supplier_name)

        supplier_records.append({
            "supplier_id": f"S-{supplier_counter:03d}",
            "supplier_name": supplier_name,
            "product_id": product_id,
            "region": np.random.choice(regions),
            "unit_cost": get_unit_cost(unit_price, supplier_type),
            "lead_time_days": get_lead_time(category, supplier_type),
            "reliability_score": get_reliability(supplier_type),
            "is_approved": is_approved,
            "max_capacity": get_capacity(category, supplier_type),
            "compliance_status": compliance_status
        })

        supplier_counter += 1

# ------------------------------------------------------------
# Create DataFrame
# ------------------------------------------------------------
suppliers_df = pd.DataFrame(supplier_records)

# ------------------------------------------------------------
# Validation checks
# ------------------------------------------------------------
expected_rows = sum(supplier_count_map.values())
actual_rows = len(suppliers_df)

if actual_rows != expected_rows:
    raise ValueError(f"Row count mismatch. Expected {expected_rows}, got {actual_rows}")

if suppliers_df["supplier_id"].duplicated().any():
    raise ValueError("Duplicate supplier_id found.")

invalid_products = set(suppliers_df["product_id"]) - set(products_df["product_id"])

if invalid_products:
    raise ValueError(f"Invalid product IDs found in suppliers.csv: {invalid_products}")

invalid_regions = set(suppliers_df["region"]) - set(regions)

if invalid_regions:
    raise ValueError(f"Invalid supplier regions found: {invalid_regions}")

invalid_approval_values = set(suppliers_df["is_approved"]) - {"Yes", "No"}

if invalid_approval_values:
    raise ValueError(f"Invalid is_approved values found: {invalid_approval_values}")

valid_compliance_values = {"Compliant", "Under Review", "Non-Compliant"}
invalid_compliance_values = set(suppliers_df["compliance_status"]) - valid_compliance_values

if invalid_compliance_values:
    raise ValueError(f"Invalid compliance_status values found: {invalid_compliance_values}")

# Check unit_cost is lower than product unit_price
supplier_price_check = suppliers_df.merge(
    products_df[["product_id", "unit_price"]],
    on="product_id",
    how="left"
)

invalid_cost_rows = supplier_price_check[
    supplier_price_check["unit_cost"] >= supplier_price_check["unit_price"]
]

if not invalid_cost_rows.empty:
    raise ValueError("Some supplier unit_cost values are greater than or equal to product unit_price.")

# Check every product has at least 2 suppliers
supplier_counts = suppliers_df.groupby("product_id")["supplier_id"].count()

products_with_too_few_suppliers = supplier_counts[supplier_counts < 2]

if not products_with_too_few_suppliers.empty:
    raise ValueError(f"Some products have fewer than 2 suppliers: {products_with_too_few_suppliers}")

# Check at least one unapproved supplier exists
if "No" not in suppliers_df["is_approved"].values:
    raise ValueError("No unapproved supplier found. At least one is required for governance testing.")

# ------------------------------------------------------------
# Save CSV
# ------------------------------------------------------------
suppliers_df.to_csv(OUTPUT_FILE, index=False)

# ------------------------------------------------------------
# Print summary
# ------------------------------------------------------------
print("suppliers.csv generated successfully.")
print(f"Total rows generated: {actual_rows}")
print(f"Total columns generated: {len(suppliers_df.columns)}")
print()

print("Supplier count by product:")
print(suppliers_df.groupby("product_id")["supplier_id"].count())
print()

print("Approval status summary:")
print(suppliers_df["is_approved"].value_counts())
print()

print("Compliance status summary:")
print(suppliers_df["compliance_status"].value_counts())
print()

print("Preview:")
print(suppliers_df.head(15))
print()

print("Controlled MVP scenario suppliers:")
print(
    suppliers_df[
        suppliers_df["product_id"].isin(["P-101", "P-103", "P-105"])
    ]
)