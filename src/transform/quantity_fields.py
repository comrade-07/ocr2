from __future__ import annotations

import re
from typing import Any

import pandas as pd


QUANTITY_FIELDS = tuple(f"quantity_{index}" for index in range(1, 7))
DASH_CHARACTER_RE = re.compile(r"[-\u2010-\u2015]+")
# OCR sometimes appends units or explanatory text to quantities; capture only the
# first numeric token so the existing decimal-separator cleaner can normalize it.
QUANTITY_NUMBER_RE = re.compile(r"(?:\d+(?:(?:\s*[.,]\s*|\s+)\d+)*|[.,]\s*\d+)")


def clean_quantity_columns(df: pd.DataFrame) -> pd.DataFrame:
    if "decimal_separator" not in df.columns:
        return df.copy()

    result = df.copy()
    if "total_amount" in result.columns:
        result["total_amount"] = result.apply(
            lambda row: clean_amount_value(row.get("total_amount"), row.get("decimal_separator")),
            axis=1,
        )

    for field in QUANTITY_FIELDS:
        if field not in result.columns:
            continue
        result[field] = result.apply(
            lambda row: clean_quantity_value(row.get(field), row.get("decimal_separator")),
            axis=1,
        )
    return result


def clean_amount_value(value: Any, decimal_separator: Any) -> Any:
    if _is_blank(value):
        return value
    return _apply_decimal_separator(_remove_currency_units(value), decimal_separator)


def clean_quantity_value(value: Any, decimal_separator: Any) -> Any:
    if _is_blank(value):
        return value
    return _apply_decimal_separator(_extract_quantity_number(value), decimal_separator)


def _apply_decimal_separator(value: Any, decimal_separator: Any) -> Any:
    separator = str(decimal_separator or "").strip()
    if separator not in {",", "."}:
        return value

    text = str(value).strip()
    if separator == ",":
        return text.replace(".", "").replace(",", ".")

    if "," in text:
        return text.replace(",", "")
    return value


def _remove_currency_units(value: Any) -> str:
    text = str(value).strip()
    text = re.sub(r"[A-Za-z]{2,5}", "", text)
    text = re.sub(r"[$€£¥₹₩₫₱฿₦₴₽₪₺₡₲₵₭₮₸₼₾₿]", "", text)
    return text.strip()


def _extract_quantity_number(value: Any) -> Any:
    if isinstance(value, int | float):
        return value

    text = DASH_CHARACTER_RE.sub(" ", str(value).strip())
    match = QUANTITY_NUMBER_RE.search(text)
    if match is None:
        return text
    return re.sub(r"\s+", "", match.group(0))


def _is_blank(value: Any) -> bool:
    return value is None or pd.isna(value) or str(value).strip() == ""
