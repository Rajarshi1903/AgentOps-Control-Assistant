from typing import List, Optional, Any, Dict
from pydantic import Field
from .common import BaseAgentOutput


class CoordinatorOutput(BaseAgentOutput):
    intent: str
    product_input: str
    resolved_product_id: str
    resolved_product_name: str
    region: str
    workflow: List[str]
    requested_datasets: List[str]
    forbidden_datasets: List[str]
    forbidden_steps: List[str]
    user_requested_restricted_data: bool
    user_requested_no_citations: bool
    external_communication_requested: bool


class ForecastingOutput(BaseAgentOutput):
    product_id: str
    region: str
    forecast_horizon_days: int = 1
    forecasted_demand: int
    historical_avg_demand: float
    recent_avg_demand: float
    demand_spike_detected: bool
    forecast_confidence: float = Field(ge=0.0, le=1.0)
    visualization_files: List[str]= Field(default_factory=list)
    method_used: str


class InventoryOutput(BaseAgentOutput):
    product_id: str
    region: str
    warehouse_id: str
    forecasted_demand: int
    current_stock: int
    safety_stock: int
    reorder_point: int
    shortage_quantity: int
    procurement_required: bool
    stock_position: str
    calculation: str


class ProcurementOutput(BaseAgentOutput):
    product_id: str
    region: str
    recommended_quantity: int
    recommended_supplier_id: Optional[str] = None
    recommended_supplier_name: Optional[str] = None
    supplier_region: Optional[str] = None
    unit_cost: Optional[float] = None
    lead_time_days: Optional[int] = None
    reliability_score: Optional[int] = None
    is_approved: Optional[str] = None
    compliance_status: Optional[str] = None
    max_capacity: Optional[int] = None
    procurement_value: float = 0
    supplier_selection_reason: str


class LogisticsOutput(BaseAgentOutput):
    supplier_id: Optional[str] = None
    destination_region: str
    warehouse_id: str
    recommended_route_id: Optional[str] = None
    origin_region: Optional[str] = None
    destination_node: Optional[str] = None
    transport_mode: Optional[str] = None
    distance_km: Optional[int] = None
    base_cost: float = 0
    estimated_time_days: int = 0
    route_risk_level: str = "None"
    route_score: float = 0
    route_disruption_exists: bool = False
    route_disruption_severity: str = "None"
    route_disruption_status: str = "None"
    impact_delay_days: int = 0
    impact_cost: float = 0
    adjusted_time_days: int = 0
    adjusted_route_cost: float = 0



class FinalResponseOutput(BaseAgentOutput):
    final_decision: str
    response_summary: str
    recommended_next_action: str
    business_summary: Dict[str, Any]
    governance_summary: Dict[str, Any]
    evidence_summary: List[Dict[str, Any]]
    detailed_response: str
    natural_language_explanation: str

