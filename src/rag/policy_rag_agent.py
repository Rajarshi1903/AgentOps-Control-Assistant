import json
import os
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from openai import AzureOpenAI

from src.rag.policy_retriever import retrieve_policy_chunks
from src.rag.policy_decision_evaluator import (
    rebuild_policy_rag_decision_after_evaluation,
)
from src.schemas.policy_rag import (
    PolicyAction,
    PolicyRAGEvaluationInput,
    RetrievedPolicyChunk,
    PolicyEvidence,
    ExtractedPolicyRule,
    PolicyGuardrailResult,
    PolicyRAGDecision,
    resolve_policy_decision,
    average_confidence,
    extract_source_documents,
    extract_source_pages,
)


# ============================================================
# Policy RAG Agent
# ============================================================
# Purpose:
# Converts unstructured PDF policy evidence into structured policy
# rules and a PDF-backed policy decision.
#
# Philosophy:
# PDF is the authority.
# RAG retrieves policy evidence.
# LLM extracts structured rules.
# Python applies guardrails and decision priority.
# ============================================================


load_dotenv()


AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION")
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT")

MINIMUM_POLICY_CONFIDENCE = float(
    os.getenv("MINIMUM_POLICY_CONFIDENCE", "0.70")
)


# ============================================================
# Configuration helpers
# ============================================================

def validate_llm_config() -> None:
    """
    Validates Azure OpenAI chat model configuration.
    """

    missing = []

    required = {
        "AZURE_OPENAI_ENDPOINT": AZURE_OPENAI_ENDPOINT,
        "AZURE_OPENAI_API_KEY": AZURE_OPENAI_API_KEY,
        "AZURE_OPENAI_API_VERSION": AZURE_OPENAI_API_VERSION,
        "AZURE_OPENAI_DEPLOYMENT": AZURE_OPENAI_DEPLOYMENT,
    }

    for key, value in required.items():
        if not value:
            missing.append(key)

    if missing:
        raise EnvironmentError(
            f"Missing Azure OpenAI LLM environment variables: {', '.join(missing)}"
        )


def get_azure_chat_client() -> AzureOpenAI:
    """
    Returns Azure OpenAI client for chat completion.
    """

    validate_llm_config()

    return AzureOpenAI(
        azure_endpoint=AZURE_OPENAI_ENDPOINT,
        api_key=AZURE_OPENAI_API_KEY,
        api_version=AZURE_OPENAI_API_VERSION,
    )


# ============================================================
# Pydantic compatibility helper
# ============================================================

def _safe_model_dump(model: Any) -> Dict[str, Any]:
    """
    Supports both Pydantic v1 and v2 serialization.
    """

    if hasattr(model, "model_dump"):
        return model.model_dump()

    if hasattr(model, "dict"):
        return model.dict()

    return dict(model)


def _as_dict(value: Any) -> Dict[str, Any]:
    """
    Converts dict-like/Pydantic objects into plain dictionary.
    """

    if value is None:
        return {}

    if isinstance(value, dict):
        return value

    if hasattr(value, "model_dump"):
        return value.model_dump()

    if hasattr(value, "dict"):
        return value.dict()

    return {}


# ============================================================
# Context builder from LangGraph state
# ============================================================

