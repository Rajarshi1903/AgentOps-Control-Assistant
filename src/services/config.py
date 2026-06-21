import os
from pathlib import Path
from dotenv import load_dotenv


load_dotenv()


DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

SQLITE_DB_PATH = os.getenv("SQLITE_DB_PATH", str(DATA_DIR / "audit_logs.db"))

AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT")

AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT")
AZURE_SEARCH_KEY = os.getenv("AZURE_SEARCH_KEY")
AZURE_SEARCH_INDEX_NAME = os.getenv("AZURE_SEARCH_INDEX_NAME")


def validate_azure_openai_config() -> None:
    missing = []

    if not AZURE_OPENAI_ENDPOINT:
        missing.append("AZURE_OPENAI_ENDPOINT")
    if not AZURE_OPENAI_API_KEY:
        missing.append("AZURE_OPENAI_API_KEY")
    if not AZURE_OPENAI_API_VERSION:
        missing.append("AZURE_OPENAI_API_VERSION")
    if not AZURE_OPENAI_DEPLOYMENT:
        missing.append("AZURE_OPENAI_DEPLOYMENT")

    if missing:
        raise EnvironmentError(
            f"Missing Azure OpenAI environment variables: {', '.join(missing)}"
        )


def validate_azure_search_config() -> None:
    missing = []

    if not AZURE_SEARCH_ENDPOINT:
        missing.append("AZURE_SEARCH_ENDPOINT")
    if not AZURE_SEARCH_KEY:
        missing.append("AZURE_SEARCH_KEY")
    if not AZURE_SEARCH_INDEX_NAME:
        missing.append("AZURE_SEARCH_INDEX_NAME")

    if missing:
        raise EnvironmentError(
            f"Missing Azure AI Search environment variables: {', '.join(missing)}"
        )