import os
from typing import List, Optional

from dotenv import load_dotenv
from openai import AzureOpenAI

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery

from src.schemas.policy_rag import RetrievedPolicyChunk


load_dotenv()


AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION")
AZURE_OPENAI_EMBEDDING_DEPLOYMENT = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT")

AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT")
AZURE_SEARCH_KEY = os.getenv("AZURE_SEARCH_KEY")
AZURE_SEARCH_INDEX_NAME = (
    os.getenv("AZURE_SEARCH_INDEX_NAME")
    or "agentops-policy-handbook-index"
)


def validate_retriever_config() -> None:
    """
    Validates Azure config required for retrieval.
    """

    missing = []

    required = {
        "AZURE_OPENAI_ENDPOINT": AZURE_OPENAI_ENDPOINT,
        "AZURE_OPENAI_API_KEY": AZURE_OPENAI_API_KEY,
        "AZURE_OPENAI_API_VERSION": AZURE_OPENAI_API_VERSION,
        "AZURE_OPENAI_EMBEDDING_DEPLOYMENT": AZURE_OPENAI_EMBEDDING_DEPLOYMENT,
        "AZURE_SEARCH_ENDPOINT": AZURE_SEARCH_ENDPOINT,
        "AZURE_SEARCH_KEY": AZURE_SEARCH_KEY,
        "AZURE_SEARCH_INDEX_NAME": AZURE_SEARCH_INDEX_NAME,
    }

    for key, value in required.items():
        if not value:
            missing.append(key)

    if missing:
        raise EnvironmentError(
            f"Missing retriever environment variables: {', '.join(missing)}"
        )


def get_azure_openai_client() -> AzureOpenAI:
    """
    Returns Azure OpenAI client for query embeddings.
    """

    return AzureOpenAI(
        azure_endpoint=AZURE_OPENAI_ENDPOINT,
        api_key=AZURE_OPENAI_API_KEY,
        api_version=AZURE_OPENAI_API_VERSION,
    )


def get_search_client() -> SearchClient:
    """
    Returns Azure AI Search client.
    """

    credential = AzureKeyCredential(AZURE_SEARCH_KEY)

    return SearchClient(
        endpoint=AZURE_SEARCH_ENDPOINT,
        index_name=AZURE_SEARCH_INDEX_NAME,
        credential=credential,
    )


def generate_query_embedding(query: str) -> List[float]:
    """
    Generates embedding for retrieval query.
    Must use the same embedding deployment used during ingestion.
    """

    client = get_azure_openai_client()

    response = client.embeddings.create(
        model=AZURE_OPENAI_EMBEDDING_DEPLOYMENT,
        input=query,
    )

    return response.data[0].embedding


def retrieve_policy_chunks(
    query: str,
    top_k: int = 5,
    policy_area_filter: Optional[str] = None
) -> List[RetrievedPolicyChunk]:
    """
    Retrieves relevant policy chunks from Azure AI Search.

    Args:
        query: natural-language policy query
        top_k: number of chunks to retrieve
        policy_area_filter: optional policy_area filter, e.g. high_value_procurement

    Returns:
        List[RetrievedPolicyChunk]
    """

    validate_retriever_config()

    query_embedding = generate_query_embedding(query)

    search_client = get_search_client()

    vector_query = VectorizedQuery(
        vector=query_embedding,
        k_nearest_neighbors=top_k,
        fields="content_vector",
    )

    filter_expression = None

    if policy_area_filter:
        filter_expression = f"policy_area eq '{policy_area_filter}'"

    results = search_client.search(
        search_text=query,
        vector_queries=[vector_query],
        select=[
            "id",
            "chunk_id",
            "content",
            "source_document",
            "page_number",
            "section_title",
            "policy_area",
            "chunk_index",
        ],
        filter=filter_expression,
        top=top_k,
    )

    retrieved_chunks = []

    for result in results:
        retrieval_score = result.get("@search.score")

        chunk = RetrievedPolicyChunk(
            chunk_id=result["chunk_id"],
            source_document=result["source_document"],
            page_number=result.get("page_number"),
            text=result["content"],
            retrieval_score=float(retrieval_score) if retrieval_score is not None else None,
            metadata={
                "id": result.get("id"),
                "section_title": result.get("section_title"),
                "policy_area": result.get("policy_area"),
                "chunk_index": result.get("chunk_index"),
            }
        )

        retrieved_chunks.append(chunk)

    return retrieved_chunks


if __name__ == "__main__":
    test_queries = [
        {
            "query": "What policy applies when procurement value exceeds INR 50000?",
            "policy_area": "high_value_procurement",
        },
        {
            "query": "What policy applies when a supplier is unapproved?",
            "policy_area": "supplier_compliance",
        },
        {
            "query": "What policy applies when a route has an active high severity disruption?",
            "policy_area": "route_disruption",
        },
        {
            "query": "What policy applies when an agent accesses payroll.csv?",
            "policy_area": "restricted_data_access",
        },
    ]

    for item in test_queries:
        print("=" * 100)
        print("Query:", item["query"])
        print("Policy area filter:", item["policy_area"])

        chunks = retrieve_policy_chunks(
            query=item["query"],
            top_k=3,
            policy_area_filter=item["policy_area"],
        )

        print(f"Retrieved chunks: {len(chunks)}")

        for chunk in chunks:
            print("-" * 80)
            print("Chunk ID:", chunk.chunk_id)
            print("Source:", chunk.source_document)
            print("Page:", chunk.page_number)
            print("Score:", chunk.retrieval_score)
            print("Policy area:", chunk.metadata.get("policy_area"))
            print("Section:", chunk.metadata.get("section_title"))
            print("Text preview:", chunk.text[:400])