def build_policy_rag_context_from_state(
    state: Dict[str, Any]
) -> PolicyRAGEvaluationInput:
    """
    Builds PolicyRAGEvaluationInput from LangGraph state.

    This function collects governance-relevant fields from:
    - procurement_output
    - logistics_output
    - forecasting_output
    - state-level metadata
    """

    procurement_output = _as_dict(state.get("procurement_output"))
    logistics_output = _as_dict(state.get("logistics_output"))
    forecasting_output = _as_dict(state.get("forecasting_output"))

    source_files = []
    source_record_ids = []

    for output in [procurement_output, logistics_output, forecasting_output]:
        output_source_files = output.get("source_files", [])
        output_source_record_ids = output.get("source_record_ids", [])

        if isinstance(output_source_files, list):
            source_files.extend(output_source_files)

        if isinstance(output_source_record_ids, list):
            source_record_ids.extend(output_source_record_ids)

    source_files = list(dict.fromkeys(source_files))
    source_record_ids = list(dict.fromkeys(source_record_ids))

    source_citation_missing = len(source_files) == 0

    return PolicyRAGEvaluationInput(
        run_id=state.get("run_id", "RUN-UNKNOWN"),
        agent_id=state.get("evaluated_agent_id", "coordinator_agent"),
        agent_status=state.get("agent_status", "Active"),
        dataset_accessed=state.get("dataset_accessed", ""),
        tool_called=state.get("tool_called", ""),
        procurement_value=float(procurement_output.get("procurement_value", 0) or 0),
        is_approved=str(procurement_output.get("is_approved", "Yes") or "Yes"),
        compliance_status=str(
            procurement_output.get("compliance_status", "Compliant") or "Compliant"
        ),
        source_citation_missing=source_citation_missing,
        external_communication_attempted=bool(
            state.get("external_communication_attempted", False)
        ),
        restricted_data_accessed=bool(
            state.get("restricted_data_accessed", False)
        ),
        route_disruption_exists=bool(
            logistics_output.get("route_disruption_exists", False)
        ),
        route_disruption_severity=str(
            logistics_output.get("route_disruption_severity", "None") or "None"
        ),
        route_disruption_status=str(
            logistics_output.get("route_disruption_status", "None") or "None"
        ),
        forecast_confidence=float(
            forecasting_output.get("forecast_confidence", 1.0) or 1.0
        ),
        unauthorized_tool_used=bool(
            state.get("unauthorized_tool_used", False)
        ),
        source_files=source_files,
        source_record_ids=source_record_ids,
        additional_context={
            "product_id": state.get("product_id"),
            "region": state.get("region"),
            "supplier_id": state.get("supplier_id"),
            "final_decision_before_policy": state.get("final_decision"),
        },
    )


# ============================================================
# Retrieval query builder
# ============================================================

def build_policy_retrieval_tasks(
    context: PolicyRAGEvaluationInput
) -> List[Tuple[str, str, Optional[str]]]:
    """
    Builds targeted retrieval tasks from action context.

    Returns:
        list of tuples:
        (retrieval_intent, query, policy_area_filter)
    """

    tasks = []

    if context.procurement_value > 0:
        tasks.append(
            (
                "high_value_procurement",
                (
                    f"The agent recommended procurement worth INR "
                    f"{context.procurement_value}. What policy applies to "
                    f"procurement thresholds, high-value procurement, and human approval?"
                ),
                "high_value_procurement",
            )
        )

    if context.is_approved == "No" or context.compliance_status in [
        "Non-Compliant",
        "Under Review",
    ]:
        tasks.append(
            (
                "supplier_compliance",
                (
                    f"The selected supplier has approval status "
                    f"{context.is_approved} and compliance status "
                    f"{context.compliance_status}. What supplier compliance policy applies?"
                ),
                "supplier_compliance",
            )
        )

    if context.route_disruption_exists:
        tasks.append(
            (
                "route_disruption",
                (
                    f"The selected logistics route has disruption status "
                    f"{context.route_disruption_status} and severity "
                    f"{context.route_disruption_severity}. What route disruption "
                    f"policy applies?"
                ),
                "route_disruption",
            )
        )

    if context.restricted_data_accessed or context.dataset_accessed in [
        "hr_data.csv",
        "payroll.csv",
        "employee_records.csv",
        "customer_pii.csv",
    ]:
        tasks.append(
            (
                "restricted_data_access",
                (
                    f"The agent attempted to access dataset "
                    f"{context.dataset_accessed}. What restricted data access "
                    f"policy applies?"
                ),
                "restricted_data_access",
            )
        )

    if context.source_citation_missing:
        tasks.append(
            (
                "source_traceability",
                (
                    "The recommendation is missing source files or source record "
                    "identifiers. What source traceability policy applies?"
                ),
                "source_traceability",
            )
        )

    if context.external_communication_attempted:
        tasks.append(
            (
                "external_communication",
                (
                    "The agent attempted external communication such as supplier "
                    "email, vendor API call, purchase order submission, or external "
                    "notification. What external communication policy applies?"
                ),
                "external_communication",
            )
        )

    if context.unauthorized_tool_used:
        tasks.append(
            (
                "tool_usage",
                (
                    f"The agent attempted to use unauthorized tool "
                    f"{context.tool_called}. What tool usage policy applies?"
                ),
                "tool_usage",
            )
        )

    if context.agent_status != "Active":
        tasks.append(
            (
                "agent_status",
                (
                    f"The agent status is {context.agent_status}. What policy applies "
                    f"to suspended or inactive agents?"
                ),
                "agent_status",
            )
        )

    if context.forecast_confidence < 0.70:
        tasks.append(
            (
                "forecast_confidence",
                (
                    f"The forecast confidence is {context.forecast_confidence}. "
                    f"What policy applies to low forecast confidence?"
                ),
                "forecast_confidence",
            )
        )

    if not tasks:
        tasks.append(
            (
                "general_policy",
                (
                    "No obvious policy violation is present. What general governance "
                    "policy applies to allowing safe autonomous agent actions?"
                ),
                "general_policy",
            )
        )

    return tasks


