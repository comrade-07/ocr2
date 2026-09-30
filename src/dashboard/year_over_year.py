from __future__ import annotations

from dataclasses import dataclass
from math import isinf
import re
from typing import Iterable

import pandas as pd

from src.pipeline.run_gold_pipeline import SOLAR_ENERGY_KPIS
from src.transform.account_mapping import SCOPE2_ACTIVITY_GROUPS
from src.transform.unit_conversion import kwh_conversion_factor


PREVIOUS_DATA_FILENAME = "scope2_previous_data.xlsx"
PREVIOUS_DATA_EXAMPLE_FILENAME = "scope2_previous_data.example.xlsx"
YOY_VALUE_COLUMN = "Amount of energy consumed"
YOY_DATE_COLUMN = "Consumption start date"
YOY_SOURCE_COLUMN = "source_files"
YOY_MATCH_COLUMNS = [
    "Division",
    "Legal Entity Name",
    "Unit",
    "KPI Component",
    YOY_DATE_COLUMN,
]

# Edit these thresholds to change the dashboard color bands.
YOY_DIFFERENCE_THRESHOLDS = (
    (0.10, "yoy-good"),
    (0.30, "yoy-watch"),
    (0.50, "yoy-warning"),
    (float("inf"), "yoy-alert"),
)


@dataclass(frozen=True)
class YearOverYearCell:
    current_value: float | None
    previous_value: float | None
    percent_difference: float | None
    css_class: str
    status: str


def year_over_year_class(percent_difference: float | None) -> str:
    if percent_difference is None:
        return "yoy-missing"

    difference = abs(float(percent_difference))
    for max_difference, css_class in YOY_DIFFERENCE_THRESHOLDS:
        if difference <= max_difference:
            return css_class
    return "yoy-alert"


def percent_difference(current_value: float | None, previous_value: float | None) -> float | None:
    if current_value is None or previous_value is None:
        return None
    if previous_value == 0:
        if current_value == 0:
            return 0.0
        return float("inf")
    return (current_value - previous_value) / abs(previous_value)


def build_year_over_year(
    facility_df: pd.DataFrame,
    current_df: pd.DataFrame,
    previous_df: pd.DataFrame,
    months: Iterable[pd.Timestamp],
    facility_key_columns: list[str],
    gold_facility_aliases: dict[str, str],
    previous_months: Iterable[pd.Timestamp] | None = None,
) -> pd.DataFrame:
    month_list = list(months)
    previous_month_list = list(previous_months) if previous_months is not None else month_list
    month_labels = [month.strftime("%b %Y") for month in month_list]
    base_columns = [*facility_key_columns, *month_labels]

    if facility_df.empty:
        return pd.DataFrame(columns=base_columns)
    if len(previous_month_list) != len(month_list):
        raise ValueError("previous_months must have the same length as months")

    current_values = _monthly_values(current_df, month_list, facility_key_columns, gold_facility_aliases)
    previous_values = _monthly_values(previous_df, previous_month_list, facility_key_columns, gold_facility_aliases)

    records = []
    for _, facility_row in facility_df.iterrows():
        facility_key = tuple(_normalize_value(facility_row.get(column, "")) for column in facility_key_columns)
        record = {column: facility_row.get(column, "") for column in facility_key_columns}
        for month, previous_month in zip(month_list, previous_month_list):
            month_key = month.strftime("%Y-%m")
            previous_month_key = previous_month.strftime("%Y-%m")
            key = (facility_key, month_key)
            current_value = current_values.get(key)
            previous_value = previous_values.get((facility_key, previous_month_key))
            difference = percent_difference(current_value, previous_value)
            record[month.strftime("%b %Y")] = YearOverYearCell(
                current_value=current_value,
                previous_value=previous_value,
                percent_difference=difference,
                css_class=year_over_year_class(difference),
                status=_cell_status(current_value, previous_value),
            )
        records.append(record)

    return pd.DataFrame(records, columns=base_columns)


