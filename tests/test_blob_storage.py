import sys
import types

import pytest

from src.core.blob_storage import manual_blob_name, upload_manual_file


def test_manual_blob_name_normalizes_separators():
    assert (
        manual_blob_name("scope2", "invoice.pdf", "/dev\\manual/")
        == "dev/manual/scope2/invoice.pdf"
    )


@pytest.mark.parametrize("unsafe_value", ["", ".", "..", "folder/../file.pdf"])
def test_manual_blob_name_rejects_unsafe_paths(unsafe_value):
    with pytest.raises(ValueError):
        manual_blob_name("scope2", unsafe_value)


def test_upload_manual_file_requires_configuration(monkeypatch):
    monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)
    monkeypatch.delenv("AZURE_BLOB_CONTAINER", raising=False)

    with pytest.raises(ValueError, match="AZURE_STORAGE_CONNECTION_STRING"):
        upload_manual_file("manual/scope2/invoice.pdf", b"invoice")


def test_upload_manual_file_returns_read_only_sas_url(monkeypatch):
    uploaded = {}

    class FakeAzureError(Exception):
        pass

    class FakeBlobClient:
        url = "https://account.blob.test/container/manual/scope2/invoice.pdf"

        def upload_blob(self, data, overwrite, content_settings):
            uploaded.update(
                data=data,
                overwrite=overwrite,
                content_settings=content_settings,
            )

    class FakeBlobServiceClient:
        account_name = "account"

        @classmethod
        def from_connection_string(cls, connection_string):
            uploaded["connection_string"] = connection_string
            return cls()

        def get_blob_client(self, *, container, blob):
            uploaded.update(container=container, blob=blob)
            return FakeBlobClient()

    class FakeBlobSasPermissions:
        def __init__(self, *, read):
            self.read = read

    class FakeContentSettings:
        def __init__(self, *, content_type, content_disposition):
            self.content_type = content_type
            self.content_disposition = content_disposition

    def fake_generate_blob_sas(**kwargs):
        uploaded["sas"] = kwargs
        return "sig=read-only"

    azure_module = types.ModuleType("azure")
    azure_module.__path__ = []
    azure_core_module = types.ModuleType("azure.core")
    azure_core_module.__path__ = []
    azure_exceptions_module = types.ModuleType("azure.core.exceptions")
    azure_storage_module = types.ModuleType("azure.storage")
    azure_storage_module.__path__ = []
    azure_blob_module = types.ModuleType("azure.storage.blob")
    azure_exceptions_module.AzureError = FakeAzureError
    azure_blob_module.BlobServiceClient = FakeBlobServiceClient
    azure_blob_module.BlobSasPermissions = FakeBlobSasPermissions
    azure_blob_module.ContentSettings = FakeContentSettings
    azure_blob_module.generate_blob_sas = fake_generate_blob_sas

    monkeypatch.setitem(sys.modules, "azure", azure_module)
    monkeypatch.setitem(sys.modules, "azure.core", azure_core_module)
    monkeypatch.setitem(sys.modules, "azure.core.exceptions", azure_exceptions_module)
    monkeypatch.setitem(sys.modules, "azure.storage", azure_storage_module)
    monkeypatch.setitem(sys.modules, "azure.storage.blob", azure_blob_module)
    monkeypatch.setenv(
        "AZURE_STORAGE_CONNECTION_STRING",
        "DefaultEndpointsProtocol=https;AccountName=account;AccountKey=secret==;EndpointSuffix=core.windows.net",
    )
    monkeypatch.setenv("AZURE_BLOB_CONTAINER", "container")

    result = upload_manual_file(
        "manual/scope2/invoice.pdf",
        b"invoice",
        link_mode="sas",
        sas_years=2,
    )

    assert result.endswith("?sig=read-only")
    assert uploaded["data"] == b"invoice"
    assert uploaded["overwrite"] is False
    assert uploaded["container"] == "container"
    assert uploaded["blob"] == "manual/scope2/invoice.pdf"
    assert uploaded["content_settings"].content_type == "application/pdf"
    assert uploaded["content_settings"].content_disposition == "inline"
    assert uploaded["sas"]["account_key"] == "secret=="
    assert uploaded["sas"]["permission"].read is True