# ============================================================
# Retrieval helper
# ============================================================

def retrieve_chunks_for_context(
    context: PolicyRAGEvaluationInput,
    top_k_per_task: int = 3
) -> Tuple[str, List[RetrievedPolicyChunk]]:
    """
    Retrieves relevant policy chunks for all applicable retrieval tasks.

    Uses policy_area filter first.
    If no chunks are found for a filtered search, falls back to unfiltered search.
    """

    retrieval_tasks = build_policy_retrieval_tasks(context)

    all_chunks = []
    combined_query_parts = []

    for retrieval_intent, query, policy_area_filter in retrieval_tasks:
        combined_query_parts.append(query)

        chunks = retrieve_policy_chunks(
            query=query,
            top_k=top_k_per_task,
            policy_area_filter=policy_area_filter,
        )

        if not chunks and policy_area_filter:
            chunks = retrieve_policy_chunks(
                query=query,
                top_k=top_k_per_task,
                policy_area_filter=None,
            )

        all_chunks.extend(chunks)

    # Deduplicate chunks by chunk_id while preserving order.
    deduped_chunks = []
    seen_chunk_ids = set()

    for chunk in all_chunks:
        if chunk.chunk_id not in seen_chunk_ids:
            deduped_chunks.append(chunk)
            seen_chunk_ids.add(chunk.chunk_id)

    combined_query = "\n".join(combined_query_parts)

    return combined_query, deduped_chunks


# ============================================================
# Prompt construction
# ============================================================

def build_extraction_prompt(
    context: PolicyRAGEvaluationInput,
    retrieved_chunks: List[RetrievedPolicyChunk]
) -> List[Dict[str, str]]:
    """
    Builds messages for Azure OpenAI chat completion.

    The LLM must extract structured policy rules only from retrieved PDF chunks.
    """

    action_context_json = json.dumps(
        _safe_model_dump(context),
        indent=2,
        ensure_ascii=False,
    )

    chunks_payload = []

    for index, chunk in enumerate(retrieved_chunks, start=1):
        chunks_payload.append(
            {
                "chunk_number": index,
                "chunk_id": chunk.chunk_id,
                "source_document": chunk.source_document,
                "page_number": chunk.page_number,
                "retrieval_score": chunk.retrieval_score,
                "metadata": chunk.metadata,
                "text": chunk.text,
            }
        )

    chunks_json = json.dumps(
        chunks_payload,
        indent=2,
        ensure_ascii=False,
    )

    system_message = """
You are a strict enterprise policy extraction agent for an AgentOps Control Tower.

The policy handbook PDF is the authoritative source.
You must extract policy rules only from the retrieved PDF chunks provided to you.
Do not invent policies.
Do not use outside knowledge.
Do not make free-form decisions without evidence.

Your task:
1. Read the action context.
2. Read the retrieved policy chunks.
3. Extract only applicable policy rules from the chunks.
4. Return strict JSON only.
5. Every extracted rule must include evidence_text copied from the retrieved chunks.
6. Every extracted rule must include source_document and source_page.
7. Allowed actions are only: Allow, Escalate, Block.
8. Allowed severities are only: Low, Medium, High, Critical.
9. If no policy rule clearly applies, return an empty rules list.

Important:
- If procurement value exceeds a threshold described in the chunks, extract the threshold and action.
- If supplier approval or compliance policy applies, extract the expected action.
- If route disruption policy applies, extract the expected action.
- If restricted data, missing source traceability, external communication, unauthorized tool usage, or inactive agent policy applies, extract the expected action.
- Do not return markdown.
- Do not wrap JSON in code fences.
"""

    user_message = f"""
ACTION CONTEXT:
{action_context_json}

RETRIEVED POLICY CHUNKS:
{chunks_json}

Return JSON in exactly this shape:

{{
  "rules": [
    {{
      "applicable": true,
      "policy_name": "string",
      "policy_area": "string",
      "condition_field": "string or null",
      "operator": "one of >, >=, <, <=, ==, !=, in, not_in, exists, not_exists or null",
      "threshold_value": 50000 or null,
      "expected_value": "string/number/boolean or null",
      "allowed_values": ["optional list"] or null,
      "action": "Allow or Escalate or Block",
      "severity": "Low or Medium or High or Critical",
      "evidence_text": "exact sentence or paragraph copied from retrieved chunks",
      "source_document": "source PDF filename",
      "source_page": 1,
      "chunk_id": "chunk id",
      "retrieval_score": 0.91,
      "confidence": 0.0 to 1.0,
      "extraction_notes": "short explanation"
    }}
  ],
  "final_reason": "short explanation of extracted policy rules",
  "overall_confidence": 0.0 to 1.0
}}
"""

    return [
        {"role": "system", "content": system_message.strip()},
        {"role": "user", "content": user_message.strip()},
    ]


