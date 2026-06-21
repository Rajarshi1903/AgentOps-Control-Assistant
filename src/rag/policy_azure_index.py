import os
from datetime import datetime, timezone
from typing import Dict, List, Any

from dotenv import load_dotenv
from openai import AzureOpenAI

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SimpleField,
    SearchableField,
    SearchField,
    SearchFieldDataType,
    VectorSearch,
    HnswAlgorithmConfiguration,
    VectorSearchProfile,
)


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

# text-embedding-3-small default dimension is commonly 1536.
# If your Azure deployment uses a custom dimension, update this value.
EMBEDDING_DIMENSIONS = int(os.getenv("AZURE_OPENAI_EMBEDDING_DIMENSIONS", "1536"))


def validate_azure_config() -> None:
    """
    Validates required Azure environment variables.
    """

    missing = []

    required_values = {
        "AZURE_OPENAI_ENDPOINT": AZURE_OPENAI_ENDPOINT,
        "AZURE_OPENAI_API_KEY": AZURE_OPENAI_API_KEY,
        "AZURE_OPENAI_API_VERSION": AZURE_OPENAI_API_VERSION,
        "AZURE_OPENAI_EMBEDDING_DEPLOYMENT": AZURE_OPENAI_EMBEDDING_DEPLOYMENT,
        "AZURE_SEARCH_ENDPOINT": AZURE_SEARCH_ENDPOINT,
        "AZURE_SEARCH_KEY": AZURE_SEARCH_KEY,
        "AZURE_SEARCH_INDEX_NAME": AZURE_SEARCH_INDEX_NAME,
    }

    for key, value in required_values.items():
        if not value:
            missing.append(key)

    if missing:
        raise EnvironmentError(
            f"Missing required Azure environment variables: {', '.join(missing)}"
        )


def get_azure_openai_client() -> AzureOpenAI:
    """
    Creates Azure OpenAI client for embeddings.
    """

    return AzureOpenAI(
        azure_endpoint=AZURE_OPENAI_ENDPOINT,
        api_key=AZURE_OPENAI_API_KEY,
        api_version=AZURE_OPENAI_API_VERSION,
    )


def generate_embedding(text: str) -> List[float]:
    """
    Generates embedding vector using Azure OpenAI embedding deployment.
    """

    client = get_azure_openai_client()

    response = client.embeddings.create(
        model=AZURE_OPENAI_EMBEDDING_DEPLOYMENT,
        input=text,
    )

    return response.data[0].embedding


def create_or_recreate_policy_index() -> None:
    """
    Creates Azure AI Search vector index.
    If index exists, deletes and recreates it for clean MVP rebuild.
    """

    validate_azure_config()

    credential = AzureKeyCredential(AZURE_SEARCH_KEY)
    index_client = SearchIndexClient(
        endpoint=AZURE_SEARCH_ENDPOINT,
        credential=credential
    )

    existing_indexes = [index.name for index in index_client.list_indexes()]

    if AZURE_SEARCH_INDEX_NAME in existing_indexes:
        print(f"Deleting existing index: {AZURE_SEARCH_INDEX_NAME}")
        index_client.delete_index(AZURE_SEARCH_INDEX_NAME)

    fields = [
        SimpleField(
            name="id",
            type=SearchFieldDataType.String,
            key=True,
            filterable=True,
        ),
        SimpleField(
            name="chunk_id",
            type=SearchFieldDataType.String,
            filterable=True,
            sortable=True,
        ),
        SearchableField(
            name="content",
            type=SearchFieldDataType.String,
            searchable=True,
        ),
        SimpleField(
            name="source_document",
            type=SearchFieldDataType.String,
            filterable=True,
            facetable=True,
        ),
        SimpleField(
            name="page_number",
            type=SearchFieldDataType.Int32,
            filterable=True,
            sortable=True,
            facetable=True,
        ),
        SearchableField(
            name="section_title",
            type=SearchFieldDataType.String,
            searchable=True,
            filterable=True,
            facetable=True,
        ),
        SimpleField(
            name="policy_area",
            type=SearchFieldDataType.String,
            filterable=True,
            facetable=True,
        ),
        SimpleField(
            name="chunk_index",
            type=SearchFieldDataType.Int32,
            filterable=True,
            sortable=True,
        ),
        SimpleField(
            name="created_at",
            type=SearchFieldDataType.String,
            filterable=True,
            sortable=True,
        ),
        SearchField(
            name="content_vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=EMBEDDING_DIMENSIONS,
            vector_search_profile_name="policy-vector-profile",
        ),
    ]

    vector_search = VectorSearch(
        algorithms=[
            HnswAlgorithmConfiguration(
                name="policy-hnsw"
            )
        ],
        profiles=[
            VectorSearchProfile(
                name="policy-vector-profile",
                algorithm_configuration_name="policy-hnsw",
            )
        ],
    )

    index = SearchIndex(
        name=AZURE_SEARCH_INDEX_NAME,
        fields=fields,
        vector_search=vector_search,
    )

    index_client.create_index(index)

    print(f"Azure AI Search index created: {AZURE_SEARCH_INDEX_NAME}")


