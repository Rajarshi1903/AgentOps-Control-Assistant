from pathlib import Path
import pandas as pd

# ============================================================
# Generate agent_permissions.csv
# ============================================================
# Output:
# data/agent_permissions.csv
#
# Purpose:
# Defines agent-level dataset access, tool access, restricted data,
# financial action limits, external communication permission,
# approval requirements, and operational status.
# ============================================================

# -----------------------------
# File paths
# -----------------------------
DATA_DIR = Path("data")
DATA_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_FILE = DATA_DIR / "agent_permissions.csv"

# -----------------------------
# Controlled values
# -----------------------------
valid_agent_types = {
    "orchestrator",
    "business_agent",
    "governance_agent",
    "logging_agent",
    "presentation_agent"
}

valid_external_communication_values = {"Yes", "No"}
valid_approval_required_values = {"Yes", "No", "Conditional"}
valid_status_values = {"Active", "Inactive", "Suspended"}

# -----------------------------
# Common restricted datasets
# -----------------------------
common_restricted_datasets = (
    "hr_data.csv;"
    "payroll.csv;"
    "employee_records.csv;"
    "customer_pii.csv"
)

# -----------------------------
# Agent permissions data
# -----------------------------
agent_permissions_data = [
    {
        "agent_id": "coordinator_agent",
        "agent_name": "Coordinator Agent",
        "agent_type": "orchestrator",
        "allowed_datasets": (
            "products.csv;"
            "sales_history.csv;"
            "inventory.csv;"
            "suppliers.csv;"
            "routes.csv;"
            "disruptions.csv;"
            "agent_permissions.csv;"
            "policy_rules.yaml"
        ),
        "allowed_tools": (
            "intent_parser;"
            "workflow_planner;"
            "agent_router"
        ),
        "restricted_datasets": common_restricted_datasets,
        "max_action_value": 50000,
        "can_external_communicate": "No",
        "approval_required": "Conditional",
        "status": "Active"
    },
    {
        "agent_id": "forecasting_agent",
        "agent_name": "Forecasting Agent",
        "agent_type": "business_agent",
        "allowed_datasets": (
            "products.csv;"
            "sales_history.csv"
        ),
        "allowed_tools": (
            "forecast_model;"
            "trend_detector"
        ),
        "restricted_datasets": common_restricted_datasets,
        "max_action_value": 0,
        "can_external_communicate": "No",
        "approval_required": "No",
        "status": "Active"
    },
    {
        "agent_id": "inventory_agent",
        "agent_name": "Inventory Agent",
        "agent_type": "business_agent",
        "allowed_datasets": (
            "products.csv;"
            "inventory.csv"
        ),
        "allowed_tools": (
            "stock_checker;"
            "shortage_calculator"
        ),
        "restricted_datasets": common_restricted_datasets,
        "max_action_value": 0,
        "can_external_communicate": "No",
        "approval_required": "No",
        "status": "Active"
    },
    {
        "agent_id": "procurement_agent",
        "agent_name": "Procurement Agent",
        "agent_type": "business_agent",
        "allowed_datasets": (
            "products.csv;"
            "inventory.csv;"
            "suppliers.csv"
        ),
        "allowed_tools": (
            "supplier_selector;"
            "procurement_value_calculator;"
            "capacity_checker"
        ),
        "restricted_datasets": common_restricted_datasets,
        "max_action_value": 50000,
        "can_external_communicate": "No",
        "approval_required": "Conditional",
        "status": "Active"
    },
    {
        "agent_id": "logistics_agent",
        "agent_name": "Logistics Agent",
        "agent_type": "business_agent",
        "allowed_datasets": (
            "suppliers.csv;"
            "routes.csv;"
            "disruptions.csv"
        ),
        "allowed_tools": (
            "route_optimizer;"
            "route_score_calculator;"
            "disruption_checker"
        ),
        "restricted_datasets": common_restricted_datasets,
        "max_action_value": 0,
        "can_external_communicate": "No",
        "approval_required": "Conditional",
        "status": "Active"
    },
    {
        "agent_id": "policy_engine",
        "agent_name": "Policy Engine",
        "agent_type": "governance_agent",
        "allowed_datasets": (
            "agent_permissions.csv;"
            "policy_rules.yaml"
        ),
        "allowed_tools": (
            "policy_checker;"
            "permission_validator"
        ),
        "restricted_datasets": common_restricted_datasets,
        "max_action_value": 0,
        "can_external_communicate": "No",
        "approval_required": "No",
        "status": "Active"
    },
    {
        "agent_id": "risk_scoring_engine",
        "agent_name": "Risk Scoring Engine",
        "agent_type": "governance_agent",
        "allowed_datasets": (
            "agent_permissions.csv;"
            "policy_rules.yaml;"
            "suppliers.csv;"
            "routes.csv;"
            "disruptions.csv"
        ),
        "allowed_tools": (
            "risk_score_calculator;"
            "risk_level_classifier"
        ),
        "restricted_datasets": common_restricted_datasets,
        "max_action_value": 0,
        "can_external_communicate": "No",
        "approval_required": "No",
        "status": "Active"
    },
    {
        "agent_id": "audit_logger",
        "agent_name": "Audit Logger",
        "agent_type": "logging_agent",
        "allowed_datasets": (
            "audit_logs.db;"
            "agent_activity_log.csv"
        ),
        "allowed_tools": (
            "audit_writer;"
            "log_exporter"
        ),
        "restricted_datasets": common_restricted_datasets,
        "max_action_value": 0,
        "can_external_communicate": "No",
        "approval_required": "No",
        "status": "Active"
    },
    {
        "agent_id": "dashboard_agent",
        "agent_name": "Dashboard Agent",
        "agent_type": "presentation_agent",
        "allowed_datasets": (
            "products.csv;"
            "inventory.csv;"
            "suppliers.csv;"
            "routes.csv;"
            "disruptions.csv;"
            "audit_logs.db;"
            "agent_activity_log.csv"
        ),
        "allowed_tools": (
            "dashboard_renderer;"
            "approval_queue_viewer"
        ),
        "restricted_datasets": common_restricted_datasets,
        "max_action_value": 0,
        "can_external_communicate": "No",
        "approval_required": "No",
        "status": "Active"
    },
    {
        "agent_id": "experimental_agent",
        "agent_name": "Experimental Agent",
        "agent_type": "business_agent",
        "allowed_datasets": "products.csv",
        "allowed_tools": "none",
        "restricted_datasets": (
            "hr_data.csv;"
            "payroll.csv;"
            "employee_records.csv;"
            "customer_pii.csv;"
            "suppliers.csv;"
            "inventory.csv"
        ),
        "max_action_value": 0,
        "can_external_communicate": "No",
        "approval_required": "Yes",
        "status": "Suspended"
    }
]

