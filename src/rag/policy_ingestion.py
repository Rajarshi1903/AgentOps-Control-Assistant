import json
from pathlib import Path
from typing import Dict, List, Any

from pypdf import PdfReader

from src.rag.policy_chunker import build_policy_chunks


POLICY_PDF_PATH = Path("data/policies/agentops_supply_chain_policy_handbook.pdf")
OUTPUT_DIR = Path("outputs/policy_ingestion")
CHUNKS_PREVIEW_FILE = OUTPUT_DIR / "chunks_preview.json"


def load_pdf_pages(pdf_path: Path) -> List[Dict[str, Any]]:
    """
    Loads PDF and extracts page-level text.
    Preserves page numbers for citations.
    """

    if not pdf_path.exists():
        raise FileNotFoundError(f"Policy PDF not found at: {pdf_path}")

    reader = PdfReader(str(pdf_path))

    pages = []

    for page_index, page in enumerate(reader.pages):
        text = page.extract_text() or ""

        pages.append(
            {
                "page_number": page_index + 1,
                "text": text,
            }
        )

    return pages


def save_chunks_preview(chunks: List[Dict[str, Any]]) -> None:
    """
    Saves local JSON preview of chunks for debugging and demo.
    """

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with open(CHUNKS_PREVIEW_FILE, "w", encoding="utf-8") as file:
        json.dump(chunks, file, indent=2, ensure_ascii=False)


def ingest_policy_pdf(
    pdf_path: Path = POLICY_PDF_PATH,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
    upload_to_azure: bool = False
) -> List[Dict[str, Any]]:
    """
    Main ingestion function.

    Steps:
    1. Load PDF
    2. Extract page text
    3. Build chunks
    4. Save chunks preview JSON
    5. Optionally upload to Azure AI Search
    """

    pages = load_pdf_pages(pdf_path)

    source_document = pdf_path.name

    chunks = build_policy_chunks(
        pages=pages,
        source_document=source_document,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap
    )

    if not chunks:
        raise ValueError("No valid chunks were created from the policy PDF.")

    save_chunks_preview(chunks)

    print("PDF loaded successfully.")
    print(f"Pages extracted: {len(pages)}")
    print(f"Chunks created: {len(chunks)}")
    print(f"Chunks preview saved to: {CHUNKS_PREVIEW_FILE}")

    if upload_to_azure:
        from src.rag.policy_azure_index import upload_policy_chunks_to_azure_search

        upload_policy_chunks_to_azure_search(chunks)

    return chunks


if __name__ == "__main__":
    ingest_policy_pdf(upload_to_azure=True)