def year_over_year_export_df(
    year_over_year_df: pd.DataFrame,
    months: Iterable[pd.Timestamp],
    facility_key_columns: list[str],
) -> pd.DataFrame:
    result = year_over_year_df[[*facility_key_columns]].rename(
        columns={
            "division": "Division",
            "legal_entity_name": "Legal Entity Name",
            "unit": "Unit",
            "kpi_component": "KPI Component",
        }
    )
    for month in months:
        label = month.strftime("%b %Y")
        result[f"{label} Current"] = year_over_year_df[label].map(lambda cell: cell.current_value)
        result[f"{label} Previous"] = year_over_year_df[label].map(lambda cell: cell.previous_value)
        result[f"{label} % Difference"] = year_over_year_df[label].map(_export_difference)
    return result


def high_variance_year_over_year_df(
    year_over_year_df: pd.DataFrame,
    current_df: pd.DataFrame,
    previous_df: pd.DataFrame,
    months: Iterable[pd.Timestamp],
    facility_key_columns: list[str],
    gold_facility_aliases: dict[str, str],
    previous_months: Iterable[pd.Timestamp] | None = None,
    minimum_abs_difference: float = 0.10,
) -> pd.DataFrame:
    month_list = list(months)
    previous_month_list = list(previous_months) if previous_months is not None else month_list
    if len(previous_month_list) != len(month_list):
        raise ValueError("previous_months must have the same length as months")

    columns = [
        "Division",
        "Legal Entity",
        "Unit",
        "KPI Component",
        "Month",
        "Previous Year amount",
        "Current Year amount",
        "YOY%",
        "Current Year files",
        "Previous Year files",
    ]
    if year_over_year_df.empty:
        return pd.DataFrame(columns=columns)

    current_sources = _monthly_sources(current_df, month_list, facility_key_columns, gold_facility_aliases)
    previous_sources = _monthly_sources(previous_df, previous_month_list, facility_key_columns, gold_facility_aliases)
    current_links = _monthly_links(current_df, month_list, facility_key_columns, gold_facility_aliases)
    records = []
    for _, row in year_over_year_df.iterrows():
        facility_key = tuple(_normalize_value(row.get(column, "")) for column in facility_key_columns)
        for month, previous_month in zip(month_list, previous_month_list):
            label = month.strftime("%b %Y")
            cell = row.get(label)
            if not isinstance(cell, YearOverYearCell) or cell.percent_difference is None:
                continue
            if pd.isna(cell.percent_difference):
                continue
            variance = abs(float(cell.percent_difference))
            if variance <= minimum_abs_difference:
                continue

            month_key = month.strftime("%Y-%m")
            previous_month_key = previous_month.strftime("%Y-%m")
            row_links = current_links.get((facility_key, month_key), [])
            record = {
                "Division": row.get("division", ""),
                "Legal Entity": row.get("legal_entity_name", ""),
                "Unit": row.get("unit", ""),
                "KPI Component": row.get("kpi_component", ""),
                "Month": label,
                "Previous Year amount": cell.previous_value,
                "Current Year amount": cell.current_value,
                "YOY%": _format_difference(cell),
                "Current Year files": "\n".join(current_sources.get((facility_key, month_key), [])),
                "Previous Year files": "\n".join(previous_sources.get((facility_key, previous_month_key), [])),
                "_variance_sort": variance,
            }
            for link_index, link in enumerate(row_links, start=1):
                record[f"Current Year link {link_index}"] = link
            records.append(
                record
            )

    if not records:
        return pd.DataFrame(columns=columns)

    result = pd.DataFrame(records)
    result = result.sort_values(
        ["_variance_sort", "Division", "Legal Entity", "Unit", "KPI Component", "Month"],
        ascending=[False, True, True, True, True, True],
        kind="mergesort",
    )
    return result.drop(columns=["_variance_sort"]).reset_index(drop=True)