# -----------------------------
# Create DataFrame
# -----------------------------
agent_permissions_df = pd.DataFrame(agent_permissions_data)

# -----------------------------
# Expected column order
# -----------------------------
expected_columns = [
    "agent_id",
    "agent_name",
    "agent_type",
    "allowed_datasets",
    "allowed_tools",
    "restricted_datasets",
    "max_action_value",
    "can_external_communicate",
    "approval_required",
    "status"
]

agent_permissions_df = agent_permissions_df[expected_columns]

# -----------------------------
# Validation checks
# -----------------------------

# 1. Exact row count
expected_rows = 10
actual_rows = len(agent_permissions_df)

if actual_rows != expected_rows:
    raise ValueError(f"Expected {expected_rows} agents, but found {actual_rows}")

# 2. Unique agent_id
if agent_permissions_df["agent_id"].duplicated().any():
    duplicate_agents = agent_permissions_df[
        agent_permissions_df["agent_id"].duplicated()
    ]["agent_id"].tolist()
    raise ValueError(f"Duplicate agent_id found: {duplicate_agents}")

# 3. Required columns present
missing_columns = set(expected_columns) - set(agent_permissions_df.columns)

if missing_columns:
    raise ValueError(f"Missing required columns: {missing_columns}")

# 4. No null values
if agent_permissions_df.isnull().any().any():
    raise ValueError("Null values found in agent_permissions.csv")