# ============================================================
# LLM extraction
# ============================================================

def call_llm_for_policy_extraction(
    context: PolicyRAGEvaluationInput,
    retrieved_chunks: List[RetrievedPolicyChunk]
) -> Dict[str, Any]:
    """
    Calls Azure OpenAI to extract structured policy rules.
    """

    if not retrieved_chunks:
        return {
            "rules": [],
            "final_reason": "No retrieved policy chunks were available.",
            "overall_confidence": 0.0,
        }

    client = get_azure_chat_client()

    messages = build_extraction_prompt(
        context=context,
        retrieved_chunks=retrieved_chunks,
    )

    response = client.chat.completions.create(
        model=AZURE_OPENAI_DEPLOYMENT,
        messages=messages,
        temperature=0,
        response_format={"type": "json_object"},
    )

    raw_content = response.choices[0].message.content

    try:
        parsed = json.loads(raw_content)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"LLM did not return valid JSON. Raw response: {raw_content}"
        ) from exc

    if "rules" not in parsed:
        raise ValueError(f"LLM JSON output missing 'rules': {parsed}")

    return parsed


# ============================================================
# Rule validation / conversion
# ============================================================

def _find_chunk_by_id(
    chunk_id: Optional[str],
    retrieved_chunks: List[RetrievedPolicyChunk]
) -> Optional[RetrievedPolicyChunk]:
    """
    Finds retrieved chunk by chunk_id.
    """

    if not chunk_id:
        return None

    for chunk in retrieved_chunks:
        if chunk.chunk_id == chunk_id:
            return chunk

    return None


def convert_llm_rules_to_schema(
    llm_output: Dict[str, Any],
    retrieved_chunks: List[RetrievedPolicyChunk]
) -> List[ExtractedPolicyRule]:
    """
    Converts LLM JSON rules into validated ExtractedPolicyRule objects.
    Invalid or non-applicable rules are skipped.
    """

    extracted_rules = []

    for raw_rule in llm_output.get("rules", []):
        if not raw_rule.get("applicable", False):
            continue

        chunk = _find_chunk_by_id(
            raw_rule.get("chunk_id"),
            retrieved_chunks,
        )

        source_document = raw_rule.get("source_document")
        source_page = raw_rule.get("source_page")
        retrieval_score = raw_rule.get("retrieval_score")

        if chunk:
            source_document = source_document or chunk.source_document
            source_page = source_page or chunk.page_number
            retrieval_score = retrieval_score or chunk.retrieval_score

        evidence = PolicyEvidence(
            evidence_text=raw_rule.get("evidence_text", ""),
            source_document=source_document or "unknown_source_document",
            source_page=source_page,
            chunk_id=raw_rule.get("chunk_id"),
            retrieval_score=retrieval_score,
            citation_available=bool(source_document and source_page),
        )

        rule = ExtractedPolicyRule(
            applicable=True,
            policy_name=raw_rule.get("policy_name", "Unknown Policy"),
            policy_area=raw_rule.get("policy_area", "Unknown Policy Area"),
            condition_field=raw_rule.get("condition_field"),
            operator=raw_rule.get("operator"),
            threshold_value=raw_rule.get("threshold_value"),
            expected_value=raw_rule.get("expected_value"),
            allowed_values=raw_rule.get("allowed_values"),
            action=raw_rule.get("action", "Escalate"),
            severity=raw_rule.get("severity", "High"),
            evidence=evidence,
            confidence=float(raw_rule.get("confidence", 0.0)),
            extraction_notes=raw_rule.get("extraction_notes"),
        )

        extracted_rules.append(rule)

    return extracted_rules


