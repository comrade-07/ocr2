from typing import Any


def build_confidence_summary(mapped_fields: dict[str, dict[str, Any]], threshold: float) -> dict[str, Any]:
    low_confidence = []
    missing = []

    for field_name, payload in mapped_fields.items():
        value = payload.get("value")
        confidence = payload.get("confidence")
        if value in (None, ""):
            missing.append(field_name)
        elif confidence is not None and confidence < threshold:
            low_confidence.append(field_name)

    return {
        "missing_fields": missing,
        "low_confidence_fields": low_confidence,
        "needs_review": bool(missing or low_confidence),
    }
