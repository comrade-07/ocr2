import pandas as pd

from src.normalize.date_normalizer import REVIEW_DATE, normalize_date
from src.transform.date_fields import add_normalized_date_columns


def test_normalize_date_handles_common_non_ambiguous_formats():
    assert normalize_date("25 Jul 2025") == "2025-07-25"
    assert normalize_date("2025-07-25") == "2025-07-25"
    assert normalize_date("2025/07/25") == "2025-07-25"
    assert normalize_date("19/06/2025") == "2025-06-19"
    assert normalize_date("1 August 25") == "2025-08-01"
    assert normalize_date("May-16-2025") == "2025-05-16"
    assert normalize_date("04. 08. 2025") == "2025-04-08"
    assert normalize_date("03. 09. 2025") == "2025-03-09"


def test_normalize_date_handles_minguo_dates():
    assert normalize_date("114/07/25") == "2025-07-25"


def test_normalize_date_handles_spanish_dates_with_filler_words():
    assert normalize_date("06 de julio de 2025") == "2025-07-06"
    assert normalize_date("15 de julio de 2025") == "2025-07-15"
    assert normalize_date("13 de agosto de 2025") == "2025-08-13"
    assert normalize_date("28 de agosto de 2025") == "2025-08-28"
    assert normalize_date("11 de septiembre de 2025") == "2025-09-11"
    assert normalize_date("25 de febrero de 2025") == "2025-02-25"
    assert normalize_date("15 de marzo de 2025") == "2025-03-15"
    assert normalize_date("18 de abril de 2025") == "2025-04-18"
    assert normalize_date("19 de mayo de 2025") == "2025-05-19"


def test_normalize_date_defaults_missing_day_to_first_of_month():
    assert normalize_date("Okt-2025") == "2025-10-01"
    assert normalize_date("Sep. 2025") == "2025-09-01"


def test_normalize_date_outputs_iso_format_for_ambiguous_dates():
    assert normalize_date("09/12/2025") == "2025-09-12"
    assert normalize_date("04-05-25") == "2025-04-05"


def test_normalize_date_adds_day_for_2359_time_only():
    assert normalize_date("2025-07-25 23:59:00") == "2025-07-26"
    assert normalize_date("2025-07-25 23:58:59") == "2025-07-25"


def test_normalize_date_preserves_blank_and_non_date_values():
    assert normalize_date("") == ""
    assert normalize_date(None) is None
    assert normalize_date("not a date") == "not a date"


def test_normalize_date_returns_review_date_for_invalid_date_like_values():
    assert normalize_date("2025-02-30") == REVIEW_DATE
    assert normalize_date("31/31/2025") == REVIEW_DATE


def test_add_normalized_date_columns_only_targets_business_dates():
    df = pd.DataFrame([{
        "invoice_date": "25 Jul 2025",
        "consumption_start_date_1": "01.07.25",
        "consumption_end_date_1": "01.08.25",
        "consumption_start_date_2": "",
        "consumption_end_date_2": "",
        "createdDateTime": "2026-06-14T15:07:06Z",
        "lastUpdatedDateTime": "2026-06-14T15:07:12Z",
    }])

    result = add_normalized_date_columns(df)

    assert result.loc[0, "invoice_date"] == "25 Jul 2025"
    assert result.loc[0, "invoice_date_normalized"] == "2025-07-25"
    assert result.loc[0, "consumption_start_date_1"] == "01.07.25"
    assert result.loc[0, "consumption_start_date_1_normalized"] == "2025-07-01"
    assert result.loc[0, "consumption_end_date_1"] == "01.08.25"
    assert result.loc[0, "consumption_end_date_1_normalized"] == "2025-08-01"
    assert result.loc[0, "consumption_start_date_2"] == ""
    assert result.loc[0, "consumption_start_date_2_normalized"] == ""
    assert result.loc[0, "consumption_end_date_2"] == ""
    assert result.loc[0, "consumption_end_date_2_normalized"] == ""
    assert "createdDateTime_normalized" not in result.columns
    assert "lastUpdatedDateTime_normalized" not in result.columns


def test_add_normalized_date_columns_uses_end_date_to_resolve_ambiguous_start_date():
    df = pd.DataFrame([{
        "consumption_start_date_1": "1/6/2025",
        "consumption_end_date_1": "6/30/2025",
        "consumption_start_date_2": "",
        "consumption_end_date_2": "",
    }])

    result = add_normalized_date_columns(df)

    assert result.loc[0, "consumption_start_date_1_normalized"] == "2025-06-01"
    assert result.loc[0, "consumption_end_date_1_normalized"] == "2025-06-30"


def test_add_normalized_date_columns_uses_plausible_range_when_both_dates_are_ambiguous():
    df = pd.DataFrame([{
        "consumption_start_date_1": "01.07.25",
        "consumption_end_date_1": "01.08.25",
        "consumption_start_date_2": "",
        "consumption_end_date_2": "",
    }])

    result = add_normalized_date_columns(df)

    assert result.loc[0, "consumption_start_date_1_normalized"] == "2025-07-01"
    assert result.loc[0, "consumption_end_date_1_normalized"] == "2025-08-01"


def test_add_normalized_date_columns_uses_start_date_to_resolve_ambiguous_end_date():
    df = pd.DataFrame([{
        "consumption_start_date_1": "2025-07-01",
        "consumption_end_date_1": "01.08.25",
        "consumption_start_date_2": "",
        "consumption_end_date_2": "",
    }])

    result = add_normalized_date_columns(df)

    assert result.loc[0, "consumption_start_date_1_normalized"] == "2025-07-01"
    assert result.loc[0, "consumption_end_date_1_normalized"] == "2025-08-01"
