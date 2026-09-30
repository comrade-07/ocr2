from dotenv import load_dotenv
import os

load_dotenv()

AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
AZURE_BLOB_CONTAINER = os.getenv("AZURE_BLOB_CONTAINER")