# ============================================================
# Guardrails and decision resolution
# ============================================================

def build_guardrail_result(
    retrieved_chunks: List[RetrievedPolicyChunk],
    extracted_rules: List[ExtractedPolicyRule],
    llm_confidence: float,
    actionable_context: bool
) -> PolicyGuardrailResult:
    """
    Applies RAG guardrails.

    Rules:
    - no evidence -> Escalate
    - actionable context but no extracted rules -> Escalate
    - low confidence -> Escalate
    - missing citation -> Escalate
    - otherwise safe
    """

    evidence_available = bool(retrieved_chunks)

    citation_available = all(
        rule.evidence.citation_available
        and bool(rule.evidence.evidence_text)
        for rule in extracted_rules
    ) if extracted_rules else False

    actual_confidence = (
        average_confidence(extracted_rules)
        if extracted_rules
        else float(llm_confidence or 0.0)
    )

    confidence_ok = actual_confidence >= MINIMUM_POLICY_CONFIDENCE

    guardrails_triggered = []

    if not evidence_available:
        guardrails_triggered.append("no_policy_evidence_retrieved")

    if actionable_context and not extracted_rules:
        guardrails_triggered.append("no_applicable_policy_extracted")

    if not confidence_ok:
        guardrails_triggered.append("low_policy_interpretation_confidence")

    if extracted_rules and not citation_available:
        guardrails_triggered.append("missing_policy_citation")

    if guardrails_triggered:
        return PolicyGuardrailResult(
            evidence_available=evidence_available,
            confidence_ok=confidence_ok,
            citation_available=citation_available,
            decision_safe=False,
            guardrail_decision="Escalate",
            guardrail_reason=(
                "RAG policy guardrails triggered: "
                + ", ".join(guardrails_triggered)
            ),
            minimum_confidence_required=MINIMUM_POLICY_CONFIDENCE,
            actual_confidence=actual_confidence,
            guardrails_triggered=guardrails_triggered,
        )

    return PolicyGuardrailResult(
        evidence_available=evidence_available,
        confidence_ok=confidence_ok,
        citation_available=citation_available,
        decision_safe=True,
        guardrail_decision="Allow",
        guardrail_reason="Evidence, confidence, and citations are sufficient.",
        minimum_confidence_required=MINIMUM_POLICY_CONFIDENCE,
        actual_confidence=actual_confidence,
        guardrails_triggered=[],
    )


def _has_actionable_context(context: PolicyRAGEvaluationInput) -> bool:
    """
    Determines whether the context contains a policy-relevant signal.
    """

    return any(
        [
            context.procurement_value > 0,
            context.is_approved == "No",
            context.compliance_status in ["Non-Compliant", "Under Review"],
            context.route_disruption_exists,
            context.restricted_data_accessed,
            context.source_citation_missing,
            context.external_communication_attempted,
            context.unauthorized_tool_used,
            context.agent_status != "Active",
            context.forecast_confidence < 0.70,
        ]
    )


def resolve_final_rag_decision(
    extracted_rules: List[ExtractedPolicyRule],
    guardrail_result: PolicyGuardrailResult
) -> PolicyAction:
    """
    Resolves final decision using:
    Block > Escalate > Allow
    """

    rule_actions = [rule.action for rule in extracted_rules]

    if guardrail_result.guardrail_decision != "Allow":
        rule_actions.append(guardrail_result.guardrail_decision)

    return resolve_policy_decision(rule_actions)


# ============================================================
# Main public function
# ============================================================

