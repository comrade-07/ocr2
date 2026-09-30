import pandas as pd

from src.transform.quantity_fields import clean_quantity_columns, clean_quantity_value


def test_clean_quantity_value_removes_trailing_ocr_text_before_decimal_normalization():
    assert clean_quantity_value("1.234,56 kWh", ",") == "1234.56"
    assert clean_quantity_value("1,234.56 total consumption", ".") == "1234.56"
    assert clean_quantity_value("123.45 kWh estimated", ".") == "123.45"
    assert clean_quantity_value("1 234,56 kWh", ",") == "1234.56"


def test_clean_quantity_value_tolerates_ocr_spaces_around_thousands_separator():
    assert clean_quantity_value("71,999", ".") == "71999"
    assert clean_quantity_value("31, 799", ".") == "31799"
    assert clean_quantity_value("31 ,799", ".") == "31799"
    assert clean_quantity_value("31 , 799", ".") == "31799"


def test_clean_quantity_value_extracts_number_without_requiring_it_to_start_text():
    assert clean_quantity_value("Consumption 987.65 kWh", ".") == "987.65"
    assert clean_quantity_value("-12.5 adjustment", ".") == "12.5"


def test_clean_quantity_value_treats_dash_characters_as_ocr_noise():
    assert clean_quantity_value("1-234,56 kWh", ",") == "1234.56"
    assert clean_quantity_value("Consumption - 987.65 kWh", ".") == "987.65"
    assert clean_quantity_value("123.45-kWh", ".") == "123.45"
    assert clean_quantity_value("\u2013123.45 kWh", ".") == "123.45"


def test_clean_quantity_value_preserves_blank_and_non_numeric_values():
    assert clean_quantity_value("", ".") == ""
    assert clean_quantity_value(None, ".") is None
    assert clean_quantity_value("not extracted", ".") == "not extracted"


def test_clean_quantity_columns_cleans_quantity_1_to_6_only_when_present():
    source_df = pd.DataFrame([{
        "decimal_separator": ",",
        "quantity_1": "1.234,56 kWh",
        "quantity_2": "987,65 consumption",
        "quantity_6": "0 kWh",
        "other_quantity": "123 kWh",
    }])

    result = clean_quantity_columns(source_df)

    assert result.loc[0, "quantity_1"] == "1234.56"
    assert result.loc[0, "quantity_2"] == "987.65"
    assert result.loc[0, "quantity_6"] == "0"
    assert result.loc[0, "other_quantity"] == "123 kWh"
