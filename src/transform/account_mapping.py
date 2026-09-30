from __future__ import annotations

from pathlib import Path
from typing import Any
import re

import pandas as pd

from src.normalize.text_normalizer import clean_energy_unit

from src.lookup.mapping_lookup import (
    build_lookup_key,
    load_lookup_config,
    load_lookup_table,
    normalize_lookup_value,
)


ACCOUNT_MAPPING_COLUMNS = [
    "division",
    "legal_entity",
    "unit_name",
    "supplier_name",
    "division_shorthand",
    "facility_type",
    "scope",
    "facility_identifier",
    "activity_group",
    "invoice_count",
    "invoice_frequency",
    "consumption_unit",
    "decimal_separator",
    "currency",
]
OCR_CONTEXT_COLUMNS = {"legal_entity", "unit_name"}
SCOPE2_ACTIVITY_GROUPS = ("Electricity", "Steam", "Heat", "Cool")
MAPPING_RESULT_COLUMNS = ["mapping_status", "mapping_method", "mapping_message", "extracted_account_number"]
MAPPING_COLUMN_ALIASES = {
    "effective_start_date": ("effective_start_date", "effective start date"),
    "effective_end_date": ("effective_end_date", "effective end date"),
    "account_number": ("account_number", "account number", "account no", "account #"),
    "division": ("division",),
    "legal_entity": ("legal_entity", "legal entity", "legal entity name", "legal_entity_name"),
    "unit_name": ("unit_name", "unit name", "unit"),
    "supplier_name": ("supplier_name", "supplier name", "supplier"),
    "division_shorthand": ("division_shorthand", "division shorthand"),
    "facility_type": ("facility_type", "facility type"),
    "scope": ("scope",),
    "facility_identifier": ("facility_identifier", "facility identifier"),
    "activity_group": ("activity_group", "activity group", "energy type"),
    "invoice_count": ("invoice_count", "invoice count"),
    "invoice_frequency": ("invoice_frequency", "invoice frequency"),
    "consumption_unit": ("consumption_unit", "consumption unit", "energy unit"),
    "decimal_separator": ("decimal_separator", "decimal separator"),
    "currency": ("currency",),
    "ocr_unit_name_list": ("ocr_unit_name_list", "ocr unit name list"),
    "ocr_legal_entity_name_list": (
        "ocr_legal_entity_name_list",
        "ocr legal entity name list",
    ),
}


def load_account_mapping_table(
    config_dir: str | Path = "config",
    lookup_name: str = "mapping",
) -> pd.DataFrame:
    config = load_lookup_config(lookup_name, config_dir=config_dir)
    table = _canonicalize_mapping_columns(load_lookup_table(config))
    _require_mapping_columns(table)
    activity_groups = {value.casefold(): value for value in SCOPE2_ACTIVITY_GROUPS}
    table["activity_group"] = table["activity_group"].map(
        lambda value: activity_groups.get(normalize_lookup_value(value), value)
    )
    return table


def manual_mapping_candidates(table: pd.DataFrame, values: dict[str, Any]) -> pd.DataFrame:
    candidates = table
    for column in ("division", "legal_entity", "unit_name", "activity_group", "account_number"):
        value = values.get(column)
        if not _is_blank(value):
            candidates = candidates[candidates[column].map(normalize_lookup_value) == normalize_lookup_value(value)]
    return candidates


