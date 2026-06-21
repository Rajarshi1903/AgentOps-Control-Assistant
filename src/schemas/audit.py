from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field
from .common import ApprovalStatus, utc_now


class HumanApprovalOutput(BaseModel):
    run_id: str
    approval_id: str
    approval_required: bool
    approval_status: ApprovalStatus
    requested_by_agent: str
    reviewer_role: str
    action_under_review: str
    decision_options: List[str]
    created_at: datetime = Field(default_factory=utc_now)
    decision_at: Optional[datetime] = None
    reviewer_comments: Optional[str] = None


class AuditEvent(BaseModel):
    event_id: str
    run_id: str
    timestamp: datetime = Field(default_factory=utc_now)
    agent_id: str
    agent_name: str
    action_type: str
    dataset_accessed: str
    tool_called: str
    input_summary: str
    output_summary: str
    triggered_policies: List[str] = Field(default_factory=list)
    policy_decision: str = "Allow"
    risk_score: int = 0
    risk_level: str = "Low"
    approval_status: str = "Not Required"
    source_files: List[str] = Field(default_factory=list)
    final_decision: str = "Allow"