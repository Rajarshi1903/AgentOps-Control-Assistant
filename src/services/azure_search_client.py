from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient

from .config import (
    AZURE_SEARCH_ENDPOINT,
    AZURE_SEARCH_KEY,
    AZURE_SEARCH_INDEX_NAME,
    validate_azure_search_config,
)


def get_azure_search_client() -> SearchClient:
    validate_azure_search_config()

    return SearchClient(
        endpoint=AZURE_SEARCH_ENDPOINT,
        index_name=AZURE_SEARCH_INDEX_NAME,
        credential=AzureKeyCredential(AZURE_SEARCH_KEY),
    )