def _monthly_values(
    df: pd.DataFrame,
    months: list[pd.Timestamp],
    facility_key_columns: list[str],
    gold_facility_aliases: dict[str, str],
) -> dict[tuple[tuple[str, str, str], str], float]:
    required_columns = {*gold_facility_aliases.values(), YOY_DATE_COLUMN, YOY_VALUE_COLUMN}
    month_keys = {month.strftime("%Y-%m") for month in months}
    if df.empty or not required_columns.issubset(set(df.columns)):
        return {}

    values: dict[tuple[tuple[str, str, str], str], float] = {}
    parsed_months = pd.to_datetime(df[YOY_DATE_COLUMN], errors="coerce").dt.to_period("M")
    numeric_values = pd.to_numeric(df[YOY_VALUE_COLUMN], errors="coerce")
    for row_index, (_, row) in enumerate(df.iterrows()):
        period = parsed_months.iloc[row_index]
        value = numeric_values.iloc[row_index]
        if pd.isna(period) or pd.isna(value):
            continue
        month_key = str(period)
        if month_key not in month_keys:
            continue

        facility_key = tuple(
            _normalize_value(row.get(gold_facility_aliases[column], ""))
            for column in facility_key_columns
        )
        if not all(facility_key):
            continue

        key = (facility_key, month_key)
        values[key] = values.get(key, 0.0) + float(value)
    return values


def _monthly_sources(
    df: pd.DataFrame,
    months: list[pd.Timestamp],
    facility_key_columns: list[str],
    gold_facility_aliases: dict[str, str],
) -> dict[tuple[tuple[str, ...], str], list[str]]:
    required_columns = {*gold_facility_aliases.values(), YOY_DATE_COLUMN}
    month_keys = {month.strftime("%Y-%m") for month in months}
    if df.empty or not required_columns.issubset(set(df.columns)):
        return {}

    parsed_months = pd.to_datetime(df[YOY_DATE_COLUMN], errors="coerce").dt.to_period("M")
    sources: dict[tuple[tuple[str, ...], str], list[str]] = {}
    for row_index, (_, row) in enumerate(df.iterrows()):
        period = parsed_months.iloc[row_index]
        if pd.isna(period):
            continue
        month_key = str(period)
        if month_key not in month_keys:
            continue

        facility_key = tuple(
            _normalize_value(row.get(gold_facility_aliases[column], ""))
            for column in facility_key_columns
        )
        if not all(facility_key):
            continue

        key = (facility_key, month_key)
        sources[key] = _unique_values([*sources.get(key, []), *_row_sources(row)])
    return sources


def _monthly_links(
    df: pd.DataFrame,
    months: list[pd.Timestamp],
    facility_key_columns: list[str],
    gold_facility_aliases: dict[str, str],
) -> dict[tuple[tuple[str, ...], str], list[str]]:
    required_columns = {*gold_facility_aliases.values(), YOY_DATE_COLUMN}
    month_keys = {month.strftime("%Y-%m") for month in months}
    if df.empty or not required_columns.issubset(set(df.columns)):
        return {}

    parsed_months = pd.to_datetime(df[YOY_DATE_COLUMN], errors="coerce").dt.to_period("M")
    links: dict[tuple[tuple[str, ...], str], list[str]] = {}
    for row_index, (_, row) in enumerate(df.iterrows()):
        period = parsed_months.iloc[row_index]
        if pd.isna(period):
            continue
        month_key = str(period)
        if month_key not in month_keys:
            continue

        facility_key = tuple(
            _normalize_value(row.get(gold_facility_aliases[column], ""))
            for column in facility_key_columns
        )
        if not all(facility_key):
            continue

        key = (facility_key, month_key)
        links[key] = _unique_values([*links.get(key, []), *_row_links(row)])
    return links


def _row_sources(row: pd.Series) -> list[str]:
    source_values = []
    for column in row.index:
        column_text = str(column)
        if column_text == YOY_SOURCE_COLUMN or column_text == "source_file":
            source_values.extend(str(row.get(column) or "").split(";"))
    return _unique_values(source_values)


