from typing import Any, Dict, List, Optional, Literal, Union
from pydantic import BaseModel, Field


# ============================================================
# Controlled values
# ============================================================

PolicyAction = Literal["Allow", "Escalate", "Block"]

PolicySeverity = Literal["Low", "Medium", "High", "Critical"]

PolicyOperator = Literal[
    ">",
    ">=",
    "<",
    "<=",
    "==",
    "!=",
    "in",
    "not_in",
    "exists",
    "not_exists",
]

RetrievalIntent = Literal[
    "high_value_procurement",
    "supplier_compliance",
    "route_disruption",
    "restricted_data_access",
    "source_traceability",
    "external_communication",
    "tool_usage",
    "agent_status",
    "forecast_confidence",
    "general_policy",
]


# ============================================================
# 1. PolicyRAGEvaluationInput
# ============================================================
# This schema represents the structured action context that will
# be sent into the PDF-first RAG Policy Engine.
#
# It is similar to PolicyEvaluationContext, but designed for RAG.
# The RAG agent will use this context to decide what policy clauses
# should be retrieved from the policy handbook PDF.
# ============================================================

class PolicyRAGEvaluationInput(BaseModel):
    run_id: str
    agent_id: str
    agent_status: str = "Active"

    dataset_accessed: str = ""
    tool_called: str = ""

    procurement_value: float = 0
    is_approved: str = "Yes"
    compliance_status: str = "Compliant"

    source_citation_missing: bool = False
    external_communication_attempted: bool = False
    restricted_data_accessed: bool = False

    route_disruption_exists: bool = False
    route_disruption_severity: str = "None"
    route_disruption_status: str = "None"

    forecast_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    unauthorized_tool_used: bool = False

    source_files: List[str] = Field(default_factory=list)
    source_record_ids: List[str] = Field(default_factory=list)

    additional_context: Dict[str, Any] = Field(default_factory=dict)


# ============================================================
# 2. PolicyRAGQuery
# ============================================================
# This schema represents the query sent to the PDF retriever.
#
# Example:
# "The Procurement Agent recommended procurement worth INR 387000.
#  What policy applies to high-value procurement?"
# ============================================================

class PolicyRAGQuery(BaseModel):
    run_id: str
    query: str
    retrieval_intent: RetrievalIntent = "general_policy"
    top_k: int = Field(default=5, ge=1, le=20)

    action_context: Dict[str, Any] = Field(default_factory=dict)

    generated_by: str = "policy_rag_agent"


# ============================================================
# 3. RetrievedPolicyChunk
# ============================================================
# This schema represents a chunk retrieved from the PDF/vector store.
#
# Retrieved chunks are raw evidence candidates.
# Not every retrieved chunk necessarily becomes a triggered policy.
# ============================================================

class RetrievedPolicyChunk(BaseModel):
    chunk_id: str
    source_document: str
    page_number: Optional[int] = None
    text: str

    retrieval_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)

    metadata: Dict[str, Any] = Field(default_factory=dict)


# ============================================================
# 4. PolicyEvidence
# ============================================================
# This schema represents the exact policy evidence used for a
# policy rule.
#
# A retrieved chunk may be long, but evidence_text should contain
# the specific clause/sentence/paragraph used for the decision.
# ============================================================

class PolicyEvidence(BaseModel):
    evidence_text: str
    source_document: str
    source_page: Optional[int] = None
    chunk_id: Optional[str] = None

    retrieval_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)

    citation_available: bool = True


# ============================================================
# 5. ExtractedPolicyRule
# ============================================================
# This is the most important schema.
#
# It represents a structured policy rule extracted from unstructured
# PDF policy text.
#
# Example:
# PDF text:
# "Any procurement recommendation exceeding INR 50,000 must be
#  escalated to a human reviewer."
#
# Extracted rule:
# condition_field = procurement_value
# operator = >
# threshold_value = 50000
# action = Escalate
# ============================================================

class ExtractedPolicyRule(BaseModel):
    applicable: bool

    policy_name: str
    policy_area: str

    condition_field: Optional[str] = None
    operator: Optional[PolicyOperator] = None

    threshold_value: Optional[float] = None
    expected_value: Optional[Union[str, float, bool]] = None
    allowed_values: Optional[List[Union[str, float, bool]]] = None

    action: PolicyAction
    severity: PolicySeverity

    evidence: PolicyEvidence

    confidence: float = Field(ge=0.0, le=1.0)

    extraction_notes: Optional[str] = None


# ============================================================
# 6. PolicyGuardrailResult
# ============================================================
# Since PDF/RAG is less deterministic than YAML, guardrails are
# mandatory.
#
# Recommended behavior:
# - no evidence       -> Escalate
# - low confidence   -> Escalate
# - missing citation -> Escalate
# - block rule found -> Block
# ============================================================

class PolicyGuardrailResult(BaseModel):
    evidence_available: bool
    confidence_ok: bool
    citation_available: bool
    decision_safe: bool

    guardrail_decision: PolicyAction
    guardrail_reason: str

    minimum_confidence_required: float = Field(default=0.70, ge=0.0, le=1.0)
    actual_confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    guardrails_triggered: List[str] = Field(default_factory=list)


# ============================================================
# 7. PolicyRAGDecision
# ============================================================
# Final output from the PDF-first RAG Policy Engine.
#
# This decision is created after:
# 1. Building action context
# 2. Retrieving PDF chunks
# 3. Extracting structured policy rules
# 4. Applying extracted rules in Python
# 5. Applying guardrails
# 6. Resolving final decision priority
# ============================================================

class PolicyRAGDecision(BaseModel):
    run_id: str

    query: str
    decision: PolicyAction

    triggered_rules: List[ExtractedPolicyRule] = Field(default_factory=list)
    retrieved_chunks: List[RetrievedPolicyChunk] = Field(default_factory=list)

    guardrail_result: PolicyGuardrailResult

    final_reason: str
    evidence_available: bool

    confidence: float = Field(ge=0.0, le=1.0)

    decision_priority_applied: str = "Block > Escalate > Allow"

    source_documents: List[str] = Field(default_factory=list)
    source_pages: List[int] = Field(default_factory=list)

    generated_by: str = "pdf_first_policy_rag_engine"


# ============================================================
# Utility: decision priority
# ============================================================

DECISION_PRIORITY = {
    "Block": 3,
    "Escalate": 2,
    "Allow": 1,
}


def resolve_policy_decision(actions: List[PolicyAction]) -> PolicyAction:
    """
    Resolves final policy decision using priority:

    Block > Escalate > Allow
    """

    if not actions:
        return "Allow"

    return max(actions, key=lambda action: DECISION_PRIORITY[action])


# ============================================================
# Utility: confidence helper
# ============================================================

def average_confidence(rules: List[ExtractedPolicyRule]) -> float:
    """
    Calculates average confidence across extracted policy rules.

    If no rules are available, returns 0.0.
    """

    if not rules:
        return 0.0

    return round(
        sum(rule.confidence for rule in rules) / len(rules),
        2
    )


# ============================================================
# Utility: source page extraction
# ============================================================

def extract_source_pages(rules: List[ExtractedPolicyRule]) -> List[int]:
    """
    Extracts unique source pages from triggered rules.
    """

    pages = []

    for rule in rules:
        page = rule.evidence.source_page

        if page is not None and page not in pages:
            pages.append(page)

    return pages


def extract_source_documents(rules: List[ExtractedPolicyRule]) -> List[str]:
    """
    Extracts unique source documents from triggered rules.
    """

    documents = []

    for rule in rules:
        document = rule.evidence.source_document

        if document not in documents:
            documents.append(document)

    return documents
