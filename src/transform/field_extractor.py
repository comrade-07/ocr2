from typing import Any

VALUE_KEYS = ["valueString", "valueNumber", "valueDate", "valueCurrency", "content"]
MOJIBAKE_MARKERS = ("Ã", "Â", "â", "ð", "�")


def repair_utf8_mojibake(value: Any) -> Any:
    """Repair UTF-8 text that was mistakenly decoded as Windows-1252."""
    if not isinstance(value, str) or not any(marker in value for marker in MOJIBAKE_MARKERS):
        return value

    repaired = value
    # Some upstream exports have applied the wrong decode more than once. Stop
    # after three improving passes so legitimate text cannot loop indefinitely.
    for _ in range(3):
        try:
            candidate = repaired.encode("cp1252").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            break

        # Avoid changing legitimate text unless the round-trip clearly removes
        # encoding-error markers.
        current_markers = sum(repaired.count(marker) for marker in MOJIBAKE_MARKERS)
        candidate_markers = sum(candidate.count(marker) for marker in MOJIBAKE_MARKERS)
        if candidate_markers >= current_markers:
            break
        repaired = candidate
    return repaired


def extract_value(field_payload: dict[str, Any] | None) -> Any:
    if not isinstance(field_payload, dict):
        return None
    for key in VALUE_KEYS:
        if key in field_payload and field_payload[key] not in (None, ""):
            return repair_utf8_mojibake(field_payload[key])
    return None


def extract_confidence(field_payload: dict[str, Any] | None) -> float | None:
    if not isinstance(field_payload, dict):
        return None
    confidence = field_payload.get("confidence")
    return float(confidence) if confidence is not None else None


def extract_with_fallback(raw_fields: dict[str, Any], sources: list[str]) -> dict[str, Any]:
    for source_name in sources:
        if source_name in raw_fields:
            payload = raw_fields[source_name]
            return {
                "value": extract_value(payload),
                "confidence": extract_confidence(payload),
                "source_field": source_name,
            }
    return {"value": None, "confidence": None, "source_field": None}
