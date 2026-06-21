from src.schemas.policy_rag import (
    PolicyEvidence,
    ExtractedPolicyRule,
    PolicyGuardrailResult,
    PolicyRAGDecision,
    RetrievedPolicyChunk,
)


def test_policy_rag_schema_creation():
    evidence = PolicyEvidence(
        evidence_text="Any procurement recommendation exceeding INR 50,000 must be escalated.",
        source_document="agentops_supply_chain_policy_handbook.pdf",
        source_page=4,
        chunk_id="chunk_004",
        retrieval_score=0.91,
    )

    rule = ExtractedPolicyRule(
        applicable=True,
        policy_name="High-Value Procurement Approval",
        policy_area="Procurement Governance",
        condition_field="procurement_value",
        operator=">",
        threshold_value=50000,
        action="Escalate",
        severity="High",
        evidence=evidence,
        confidence=0.91,
    )

    chunk = RetrievedPolicyChunk(
        chunk_id="chunk_004",
        source_document="agentops_supply_chain_policy_handbook.pdf",
        page_number=4,
        text="Any procurement recommendation exceeding INR 50,000 must be escalated.",
        retrieval_score=0.91,
    )

    guardrail = PolicyGuardrailResult(
        evidence_available=True,
        confidence_ok=True,
        citation_available=True,
        decision_safe=True,
        guardrail_decision="Allow",
        guardrail_reason="Evidence and confidence are sufficient.",
        actual_confidence=0.91,
    )

    decision = PolicyRAGDecision(
        run_id="RUN-001",
        query="What policy applies to procurement value INR 387000?",
        decision="Escalate",
        triggered_rules=[rule],
        retrieved_chunks=[chunk],
        guardrail_result=guardrail,
        final_reason="Procurement value exceeds INR 50,000 according to retrieved policy evidence.",
        evidence_available=True,
        confidence=0.91,
        source_documents=["agentops_supply_chain_policy_handbook.pdf"],
        source_pages=[4],
    )

    assert decision.decision == "Escalate"
    assert decision.triggered_rules[0].policy_name == "High-Value Procurement Approval"
    assert decision.evidence_available is True