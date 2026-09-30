from __future__ import annotations

import pandas as pd

from src.normalize.text_normalizer import clean_energy_unit, clean_proper_text, clean_upper_text


TEXT_FIELD_CLEANERS = {
    "legal_entity": clean_proper_text,
    "unit_name": clean_proper_text,
    "supplier": clean_upper_text,
    "quantity_unit_1": clean_energy_unit,
    "quantity_unit_2": clean_energy_unit,
}


def clean_text_columns(
    df: pd.DataFrame,
    field_cleaners: dict | None = None,
    skip_field_masks: dict[str, pd.Series] | None = None,
) -> pd.DataFrame:
    result = df.copy()
    cleaners = field_cleaners or TEXT_FIELD_CLEANERS
    skip_field_masks = skip_field_masks or {}

    for field, cleaner in cleaners.items():
        if field not in result.columns:
            continue
        cleaned = result[field].map(cleaner)
        skip_mask = skip_field_masks.get(field)
        if skip_mask is not None:
            skip_mask = skip_mask.reindex(result.index, fill_value=False)
            result[field] = result[field].where(skip_mask, cleaned)
        else:
            result[field] = cleaned

    return result
