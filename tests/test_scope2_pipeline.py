import csv
import json

from src.pipeline.run_pipeline import run_pipeline


def test_pipeline_writes_sharepoint_link_to_bronze_csv(tmp_path):
    source_dir = tmp_path / "source"
    config_dir = tmp_path / "config"
    output_dir = tmp_path / "bronze"
    checkpoint_dir = tmp_path / "checkpoints"
    source_dir.mkdir()
    (config_dir / "field_mapping").mkdir(parents=True)
    (config_dir / "confidence").mkdir()
    (config_dir / "settings.yaml").write_text(
        "\n".join([
            "paths:",
            f"  raw_json_scope2: {source_dir.as_posix()}",
            f"  bronze_output: {output_dir.as_posix()}",
            f"  review_checkpoint_output: {checkpoint_dir.as_posix()}",
            "",
        ]),
        encoding="utf-8",
    )
    (config_dir / "confidence" / "scope2_confidence.yaml").write_text(
        "\n".join([
            "thresholds:",
            "  critical: 0.80",
            "  optional: 0.60",
            "  noncritical: 0.30",
            "critical_fields:",
            "  - legal_entity",
            "optional_fields: []",
            "noncritical_fields: []",
            "",
        ]),
        encoding="utf-8",
    )
    (config_dir / "field_mapping" / "scope2_fields.yaml").write_text(
        "\n".join([
            "fields:",
            "  legal_entity:",
            '    sources: ["Legal Entity"]',
            "",
        ]),
        encoding="utf-8",
    )

    sharepoint_link = "https://example.sharepoint.com/sites/invoices/sample.pdf"
    source_json = source_dir / "sample.json"
    source_json.write_text(
        json.dumps({
            "sharepoint_link": sharepoint_link,
            "fields": {
                "Legal Entity": {
                    "valueString": "Sample Entity",
                    "confidence": 0.95,
                },
            },
        }),
        encoding="utf-8",
    )

    output = run_pipeline(input_dir=source_dir, config_dir=config_dir)

    assert output.exists()
    with output.open(newline="", encoding="utf-8-sig") as file:
        rows = list(csv.DictReader(file))

    assert rows[0]["sharepoint_link"] == sharepoint_link
    assert (checkpoint_dir / "scope2" / "step_2_review_summary_checkpoint.csv").exists()


def test_pipeline_writes_document_metadata_to_bronze_csv(tmp_path):
    source_dir = tmp_path / "source"
    config_dir = tmp_path / "config"
    output_dir = tmp_path / "bronze"
    checkpoint_dir = tmp_path / "checkpoints"
    source_dir.mkdir()
    (config_dir / "field_mapping").mkdir(parents=True)
    (config_dir / "confidence").mkdir()
    (config_dir / "settings.yaml").write_text(
        "\n".join([
            "paths:",
            f"  raw_json_scope2: {source_dir.as_posix()}",
            f"  bronze_output: {output_dir.as_posix()}",
            f"  review_checkpoint_output: {checkpoint_dir.as_posix()}",
            "",
        ]),
        encoding="utf-8",
    )
    (config_dir / "confidence" / "scope2_confidence.yaml").write_text(
        "\n".join([
            "thresholds:",
            "  critical: 0.80",
            "  optional: 0.60",
            "  noncritical: 0.30",
            "critical_fields:",
            "  - legal_entity",
            "optional_fields: []",
            "noncritical_fields: []",
            "",
        ]),
        encoding="utf-8",
    )
    (config_dir / "field_mapping" / "scope2_fields.yaml").write_text(
        "\n".join([
            "fields:",
            "  legal_entity:",
            '    sources: ["Legal Entity"]',
            "",
        ]),
        encoding="utf-8",
    )

    source_json = source_dir / "sample.json"
    source_json.write_text(
        json.dumps({
            "fields": {
                "Legal Entity": {
                    "valueString": "Sample Entity",
                    "confidence": 0.95,
                },
            },
            "document_confidence": 0.999,
            "status": "succeeded",
            "createdDateTime": "2026-06-14T15:07:06Z",
            "lastUpdatedDateTime": "2026-06-14T15:07:12Z",
            "apiVersion": "2024-11-30",
            "modelId": "ocr-scope2-260609",
        }),
        encoding="utf-8",
    )

    output = run_pipeline(input_dir=source_dir, config_dir=config_dir)

    assert output.exists()
    with output.open(newline="", encoding="utf-8-sig") as file:
        rows = list(csv.DictReader(file))

    assert rows[0]["document_confidence"] == "0.999"
    assert rows[0]["status"] == "succeeded"
    assert rows[0]["createdDateTime"] == "2026-06-14T15:07:06Z"
    assert rows[0]["lastUpdatedDateTime"] == "2026-06-14T15:07:12Z"
    assert rows[0]["apiVersion"] == "2024-11-30"
    assert rows[0]["modelId"] == "ocr-scope2-260609"


