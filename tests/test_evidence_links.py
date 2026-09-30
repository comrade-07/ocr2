from pathlib import Path

import pytest

from src.review.evidence_links import build_upload_evidence_url


def test_saved_path_is_encoded_relative_to_upload_folder(tmp_path: Path) -> None:
    saved_file = tmp_path / "2026 bills" / "20260914_invoice #1% & costs.pdf"
    actual = build_upload_evidence_url(
        saved_file,
        tmp_path,
        "https://tenant.sharepoint.com/sites/ESG/Shared%20Documents/Evidence/",
    )
    assert actual == (
        "https://tenant.sharepoint.com/sites/ESG/Shared%20Documents/Evidence/"
        "2026%20bills/20260914_invoice%20%231%25%20%26%20costs.pdf"
    )


def test_unconfigured_url_preserves_local_only_uploads(tmp_path: Path) -> None:
    assert build_upload_evidence_url(tmp_path / "bill.pdf", tmp_path, "") == ""


@pytest.mark.parametrize(
    "folder_url",
    [
        "C:/Evidence",
        "http://tenant.sharepoint.com/Evidence",
        "https://tenant.sharepoint.com/Forms/AllItems.aspx",
        "https://tenant.sharepoint.com/Evidence?id=folder",
        "https://tenant.sharepoint.com/:f:/s/ESG/sharing-token",
        "https://tenant.sharepoint.com/Evidence#folder",
    ],
)
def test_invalid_folder_urls_are_rejected(tmp_path: Path, folder_url: str) -> None:
    with pytest.raises(ValueError):
        build_upload_evidence_url(tmp_path / "bill.pdf", tmp_path, folder_url)


def test_file_outside_upload_directory_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="inside"):
        build_upload_evidence_url(
            tmp_path / "elsewhere" / "bill.pdf",
            tmp_path / "uploads",
            "https://tenant.sharepoint.com/Evidence",
        )
