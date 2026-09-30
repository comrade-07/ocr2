import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from src.core.config_loader import load_yaml
from src.core.logger import get_logger
from src.core.path_settings import bronze_output_dir
from src.extract.json_reader import list_json_files, read_json_file
from src.transform.field_extractor import extract_with_fallback
from src.transform.field_mapper import map_fields
from src.transform.confidence_extractor import build_confidence_summary
from src.output.csv_writer import write_csv
from src.pipeline.run_review_pipeline import run_review_pipeline
from src.review.duplicates import (
    BUSINESS_DUPLICATE_KEY_COLUMN,
    DUPLICATE_GROUP_COLUMN,
    DUPLICATE_MATCH_TYPE_COLUMN,
    DUPLICATE_OF_SOURCE_FILE_COLUMN,
    DUPLICATE_STATUS_COLUMN,
    SOURCE_CONTENT_HASH_COLUMN,
    mark_duplicate_rows,
)

logger = get_logger(__name__)

DEFAULT_INVOICE_TYPE = "scope2"
DEFAULT_LOW_CONFIDENCE_THRESHOLD = 0.80
DEFAULT_BUSINESS_DUPLICATE_FIELDS = [
    "account_number",
    "supplier",
    "invoice_date",
    "total_amount",
    "consumption_start_date_1",
    "consumption_end_date_1",
    "consumption_start_date_2",
    "consumption_end_date_2",
    "quantity_1",
    "quantity_2",
    "quantity_3",
    "quantity_4",
    "quantity_5",
    "quantity_6",
    "quantity_unit_1",
    "quantity_unit_2",
]
DATE_DUPLICATE_FIELDS = {
    "invoice_date",
    "consumption_start_date_1",
    "consumption_end_date_1",
    "consumption_start_date_2",
    "consumption_end_date_2",
    "disposal_date",
    "service_start_date",
    "service_end_date",
    "waste_line_load_date",
}
NUMBER_DUPLICATE_FIELDS = {
    "total_amount",
    "quantity_1",
    "quantity_2",
    "quantity_3",
    "quantity_4",
    "quantity_5",
    "quantity_6",
    "invoice_weight",
    "waste_line_quantity",
    "waste_line_price",
    "waste_line_amount",
}


def _flatten_document_fields(mapped_fields: dict) -> dict:
    flat = {}
    for name, payload in mapped_fields.items():
        flat[name] = payload.get("value")
        flat[f"{name}_confidence"] = payload.get("confidence")
    return flat


def _extract_sharepoint_link(raw_payload: dict) -> str | None:
    return raw_payload.get("sharepoint_link")


def _extract_document_metadata(raw_payload: dict) -> dict:
    metadata_fields = [
        "document_confidence",
        "status",
        "createdDateTime",
        "lastUpdatedDateTime",
        "apiVersion",
        "modelId",
    ]
    return {field: raw_payload.get(field) for field in metadata_fields}


def _source_content_hash(raw_payload: dict, line_payload: dict | None = None, line_id: str | None = None) -> str:
    content = raw_payload.get("fields", raw_payload)
    if line_payload is not None:
        content = {
            "document": content,
            "line": line_payload,
            "line_id": line_id,
        }
    canonical_content = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical_content.encode("utf-8")).hexdigest()


