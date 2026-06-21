from typing import Any, Dict, List
from pydantic import BaseModel


class FinalWorkflowResponse(BaseModel):
    run_id: str
    product_id: str
    product_name: str
    region: str

    forecast_summary: Dict[str, Any]
    inventory_summary: Dict[str, Any]
    procurement_summary: Dict[str, Any]
    logistics_summary: Dict[str, Any]
    governance_summary: Dict[str, Any]

    source_files: List[str]
    final_message: str