from typing import Any, Dict, List, TypedDict

from .agent_outputs import (
    CoordinatorOutput,
    ForecastingOutput,
    InventoryOutput,
    ProcurementOutput,
    LogisticsOutput,
)

from .governance import (
    PolicyEvaluationContext,
    PolicyEngineOutput,
    RiskScoringOutput,
    HumanApprovalOutput,
    AuditLoggerOutput,
)

from .policy_rag import PolicyRAGDecision


class AgentGraphState(TypedDict, total=False):
    # ========================================================
    # Run metadata
    # ========================================================
    run_id: str
    user_query: str
    user_role: str

    # ========================================================
    # Coordinator / routing
    # ========================================================
    intent: str

    # Final validated workflow steps that graph router should execute.
    workflow_steps: List[str]

    # Steps explicitly requested by the user or extracted by Coordinator.
    requested_steps: List[str]

    # Steps explicitly forbidden by the user.
    # Example: "Do not check inventory" -> ["inventory"]
    forbidden_steps: List[str]

    # Steps already completed by the graph.
    completed_steps: List[str]

    # Optional next-step routing field, if used anywhere.
    next_step: str

    # Tracks why a step was skipped.
    # Example:
    # {
    #   "inventory": "Skipped because user explicitly forbade this step."
    # }
    skip_reason: Dict[str, str]

    # Supplier selection strategy extracted by Coordinator.
    # Example: compliance_first, cheapest, fastest, highest_reliability
    selection_strategy: str

    # ========================================================
    # Extracted business entities
    # ========================================================
    product_id: str
    product_name: str
    region: str
    supplier_id: str

    # ========================================================
    # Coordinator output
    # ========================================================
    coordinator_output: CoordinatorOutput

    # ========================================================
    # Business agent outputs
    # ========================================================
    forecasting_output: ForecastingOutput
    inventory_output: InventoryOutput
    procurement_output: ProcurementOutput
    logistics_output: LogisticsOutput

    # ========================================================
    # Governance context and outputs
    # ========================================================

    # Existing policy context schema, kept for backward compatibility.
    policy_context: PolicyEvaluationContext

    # New normalized/factual policy context built from actual state.
    # This should eventually be produced by policy_context_builder.py.
    policy_context_output: Dict[str, Any]

    policy_rag_decision: PolicyRAGDecision
    policy_output: PolicyEngineOutput
    risk_output: RiskScoringOutput
    approval_output: HumanApprovalOutput

    # Audit logger output.
    audit_output: AuditLoggerOutput

    # Optional direct audit events if still used elsewhere.
    audit_events: List[Dict[str, Any]]

    # ========================================================
    # Data access governance
    # ========================================================

    # Datasets explicitly requested or mentioned by user/query.
    # Example: ["payroll.csv"]
    requested_datasets: List[str]

    # Datasets explicitly forbidden by user/query.
    # Example: ["suppliers.csv"]
    forbidden_datasets: List[str]

    # Datasets actually accessed successfully by agents.
    # Example: ["inventory.csv", "products.csv"]
    dataset_accessed: List[str]

    # Datasets agents attempted to access, whether allowed or denied.
    # Example: ["inventory.csv", "payroll.csv"]
    dataset_access_attempted: List[str]

    # Full access audit log from data_access_guard.py.
    # Each item records agent_id, file_name, allowed/denied, restricted, reason, etc.
    data_access_log: List[Dict[str, Any]]

    # True if user requested or mentioned a restricted dataset.
    # Example: "Use payroll.csv..." -> True
    user_requested_restricted_data: bool

    # True if restricted data was actually attempted/accessed.
    restricted_data_accessed: bool

    # True if any dataset access was denied because it was unauthorized,
    # restricted, not allowlisted, or forbidden by user.
    unauthorized_dataset_accessed: bool

    # True if an agent attempted a dataset explicitly forbidden by user.
    agent_accessed_forbidden_dataset: bool

    # ========================================================
    # User instruction / constraint governance
    # ========================================================

    # True if the pipeline violated a user constraint.
    # Example: user says "Do not run procurement" but procurement runs.
    user_instruction_violation: bool

    # True if user explicitly requested no citations/source records/policy evidence.
    user_requested_no_citations: bool

    # True if final/business recommendation actually lacks required source traceability.
    source_citation_missing: bool

    # ========================================================
    # Tool / external communication governance
    # ========================================================

    # Optional single tool name if older code uses this.
    tool_called: str

    # Optional list of tools called, useful for future tracking.
    tools_called: List[str]

    # True if user requested external communication.
    # Example: "Send the purchase order to the supplier."
    external_communication_requested: bool

    # True if an agent actually attempted external communication.
    external_communication_attempted: bool

    # True if an unauthorized tool was used or attempted.
    unauthorized_tool_used: bool

    # Optional generic agent status.
    agent_status: str

    # ========================================================
    # Final decision and final response
    # ========================================================
    final_decision: str

    # Structured final response object/dict returned by final_response_agent.
    final_response_output: Dict[str, Any]

    # Markdown/string final response returned by final_response_agent.
    final_response: str

    #Time logging
    node_timings: List[Dict[str, Any]]
    workflow_duration_seconds: float
    last_completed_step_timing: Dict[str, Any]


    # ========================================================
    # Errors
    # ========================================================
    # Use Any because wrappers may append strings or dict errors like:
    # {"step": "audit", "error": "..."}
    errors: List[Any]