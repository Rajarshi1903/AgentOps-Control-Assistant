from datetime import datetime, timezone
from typing import List, Literal
from pydantic import BaseModel, Field


ExecutionStatus = Literal["success", "failed", "skipped"]
Decision = Literal["Allow", "Escalate", "Block"]
RiskLevel = Literal["Low", "Medium", "High", "Critical"]
ApprovalStatus = Literal["Pending", "Approved", "Rejected", "Not Required"]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class BaseAgentOutput(BaseModel):
    run_id: str
    step_id: str
    agent_id: str
    agent_name: str
    timestamp: datetime = Field(default_factory=utc_now)
    status: ExecutionStatus
    source_files: List[str] = Field(default_factory=list)
    source_record_ids: List[str] = Field(default_factory=list)
    message: str