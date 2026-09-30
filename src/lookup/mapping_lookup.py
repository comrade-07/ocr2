from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from src.core.config_loader import load_yaml


LOOKUP_KEY_SEPARATOR = "|"


@dataclass(frozen=True)
class LookupConfig:
    name: str
    path: Path
    sheet_name: str
    ocr_key_fields: tuple[str, ...]
    workbook_key_columns: tuple[str, ...]
    delimiter: str = "|"
    date_key_fields: tuple[str, ...] = ()


def _excel_serial_date(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    if isinstance(value, pd.Timestamp):
        value = value.to_pydatetime()
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return str((value - date(1899, 12, 30)).days)

    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return normalize_lookup_value(value)
    return str((parsed.date() - date(1899, 12, 30)).days)


def normalize_lookup_value(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip().lower()
    return " ".join(text.split())


def build_lookup_key(
    record: dict[str, Any],
    fields: list[str] | tuple[str, ...],
    delimiter: str = LOOKUP_KEY_SEPARATOR,
    date_key_fields: list[str] | tuple[str, ...] = (),
) -> str:
    date_fields = set(date_key_fields)
    parts = []
    for field in fields:
        value = record.get(field)
        if field in date_fields:
            parts.append(_excel_serial_date(value))
        else:
            parts.append(normalize_lookup_value(value))
    return delimiter.join(parts)


def load_lookup_config(
    name: str,
    config_dir: str | Path = "config",
    config_file: str = "mapping_files.yaml",
) -> LookupConfig:
    config_dir = Path(config_dir)
    config_path = config_dir / config_file
    if not config_path.exists() and config_file == "mapping_files.yaml":
        config_path = config_dir / "mapping_files.example.yaml"

    config = load_yaml(config_path)
    mapping_files = config.get("mapping_files", {})
    if name not in mapping_files:
        raise KeyError(f"Unknown mapping file config: {name}")

    item = mapping_files[name]
    workbook_path = Path(item["path"])
    if not workbook_path.is_absolute():
        workbook_path = (config_dir.parent / workbook_path).resolve()

    return LookupConfig(
        name=name,
        path=workbook_path,
        sheet_name=item.get("sheet_name", name),
        ocr_key_fields=tuple(item.get("ocr_key_fields", item["workbook_key_columns"])),
        workbook_key_columns=tuple(item["workbook_key_columns"]),
        delimiter=item.get("delimiter", LOOKUP_KEY_SEPARATOR),
        date_key_fields=tuple(item.get("date_key_fields", ())),
    )


def load_lookup_table(config: LookupConfig, active_only: bool = True) -> pd.DataFrame:
    if not config.path.exists():
        raise FileNotFoundError(f"Mapping workbook not found: {config.path}")

    table = pd.read_excel(
        config.path,
        sheet_name=config.sheet_name,
        dtype=object,
        engine="openpyxl",
    )
    table = table.dropna(how="all").copy()
    table = table.loc[:, ~table.columns.astype(str).str.startswith("Unnamed:")]

    if active_only and "active" in table.columns:
        active = table["active"].map(normalize_lookup_value)
        table = table[active.ne("no")].copy()

    missing_columns = [column for column in config.workbook_key_columns if column not in table.columns]
    if missing_columns:
        raise KeyError(f"Missing lookup columns in {config.path}: {missing_columns}")

    table["_python_lookup_key"] = table.apply(
        lambda row: build_lookup_key(
            row.to_dict(),
            config.workbook_key_columns,
            delimiter=config.delimiter,
            date_key_fields=config.date_key_fields,
        ),
        axis=1,
    )
    table = table[table["_python_lookup_key"].str.strip().ne("")]
    return table


def lookup_row(
    ocr_record: dict[str, Any],
    lookup_name: str,
    config_dir: str | Path = "config",
    config_file: str = "mapping_files.yaml",
) -> dict[str, Any] | None:
    config = load_lookup_config(lookup_name, config_dir=config_dir, config_file=config_file)
    table = load_lookup_table(config)
    key = build_lookup_key(
        ocr_record,
        config.ocr_key_fields,
        delimiter=config.delimiter,
        date_key_fields=config.date_key_fields,
    )
    matches = table[table["_python_lookup_key"].eq(key)]
    if matches.empty:
        return None
    result = matches.iloc[0].drop(labels=["_python_lookup_key"], errors="ignore")
    return result.where(pd.notna(result), None).to_dict()
