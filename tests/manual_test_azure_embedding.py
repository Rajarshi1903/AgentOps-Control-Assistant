import os
from dotenv import load_dotenv
from openai import AzureOpenAI

load_dotenv()

endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
api_key = os.getenv("AZURE_OPENAI_API_KEY")
api_version = os.getenv("AZURE_OPENAI_API_VERSION")
embedding_deployment = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT")

print("Endpoint:", endpoint)
print("API version:", api_version)
print("Embedding deployment:", embedding_deployment)

client = AzureOpenAI(
    azure_endpoint=endpoint,
    api_key=api_key,
    api_version=api_version,
)

response = client.embeddings.create(
    model=embedding_deployment,
    input="This is a test embedding request."
)

embedding = response.data[0].embedding

print("Embedding generated successfully.")
print("Embedding dimensions:", len(embedding))
