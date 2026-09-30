"""Construct browser evidence addresses without contacting SharePoint."""

from pathlib import Path
from urllib.parse import quote, unquote, urlsplit, urlunsplit


def build_upload_evidence_url(
    stored_file_path: Path, upload_directory: Path, folder_url: str
) -> str:
    """Append the saved relative path to a configured direct SharePoint folder URL."""
    if not isinstance(folder_url, str):
        raise ValueError(
            'The evidence folder URL must be text; use "" to disable links.'
        )
    folder_url = folder_url.strip()
    if folder_url == "":
        return ""

    parsed_url = urlsplit(folder_url)
    if parsed_url.scheme != "https" or parsed_url.hostname is None:
        raise ValueError("The evidence folder URL must be an absolute HTTPS address.")
    if parsed_url.username is not None or parsed_url.password is not None:
        raise ValueError("The evidence folder URL must not contain credentials.")
    if parsed_url.query != "" or parsed_url.fragment != "":
        raise ValueError(
            "Use the direct SharePoint folder URL, without query parameters or fragments."
        )
    folder_path = unquote(parsed_url.path).rstrip("/")
    if folder_path.lower().endswith(".aspx") or folder_path.startswith("/:"):
        raise ValueError(
            "Use the direct folder URL, not a SharePoint page or sharing link."
        )

    try:
        relative_path = stored_file_path.resolve().relative_to(
            upload_directory.resolve()
        )
    except ValueError as error:
        raise ValueError(
            "The evidence file must be inside the configured upload folder."
        ) from error
    if relative_path == Path("."):
        raise ValueError(
            "The evidence path must identify a file within the upload folder."
        )

    # Decode only the configured URL. A '%' in a saved filename is literal data.
    encoded_folder = quote(folder_path, safe="/")
    encoded_file = quote(relative_path.as_posix(), safe="/")
    evidence_path = f"{encoded_folder}/{encoded_file}"
    return urlunsplit((parsed_url.scheme, parsed_url.netloc, evidence_path, "", ""))
