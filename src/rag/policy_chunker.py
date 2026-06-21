import re
from typing import Dict, List, Any
# Policy area keyword map
# ============================================================
# Used during ingestion to tag chunks with policy_area metadata.
# This improves retrieval and later allows filtered/hybrid search.
# ============================================================

POLICY_AREA_KEYWORDS = {
    "high_value_procurement": [
        "high-value procurement",
        "procurement recommendation exceeding",
        "procurement above",
        "inr 50,000",
        "inr 50000",
        "human reviewer",
        "human approval",
        "procurement governance",
        "high-value",
    ],
    "supplier_compliance": [
        "supplier compliance",
        "unapproved supplier",
        "unapproved vendor",
        "non-compliant",
        "non compliant",
        "approval status",
        "supplier approval",
        "vendor compliance",
    ],
    "route_disruption": [
        "route disruption",
        "logistics",
        "active disruption",
        "high or critical",
        "delivery risk",
        "route risk",
        "transport disruption",
        "business continuity risk",
    ],
    "restricted_data_access": [
        "restricted data",
        "payroll",
        "hr_data",
        "hr data",
        "employee records",
        "customer pii",
        "customer_pii",
        "confidential data",
    ],
    "source_traceability": [
        "source traceability",
        "source files",
        "source record",
        "source record identifiers",
        "cite source",
        "policy evidence",
        "source references",
    ],
    "external_communication": [
        "external communication",
        "supplier emails",
        "supplier email",
        "vendor api",
        "purchase order submissions",
        "purchase order submission",
        "external notifications",
        "external action",
    ],
    "tool_usage": [
        "tool usage",
        "unauthorized tool",
        "allowed tools",
        "tool governance",
        "tool misuse",
    ],
    "agent_status": [
        "suspended",
        "inactive agent",
        "agent status",
        "must not execute",
        "suspended agent",
        "inactive",
    ],
    "forecast_confidence": [
        "forecast confidence",
        "low confidence",
        "below 0.70",
        "below 0.7",
        "model confidence",
        "forecast confidence policy",
    ],
    "audit_logging": [
        "audit logging",
        "audit trail",
        "evidence retention",
        "logs must include",
        "logged",
        "timestamp",
    ],
    "decision_priority": [
        "block overrides escalate",
        "escalate overrides allow",
        "decision priority",
        "enforcement actions",
    ],
}


# ============================================================
# Section detection patterns
# ============================================================
# These are intentionally simple and robust for reportlab-generated
# policy PDFs.
# ============================================================

SECTION_PATTERNS = [
    r"^\d+\.\s+(.+)$",
    r"^[A-Z][A-Za-z\s\-\/]+Policy$",
    r"^[A-Z][A-Za-z\s\-\/]+Governance$",
    r"^[A-Z][A-Za-z\s\-\/]+Requirements$",
    r"^[A-Z][A-Za-z\s\-\/]+Actions$",
    r"^[A-Z][A-Za-z\s\-\/]+Rules$",
]


def clean_text(text: str) -> str:
    """
    Cleans extracted PDF text while preserving policy wording.
    """

    if not text:
        return ""

    text = text.replace("\x00", " ")
    text = text.replace("\r", "\n")

    # Normalize spaces but preserve newlines.
    text = re.sub(r"[ \t]+", " ", text)

    # Reduce excessive blank lines.
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Remove spaces before punctuation.
    text = re.sub(r"\s+([,.;:])", r"\1", text)

    return text.strip()


def detect_section_title(text: str, fallback: str = "Unknown Section") -> str:
    """
    Attempts to detect section title from page/chunk text.
    """

    lines = [line.strip() for line in text.splitlines() if line.strip()]

    for line in lines[:12]:
        cleaned_line = line.strip()

        for pattern in SECTION_PATTERNS:
            match = re.match(pattern, cleaned_line)

            if match:
                if match.groups():
                    return match.group(1).strip()

                return cleaned_line

    return fallback


def detect_policy_area(text: str) -> str:
    """
    Tags policy area based on keywords/headings.

    Returns:
        policy_area string, for example:
        high_value_procurement, supplier_compliance, route_disruption, etc.
    """

    lower_text = text.lower()

    for policy_area, keywords in POLICY_AREA_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in lower_text:
                return policy_area

    return "general_policy"


def split_text_with_overlap(
    text: str,
    chunk_size: int = 1000,
    chunk_overlap: int = 200
) -> List[str]:
    """
    Splits text into character chunks with overlap.
    Attempts to split near paragraph/sentence boundaries.

    Args:
        text: cleaned text
        chunk_size: max characters per chunk
        chunk_overlap: characters shared between adjacent chunks

    Returns:
        list of chunk strings
    """

    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be smaller than chunk_size")

    text = clean_text(text)

    if len(text) <= chunk_size:
        return [text] if len(text.strip()) >= 50 else []

    chunks = []
    start = 0

    while start < len(text):
        end = min(start + chunk_size, len(text))

        if end < len(text):
            paragraph_break = text.rfind("\n\n", start, end)
            sentence_break = text.rfind(". ", start, end)

            if paragraph_break > start + int(chunk_size * 0.5):
                end = paragraph_break
            elif sentence_break > start + int(chunk_size * 0.5):
                end = sentence_break + 1

        chunk = text[start:end].strip()

        if len(chunk) >= 50:
            chunks.append(chunk)

        if end >= len(text):
            break

        start = max(end - chunk_overlap, start + 1)

    return chunks


def build_policy_chunks(
    pages: List[Dict[str, Any]],
    source_document: str,
    chunk_size: int = 1000,
    chunk_overlap: int = 200
) -> List[Dict[str, Any]]:
    """
    Converts page-level PDF text into metadata-rich policy chunks.

    Args:
        pages: list of dictionaries like:
            {
                "page_number": 1,
                "text": "page text..."
            }

        source_document: PDF filename

    Returns:
        list of chunk dictionaries ready for embedding/indexing
    """

    all_chunks = []
    global_chunk_index = 0
    last_section_title = "Unknown Section"

    for page in pages:
        page_number = page["page_number"]
        page_text = clean_text(page.get("text", ""))

        if not page_text or len(page_text) < 50:
            continue

        section_title = detect_section_title(
            page_text,
            fallback=last_section_title
        )

        if section_title != "Unknown Section":
            last_section_title = section_title

        page_chunks = split_text_with_overlap(
            page_text,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap
        )

        for local_chunk_index, chunk_text in enumerate(page_chunks):
            policy_area = detect_policy_area(chunk_text)

            safe_source_name = source_document.replace(".pdf", "").replace(" ", "_")

            chunk_id = (
                f"{safe_source_name}"
                f"_page_{page_number}"
                f"_chunk_{local_chunk_index + 1}"
            )

            all_chunks.append(
                {
                    "id": f"policy_chunk_{global_chunk_index + 1:05d}",
                    "chunk_id": chunk_id,
                    "content": chunk_text,
                    "source_document": source_document,
                    "page_number": int(page_number),
                    "section_title": section_title,
                    "policy_area": policy_area,
                    "chunk_index": int(global_chunk_index),
                }
            )

            global_chunk_index += 1

    return all_chunks


