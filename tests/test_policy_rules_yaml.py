from pathlib import Path
import yaml


def test_policy_rules_yaml_loads():
    policy_file = Path("data/policy_rules.yaml")

    assert policy_file.exists()

    with open(policy_file, "r", encoding="utf-8") as file:
        policy_rules = yaml.safe_load(file)

    assert "metadata" in policy_rules
    assert "decision_priority" in policy_rules
    assert "policies" in policy_rules
    assert "risk_scoring" in policy_rules
    assert "risk_levels" in policy_rules


def test_policy_rules_decision_priority():
    with open("data/policy_rules.yaml", "r", encoding="utf-8") as file:
        policy_rules = yaml.safe_load(file)

    assert policy_rules["decision_priority"] == ["Block", "Escalate", "Allow"]


def test_policy_rules_procurement_threshold():
    with open("data/policy_rules.yaml", "r", encoding="utf-8") as file:
        policy_rules = yaml.safe_load(file)

    policies = policy_rules["policies"]

    high_value_policy = next(
        policy for policy in policies
        if policy["policy_id"] == "POL-001"
    )

    assert high_value_policy["condition"]["field"] == "procurement_value"
    assert high_value_policy["condition"]["operator"] == ">"
    assert high_value_policy["condition"]["value"] == 50000
    assert high_value_policy["action"] == "Escalate"


def test_risk_scoring_values():
    with open("data/policy_rules.yaml", "r", encoding="utf-8") as file:
        policy_rules = yaml.safe_load(file)

    risk_scoring = policy_rules["risk_scoring"]

    assert risk_scoring["base_score"] == 10
    assert risk_scoring["max_score"] == 100
    assert risk_scoring["factors"]["high_value_procurement"]["points"] == 30
    assert risk_scoring["factors"]["unapproved_vendor"]["points"] == 40
    assert risk_scoring["factors"]["external_communication"]["points"] == 25
    assert risk_scoring["factors"]["restricted_data_access"]["points"] == 30
    assert risk_scoring["factors"]["missing_source_citation"]["points"] == 20
    assert risk_scoring["factors"]["route_disruption"]["points"] == 25
    assert risk_scoring["factors"]["low_forecast_confidence"]["points"] == 20