def test_pipeline_routes_renamed_duplicate_content_to_flagged_duplicate_checkpoint(tmp_path):
    source_dir = tmp_path / "source"
    config_dir = tmp_path / "config"
    output_dir = tmp_path / "bronze"
    checkpoint_dir = tmp_path / "checkpoints"
    source_dir.mkdir()
    (config_dir / "field_mapping").mkdir(parents=True)
    (config_dir / "confidence").mkdir()
    (config_dir / "settings.yaml").write_text(
        "\n".join([
            "paths:",
            f"  raw_json_scope2: {source_dir.as_posix()}",
            f"  bronze_output: {output_dir.as_posix()}",
            f"  review_checkpoint_output: {checkpoint_dir.as_posix()}",
            "",
        ]),
        encoding="utf-8",
    )
    (config_dir / "confidence" / "scope2_confidence.yaml").write_text(
        "\n".join([
            "thresholds:",
            "  critical: 0.80",
            "  optional: 0.60",
            "  noncritical: 0.30",
            "critical_fields:",
            "  - legal_entity",
            "optional_fields: []",
            "noncritical_fields: []",
            "",
        ]),
        encoding="utf-8",
    )
    (config_dir / "field_mapping" / "scope2_fields.yaml").write_text(
        "\n".join([
            "fields:",
            "  legal_entity:",
            '    sources: ["Legal Entity"]',
            "",
        ]),
        encoding="utf-8",
    )

    shared_fields = {
        "Legal Entity": {
            "valueString": "Sample Entity",
            "confidence": 0.95,
        },
    }
    (source_dir / "invoice_a.json").write_text(
        json.dumps({
            "fields": shared_fields,
            "createdDateTime": "2026-06-14T15:07:06Z",
        }),
        encoding="utf-8",
    )
    (source_dir / "invoice_b_renamed.json").write_text(
        json.dumps({
            "fields": shared_fields,
            "createdDateTime": "2026-06-15T15:07:06Z",
        }),
        encoding="utf-8",
    )

    output = run_pipeline(input_dir=source_dir, config_dir=config_dir)

    with output.open(newline="", encoding="utf-8-sig") as file:
        bronze_rows = list(csv.DictReader(file))
    with (checkpoint_dir / "scope2" / "step_0_flagged_duplicates_checkpoint.csv").open(
        newline="",
        encoding="utf-8-sig",
    ) as file:
        duplicate_rows = list(csv.DictReader(file))
    with (checkpoint_dir / "scope2" / "step_2_review_summary_checkpoint.csv").open(
        newline="",
        encoding="utf-8-sig",
    ) as file:
        summary_rows = list(csv.DictReader(file))

    assert [row["duplicate_status"] for row in bronze_rows] == ["PRIMARY", "DUPLICATE"]
    assert len(duplicate_rows) == 1
    assert duplicate_rows[0]["source_file"] == "invoice_b_renamed.json"
    assert duplicate_rows[0]["duplicate_of_source_file"] == "invoice_a.json"
    assert [row["invoice_id"] for row in summary_rows] == ["invoice_a.json"]