def evaluate_policy_with_rag(
    context: PolicyRAGEvaluationInput,
    top_k_per_task: int = 3
) -> PolicyRAGDecision:
    """
    Main PDF-first RAG policy evaluation function.

    Args:
        context: structured action context
        top_k_per_task: chunks retrieved per policy retrieval task

    Returns:
        PolicyRAGDecision
    """

    combined_query, retrieved_chunks = retrieve_chunks_for_context(
        context=context,
        top_k_per_task=top_k_per_task,
    )

    actionable_context = _has_actionable_context(context)

    llm_output = call_llm_for_policy_extraction(
        context=context,
        retrieved_chunks=retrieved_chunks,
    )

    extracted_rules = convert_llm_rules_to_schema(
        llm_output=llm_output,
        retrieved_chunks=retrieved_chunks,
    )

    llm_confidence = float(llm_output.get("overall_confidence", 0.0) or 0.0)

    guardrail_result = build_guardrail_result(
        retrieved_chunks=retrieved_chunks,
        extracted_rules=extracted_rules,
        llm_confidence=llm_confidence,
        actionable_context=actionable_context,
    )

    final_decision = resolve_final_rag_decision(
        extracted_rules=extracted_rules,
        guardrail_result=guardrail_result,
    )

    final_confidence = (
        average_confidence(extracted_rules)
        if extracted_rules
        else llm_confidence
    )

    if final_confidence < 0:
        final_confidence = 0.0

    if final_confidence > 1:
        final_confidence = 1.0

    if extracted_rules:
        final_reason = llm_output.get(
            "final_reason",
            "Policy decision generated from retrieved PDF evidence.",
        )
    else:
        final_reason = (
            "No applicable policy rule was extracted from the retrieved PDF evidence."
        )

    if guardrail_result.guardrails_triggered:
        final_reason = (
            final_reason
            + " Guardrail note: "
            + guardrail_result.guardrail_reason
        )

    initial_decision = PolicyRAGDecision(
        run_id=context.run_id,
        query=combined_query,
        decision=final_decision,
        triggered_rules=extracted_rules,
        retrieved_chunks=retrieved_chunks,
        guardrail_result=guardrail_result,
        final_reason=final_reason,
        evidence_available=bool(retrieved_chunks),
        confidence=round(float(final_confidence), 2),
        decision_priority_applied="Block > Escalate > Allow",
        source_documents=extract_source_documents(extracted_rules),
        source_pages=extract_source_pages(extracted_rules),
    )

    evaluated_decision, _ = rebuild_policy_rag_decision_after_evaluation(
        original_decision=initial_decision,
        context=context,
    )

    return evaluated_decision


def evaluate_policy_with_rag_from_state(
    state: Dict[str, Any],
    top_k_per_task: int = 3
) -> PolicyRAGDecision:
    """
    Convenience function for LangGraph state.

    Builds PolicyRAGEvaluationInput from state and evaluates policy with RAG.
    """

    context = build_policy_rag_context_from_state(state)

    return evaluate_policy_with_rag(
        context=context,
        top_k_per_task=top_k_per_task,
    )


# ============================================================
# Local manual tests
# ============================================================

if __name__ == "__main__":
    test_contexts = [
        PolicyRAGEvaluationInput(
            run_id="RUN-RAG-TEST-001",
            agent_id="procurement_agent",
            procurement_value=387000,
            is_approved="Yes",
            compliance_status="Compliant",
            source_files=["supplier.csv", "inventory.csv"],
            source_record_ids=["S-001", "INV-003"],
        ),
        PolicyRAGEvaluationInput(
            run_id="RUN-RAG-TEST-002",
            agent_id="procurement_agent",
            procurement_value=25000,
            is_approved="No",
            compliance_status="Non-Compliant",
            source_files=["suppliers.csv"],
            source_record_ids=["S-002"],
        ),
        PolicyRAGEvaluationInput(
            run_id="RUN-RAG-TEST-003",
            agent_id="logistics_agent",
            route_disruption_exists=True,
            route_disruption_status="Active",
            route_disruption_severity="High",
            source_files=["routes.csv", "disruptions.csv"],
            source_record_ids=["R-027", "D-001"],
        ),
        PolicyRAGEvaluationInput(
            run_id="RUN-RAG-TEST-004",
            agent_id="experimental_agent",
            dataset_accessed="payroll.csv",
            restricted_data_accessed=True,
            source_files=["agent_permissions.csv"],
            source_record_ids=["experimental_agent"],
        ),
    ]

    for context in test_contexts:
        print("=" * 100)
        print("Run ID:", context.run_id)
        print("Agent:", context.agent_id)

        decision = evaluate_policy_with_rag(context)

        print("Decision:", decision.decision)
        print("Confidence:", decision.confidence)
        print("Evidence available:", decision.evidence_available)
        print("Final reason:", decision.final_reason)
        print("Triggered rules:", len(decision.triggered_rules))

        for rule in decision.triggered_rules:
            print("-" * 80)
            print("Policy:", rule.policy_name)
            print("Area:", rule.policy_area)
            print("Action:", rule.action)
            print("Severity:", rule.severity)
            print("Condition:", rule.condition_field, rule.operator, rule.threshold_value or rule.expected_value)
            print("Evidence:", rule.evidence.evidence_text[:300])
            print("Source:", rule.evidence.source_document, "page", rule.evidence.source_page)