# 5. Validate agent_type
invalid_agent_types = set(agent_permissions_df["agent_type"]) - valid_agent_types

if invalid_agent_types:
    raise ValueError(f"Invalid agent_type values found: {invalid_agent_types}")

# 6. Validate can_external_communicate
invalid_external_values = (
    set(agent_permissions_df["can_external_communicate"])
    - valid_external_communication_values
)

if invalid_external_values:
    raise ValueError(
        f"Invalid can_external_communicate values found: {invalid_external_values}"
    )

# 7. Validate approval_required
invalid_approval_values = (
    set(agent_permissions_df["approval_required"])
    - valid_approval_required_values
)

if invalid_approval_values:
    raise ValueError(
        f"Invalid approval_required values found: {invalid_approval_values}"
    )

# 8. Validate status
invalid_status_values = set(agent_permissions_df["status"]) - valid_status_values

if invalid_status_values:
    raise ValueError(f"Invalid status values found: {invalid_status_values}")

# 9. Validate max_action_value
if (agent_permissions_df["max_action_value"] < 0).any():
    raise ValueError("max_action_value cannot be negative")

# 10. Procurement agent must have 50000 limit
procurement_limit = agent_permissions_df.loc[
    agent_permissions_df["agent_id"] == "procurement_agent",
    "max_action_value"
].iloc[0]

if procurement_limit != 50000:
    raise ValueError("procurement_agent must have max_action_value = 50000")

# 11. Coordinator agent must have 50000 limit
coordinator_limit = agent_permissions_df.loc[
    agent_permissions_df["agent_id"] == "coordinator_agent",
    "max_action_value"
].iloc[0]

if coordinator_limit != 50000:
    raise ValueError("coordinator_agent must have max_action_value = 50000")

# 12. All external communication should be No for MVP
if not (agent_permissions_df["can_external_communicate"] == "No").all():
    raise ValueError("All agents should have can_external_communicate = No for MVP")

# 13. Experimental agent should be suspended
experimental_status = agent_permissions_df.loc[
    agent_permissions_df["agent_id"] == "experimental_agent",
    "status"
].iloc[0]

if experimental_status != "Suspended":
    raise ValueError("experimental_agent should have status = Suspended")

# 14. Production agents should be Active
production_agents = agent_permissions_df[
    agent_permissions_df["agent_id"] != "experimental_agent"
]

if not (production_agents["status"] == "Active").all():
    raise ValueError("All production agents should have status = Active")

# 15. Procurement and logistics should require conditional approval
approval_expectations = {
    "procurement_agent": "Conditional",
    "logistics_agent": "Conditional",
    "coordinator_agent": "Conditional"
}

for agent_id, expected_approval in approval_expectations.items():
    actual_approval = agent_permissions_df.loc[
        agent_permissions_df["agent_id"] == agent_id,
        "approval_required"
    ].iloc[0]

    if actual_approval != expected_approval:
        raise ValueError(
            f"{agent_id} should have approval_required = {expected_approval}"
        )

# -----------------------------
# Save CSV
# -----------------------------
agent_permissions_df.to_csv(OUTPUT_FILE, index=False)

# -----------------------------
# Print summary
# -----------------------------
print("agent_permissions.csv generated successfully.")
print(f"Saved to: {OUTPUT_FILE}")
print(f"Total rows generated: {len(agent_permissions_df)}")
print(f"Total columns generated: {len(agent_permissions_df.columns)}")
print()

print("Agent type distribution:")
print(agent_permissions_df["agent_type"].value_counts())
print()

print("Approval requirement distribution:")
print(agent_permissions_df["approval_required"].value_counts())
print()

print("Status distribution:")
print(agent_permissions_df["status"].value_counts())
print()

print("Preview:")
print(agent_permissions_df)