def add_account_mapping_columns(
    df: pd.DataFrame,
    config_dir: str | Path = "config",
    lookup_name: str = "mapping",
    return_mapped_fields: bool = False,
) -> pd.DataFrame | tuple[pd.DataFrame, dict[str, pd.Series]]:
    table = load_account_mapping_table(config_dir, lookup_name)

    lookup_by_account = _lookup_by_account_number(table)
    lookup_by_unit_alias = _lookup_by_alias(table, "ocr_unit_name_list")
    lookup_by_legal_entity_alias = _lookup_by_alias(table, "ocr_legal_entity_name_list")
    result = df.copy()
    result["extracted_account_number"] = df.get("extracted_account_number", df.get("account_number", ""))
    for column in MAPPING_RESULT_COLUMNS[:3]:
        result[column] = ""
    mapped_fields = {
        column: pd.Series(False, index=result.index)
        for column in ACCOUNT_MAPPING_COLUMNS
    }

    for column in ACCOUNT_MAPPING_COLUMNS:
        if column in OCR_CONTEXT_COLUMNS and column in result.columns:
            result[column] = result[column].astype(object)
        else:
            result[column] = pd.Series([""] * len(result), index=result.index, dtype=object)

    for index, row in df.iterrows():
        mapping_row, status, method = _find_mapping_row(
            row.to_dict(),
            lookup_by_account=lookup_by_account,
            lookup_by_unit_alias=lookup_by_unit_alias,
            lookup_by_legal_entity_alias=lookup_by_legal_entity_alias,
        )
        _set_mapping_result(result, index, status, method)
        if mapping_row is None:
            continue
        result.at[index, "account_number"] = mapping_row.get("account_number", "")
        for column in ACCOUNT_MAPPING_COLUMNS:
            value = mapping_row.get(column)
            if not _is_blank(value):
                result.at[index, column] = value
                mapped_fields[column].at[index] = True

    ordered_result = _order_mapping_columns_after_account_number(result)
    if return_mapped_fields:
        return ordered_result, mapped_fields
    return ordered_result


def add_manual_unit_mapping_columns(
    df: pd.DataFrame,
    config_dir: str | Path = "config",
    lookup_name: str = "mapping",
) -> pd.DataFrame:
    table = load_account_mapping_table(config_dir, lookup_name)

    lookup_by_unit_name = _lookup_by_column(table, "unit_name")
    result = df.copy()
    for column in MAPPING_RESULT_COLUMNS:
        result[column] = ""
    if "account_number" not in result.columns:
        result["account_number"] = pd.Series([""] * len(result), index=result.index, dtype=object)

    for column in ACCOUNT_MAPPING_COLUMNS:
        if column in result.columns:
            result[column] = result[column].astype(object)
        else:
            result[column] = pd.Series([""] * len(result), index=result.index, dtype=object)

    for index, row in result.iterrows():
        if _is_blank(row.get("activity_group")):
            # Old checkpoints selected a unit only. Keep unique legacy matches.
            candidates = lookup_by_unit_name.get(normalize_lookup_value(row.get("unit_name")), [])
            if not _is_blank(row.get("account_number")):
                candidates = [
                    candidate for candidate in candidates
                    if normalize_lookup_value(candidate.get("account_number")) == normalize_lookup_value(row.get("account_number"))
                ]
        else:
            candidates = manual_mapping_candidates(table, row.to_dict()).to_dict("records")
        mapping_row, status = _unique_mapping(candidates)
        _set_mapping_result(result, index, status, "MANUAL_SELECTION")
        if mapping_row is None:
            continue
        for column in ["account_number", *ACCOUNT_MAPPING_COLUMNS]:
            if column == "consumption_unit" and clean_energy_unit(row.get(column)):
                continue
            value = mapping_row.get(column)
            if not _is_blank(value):
                result.at[index, column] = value

    return _order_mapping_columns_after_account_number(result)


def _find_mapping_row(
    row: dict[str, Any],
    lookup_by_account: dict[str, list[dict[str, Any]]],
    lookup_by_unit_alias: dict[str, list[dict[str, Any]]],
    lookup_by_legal_entity_alias: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, Any] | None, str, str]:
    for field, lookup, method in (
        ("account_number", lookup_by_account, "ACCOUNT"),
        ("unit_name", lookup_by_unit_alias, "UNIT_ALIAS"),
        ("legal_entity", lookup_by_legal_entity_alias, "LEGAL_ENTITY_ALIAS"),
    ):
        candidates = lookup.get(normalize_lookup_value(row.get(field)), [])
        if not candidates:
            continue
        activity_group = normalize_lookup_value(row.get("activity_group"))
        if activity_group:
            candidates = [
                candidate for candidate in candidates
                if normalize_lookup_value(candidate.get("activity_group")) == activity_group
            ]
            if not candidates:
                return None, "CONFLICT", method
        mapping_row, status = _unique_mapping(candidates)
        return mapping_row, status, method
    return None, "UNMAPPED", ""


def _unique_mapping(candidates: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, str]:
    if not candidates:
        return None, "UNMAPPED"
    if len(candidates) != 1:
        return None, "AMBIGUOUS"
    mapping_row = candidates[0]
    if any(_is_blank(mapping_row.get(column)) for column in ("account_number", "activity_group")):
        return None, "INCOMPLETE"
    return mapping_row, "MAPPED"


