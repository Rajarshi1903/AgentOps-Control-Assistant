import json
import os
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from openai import AzureOpenAI


load_dotenv()


AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION")
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT")


def validate_llm_config() -> None:
    missing = []

    required = {
        "AZURE_OPENAI_ENDPOINT": AZURE_OPENAI_ENDPOINT,
        "AZURE_OPENAI_API_KEY": AZURE_OPENAI_API_KEY,
        "AZURE_OPENAI_API_VERSION": AZURE_OPENAI_API_VERSION,
        "AZURE_OPENAI_DEPLOYMENT": AZURE_OPENAI_DEPLOYMENT,
    }

    for key, value in required.items():
        if not value:
            missing.append(key)

    if missing:
        raise EnvironmentError(
            f"Missing Azure OpenAI LLM environment variables: {', '.join(missing)}"
        )


def get_azure_openai_chat_client() -> AzureOpenAI:
    validate_llm_config()

    return AzureOpenAI(
        azure_endpoint=AZURE_OPENAI_ENDPOINT,
        api_key=AZURE_OPENAI_API_KEY,
        api_version=AZURE_OPENAI_API_VERSION,
    )


def call_llm_json(
    messages: List[Dict[str, str]],
    temperature: float = 0.0,
    max_tokens: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Calls Azure OpenAI chat model and expects JSON output.

    The system/user prompt must include the word JSON because JSON mode requires
    the model to be instructed to output JSON.
    """

    client = get_azure_openai_chat_client()

    kwargs: Dict[str, Any] = {
        "model": AZURE_OPENAI_DEPLOYMENT,
        "messages": messages,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }

    if max_tokens:
        kwargs["max_tokens"] = max_tokens

    response = client.chat.completions.create(**kwargs)

    raw_content = response.choices[0].message.content

    try:
        return json.loads(raw_content)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"LLM did not return valid JSON. Raw response: {raw_content}"
        ) from exc


def call_llm_text(
    messages: List[Dict[str, str]],
    temperature: float = 0.2,
    max_tokens: Optional[int] = None,
) -> str:
    """
    Calls Azure OpenAI chat model and returns plain text.
    """

    client = get_azure_openai_chat_client()

    kwargs: Dict[str, Any] = {
        "model": AZURE_OPENAI_DEPLOYMENT,
        "messages": messages,
        "temperature": temperature,
    }

    if max_tokens:
        kwargs["max_tokens"] = max_tokens

    response = client.chat.completions.create(**kwargs)

    return response.choices[0].message.content or ""