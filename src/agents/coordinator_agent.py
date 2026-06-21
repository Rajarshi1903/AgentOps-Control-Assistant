import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from src.services.llm_client import call_llm_json
from src.services.data_access_guard import (
    RESTRICTED_DATASETS,
    build_query_governance_flags,
    normalize_dataset_list,
    unique_preserve_order,
)


# ============================================================
# LLM Coordinator Agent
# ============================================================
# Purpose:
# Extracts intent, entities, selection strategy, requested workflow
# steps, forbidden workflow steps, and governance constraints from
# natural-language user query.
#
# LLM is the primary path.
# Regex/deterministic fallback is used if LLM extraction fails.
#
# Important:
# - LLM understands the user query.
# - Deterministic helpers catch obvious governance constraints.
# - Python validates all extracted values.
# - Python deterministically builds workflow_steps.
# - Downstream nodes receive top-level product_id, region,
#   supplier_id, selection_strategy, requested_steps, forbidden_steps,
#   requested_datasets, and governance flags.
# ============================================================


DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
PRODUCTS_FILE = DATA_DIR / "products.csv"
SUPPLIERS_FILE = DATA_DIR / "suppliers.csv"


VALID_REGIONS = {"North", "South", "East", "West"}

VALID_INTENTS = {
    "demand_spike",
    "forecast",
    "inventory",
    "procurement",
    "supplier_lookup",
    "logistics",
    "route_risk",
    "supply_chain_decision",
    "general",
}

VALID_SELECTION_STRATEGIES = {
    "compliance_first",
    "cheapest",
    "fastest",
    "highest_reliability",
}

VALID_WORKFLOW_STEPS = {
    "forecasting",
    "inventory",
    "procurement",
    "logistics",
    "policy",
    "risk",
    "approval",
    "audit",
    "final_response",
}

STEP_ALIASES = {
    "forecast": "forecasting",
    "forecasting": "forecasting",
    "inventory": "inventory",
    "stock": "inventory",
    "procurement": "procurement",
    "purchase": "procurement",
    "supplier": "procurement",
    "supplier_selection": "procurement",
    "logistics": "logistics",
    "route": "logistics",
    "routing": "logistics",
    "delivery": "logistics",
    "shipment": "logistics",
    "policy": "policy",
    "governance": "policy",
    "compliance": "policy",
    "risk": "risk",
    "approval": "approval",
    "human_review": "approval",
    "audit": "audit",
    "traceability": "audit",
    "final": "final_response",
    "final_response": "final_response",
}


# ============================================================
# Utility helpers
# ============================================================

def _safe_model_dump(model: Any) -> Dict[str, Any]:
    """
    Supports both Pydantic v1/v2 and dict objects.
    """

    if model is None:
        return {}

    if isinstance(model, dict):
        return model

    if hasattr(model, "model_dump"):
        return model.model_dump()

    if hasattr(model, "dict"):
        return model.dict()

    return {}


def _load_products() -> pd.DataFrame:
    """
    Loads products.csv.
    """

    if PRODUCTS_FILE.exists():
        return pd.read_csv(PRODUCTS_FILE)

    return pd.DataFrame()


def _load_suppliers() -> pd.DataFrame:
    """
    Loads suppliers.csv.
    """

    if SUPPLIERS_FILE.exists():
        return pd.read_csv(SUPPLIERS_FILE)

    return pd.DataFrame()


def _get_valid_product_ids() -> List[str]:
    """
    Returns valid product IDs from products.csv.
    """

    products = _load_products()

    if "product_id" not in products.columns:
        return []

    return products["product_id"].astype(str).tolist()


def _get_product_name_map() -> Dict[str, str]:
    """
    Returns product_id to product_name mapping.
    """

    products = _load_products()

    if "product_id" not in products.columns or "product_name" not in products.columns:
        return {}

    return {
        str(row["product_id"]): str(row["product_name"])
        for _, row in products.iterrows()
    }


