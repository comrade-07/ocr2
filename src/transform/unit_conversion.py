from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from src.normalize.text_normalizer import clean_energy_unit


@dataclass(frozen=True)
class UnitConversionRule:
    from_unit: str
    to_unit: str
    factor: float


UNIT_CONVERSION_RULES = [
    UnitConversionRule(from_unit="kWh", to_unit="kWh", factor=1),
    UnitConversionRule(from_unit="MWh", to_unit="kWh", factor=1000),
    # Business conversion factors supplied for purchased steam and cooling.
    UnitConversionRule(from_unit="ton", to_unit="kWh", factor=720),
    UnitConversionRule(from_unit="RTH", to_unit="kWh", factor=0.62),
]


def kwh_conversion_factor(unit: Any) -> float | None:
    normalized = _normalize_unit(unit)
    return next(
        (rule.factor for rule in UNIT_CONVERSION_RULES if _normalize_unit(rule.from_unit) == normalized),
        None,
    )


def apply_unit_conversions(
    df: pd.DataFrame,
    amount_column: str = "Amount of energy consumed",
    unit_column: str = "Energy Unit",
    original_unit_column: str = "Original Energy Unit",
    conversion_rules: list[UnitConversionRule] | None = None,
    additional_amount_columns: tuple[str, ...] = (),
) -> pd.DataFrame:
    result = df.copy()
    if amount_column not in result.columns or unit_column not in result.columns:
        return result

    if original_unit_column not in result.columns:
        result[original_unit_column] = result[unit_column]
    amount_columns = [column for column in (amount_column, *additional_amount_columns) if column in result.columns]
    for column in amount_columns:
        result[column] = result[column].astype(object)

    rules_by_unit = {
        _normalize_unit(rule.from_unit): rule
        for rule in (conversion_rules or UNIT_CONVERSION_RULES)
    }

    for index, row in result.iterrows():
        rule = rules_by_unit.get(_normalize_unit(row.get(unit_column)))
        if rule is None:
            if conversion_rules is None:
                raise ValueError(f"Unsupported energy unit: {row.get(unit_column)!r}. Correct the source unit before publishing Gold.")
            continue

        amount = _coerce_number(row.get(amount_column))
        if amount is None:
            continue

        for column in amount_columns:
            value = _coerce_number(row.get(column))
            if value is not None:
                result.at[index, column] = _clean_number(value * rule.factor)
        result.at[index, unit_column] = rule.to_unit

    return _move_column_after(result, original_unit_column, "Total amount of energy consumed")


def _normalize_unit(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(clean_energy_unit(value) or value).strip().casefold()


def _coerce_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool) or pd.isna(value):
        return None
    if isinstance(value, int | float):
        return float(value)

    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _clean_number(value: float) -> float | int:
    if float(value).is_integer():
        return int(value)
    return value


def _move_column_after(df: pd.DataFrame, column: str, after_column: str) -> pd.DataFrame:
    if column not in df.columns or after_column not in df.columns:
        return df
    columns = [item for item in df.columns if item != column]
    insert_at = columns.index(after_column) + 1
    columns[insert_at:insert_at] = [column]
    return df.loc[:, columns]