def _row_links(row: pd.Series) -> list[str]:
    link_values = []
    for column in row.index:
        column_text = str(column)
        if column_text == "sharepoint_link" or re.fullmatch(r"sharepoint_link_\d+", column_text):
            link_values.extend(str(row.get(column) or "").split(";"))
    return _unique_values(link_values)


def _unique_values(values: Iterable[object]) -> list[str]:
    unique_values = []
    seen = set()
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        normalized = text.casefold()
        if normalized in seen:
            continue
        seen.add(normalized)
        unique_values.append(text)
    return unique_values


def _cell_status(current_value: float | None, previous_value: float | None) -> str:
    if current_value is None and previous_value is None:
        return "No data"
    if previous_value is None:
        return "No previous data"
    if current_value is None:
        return "No current data"
    return "Compared"


def _export_difference(cell: YearOverYearCell) -> float | str | None:
    if cell.percent_difference is None:
        return None
    if isinf(cell.percent_difference):
        return "inf"
    return round(cell.percent_difference, 4)


def _format_difference(cell: YearOverYearCell) -> str | None:
    if cell.percent_difference is None:
        return None
    if isinf(cell.percent_difference):
        return ">999%"
    return f"{cell.percent_difference:+.0%}"


def _normalize_value(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip().casefold().replace("_", " ")
    text = re.sub(r"[.'`]", "", text)
    text = re.sub(r"[\W_]+", " ", text, flags=re.UNICODE)
    return " ".join(text.split())


def normalize_reporting_data(df: pd.DataFrame, return_issues: bool = False):
    """Validate reporting identity and normalize historical/current quantities to kWh."""
    if df.empty:
        return (df.copy(), df.iloc[0:0].copy()) if return_issues else df.copy()
    required = {*YOY_MATCH_COLUMNS, YOY_VALUE_COLUMN, "Energy Unit"}
    missing = sorted(required - set(df.columns))
    if missing:
        issues = df.copy()
        issues["mapping_message"] = "Reporting data requires explicit columns: " + ", ".join(missing)
        result = df.iloc[0:0].reindex(columns=list(dict.fromkeys([*df.columns, *sorted(required)])))
        return (result, issues) if return_issues else result
    result = df.copy()
    if "Energy KPI" in result.columns:
        result = result.loc[~result["Energy KPI"].isin(SOLAR_ENERGY_KPIS)].copy()
    components = {f"purchased {group.lower()}": f"Purchased {group.lower()}"
                  for group in SCOPE2_ACTIVITY_GROUPS}
    result["KPI Component"] = result["KPI Component"].astype(str).str.strip().str.casefold().map(components)
    factors = result["Energy Unit"].map(kwh_conversion_factor)
    amounts = pd.to_numeric(result[YOY_VALUE_COLUMN], errors="coerce")
    dates = pd.to_datetime(result[YOY_DATE_COLUMN], errors="coerce")
    invalid = result["KPI Component"].isna() | factors.isna() | amounts.isna() | dates.isna()
    invalid |= ~amounts.map(lambda value: pd.notna(value) and float("-inf") < value < float("inf"))
    for column in ("Division", "Legal Entity Name", "Unit"):
        invalid |= result[column].fillna("").astype(str).str.strip().eq("")
    if "business_mapping_issue" in result.columns:
        invalid |= result["business_mapping_issue"].fillna("").astype(str).str.strip().ne("")
    issues = df.loc[result.index[invalid]].copy()
    issues["mapping_message"] = "Missing/invalid reporting facility, KPI, quantity, date, unit or business mapping"
    result = result.loc[~invalid].copy()
    result[YOY_VALUE_COLUMN] = (amounts * factors).loc[result.index]
    result["Energy Unit"] = "kWh"
    return (result, issues) if return_issues else result