def _get_valid_supplier_ids() -> List[str]:
    """
    Returns valid supplier IDs from suppliers.csv.
    """

    suppliers = _load_suppliers()

    if "supplier_id" not in suppliers.columns:
        return []

    return suppliers["supplier_id"].astype(str).unique().tolist()


def _normalize_region(value: Any) -> Optional[str]:
    """
    Normalizes region values into title case if possible.
    """

    if value is None:
        return None

    if not isinstance(value, str):
        return None

    value = value.strip()

    if not value:
        return None

    if value.lower() in {"null", "none"}:
        return None

    return value.title()


def _normalize_intent(value: Any) -> str:
    """
    Normalizes intent strings.
    """

    if value is None:
        return "general"

    if not isinstance(value, str):
        return "general"

    value = value.strip().lower().replace(" ", "_").replace("-", "_")

    if value in {"supply_chain", "full_supply_chain", "end_to_end"}:
        return "supply_chain_decision"

    return value


def _normalize_selection_strategy(value: Any) -> str:
    """
    Normalizes selection strategy.
    """

    if value is None:
        return "compliance_first"

    if not isinstance(value, str):
        return "compliance_first"

    value = value.strip().lower().replace(" ", "_").replace("-", "_")

    if value in {
        "lowest_cost",
        "lowest_price",
        "cost_first",
        "cost_priority",
        "price_first",
    }:
        return "cheapest"

    if value in {
        "reliability_first",
        "most_reliable",
        "reliable",
    }:
        return "highest_reliability"

    return value


def _as_bool(value: Any) -> bool:
    """
    Converts common bool-like values to bool.
    """

    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "y", "1"}

    if isinstance(value, (int, float)):
        return bool(value)

    return False


def _normalize_step_name(value: Any) -> Optional[str]:
    """
    Normalizes a workflow step name and applies aliases.
    """

    if value is None:
        return None

    if not isinstance(value, str):
        return None

    step = value.strip().lower().replace(" ", "_").replace("-", "_")

    step = STEP_ALIASES.get(step, step)

    if step in VALID_WORKFLOW_STEPS:
        return step

    return None


def _validate_workflow_steps(value: Any) -> List[str]:
    """
    Validates and cleans LLM-generated workflow step lists.
    """

    if not isinstance(value, list):
        return []

    cleaned_steps: List[str] = []

    for raw_step in value:
        step = _normalize_step_name(raw_step)

        if step and step not in cleaned_steps:
            cleaned_steps.append(step)

    return cleaned_steps


def _validate_string_list(value: Any) -> List[str]:
    """
    Validates and cleans a generic list of strings.
    """

    if value is None:
        return []

    if isinstance(value, str):
        value = [value]

    if not isinstance(value, list):
        return []

    cleaned: List[str] = []

    for item in value:
        if not isinstance(item, str):
            continue

        item = item.strip()

        if not item:
            continue

        if item.lower() in {"null", "none"}:
            continue

        if item not in cleaned:
            cleaned.append(item)

    return cleaned


def _detect_external_communication_request(user_query: str) -> bool:
    """
    Detects whether the user is asking the system to send/communicate externally.

    This is deterministic support. The LLM can also extract this field.
    """

    if not user_query:
        return False

    query_lower = user_query.lower()

    patterns = [
        "send email",
        "send an email",
        "email the supplier",
        "notify supplier",
        "send to supplier",
        "submit purchase order",
        "send purchase order",
        "externally communicate",
        "external communication",
        "send po",
        "dispatch purchase order",
    ]

    return any(pattern in query_lower for pattern in patterns)


# ============================================================
# Workflow routing
# ============================================================

