from src.schemas.governance import (
    PolicyEvaluationContext,
    TriggeredPolicy,
    PolicyEngineOutput,
    RiskFactorTriggered,
    RiskScoringOutput,
)


def test_policy_evaluation_context_schema():
    context = PolicyEvaluationContext(
        run_id="RUN-001",
        agent_id="procurement_agent",
        agent_status="Active",
        dataset_accessed="suppliers.csv",
        tool_called="supplier_selector",
        procurement_value=387000,
        is_approved="Yes",
        source_citation_missing=False,
        external_communication_attempted=False,
        restricted_data_accessed=False,
        route_disruption_exists=False,
        route_disruption_severity="None",
        route_disruption_status="None",
        forecast_confidence=0.78,
        unauthorized_tool_used=False,
    )

    assert context.procurement_value > 50000
    assert context.agent_status == "Active"


def test_policy_engine_output_schema():
    triggered_policy = TriggeredPolicy(
        policy_id="POL-001",
        policy_name="High Value Procurement Approval",
        category="Financial Risk",
        action="Escalate",
        severity="High",
        message="Procurement value exceeds INR 50000.",
    )

    output = PolicyEngineOutput(
        run_id="RUN-001",
        step_id="STEP-006",
        agent_id="policy_engine",
        agent_name="Policy Engine",
        status="success",
        source_files=["policy_rules.yaml", "agent_permissions.csv"],
        source_record_ids=[],
        message="Policy evaluation completed.",
        evaluated_agent_id="procurement_agent",
        triggered_policies=[triggered_policy],
        policy_decision="Escalate",
        decision_priority_applied="Block > Escalate > Allow",
    )

    assert output.policy_decision == "Escalate"
    assert output.triggered_policies[0].policy_id == "POL-001"


def test_risk_scoring_output_schema():
    factor = RiskFactorTriggered(
        factor="high_value_procurement",
        points=30,
        category="Financial Risk",
    )

    output = RiskScoringOutput(
        run_id="RUN-001",
        step_id="STEP-007",
        agent_id="risk_scoring_engine",
        agent_name="Risk Scoring Engine",
        status="success",
        source_files=["policy_rules.yaml"],
        source_record_ids=[],
        message="Risk score calculated.",
        base_score=10,
        risk_factors_triggered=[factor],
        calculated_score=40,
        final_risk_score=40,
        risk_level="Medium",
        score_cap_applied=False,
    )

    assert output.final_risk_score == 40
    assert output.risk_level == "Medium"