def _business_duplicate_key(document_flat: dict, duplicate_fields: list[str] | None = None) -> str:
    duplicate_fields = duplicate_fields or DEFAULT_BUSINESS_DUPLICATE_FIELDS
    parts = []
    present_core_fields = 0
    present_measure_fields = 0
    for field_name in duplicate_fields:
        normalized_value = _normalize_duplicate_value(field_name, document_flat.get(field_name))
        if not normalized_value:
            continue
        parts.append(f"{field_name}={normalized_value}")
        present_core_fields += 1
        if _is_date_duplicate_field(field_name) or _is_number_duplicate_field(field_name):
            present_measure_fields += 1

    if present_core_fields < 3 or present_measure_fields == 0:
        return ""
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _normalize_duplicate_value(field_name: str, value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    if _is_number_duplicate_field(field_name):
        return _normalize_duplicate_number(text)
    if _is_date_duplicate_field(field_name):
        return _normalize_duplicate_date(text)
    return re.sub(r"[^a-z0-9]+", "", text.casefold())


def _is_date_duplicate_field(field_name: str) -> bool:
    return field_name in DATE_DUPLICATE_FIELDS or field_name.endswith("_date")


def _is_number_duplicate_field(field_name: str) -> bool:
    number_words = ("amount", "quantity", "weight", "price", "scale")
    return field_name in NUMBER_DUPLICATE_FIELDS or any(word in field_name for word in number_words)


def _normalize_duplicate_number(text: str) -> str:
    cleaned = re.sub(r"[^0-9,.\-]", "", text)
    if not cleaned:
        return ""
    if "," in cleaned and "." in cleaned:
        decimal_separator = "," if cleaned.rfind(",") > cleaned.rfind(".") else "."
        thousands_separator = "." if decimal_separator == "," else ","
        cleaned = cleaned.replace(thousands_separator, "").replace(decimal_separator, ".")
    elif "," in cleaned:
        comma_tail = cleaned.rsplit(",", maxsplit=1)[-1]
        cleaned = cleaned.replace(",", ".") if 1 <= len(comma_tail) <= 2 else cleaned.replace(",", "")
    elif "." in cleaned:
        dot_tail = cleaned.rsplit(".", maxsplit=1)[-1]
        if len(dot_tail) > 2:
            cleaned = cleaned.replace(".", "")
    try:
        return f"{float(cleaned):.6f}".rstrip("0").rstrip(".")
    except ValueError:
        return re.sub(r"[^0-9\-]+", "", cleaned)


def _normalize_duplicate_date(text: str) -> str:
    normalized_text = re.sub(r"\s+", " ", text.strip())
    for date_format in (
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%d/%m/%y",
        "%m/%d/%y",
        "%d.%m.%Y",
        "%d.%m.%y",
        "%d %b %Y",
        "%d %B %Y",
    ):
        try:
            return datetime.strptime(normalized_text, date_format).date().isoformat()
        except ValueError:
            continue
    return re.sub(r"[^a-z0-9]+", "", normalized_text.casefold())


def run_pipeline(
    input_dir: str | Path | None = None,
    config_dir: str | Path = "config",
    invoice_type: str | None = None,
) -> Path:
    config_dir = Path(config_dir)
    settings = load_yaml(config_dir / "settings.yaml")
    pipeline_settings = settings.get("pipeline", {})
    invoice_type = invoice_type or pipeline_settings.get("invoice_type", DEFAULT_INVOICE_TYPE)

    input_dir = input_dir or _input_path_for_invoice_type(settings, invoice_type)
    csv_output = bronze_output_dir(settings, invoice_type)
    threshold = pipeline_settings.get("low_confidence_threshold", DEFAULT_LOW_CONFIDENCE_THRESHOLD)

    field_mapping = load_yaml(config_dir / "field_mapping" / f"{invoice_type}_fields.yaml")

    records = []
    json_files = list_json_files(input_dir)
    logger.info("Found %s JSON files in %s", len(json_files), input_dir)

    for json_file in json_files:
        raw_payload = read_json_file(json_file)
        records.extend(_records_for_document(json_file, raw_payload, field_mapping, threshold))

    bronze_path = write_csv(
        mark_duplicate_rows(records),
        csv_output,
        f"{invoice_type}_bronze.csv",
        columns=_bronze_columns(field_mapping),
    )
    run_review_pipeline(config_dir=config_dir, bronze_file=bronze_path, invoice_type=invoice_type)
    return bronze_path


def _records_for_document(
    json_file: Path,
    raw_payload: dict[str, Any],
    field_mapping: dict[str, Any],
    threshold: float,
) -> list[dict[str, Any]]:
    raw_fields = raw_payload.get("fields", raw_payload)
    mapped_fields = map_fields(raw_fields, field_mapping)
    table_rows = _extract_table_rows(raw_fields, field_mapping)
    duplicate_fields = field_mapping.get("duplicate_key", {}).get("fields")

    if not table_rows:
        return [
            _bronze_record(
                json_file=json_file,
                raw_payload=raw_payload,
                mapped_fields=mapped_fields,
                threshold=threshold,
                duplicate_fields=duplicate_fields,
                line_id="1",
            )
        ]

    records = []
    for line_index, line_fields in enumerate(table_rows, start=1):
        combined_fields = {**mapped_fields, **line_fields["mapped_fields"]}
        records.append(
            _bronze_record(
                json_file=json_file,
                raw_payload=raw_payload,
                mapped_fields=combined_fields,
                threshold=threshold,
                duplicate_fields=duplicate_fields,
                line_id=str(line_index),
                line_payload=line_fields["raw_payload"],
            )
        )
    return records


def _bronze_record(
    json_file: Path,
    raw_payload: dict[str, Any],
    mapped_fields: dict[str, dict[str, Any]],
    threshold: float,
    duplicate_fields: list[str] | None,
    line_id: str,
    line_payload: dict | None = None,
) -> dict[str, Any]:
    confidence_summary = build_confidence_summary(mapped_fields, threshold)
    document_flat = _flatten_document_fields(mapped_fields)
    duplicate_values = {**document_flat, "line_id": line_id}
    return {
        "invoice_id": json_file.name,
        "line_id": line_id,
        "source_file": json_file.name,
        "source_path": str(json_file),
        SOURCE_CONTENT_HASH_COLUMN: _source_content_hash(raw_payload, line_payload, line_id if line_payload else None),
        BUSINESS_DUPLICATE_KEY_COLUMN: _business_duplicate_key(duplicate_values, duplicate_fields),
        "sharepoint_link": _extract_sharepoint_link(raw_payload),
        **document_flat,
        **_extract_document_metadata(raw_payload),
        "needs_review": confidence_summary["needs_review"],
        "missing_fields": ";".join(confidence_summary["missing_fields"]),
        "low_confidence_fields": ";".join(confidence_summary["low_confidence_fields"]),
    }


def _extract_table_rows(raw_fields: dict[str, Any], field_mapping: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for _table_name, table_rule in field_mapping.get("tables", {}).items():
        source_name = table_rule.get("source")
        if not source_name:
            continue
        table_payload = raw_fields.get(source_name)
        value_array = table_payload.get("valueArray") if isinstance(table_payload, dict) else None
        if not isinstance(value_array, list):
            continue
        for row_payload in value_array:
            row_object = row_payload.get("valueObject") if isinstance(row_payload, dict) else None
            if not isinstance(row_object, dict):
                continue
            rows.append({
                "raw_payload": row_payload,
                "mapped_fields": _map_table_row(row_object, table_rule.get("fields", {})),
            })
    return rows


def _map_table_row(
    row_object: dict[str, Any],
    row_mapping: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    mapped = {}
    for standard_name, rule in row_mapping.items():
        mapped[standard_name] = extract_with_fallback(row_object, rule.get("sources", []))
    return mapped


def _input_path_for_invoice_type(settings: dict, invoice_type: str) -> str:
    paths = settings.get("paths", {})
    category_key = f"raw_json_{invoice_type}"
    if category_key in paths:
        return paths[category_key]
    if "raw_json_scope2" in paths:
        return paths["raw_json_scope2"]
    raise KeyError(f"Missing input path in settings.yaml: paths.{category_key}")


def _bronze_columns(field_mapping: dict) -> list[str]:
    field_columns = []
    for field_name in _configured_output_fields(field_mapping):
        field_columns.extend([field_name, f"{field_name}_confidence"])
    return [
        "invoice_id",
        "line_id",
        "source_file",
        "source_path",
        SOURCE_CONTENT_HASH_COLUMN,
        BUSINESS_DUPLICATE_KEY_COLUMN,
        DUPLICATE_STATUS_COLUMN,
        DUPLICATE_GROUP_COLUMN,
        DUPLICATE_OF_SOURCE_FILE_COLUMN,
        DUPLICATE_MATCH_TYPE_COLUMN,
        "sharepoint_link",
        *field_columns,
        "document_confidence",
        "status",
        "createdDateTime",
        "lastUpdatedDateTime",
        "apiVersion",
        "modelId",
        "needs_review",
        "missing_fields",
        "low_confidence_fields",
    ]


def _configured_output_fields(field_mapping: dict) -> list[str]:
    fields = list(field_mapping.get("fields", {}))
    for table_rule in field_mapping.get("tables", {}).values():
        fields.extend(table_rule.get("fields", {}).keys())
    return fields
