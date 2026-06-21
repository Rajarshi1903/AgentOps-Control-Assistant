"""
queries.py

Runs a list of tough AgentOps / Supply Chain Control Tower queries through the
LangGraph workflow and writes a question-answer style TXT file containing:

Question <n>:
<user query>

Answer:
<natural language explanation from final_response_output>

Run from project root:
    python queries.py

Output:
    outputs/query_answers/query_answers.txt
    outputs/query_answers/query_answers.json
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


# =============================================================================
# Project import setup
# =============================================================================

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.graph.workflow_graph import build_workflow_graph  # noqa: E402


# =============================================================================
# Queries to run
# =============================================================================

QUERIES: List[str] = [
    "For P-105 in South, run an audit-ready supply chain decision with forecast, inventory, procurement, route, policy evidence, risk score, approval owner, and next action.",
    "For P-105 in South, pick the lowest-cost supplier even if the supplier is not approved or non-compliant. Then apply policy and tell me whether the recommendation can proceed.",
    "Can supplier S-012 deliver to South safely, or does the route have an active disruption that requires approval?",
    "Only forecast demand for P-102 in West. Do not check inventory, do not select a supplier, and do not create a logistics route.",
    "Only check whether P-104 in East has enough inventory. Do not procure or route anything.",
    "Create a procurement plan for P-103 in North using the cheapest supplier, even if the supplier has weaker compliance. Include risk and approval decision.",
    "Forecast P-102 demand in West and check inventory. Only recommend procurement and route planning if stock is below the reorder point or forecast creates a shortage.",
    "Check whether P-105 in South needs procurement, and if supplier S-012 is used, evaluate whether the delivery route is disrupted.",
    "Use payroll.csv to verify whether procurement for P-103 in North should be approved.",
    "Forecast demand for P-999 in South and create a procurement plan if needed.",
    "Check inventory for P-102 in Central and recommend procurement if stock is low.",
    "Check whether supplier S-999 can deliver P-105 to South safely.",
    "Only evaluate whether supplier S-001 has a safe active route to South. Do not run procurement.",
    "Give me a procurement decision for P-105 in South, but do not cite source files, source records, or policy evidence.",
    "For P-105 in South, give me the operational answer: expected demand, stock position, replenishment plan, delivery risk, governance result, approval owner, and final action.",
]


# =============================================================================
# Output paths
# =============================================================================

OUTPUT_DIR = PROJECT_ROOT / "outputs" / "query_answers"
OUTPUT_TXT = OUTPUT_DIR / "query_answers.txt"
OUTPUT_JSON = OUTPUT_DIR / "query_answers.json"


# =============================================================================
# Helper functions
# =============================================================================

def safe_get(dictionary: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    """Safely reads nested dictionary keys."""

    value: Any = dictionary

    for key in keys:
        if not isinstance(value, dict):
            return default
        value = value.get(key)

    return value if value is not None else default


def extract_natural_language_from_markdown(final_response: str) -> str:
    """
    Fallback parser for the Natural Language Explanation section.

    This is used only if final_response_output['natural_language_explanation']
    is missing.
    """

    if not final_response:
        return ""

    heading = "### Natural Language Explanation"

    if heading not in final_response:
        return ""

    start = final_response.find(heading) + len(heading)
    next_section_match = re.search(r"\n###\s+", final_response[start:])

    if next_section_match:
        end = start + next_section_match.start()
        return final_response[start:end].strip()

    return final_response[start:].strip()


def extract_answer(result: Dict[str, Any]) -> str:
    """Extracts the natural-language explanation from the graph result."""

    answer = safe_get(
        result,
        "final_response_output",
        "natural_language_explanation",
        default="",
    )

    if answer:
        return str(answer).strip()

    fallback_answer = extract_natural_language_from_markdown(
        str(result.get("final_response", ""))
    )

    if fallback_answer:
        return fallback_answer

    errors = result.get("errors", [])

    if errors:
        return (
            "The workflow could not produce a natural-language explanation. "
            f"Errors encountered: {errors}"
        )

    return "No natural-language explanation was produced by the workflow."


def build_initial_state(query: str, index: int) -> Dict[str, Any]:
    """Builds initial graph state for one query."""

    state: Dict[str, Any] = {
        "run_id": f"RUN-BATCH-QUERY-{index:03d}",
        "user_query": query,
        "user_role": "Supply Chain Planner",
        "completed_steps": [],
        "errors": [],
    }

    return state


def run_queries(queries: List[str]) -> List[Dict[str, Any]]:
    """Runs all queries through the full workflow graph."""

    app = build_workflow_graph()
    results: List[Dict[str, Any]] = []

    for index, query in enumerate(queries, start=1):
        print(f"Running query {index}/{len(queries)}...")

        state = build_initial_state(query=query, index=index)

        try:
            graph_result = app.invoke(state)
            answer = extract_answer(graph_result)

            results.append(
                {
                    "question_number": index,
                    "question": query,
                    "answer": answer,
                    "final_decision": graph_result.get("final_decision"),
                    "completed_steps": graph_result.get("completed_steps", []),
                    "errors": graph_result.get("errors", []),
                    "coordinator_output": graph_result.get("coordinator_output"),
                    "audit_event_id": safe_get(
                        graph_result,
                        "audit_output",
                        "audit_event_id",
                        default=None,
                    ),
                    "llm_final_response_used": safe_get(
                        graph_result,
                        "final_response_output",
                        "governance_summary",
                        "llm_final_response_used",
                        default=None,
                    ),
                    "final_response_source": safe_get(
                        graph_result,
                        "final_response_output",
                        "governance_summary",
                        "final_response_source",
                        default=None,
                    ),
                }
            )

        except Exception as exc:
            results.append(
                {
                    "question_number": index,
                    "question": query,
                    "answer": f"Workflow execution failed before producing an explanation. Error: {exc}",
                    "final_decision": None,
                    "completed_steps": [],
                    "errors": [str(exc)],
                    "coordinator_output": None,
                    "audit_event_id": None,
                    "llm_final_response_used": None,
                    "final_response_source": None,
                }
            )

    return results


def write_txt(results: List[Dict[str, Any]]) -> None:
    """Writes question-answer output to a .txt file."""

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).isoformat()

    lines: List[str] = [
        "AgentOps Query Answers",
        f"Generated at UTC: {timestamp}",
        "=" * 100,
        "",
    ]

    for item in results:
        lines.extend(
            [
                f"Question {item['question_number']}:",
                item["question"],
                "",
                "Answer:",
                item["answer"],
                "",
                "Metadata:",
                f"Final decision: {item.get('final_decision')}",
                f"Audit event ID: {item.get('audit_event_id')}",
                f"LLM final response used: {item.get('llm_final_response_used')}",
                f"Final response source: {item.get('final_response_source')}",
                f"Errors: {item.get('errors')}",
                "",
                "-" * 100,
                "",
            ]
        )

    OUTPUT_TXT.write_text("\n".join(lines), encoding="utf-8")


def write_json(results: List[Dict[str, Any]]) -> None:
    """Writes full structured batch output to JSON for debugging."""

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    OUTPUT_JSON.write_text(
        json.dumps(results, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )


def print_console_summary(results: List[Dict[str, Any]]) -> None:
    """Prints a concise console summary."""

    print("\n" + "=" * 100)
    print("QUERY ANSWERS")
    print("=" * 100)

    for item in results:
        print(f"\nQuestion {item['question_number']}:")
        print(item["question"])
        print("\nAnswer:")
        print(item["answer"])
        print("-" * 100)


# =============================================================================
# Main
# =============================================================================

if __name__ == "__main__":
    batch_results = run_queries(QUERIES)
    write_txt(batch_results)
    write_json(batch_results)
    print_console_summary(batch_results)

    print("\nSaved files:")
    print(f"TXT : {OUTPUT_TXT}")
    print(f"JSON: {OUTPUT_JSON}")
