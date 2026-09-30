"""Azure Blob Storage helpers for manually uploaded invoice files."""

from datetime import datetime, timedelta, timezone
import mimetypes
import os

from dotenv import load_dotenv

load_dotenv()

DEFAULT_MANUAL_PREFIX = "dev/manual"
_SUPPORTED_LINK_MODES = {"url", "sas"}


def _normalized_blob_path(value: str, label: str) -> str:
    """Normalize blob path separators and reject empty or unsafe segments."""
    normalized = str(value).replace("\\", "/").strip("/")
    segments = normalized.split("/")
    if not normalized or any(segment in {"", ".", ".."} for segment in segments):
        raise ValueError(
            f"{label} must be a non-empty blob path without '.', '..', or empty segments."
        )
    return "/".join(segments)


def manual_blob_name(
    category_key: str,
    file_name: str,
    prefix: str = DEFAULT_MANUAL_PREFIX,
) -> str:
    """Build a normalized blob name for a manual invoice upload."""
    return "/".join(
        (
            _normalized_blob_path(prefix, "prefix"),
            _normalized_blob_path(category_key, "category_key"),
            _normalized_blob_path(file_name, "file_name"),
        )
    )


def _connection_string_parts(connection_string: str) -> dict[str, str]:
    parts: dict[str, str] = {}
    for item in connection_string.split(";"):
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        parts[key.strip().lower()] = value.strip()
    return parts


def upload_manual_file(
    blob_name: str,
    data: bytes,
    *,
    link_mode: str = "url",
    sas_years: int = 10,
) -> str:
    """Upload bytes and return either the blob URL or a read-only SAS URL."""
    connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "").strip()
    container_name = os.getenv("AZURE_BLOB_CONTAINER", "").strip()
    if not connection_string:
        raise ValueError("AZURE_STORAGE_CONNECTION_STRING is not configured.")
    if not container_name:
        raise ValueError("AZURE_BLOB_CONTAINER is not configured.")

    normalized_blob_name = _normalized_blob_path(blob_name, "blob_name")
    normalized_link_mode = str(link_mode).strip().lower()
    if normalized_link_mode not in _SUPPORTED_LINK_MODES:
        raise ValueError("manual_upload_blob.link_mode must be 'url' or 'sas'.")
    if normalized_link_mode == "sas" and sas_years < 1:
        raise ValueError("manual_upload_blob.sas_years must be at least 1.")

    try:
        from azure.core.exceptions import AzureError
        from azure.storage.blob import (
            BlobSasPermissions,
            BlobServiceClient,
            ContentSettings,
            generate_blob_sas,
        )

        blob_service = BlobServiceClient.from_connection_string(connection_string)
        blob_client = blob_service.get_blob_client(
            container=container_name,
            blob=normalized_blob_name,
        )
        content_type = mimetypes.guess_type(normalized_blob_name)[0] or "application/octet-stream"
        blob_client.upload_blob(
            data,
            overwrite=False,
            content_settings=ContentSettings(
                content_type=content_type,
                content_disposition="inline",
            ),
        )

        if normalized_link_mode == "url":
            return blob_client.url

        connection_parts = _connection_string_parts(connection_string)
        account_name = connection_parts.get("accountname") or blob_service.account_name
        account_key = connection_parts.get("accountkey")
        if not account_name or not account_key:
            raise ValueError(
                "SAS links require AccountName and AccountKey in "
                "AZURE_STORAGE_CONNECTION_STRING."
            )

        now = datetime.now(timezone.utc)
        sas_token = generate_blob_sas(
            account_name=account_name,
            container_name=container_name,
            blob_name=normalized_blob_name,
            account_key=account_key,
            permission=BlobSasPermissions(read=True),
            start=now - timedelta(minutes=5),
            expiry=now + timedelta(days=365 * sas_years),
        )
        return f"{blob_client.url}?{sas_token}"
    except ValueError:
        raise
    except (AzureError, OSError) as error:
        raise ValueError(f"Azure Blob upload failed: {error}") from error