def _remove_forbidden_steps(
    workflow_steps: List[str],
    forbidden_steps: List[str],
) -> Dict[str, Any]:
    """
    Removes user-forbidden steps from workflow_steps and records skip reasons.

    Governance steps like policy, audit, and final_response are not normally
    forbidden by our extraction logic, but this method preserves them if present.
    """

    forbidden_set = set(forbidden_steps)
    cleaned_steps: List[str] = []
    skip_reason: Dict[str, str] = {}

    for step in workflow_steps:
        if step in forbidden_set:
            skip_reason[step] = "Skipped because user explicitly forbade this workflow step."
            continue

        if step not in cleaned_steps:
            cleaned_steps.append(step)

    # Always preserve minimum governance traceability.
    for required_step in ["policy", "audit", "final_response"]:
        if required_step not in cleaned_steps:
            cleaned_steps.append(required_step)

    # final_response must be last.
    if "final_response" in cleaned_steps:
        cleaned_steps = [
            step for step in cleaned_steps
            if step != "final_response"
        ]
        cleaned_steps.append("final_response")

    return {
        "workflow_steps": cleaned_steps,
        "skip_reason": skip_reason,
    }


def _build_workflow_steps(
    intent: str,
    requested_steps: Optional[List[str]] = None,
    forbidden_steps: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Builds deterministic workflow steps.

    Priority:
    1. Use validated LLM requested_steps if available.
    2. Fall back to intent-based workflow mapping.
    3. Ensure mandatory governance steps.
    4. Remove forbidden steps.
    5. Ensure final_response is last.

    Returns:
        {
            "workflow_steps": [...],
            "skip_reason": {...}
        }
    """

    forbidden_steps = forbidden_steps or []

    if requested_steps:
        steps = list(requested_steps)

    elif intent in {"demand_spike", "supply_chain_decision"}:
        steps = [
            "forecasting",
            "inventory",
            "procurement",
            "logistics",
            "policy",
            "risk",
            "approval",
            "audit",
            "final_response",
        ]

    elif intent == "forecast":
        steps = [
            "forecasting",
            "policy",
            "risk",
            "audit",
            "final_response",
        ]

    elif intent == "inventory":
        steps = [
            "inventory",
            "policy",
            "audit",
            "final_response",
        ]

    elif intent == "procurement":
        steps = [
            "inventory",
            "procurement",
            "policy",
            "risk",
            "approval",
            "audit",
            "final_response",
        ]

    elif intent == "supplier_lookup":
        steps = [
            "procurement",
            "policy",
            "risk",
            "approval",
            "audit",
            "final_response",
        ]

    elif intent in {"logistics", "route_risk"}:
        steps = [
            "logistics",
            "policy",
            "risk",
            "approval",
            "audit",
            "final_response",
        ]

    else:
        steps = [
            "policy",
            "audit",
            "final_response",
        ]

    cleaned_steps: List[str] = []

    for step in steps:
        if step in VALID_WORKFLOW_STEPS and step not in cleaned_steps:
            cleaned_steps.append(step)

    # Always ensure governance traceability.
    for required_step in ["policy", "audit", "final_response"]:
        if required_step not in cleaned_steps:
            cleaned_steps.append(required_step)

    # Procurement/logistics need risk and approval unless explicitly forbidden.
    if any(step in cleaned_steps for step in ["procurement", "logistics"]):
        if "risk" not in cleaned_steps:
            cleaned_steps.append("risk")
        if "approval" not in cleaned_steps:
            cleaned_steps.append("approval")

    # Forecasting should include risk for confidence/risk tracking.
    if "forecasting" in cleaned_steps and "risk" not in cleaned_steps:
        cleaned_steps.append("risk")

    # final_response must be last.
    if "final_response" in cleaned_steps:
        cleaned_steps = [
            step for step in cleaned_steps
            if step != "final_response"
        ]
        cleaned_steps.append("final_response")

    return _remove_forbidden_steps(
        workflow_steps=cleaned_steps,
        forbidden_steps=forbidden_steps,
    )


# ============================================================
# Fallback extraction
# ============================================================

def _fallback_extract(user_query: str) -> Dict[str, Any]:
    """
    Deterministic fallback if LLM extraction fails.
    """

    query_lower = user_query.lower()

    product_match = re.search(r"\bP-\d+\b", user_query, re.IGNORECASE)
    supplier_match = re.search(r"\bS-\d+\b", user_query, re.IGNORECASE)

    region = None
    for candidate in VALID_REGIONS:
        if candidate.lower() in query_lower:
            region = candidate
            break

    governance_flags = build_query_governance_flags(user_query)

    requested_steps: List[str] = []

    if "forecast" in query_lower or "predict" in query_lower:
        requested_steps.append("forecasting")

    if "inventory" in query_lower or "stock" in query_lower:
        requested_steps.append("inventory")

    if (
        "procurement" in query_lower
        or "purchase" in query_lower
        or "procure" in query_lower
        or "supplier selection" in query_lower
        or "supplier recommendation" in query_lower
    ):
        requested_steps.append("procurement")

    if (
        "logistics" in query_lower
        or "route" in query_lower
        or "delivery" in query_lower
        or "shipment" in query_lower
        or "transport" in query_lower
        or "disruption" in query_lower
    ):
        requested_steps.append("logistics")

    if (
        "policy" in query_lower
        or "governance" in query_lower
        or "compliance" in query_lower
        or "policy evidence" in query_lower
        or "whether policy allows" in query_lower
    ):
        requested_steps.append("policy")

    if "risk" in query_lower or "risk score" in query_lower:
        requested_steps.append("risk")

    if (
        "approval" in query_lower
        or "approval owner" in query_lower
        or "manager approval" in query_lower
        or "human review" in query_lower
    ):
        requested_steps.append("approval")

    if (
        "audit" in query_lower
        or "audit-ready" in query_lower
        or "audit ready" in query_lower
        or "traceability" in query_lower
    ):
        requested_steps.append("audit")

    if "final_response" not in requested_steps:
        requested_steps.append("final_response")

    requested_steps = _validate_workflow_steps(requested_steps)
    forbidden_steps = _validate_workflow_steps(governance_flags.get("forbidden_steps", []))

    multi_step_supply_chain_request = len(
        set(requested_steps).intersection(
            {"forecasting", "inventory", "procurement", "logistics"}
        )
    ) >= 2

    if multi_step_supply_chain_request:
        intent = "supply_chain_decision"
    elif "route risk" in query_lower or "disruption" in query_lower:
        intent = "route_risk"
    elif "safe route" in query_lower or "safe delivery" in query_lower:
        intent = "route_risk"
    elif "logistics" in query_lower or "route" in query_lower:
        intent = "logistics"
    elif "supplier" in query_lower and ("find" in query_lower or "lookup" in query_lower):
        intent = "supplier_lookup"
    elif (
        "procurement" in query_lower
        or "purchase" in query_lower
        or "supplier selection" in query_lower
        or "procure" in query_lower
    ):
        intent = "procurement"
    elif "inventory" in query_lower or "stock" in query_lower:
        intent = "inventory"
    elif "forecast" in query_lower or "predict" in query_lower:
        intent = "forecast"
    elif "demand" in query_lower or "spike" in query_lower or "increased" in query_lower:
        intent = "demand_spike"
    else:
        intent = "general"

    selection_strategy = "compliance_first"

    if (
        "cheapest" in query_lower
        or "lowest cost" in query_lower
        or "lowest-cost" in query_lower
        or "lowest price" in query_lower
        or "prioritize cost" in query_lower
        or "cost over" in query_lower
        or "ignore approval" in query_lower
        or "approval is weaker" in query_lower
        or "compliance is weaker" in query_lower
        or "regardless of compliance" in query_lower
        or "not approved" in query_lower
        or "non-compliant" in query_lower
    ):
        selection_strategy = "cheapest"
    elif "fastest" in query_lower or "shortest lead time" in query_lower:
        selection_strategy = "fastest"
    elif "most reliable" in query_lower or "highest reliability" in query_lower:
        selection_strategy = "highest_reliability"

    return {
        "intent": intent,
        "product_id": product_match.group(0).upper() if product_match else None,
        "region": region,
        "supplier_id": supplier_match.group(0).upper() if supplier_match else None,
        "selection_strategy": selection_strategy,
        "requested_steps": requested_steps,
        "forbidden_steps": forbidden_steps,
        "requested_datasets": governance_flags.get("requested_datasets", []),
        "forbidden_datasets": governance_flags.get("forbidden_datasets", []),
        "user_requested_restricted_data": governance_flags.get(
            "user_requested_restricted_data",
            False,
        ),
        "user_requested_no_citations": governance_flags.get(
            "user_requested_no_citations",
            False,
        ),
        "external_communication_requested": _detect_external_communication_request(user_query),
        "confidence": 0.50,
        "reason": "Fallback regex extraction was used.",
    }


# ============================================================
# LLM extraction
# ============================================================

def _llm_extract_query(user_query: str) -> Dict[str, Any]:
    """
    Uses Azure OpenAI to extract structured intent, entities,
    workflow steps, and governance constraints.
    """

    valid_product_ids = _get_valid_product_ids()
    valid_supplier_ids = _get_valid_supplier_ids()

    system_message = """
You are an intent, workflow planning, and governance-constraint extraction agent for an AgentOps Control Tower.

Return strict JSON only.

You must extract:
- intent
- product_id
- region
- supplier_id
- selection_strategy
- requested_steps
- forbidden_steps
- requested_datasets
- forbidden_datasets
- user_requested_restricted_data
- user_requested_no_citations
- external_communication_requested
- confidence
- reason

Allowed intents:
demand_spike, forecast, inventory, procurement, supplier_lookup, logistics, route_risk, supply_chain_decision, general

Allowed regions:
North, South, East, West

Allowed selection_strategy:
compliance_first, cheapest, fastest, highest_reliability

Allowed requested_steps and forbidden_steps:
forecasting, inventory, procurement, logistics, policy, risk, approval, audit, final_response

Intent rules:
- If user asks for increased demand, demand spike, full supply response, or end-to-end supply chain impact, use demand_spike.
- If user asks for a complete, full, end-to-end, governed, or audit-ready supply chain decision, use supply_chain_decision.
- If user asks only for forecast or prediction, use forecast.
- If user asks only for inventory or stock, use inventory.
- If user asks for procurement plan, purchase recommendation, procure, or supplier selection, use procurement.
- If user asks only to find or look up a supplier, use supplier_lookup.
- If user asks for logistics, route, delivery path, or transportation, use logistics.
- If user asks for route disruption, route risk, safe delivery, or whether a supplier can deliver safely, use route_risk.
- If none of the above applies, use general.

Workflow planning rules:
- If user asks for forecast, include forecasting.
- If user asks for inventory, stock, current stock, reorder point, or availability, include inventory.
- If user asks for procurement, purchase recommendation, supplier recommendation, replenishment, or supplier selection, include procurement.
- If user asks for route, logistics, delivery, shipment, transportation, disruption, or route risk, include logistics.
- If user asks for policy, governance, compliance, policy evidence, or whether policy allows it, include policy.
- If user asks for risk score, risk level, or risk assessment, include risk.
- If user asks for approval, approval owner, manager approval, or human review, include approval.
- If user asks for audit-ready, audit log, traceability, or audit evidence, include audit.
- Always include final_response.
- If user asks for a complete, full, end-to-end, governed, or audit-ready supply chain decision, include all relevant business and governance steps: forecasting, inventory, procurement, logistics, policy, risk, approval, audit, final_response.

Forbidden step rules:
- If user says "do not check inventory", "do not run inventory", or "do not check stock", include inventory in forbidden_steps.
- If user says "do not procure", "do not select a supplier", "do not recommend a supplier", or "do not create procurement", include procurement in forbidden_steps.
- If user says "do not create route", "do not create logistics", "do not route", or "do not evaluate route", include logistics in forbidden_steps.
- If user says "do not forecast", include forecasting in forbidden_steps.
- If user says "do not request approval" or "do not create approval request", include approval in forbidden_steps.

Dataset governance rules:
- Extract any explicitly mentioned dataset names into requested_datasets, such as payroll.csv, inventory.csv, suppliers.csv, routes.csv.
- If user asks to use payroll, payroll.csv, salary data, HR records, employee records, compensation data, or personnel data, set user_requested_restricted_data to true.
- If user says not to access a specific dataset, put that dataset in forbidden_datasets.
- If no dataset is explicitly mentioned, requested_datasets should be [].
- If no dataset is explicitly forbidden, forbidden_datasets should be [].

Citation governance rules:
- If user asks to omit citations, source files, source records, policy evidence, or says "do not cite", set user_requested_no_citations to true.
- Otherwise set user_requested_no_citations to false.

External communication rules:
- If user asks to send an email, notify supplier, send a purchase order, submit a PO, or communicate externally, set external_communication_requested to true.
- Otherwise set external_communication_requested to false.

Selection strategy rules:
- If user says cheapest, lowest cost, lowest price, prioritize cost, cost over approval, ignore approval status, approval is weaker, compliance is weaker, not approved, non-compliant, or regardless of compliance, set selection_strategy to cheapest.
- If user asks for fastest supplier or shortest lead time, set selection_strategy to fastest.
- If user asks for most reliable supplier or highest reliability, set selection_strategy to highest_reliability.
- Otherwise use compliance_first.

Entity rules:
- Use null when a field is not present.
- Do not invent product IDs, regions, or supplier IDs.
- Prefer product IDs like P-101 when present.
- Prefer supplier IDs like S-001 when present.
- Output JSON only.
"""

    user_message = f"""
User query:
{user_query}

Known product IDs:
{valid_product_ids}

Known supplier IDs:
{valid_supplier_ids}

Return JSON in this exact shape:
{{
  "intent": "supply_chain_decision",
  "product_id": "P-101 or null",
  "region": "South or null",
  "supplier_id": "S-001 or null",
  "selection_strategy": "compliance_first",
  "requested_steps": ["forecasting", "inventory", "procurement", "logistics", "policy", "risk", "approval", "audit", "final_response"],
  "forbidden_steps": [],
  "requested_datasets": [],
  "forbidden_datasets": [],
  "user_requested_restricted_data": false,
  "user_requested_no_citations": false,
  "external_communication_requested": false,
  "confidence": 0.0,
  "reason": "short reason"
}}
"""

    messages = [
        {"role": "system", "content": system_message.strip()},
        {"role": "user", "content": user_message.strip()},
    ]

    return call_llm_json(
        messages=messages,
        temperature=0,
        max_tokens=1200,
    )


# ============================================================
# Validation
# ============================================================

def _validate_extraction(
    extracted: Dict[str, Any],
    user_query: str,
) -> Dict[str, Any]:
    """
    Validates LLM/fallback extraction against known products, suppliers,
    allowed regions, allowed intents, selection strategies, workflow steps,
    and governance fields.
    """

    errors: List[str] = []

    valid_product_ids = set(_get_valid_product_ids())
    valid_supplier_ids = set(_get_valid_supplier_ids())

    intent = _normalize_intent(extracted.get("intent") or "general")
    product_id = extracted.get("product_id")
    region = extracted.get("region")
    supplier_id = extracted.get("supplier_id")
    selection_strategy = extracted.get("selection_strategy") or "compliance_first"

    requested_steps = _validate_workflow_steps(
        extracted.get("requested_steps", [])
    )

    forbidden_steps = _validate_workflow_steps(
        extracted.get("forbidden_steps", [])
    )

    requested_datasets = normalize_dataset_list(
        extracted.get("requested_datasets", [])
    )

    forbidden_datasets = normalize_dataset_list(
        extracted.get("forbidden_datasets", [])
    )

    if isinstance(product_id, str):
        product_id = product_id.strip().upper()
        if product_id.lower() in {"null", "none", ""}:
            product_id = None

    if isinstance(supplier_id, str):
        supplier_id = supplier_id.strip().upper()
        if supplier_id.lower() in {"null", "none", ""}:
            supplier_id = None

    region = _normalize_region(region)
    selection_strategy = _normalize_selection_strategy(selection_strategy)

    if intent not in VALID_INTENTS:
        errors.append(f"Invalid intent extracted: {intent}")
        intent = "general"

    if product_id and product_id not in valid_product_ids:
        errors.append(f"Invalid product_id extracted: {product_id}")
        product_id = None

    if region and region not in VALID_REGIONS:
        errors.append(f"Invalid region extracted: {region}")
        region = None

    if supplier_id and supplier_id not in valid_supplier_ids:
        errors.append(f"Invalid supplier_id extracted: {supplier_id}")
        supplier_id = None

    if selection_strategy not in VALID_SELECTION_STRATEGIES:
        errors.append(f"Invalid selection_strategy extracted: {selection_strategy}")
        selection_strategy = "compliance_first"

    user_requested_restricted_data = _as_bool(
        extracted.get("user_requested_restricted_data", False)
    )

    if any(dataset in RESTRICTED_DATASETS for dataset in requested_datasets):
        user_requested_restricted_data = True

    user_requested_no_citations = _as_bool(
        extracted.get("user_requested_no_citations", False)
    )

    external_communication_requested = _as_bool(
        extracted.get("external_communication_requested", False)
    )

    # Deterministic governance supplement.
    deterministic_flags = build_query_governance_flags(user_query)

    requested_datasets = unique_preserve_order(
        requested_datasets + deterministic_flags.get("requested_datasets", [])
    )

    forbidden_steps = unique_preserve_order(
        forbidden_steps + _validate_workflow_steps(
            deterministic_flags.get("forbidden_steps", [])
        )
    )

    user_requested_restricted_data = bool(user_requested_restricted_data) or bool(
        deterministic_flags.get("user_requested_restricted_data", False)
    )

    user_requested_no_citations = bool(user_requested_no_citations) or bool(
        deterministic_flags.get("user_requested_no_citations", False)
    )

    external_communication_requested = bool(external_communication_requested) or bool(
        _detect_external_communication_request(user_query)
    )

    extracted["intent"] = intent
    extracted["product_id"] = product_id
    extracted["region"] = region
    extracted["supplier_id"] = supplier_id
    extracted["selection_strategy"] = selection_strategy
    extracted["requested_steps"] = requested_steps
    extracted["forbidden_steps"] = forbidden_steps
    extracted["requested_datasets"] = requested_datasets
    extracted["forbidden_datasets"] = forbidden_datasets
    extracted["user_requested_restricted_data"] = user_requested_restricted_data
    extracted["user_requested_no_citations"] = user_requested_no_citations
    extracted["external_communication_requested"] = external_communication_requested
    extracted["validation_errors"] = errors

    return extracted


# ============================================================
# Main LangGraph node
# ============================================================

def coordinator_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    LLM-powered Coordinator Agent.

    LLM is primary.
    Regex extraction is fallback.

    Returns top-level fields as well as coordinator_output so downstream
    nodes can reliably read:
    - product_id
    - region
    - supplier_id
    - selection_strategy
    - requested_steps
    - forbidden_steps
    - requested_datasets
    - forbidden_datasets
    - governance flags
    - workflow_steps
    """

    user_query = state.get("user_query", "")

    try:
        extracted = _llm_extract_query(user_query)
        extraction_source = "llm"
        llm_error = None

    except Exception as exc:
        extracted = _fallback_extract(user_query)
        extracted["llm_error"] = str(exc)
        extraction_source = "fallback"
        llm_error = str(exc)

    extracted = _validate_extraction(
        extracted=extracted,
        user_query=user_query,
    )

    product_name_map = _get_product_name_map()

    product_id = extracted.get("product_id") or state.get("product_id")
    region = extracted.get("region") or state.get("region")
    supplier_id = extracted.get("supplier_id") or state.get("supplier_id")
    selection_strategy = extracted.get("selection_strategy") or "compliance_first"

    requested_steps = extracted.get("requested_steps", [])
    forbidden_steps = extracted.get("forbidden_steps", [])
    requested_datasets = extracted.get("requested_datasets", [])
    forbidden_datasets = extracted.get("forbidden_datasets", [])

    user_requested_restricted_data = bool(
        extracted.get("user_requested_restricted_data", False)
    )
    user_requested_no_citations = bool(
        extracted.get("user_requested_no_citations", False)
    )
    external_communication_requested = bool(
        extracted.get("external_communication_requested", False)
    )

    if isinstance(product_id, str):
        product_id = product_id.strip().upper()

    if isinstance(supplier_id, str):
        supplier_id = supplier_id.strip().upper()

    region = _normalize_region(region)

    workflow_result = _build_workflow_steps(
        intent=extracted["intent"],
        requested_steps=requested_steps,
        forbidden_steps=forbidden_steps,
    )

    workflow_steps = workflow_result["workflow_steps"]
    skip_reason = workflow_result["skip_reason"]

    product_name = product_name_map.get(product_id)

    validation_errors = extracted.get("validation_errors", [])

    coordinator_output = {
        "agent_id": "coordinator_agent",
        "agent_name": "LLM Coordinator Agent",
        "intent": extracted["intent"],
        "product_id": product_id,
        "product_name": product_name,
        "region": region,
        "supplier_id": supplier_id,
        "selection_strategy": selection_strategy,
        "requested_steps": requested_steps,
        "forbidden_steps": forbidden_steps,
        "requested_datasets": requested_datasets,
        "forbidden_datasets": forbidden_datasets,
        "user_requested_restricted_data": user_requested_restricted_data,
        "user_requested_no_citations": user_requested_no_citations,
        "external_communication_requested": external_communication_requested,
        "workflow_steps": workflow_steps,
        "skip_reason": skip_reason,
        "confidence": extracted.get("confidence", 0.0),
        "reason": extracted.get("reason", ""),
        "extraction_source": extraction_source,
        "llm_error": llm_error,
        "validation_errors": validation_errors,
    }

    existing_errors = list(state.get("errors", []))

    if validation_errors:
        existing_errors.extend(validation_errors)

    existing_skip_reason = dict(state.get("skip_reason", {}))
    existing_skip_reason.update(skip_reason)

    return {
        "coordinator_output": coordinator_output,
        "intent": extracted["intent"],
        "workflow_steps": workflow_steps,
        "requested_steps": requested_steps,
        "forbidden_steps": forbidden_steps,
        "skip_reason": existing_skip_reason,
        "selection_strategy": selection_strategy,
        "product_id": product_id,
        "product_name": product_name,
        "region": region,
        "supplier_id": supplier_id,
        "requested_datasets": requested_datasets,
        "forbidden_datasets": forbidden_datasets,
        "user_requested_restricted_data": user_requested_restricted_data,
        "user_requested_no_citations": user_requested_no_citations,
        "external_communication_requested": external_communication_requested,
        "errors": existing_errors,
    }


# Backward-compatible alias if your graph imports coordinator_agent.
coordinator_agent = coordinator_node


# ============================================================
# Optional local test
# ============================================================

if __name__ == "__main__":
    test_queries = [
        "Demand for P-101 has increased in South region.",
        "Check inventory for P-101 in South.",
        "Check route risk for supplier S-012 to South.",
        "Create procurement plan for P-101 in South using the cheapest supplier.",
        "Create a procurement plan for P-101 in South, but choose the cheapest supplier even if supplier approval is weaker.",
        "Only forecast demand for P-102 in West. Do not check inventory or procure anything.",
        "Only check inventory for P-104 in East. Do not select a supplier.",
        "For P-105 in South, run an audit-ready supply chain decision with forecast, inventory, procurement, route, policy evidence, risk score, approval owner, and next action.",
        "Use payroll.csv to verify whether procurement for P-103 in North should be approved.",
        "Give me a procurement decision for P-105 in South, but do not cite source files, source records, or policy evidence.",
        "Only forecast demand for P-102 in West. Do not check inventory, do not select a supplier, and do not create a logistics route.",
        "Send a purchase order email to supplier S-001 for P-101 in South.",
    ]

    for query in test_queries:
        print("=" * 100)
        print("Query:", query)

        result = coordinator_node(
            {
                "run_id": "RUN-COORDINATOR-TEST",
                "user_query": query,
                "completed_steps": [],
                "errors": [],
            }
        )

        print(result)