import csv
import json

from src.pipeline.run_waste_pipeline import run_waste_pipeline


def _write_waste_config(config_dir, source_dir, output_dir, checkpoint_dir):
    (config_dir / "field_mapping").mkdir(parents=True)
    (config_dir / "confidence").mkdir()
    (config_dir / "settings.yaml").write_text(
        "\n".join([
            "paths:",
            f"  raw_json_waste: {source_dir.as_posix()}",
            f"  bronze_output_waste: {output_dir.as_posix()}",
            f"  review_checkpoint_output_waste: {checkpoint_dir.as_posix()}",
            "",
        ]),
        encoding="utf-8",
    )
    (config_dir / "confidence" / "waste_confidence.yaml").write_text(
        "\n".join([
            "thresholds:",
            "  document_confidence: 0.60",
            "  critical: 0.80",
            "  optional: 0.60",
            "  noncritical: 0.30",
            "critical_fields:",
            "  - legal_entity",
            "  - unit_name",
            "  - invoice_date",
            "optional_fields:",
            "  - waste_line_quantity",
            "  - waste_line_unit",
            "noncritical_fields: []",
            "",
        ]),
        encoding="utf-8",
    )
    (config_dir / "field_mapping" / "waste_fields.yaml").write_text(
        "\n".join([
            "fields:",
            "  legal_entity:",
            '    sources: ["Legal Entity"]',
            "  unit_name:",
            '    sources: ["Unit Name"]',
            "  invoice_date:",
            '    sources: ["Invoice Date"]',
            "  waste_disposal_company:",
            '    sources: ["Waste Disposal Company"]',
            "tables:",
            "  waste_details_table:",
            '    source: "Waste Details Table"',
            "    fields:",
            "      waste_line_description:",
            '        sources: ["Description"]',
            "      waste_line_load_date:",
            '        sources: ["Load Date"]',
            "      waste_line_unit:",
            '        sources: ["Unit"]',
            "      waste_line_quantity:",
            '        sources: ["Quantity"]',
            "      waste_line_amount:",
            '        sources: ["Amount"]',
            "duplicate_key:",
            "  fields:",
            "    - line_id",
            "    - legal_entity",
            "    - unit_name",
            "    - invoice_date",
            "    - waste_line_load_date",
            "    - waste_line_quantity",
            "",
        ]),
        encoding="utf-8",
    )


def test_waste_pipeline_expands_waste_details_table_to_bronze_rows(tmp_path):
    source_dir = tmp_path / "source" / "waste"
    config_dir = tmp_path / "config"
    output_dir = tmp_path / "bronze"
    checkpoint_dir = tmp_path / "checkpoints"
    source_dir.mkdir(parents=True)
    _write_waste_config(config_dir, source_dir, output_dir, checkpoint_dir)

    (source_dir / "scalar.json").write_text(
        json.dumps({
            "sharepoint_link": "https://example.com/scalar.pdf",
            "fields": {
                "Legal Entity": {"valueString": "Entity One", "confidence": 0.95},
                "Unit Name": {"valueString": "Unit One", "confidence": 0.96},
                "Invoice Date": {"valueString": "22/09/2025", "confidence": 0.97},
                "Waste Disposal Company": {"valueString": "Disposal Co", "confidence": 0.91},
            },
            "document_confidence": 0.99,
        }),
        encoding="utf-8-sig",
    )
    (source_dir / "table.json").write_text(
        json.dumps({
            "sharepoint_link": "https://example.com/table.pdf",
            "fields": {
                "Legal Entity": {"valueString": "Entity Two", "confidence": 0.95},
                "Unit Name": {"valueString": "Unit Two", "confidence": 0.96},
                "Invoice Date": {"valueString": "01/27/2025", "confidence": 0.97},
                "Waste Disposal Company": {
                    "valueString": "METALLUM COMÃ‰RCIO DE SUCATAS - EIRELI - 1233",
                    "confidence": 0.91,
                },
                "Waste Details Table": {
                    "type": "array",
                    "valueArray": [
                        {
                            "type": "object",
                            "valueObject": {
                                "Description": {"valueString": "Processing and Disposal", "confidence": 0.73},
                                "Load Date": {"valueString": "1/13/2025", "confidence": 0.89},
                                "Unit": {"valueString": "GAL", "confidence": 0.90},
                                "Quantity": {"valueString": "5,000.00", "confidence": 0.89},
                                "Amount": {"valueString": "425.00", "confidence": 0.82},
                            },
                        },
                        {
                            "type": "object",
                            "valueObject": {
                                "Description": {"valueString": "Processing and Disposal", "confidence": 0.73},
                                "Load Date": {"valueString": "1/14/2025", "confidence": 0.89},
                                "Unit": {"valueString": "GAL", "confidence": 0.90},
                                "Quantity": {"valueString": "4,221.00", "confidence": 0.85},
                                "Amount": {"valueString": "358.79", "confidence": 0.79},
                            },
                        },
                        {
                            "type": "object",
                            "valueObject": {
                                "Description": {"valueString": "Processing and Disposal", "confidence": 0.73},
                                "Load Date": {"valueString": "1/13/2025", "confidence": 0.89},
                                "Unit": {"valueString": "GAL", "confidence": 0.90},
                                "Quantity": {"valueString": "5,000.00", "confidence": 0.89},
                                "Amount": {"valueString": "425.00", "confidence": 0.82},
                            },
                        },
                    ],
                },
            },
            "document_confidence": 0.99,
        }),
        encoding="utf-8",
    )

    output = run_waste_pipeline(config_dir=config_dir)

    assert output.read_bytes().startswith(b"\xef\xbb\xbf")

    with output.open(newline="", encoding="utf-8-sig") as file:
        rows = list(csv.DictReader(file))

    assert output == output_dir / "waste_bronze.csv"
    assert len(rows) == 4
    assert [row["source_file"] for row in rows] == ["scalar.json", "table.json", "table.json", "table.json"]
    assert [row["line_id"] for row in rows] == ["1", "1", "2", "3"]
    assert rows[1]["waste_line_quantity"] == "5,000.00"
    assert rows[1]["waste_disposal_company"] == "METALLUM COMÉRCIO DE SUCATAS - EIRELI - 1233"
    assert rows[2]["waste_line_load_date"] == "1/14/2025"
    assert rows[3]["waste_line_load_date"] == "1/13/2025"
    assert [row["duplicate_status"] for row in rows] == ["PRIMARY", "PRIMARY", "PRIMARY", "PRIMARY"]
    assert (checkpoint_dir / "step_2_review_summary_checkpoint.csv").exists()
    for checkpoint_file in checkpoint_dir.glob("*.csv"):
        assert checkpoint_file.read_bytes().startswith(b"\xef\xbb\xbf")
    assert not (checkpoint_dir / "scope2").exists()
