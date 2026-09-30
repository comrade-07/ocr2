from __future__ import annotations

import pandas as pd

from src.normalize.date_range_checker import normalize_date_range
from src.normalize.date_normalizer import DATE_FIELD_NAMES, normalize_date

START_END_DATE_PAIRS = {
    "consumption_start_date_1": "consumption_end_date_1",
    "consumption_start_date_2": "consumption_end_date_2",
    "service_start_date": "service_end_date",
}


def add_normalized_date_columns(
    df: pd.DataFrame,
    date_fields: list[str] | None = None,
    suffix: str = "_normalized",
) -> pd.DataFrame:
    result = df.copy()
    fields = date_fields or DATE_FIELD_NAMES

    for field in fields:
        if field not in result.columns:
            continue
        normalized_field = f"{field}{suffix}"
        if normalized_field in result.columns:
            result = _move_column_after(result, normalized_field, field)
            continue

        end_field = START_END_DATE_PAIRS.get(field)
        if end_field in result.columns:
            normalized_end_field = f"{end_field}{suffix}"
            normalized_range = result.apply(
                lambda row: normalize_date_range(row[field], row[end_field]),
                axis=1,
                result_type="expand",
            )
            result[normalized_field] = normalized_range[0]
            result[normalized_end_field] = normalized_range[1]
            result = _move_column_after(result, normalized_end_field, end_field)
        else:
            result[normalized_field] = result[field].map(normalize_date)
        result = _move_column_after(result, normalized_field, field)

    return result


def _move_column_after(df: pd.DataFrame, column: str, after_column: str) -> pd.DataFrame:
    columns = [existing for existing in df.columns if existing != column]
    insert_at = columns.index(after_column) + 1
    columns.insert(insert_at, column)
    return df.loc[:, columns]
