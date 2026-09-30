from typing import Any
from src.transform.field_extractor import extract_with_fallback


def map_fields(raw_fields: dict[str, Any], field_mapping_config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    mapped = {}
    for standard_name, rule in field_mapping_config.get("fields", {}).items():
        sources = rule.get("sources", [])
        mapped[standard_name] = extract_with_fallback(raw_fields, sources)
    return mapped
