from langchain_openai import AzureChatOpenAI

from .config import (
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_API_KEY,
    AZURE_OPENAI_API_VERSION,
    AZURE_OPENAI_DEPLOYMENT,
    validate_azure_openai_config,
)


def get_azure_llm(temperature: float = 0.0) -> AzureChatOpenAI:
    validate_azure_openai_config()

    return AzureChatOpenAI(
        azure_endpoint=AZURE_OPENAI_ENDPOINT,
        api_key=AZURE_OPENAI_API_KEY,
        api_version=AZURE_OPENAI_API_VERSION,
        azure_deployment=AZURE_OPENAI_DEPLOYMENT,
        temperature=temperature,
    )