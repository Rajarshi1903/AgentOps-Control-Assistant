from typing import List
from pydantic import BaseModel, Field
from .common import BaseAgentOutput, Decision, RiskLevel


class PolicyEvaluationContext(BaseModel):
    run_id: str
    agent_id: str
    agent_status: str = "Active"

    dataset_accessed: str = ""
    tool_called: str = ""

    procurement_value: float = 0
    is_approved: str = "Yes"

    source_citation_missing: bool = False
    external_communication_attempted: bool = False
    restricted_data_accessed: bool = False

    route_disruption_exists: bool = False
    route_disruption_severity: str = "None"
    route_disruption_status: str = "None"

    forecast_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    unauthorized_tool_used: bool = False


class TriggeredPolicy(BaseModel):
    policy_id: str
    policy_name: str
    category: str
    action: Decision
    severity: str
    message: str


class PolicyEngineOutput(BaseAgentOutput):
    evaluated_agent_id: str
    triggered_policies: List[TriggeredPolicy] = Field(default_factory=list)
    policy_decision: Decision
    decision_priority_applied: str


class RiskFactorTriggered(BaseModel):
    factor: str
    points: int
    category: str


class RiskScoringOutput(BaseAgentOutput):
    base_score: int
    risk_factors_triggered: List[RiskFactorTriggered] = Field(default_factory=list)
    calculated_score: int
    final_risk_score: int
    risk_level: RiskLevel
    score_cap_applied: bool

class HumanApprovalOutput(BaseAgentOutput):
    approval_id: str
    approval_required: bool
    approval_status: str
    requested_by_agent: str
    reviewer_role: str
    action_under_review: str

class AuditLoggerOutput(BaseAgentOutput):
    audit_event_id: str
    database_path: str
    records_written: int
    audit_status: str