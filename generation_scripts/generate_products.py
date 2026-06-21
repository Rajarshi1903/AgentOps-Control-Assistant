import pandas as pd

# Product master data
products_data = [
    {
        "product_id": "P-101",
        "product_name": "Smart Sensor Module",
        "category": "Electronics",
        "unit_of_measure": "units",
        "unit_price": 2500,
        "criticality": "High",
        "status": "Active"
    },
    {
        "product_id": "P-102",
        "product_name": "Industrial Cable",
        "category": "Electrical",
        "unit_of_measure": "meters",
        "unit_price": 300,
        "criticality": "Medium",
        "status": "Active"
    },
    {
        "product_id": "P-103",
        "product_name": "Control Valve",
        "category": "Mechanical",
        "unit_of_measure": "units",
        "unit_price": 4200,
        "criticality": "High",
        "status": "Active"
    },
    {
        "product_id": "P-104",
        "product_name": "Packaging Film",
        "category": "Packaging",
        "unit_of_measure": "rolls",
        "unit_price": 900,
        "criticality": "Low",
        "status": "Active"
    },
    {
        "product_id": "P-105",
        "product_name": "Battery Pack",
        "category": "Electronics",
        "unit_of_measure": "units",
        "unit_price": 3200,
        "criticality": "High",
        "status": "Active"
    },
    {
        "product_id": "P-106",
        "product_name": "Hydraulic Pump",
        "category": "Mechanical",
        "unit_of_measure": "units",
        "unit_price": 5800,
        "criticality": "High",
        "status": "Active"
    },
    {
        "product_id": "P-107",
        "product_name": "Thermal Insulation Sheet",
        "category": "Industrial Material",
        "unit_of_measure": "sheets",
        "unit_price": 1200,
        "criticality": "Medium",
        "status": "Active"
    },
    {
        "product_id": "P-108",
        "product_name": "Precision Bearing",
        "category": "Mechanical",
        "unit_of_measure": "units",
        "unit_price": 1500,
        "criticality": "Medium",
        "status": "Active"
    },
    {
        "product_id": "P-109",
        "product_name": "LED Display Panel",
        "category": "Electronics",
        "unit_of_measure": "units",
        "unit_price": 3500,
        "criticality": "Medium",
        "status": "Active"
    },
    {
        "product_id": "P-110",
        "product_name": "Corrugated Box",
        "category": "Packaging",
        "unit_of_measure": "boxes",
        "unit_price": 120,
        "criticality": "Low",
        "status": "Active"
    }
]

# Create DataFrame
products_df = pd.DataFrame(products_data)

# Save as CSV
products_df.to_csv("products.csv", index=False)

print("products.csv generated successfully.")
print(products_df)