def build_search_documents(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Converts local chunks into Azure Search upload documents.
    Adds embeddings.
    """

    documents = []
    created_at = datetime.now(timezone.utc).isoformat()

    for index, chunk in enumerate(chunks, start=1):
        content = chunk["content"]

        embedding = generate_embedding(content)

        if len(embedding) != EMBEDDING_DIMENSIONS:
            raise ValueError(
                f"Embedding dimension mismatch. "
                f"Expected {EMBEDDING_DIMENSIONS}, got {len(embedding)}. "
                "Update AZURE_OPENAI_EMBEDDING_DIMENSIONS if needed."
            )

        document = {
            "id": chunk["id"],
            "chunk_id": chunk["chunk_id"],
            "content": content,
            "source_document": chunk["source_document"],
            "page_number": int(chunk["page_number"]),
            "section_title": chunk["section_title"],
            "policy_area": chunk["policy_area"],
            "chunk_index": int(chunk["chunk_index"]),
            "created_at": created_at,
            "content_vector": embedding,
        }

        documents.append(document)

        print(f"Embedded chunk {index}/{len(chunks)}: {chunk['chunk_id']}")

    return documents


def upload_documents_to_search(documents: List[Dict[str, Any]]) -> None:
    """
    Uploads documents to Azure AI Search index.
    """

    credential = AzureKeyCredential(AZURE_SEARCH_KEY)
    search_client = SearchClient(
        endpoint=AZURE_SEARCH_ENDPOINT,
        index_name=AZURE_SEARCH_INDEX_NAME,
        credential=credential,
    )

    batch_size = 100
    uploaded_count = 0

    for start in range(0, len(documents), batch_size):
        batch = documents[start:start + batch_size]

        result = search_client.upload_documents(documents=batch)

        failed = [item for item in result if not item.succeeded]

        if failed:
            raise RuntimeError(f"Some documents failed to upload: {failed}")

        uploaded_count += len(batch)

        print(f"Uploaded {uploaded_count}/{len(documents)} documents.")

    print(f"Documents uploaded successfully: {uploaded_count}")


def upload_policy_chunks_to_azure_search(chunks: List[Dict[str, Any]]) -> None:
    """
    Full Azure upload flow:
    1. Validate config
    2. Test embedding deployment
    3. Create/recreate index
    4. Generate embeddings
    5. Upload documents
    """

    validate_azure_config()

    print("Testing Azure OpenAI embedding deployment...")

    test_embedding = generate_embedding("Azure OpenAI embedding connectivity test.")

    print("Embedding test successful.")
    print(f"Embedding dimensions returned: {len(test_embedding)}")

    if len(test_embedding) != EMBEDDING_DIMENSIONS:
        raise ValueError(
            f"Embedding dimension mismatch. "
            f"Expected {EMBEDDING_DIMENSIONS}, got {len(test_embedding)}. "
            "Update AZURE_OPENAI_EMBEDDING_DIMENSIONS in .env if needed."
        )

    create_or_recreate_policy_index()

    documents = build_search_documents(chunks)

    upload_documents_to_search(documents)

    print("Azure policy ingestion completed successfully.")
    print(f"Azure Search index: {AZURE_SEARCH_INDEX_NAME}")
    print(f"Documents uploaded: {len(documents)}")
    print(f"Embedding deployment: {AZURE_OPENAI_EMBEDDING_DEPLOYMENT}")
    print(f"Embedding dimensions: {EMBEDDING_DIMENSIONS}")