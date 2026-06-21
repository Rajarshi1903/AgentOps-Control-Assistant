import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from src.graph.workflow_graph import build_workflow_graph


def print_summary(case_name, result):
    print("=" * 120)
    print("CASE:", case_name)
    print("Final decision:", result.get("final_decision"))
    print("Completed steps:", result.get("completed_steps"))
    print("Errors:", result.get("errors"))

    print("-" * 120)
    print("Policy decision:", result.get("policy_output", {}).get("policy_decision"))

    rag = result.get("policy_rag_decision", {})
    print("RAG decision:", rag.get("decision"))
    print("RAG confidence:", rag.get("confidence"))
    print("RAG source pages:", rag.get("source_pages"))
    print("RAG final reason:", rag.get("final_reason"))

    print("-" * 120)
    if result.get("procurement_output"):
        print("Procurement value:", result["procurement_output"].get("procurement_value"))
        print("Supplier approved:", result["procurement_output"].get("is_approved"))
        print("Compliance:", result["procurement_output"].get("compliance_status"))

    if result.get("logistics_output"):
        print("Route:", result["logistics_output"].get("recommended_route_id"))
        print("Route disruption:", result["logistics_output"].get("route_disruption_exists"))
        print("Route severity:", result["logistics_output"].get("route_disruption_severity"))
        print("Route status:", result["logistics_output"].get("route_disruption_status"))


def run_case(app, case_name, initial_state):
    result = app.invoke(initial_state)
    print_summary(case_name, result)
    return result


if __name__ == "__main__":
    app = build_workflow_graph()

    scenarios = [
        (
            "Full demand spike should escalate",
            {
                "run_id": "RUN-MANUAL-FULL-001",
                "user_query": "Demand for P-101 has increased in South region.",
                "user_role": "Supply Chain Planner",
                "completed_steps": [],
                "errors": [],
            }
        ),
        (
            "Forecast-only workflow",
            {
                "run_id": "RUN-MANUAL-FORECAST-001",
                "user_query": "Forecast demand for P-101 in South.",
                "user_role": "Supply Chain Planner",
                "completed_steps": [],
                "errors": [],
            }
        ),
        (
            "Inventory-only workflow",
            {
                "run_id": "RUN-MANUAL-INVENTORY-001",
                "user_query": "Check inventory for P-101 in South.",
                "user_role": "Supply Chain Planner",
                "completed_steps": [],
                "errors": [],
            }
        ),
        (
            "Normal logistics route should allow",
            {
                "run_id": "RUN-MANUAL-LOGISTICS-001",
                "user_query": "Check logistics route for supplier S-001 to South warehouse.",
                "user_role": "Supply Chain Planner",
                "supplier_id": "S-001",
                "region": "South",
                "completed_steps": [],
                "errors": [],
            }
        ),
        (
            "Route disruption should escalate",
            {
                "run_id": "RUN-MANUAL-ROUTE-RISK-001",
                "user_query": "Check route risk for supplier S-012 to South.",
                "user_role": "Supply Chain Planner",
                "supplier_id": "S-012",
                "region": "South",
                "completed_steps": [],
                "errors": [],
            }
        ),
    ]

    for case_name, initial_state in scenarios:
        run_case(app, case_name, initial_state)