def _set_mapping_result(result: pd.DataFrame, index: Any, status: str, method: str) -> None:
    messages = {
        "MAPPED": "",
        "UNMAPPED": "No matching account mapping. Update the mapping workbook or correct the invoice details.",
        "AMBIGUOUS": "Multiple mapping rows match. Resolve the account or duplicate mapping rows.",
        "CONFLICT": "The account or alias conflicts with the selected energy type.",
        "INCOMPLETE": "The mapping row needs an account number and activity group.",
    }
    result.at[index, "mapping_status"] = status
    result.at[index, "mapping_method"] = method
    result.at[index, "mapping_message"] = messages[status]


def _lookup_by_account_number(table: pd.DataFrame) -> dict[str, list[dict[str, Any]]]:
    return _lookup_by_column(table, "account_number")


def _canonicalize_mapping_columns(table: pd.DataFrame) -> pd.DataFrame:
    result = table.copy()
    normalized_columns = {
        _normalize_column_name(column): column
        for column in result.columns
    }
    for canonical_column, aliases in MAPPING_COLUMN_ALIASES.items():
        source_columns = [
            normalized_columns[_normalize_column_name(alias)]
            for alias in aliases
            if _normalize_column_name(alias) in normalized_columns
        ]
        if not source_columns:
            continue
        if canonical_column not in result.columns:
            result[canonical_column] = result[source_columns[0]]
            continue
        for source_column in source_columns:
            if source_column == canonical_column:
                continue
            blank_mask = result[canonical_column].map(_is_blank)
            result.loc[blank_mask, canonical_column] = result.loc[blank_mask, source_column]
    return result


def _normalize_column_name(column: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(column).strip().lower()).strip()


def _lookup_by_column(table: pd.DataFrame, column: str) -> dict[str, list[dict[str, Any]]]:
    lookup: dict[str, list[dict[str, Any]]] = {}
    for _, row in table.iterrows():
        record = row.drop(labels=["_python_lookup_key"], errors="ignore").to_dict()
        key = build_lookup_key(record, (column,))
        if key:
            lookup.setdefault(key, []).append(record)
    return lookup


def _lookup_by_alias(table: pd.DataFrame, alias_column: str) -> dict[str, list[dict[str, Any]]]:
    if alias_column not in table.columns:
        return {}

    lookup: dict[str, list[dict[str, Any]]] = {}
    for _, row in table.iterrows():
        record = row.drop(labels=["_python_lookup_key"], errors="ignore").to_dict()
        keys = {normalize_lookup_value(alias) for alias in _split_aliases(record.get(alias_column))}
        for key in keys:
            if key:
                lookup.setdefault(key, []).append(record)
    return lookup


def _split_aliases(value: Any) -> list[str]:
    if _is_blank(value):
        return []
    return [
        part.strip()
        for part in re.split(r"[;,\n\r|]+", str(value))
        if part.strip()
    ]


def _with_empty_mapping_columns(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    for column in ACCOUNT_MAPPING_COLUMNS:
        if column not in result.columns:
            result[column] = pd.Series([""] * len(result), index=result.index, dtype=object)
        else:
            result[column] = result[column].astype(object)
    return result


def _require_mapping_columns(table: pd.DataFrame) -> None:
    missing_columns = [
        column
        for column in ["account_number", *ACCOUNT_MAPPING_COLUMNS]
        if column not in table.columns
    ]
    if missing_columns:
        raise KeyError(f"Missing account mapping columns: {missing_columns}")


def _order_mapping_columns_after_account_number(df: pd.DataFrame) -> pd.DataFrame:
    columns = [
        column
        for column in df.columns
        if column not in ACCOUNT_MAPPING_COLUMNS and column != "account_number_confidence"
    ]
    insert_at = columns.index("account_number") + 1 if "account_number" in columns else len(columns)
    account_confidence_columns = ["account_number_confidence"] if "account_number_confidence" in df.columns else []
    ordered_columns = [
        *columns[:insert_at],
        *account_confidence_columns,
        *columns[insert_at:],
        *ACCOUNT_MAPPING_COLUMNS,
    ]
    return df.loc[:, ordered_columns]


def _is_blank(value: Any) -> bool:
    return value is None or pd.isna(value) or str(value).strip() == ""
