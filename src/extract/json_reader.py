from pathlib import Path
import json

from azure.storage.blob import BlobServiceClient

from src.core.env import (
    AZURE_STORAGE_CONNECTION_STRING,
    AZURE_BLOB_CONTAINER,
)

_blob_service = BlobServiceClient.from_connection_string(
    AZURE_STORAGE_CONNECTION_STRING
)


def list_json_files(input_dir: str | Path) -> list[Path]:
    """
    Returns blob names as Path objects so the rest of the
    application can continue using `.name`, `.stem`, etc.
    """

    prefix = str(input_dir).replace("\\", "/").rstrip("/") + "/"

    container_client = _blob_service.get_container_client(
        AZURE_BLOB_CONTAINER
    )

    return sorted(
        Path(blob.name)
        for blob in container_client.list_blobs(name_starts_with=prefix)
        if blob.name.endswith(".json")
    )


def read_json_file(path: str | Path) -> dict:
    """
    Reads a JSON blob from Azure Blob Storage.
    """

    blob_name = str(path).replace("\\", "/")

    blob_client = _blob_service.get_blob_client(
        container=AZURE_BLOB_CONTAINER,
        blob=blob_name,
    )

    return json.loads(
        blob_client.download_blob().readall()
    )