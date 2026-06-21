import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import os
from dotenv import load_dotenv
from openai import AzureOpenAI

load_dotenv()

endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
api_key = os.getenv("AZURE_OPENAI_API_KEY")
api_version = os.getenv("AZURE_OPENAI_API_VERSION")
deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")

print("AZURE_OPENAI_ENDPOINT:", endpoint)
print("AZURE_OPENAI_API_VERSION:", api_version)
print("AZURE_OPENAI_DEPLOYMENT:", deployment)
print("API key present:", bool(api_key))

client = AzureOpenAI(
    azure_endpoint=endpoint,
    api_key=api_key,
    api_version=api_version,
)

response = client.chat.completions.create(
    model=deployment,
    messages=[
        {
            "role": "system",
            "content": "You are a test assistant. Return JSON only.",
        },
        {
            "role": "user",
            "content": 'Return JSON exactly like {"status": "ok", "message": "LLM is working"}',
        },
    ],
    temperature=0.7,
    response_format={"type": "json_object"},
)

print("RAW RESPONSE:")
print(response.choices[0].message.content)