def test_pipeline_routes_duplicate_with_different_ocr_confidence_by_business_key(tmp_path):
    source_dir = tmp_path / "source"
    config_dir = tmp_path / "config"
    output_dir = tmp_path / "bronze"
    checkpoint_dir = tmp_path / "checkpoints"
    source_dir.mkdir()
    (config_dir / "field_mapping").mkdir(parents=True)
    (config_dir / "confidence").mkdir()
    (config_dir / "settings.yaml").write_text(
        "\n".join([
            "paths:",
            f"  raw_json_scope2: {source_dir.as_posix()}",
            f"  bronze_output: {output_dir.as_posix()}",
            f"  review_checkpoint_output: {checkpoint_dir.as_posix()}",
            "",
        ]),
        encoding="utf-8",
    )
    (config_dir / "confidence" / "scope2_confidence.yaml").write_text(
        "\n".join([
            "thresholds:",
            "  critical: 0.80",
            "  optional: 0.60",
            "  noncritical: 0.30",
            "critical_fields:",
            "  - account_number",
            "optional_fields: []",
            "noncritical_fields: []",
            "",
        ]),
        encoding="utf-8",
    )
    (config_dir / "field_mapping" / "scope2_fields.yaml").write_text(
        "\n".join([
            "fields:",
            "  supplier:",
            '    sources: ["Supplier"]',
            "  account_number:",
            '    sources: ["Account Number"]',
            "  invoice_date:",
            '    sources: ["Invoice Date"]',
            "  total_amount:",
            '    sources: ["Total Amount"]',
            "  consumption_start_date_1:",
            '    sources: ["Consumption Start Date"]',
            "  consumption_end_date_1:",
            '    sources: ["Consumption End Date"]',
            "  quantity_1:",
            '    sources: ["Quantity 1"]',
            "",
        ]),
        encoding="utf-8",
    )

    (source_dir / "clean_invoice.json").write_text(
        json.dumps({
            "fields": {
                "Supplier": {"valueString": "ABC Utility", "confidence": 0.99},
                "Account Number": {"valueString": "ACC-100", "confidence": 0.99},
                "Invoice Date": {"valueString": "2026-06-01", "confidence": 0.99},
                "Total Amount": {"valueString": "USD 1,234.50", "confidence": 0.99},
                "Consumption Start Date": {"valueString": "2026-05-01", "confidence": 0.99},
                "Consumption End Date": {"valueString": "2026-05-31", "confidence": 0.99},
                "Quantity 1": {"valueString": "1,000.00", "confidence": 0.99},
            },
        }),
        encoding="utf-8",
    )
    (source_dir / "rough_invoice_copy.json").write_text(
        json.dumps({
            "fields": {
                "Supplier": {"valueString": " ABC Utility ", "confidence": 0.82},
                "Account Number": {"valueString": "ACC 100", "confidence": 0.84},
                "Invoice Date": {"valueString": "01/06/2026", "confidence": 0.81},
                "Total Amount": {"valueString": "$1234.5", "confidence": 0.80},
                "Consumption Start Date": {"valueString": "01/05/2026", "confidence": 0.80},
                "Consumption End Date": {"valueString": "31/05/2026", "confidence": 0.80},
                "Quantity 1": {"valueString": "1000", "confidence": 0.80},
            },
        }),
        encoding="utf-8",
    )

    output = run_pipeline(input_dir=source_dir, config_dir=config_dir)

    with output.open(newline="", encoding="utf-8-sig") as file:
        bronze_rows = list(csv.DictReader(file))
    with (checkpoint_dir / "scope2" / "step_0_flagged_duplicates_checkpoint.csv").open(
        newline="",
        encoding="utf-8-sig",
    ) as file:
        duplicate_rows = list(csv.DictReader(file))

    assert [row["duplicate_status"] for row in bronze_rows] == ["PRIMARY", "DUPLICATE"]
    assert duplicate_rows[0]["source_file"] == "rough_invoice_copy.json"
    assert duplicate_rows[0]["duplicate_of_source_file"] == "clean_invoice.json"
    assert duplicate_rows[0]["duplicate_match_type"] == "BUSINESS_KEY"
