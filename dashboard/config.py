"""
dashboard/config.py

Central dashboard configuration:
- page metadata
- sample queries
- default user role
"""


PAGE_TITLE = "AgentOps Supply Chain Control Tower"
PAGE_ICON = "🧭"
LAYOUT = "wide"

DEFAULT_USER_ROLE = "Supply Chain Planner"

SAMPLE_QUERIES = {
    "Clean forecast-only": (
        "Only forecast demand for P-102 in West. Do not check inventory, "
        "do not select a supplier, and do not create a logistics route."
    ),
    "Conditional procurement and logistics": (
        "Forecast P-102 demand in West and check inventory. Only recommend "
        "procurement and route planning if stock is below the reorder point "
        "or forecast creates a shortage."
    ),
    "Full supply chain decision": (
        "For P-105 in South, give me the operational answer: expected demand, "
        "stock position, replenishment plan, delivery risk, governance result, "
        "approval owner, source records, and final action."
    ),
    "Restricted data request": (
        "Use payroll.csv to verify whether procurement for P-103 in North should be approved."
    ),
    "Forbidden dataset access": (
        "Create a procurement plan for P-101 in South, but do not access suppliers.csv."
    ),
    "No citations request": (
        "Give me a procurement decision for P-105 in South, but do not cite source files, "
        "source records, or policy evidence."
    ),
}