from dotenv import load_dotenv
import os

loaded = load_dotenv()

print("Loaded:", loaded)
print("Connection:", os.getenv("AZURE_STORAGE_CONNECTION_STRING"))
print("Container:", os.getenv("AZURE_BLOB_CONTAINER"))

AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
AZURE_BLOB_CONTAINER = os.getenv("AZURE_BLOB_CONTAINER")