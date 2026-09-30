import pandas as pd

from src.dashboard.year_over_year import (
    build_year_over_year,
    high_variance_year_over_year_df,
    percent_difference,
    year_over_year_class,
    year_over_year_export_df,
)


FACILITY_COLUMNS = ["division", "legal_entity_name", "unit"]
FACILITY_ALIASES = {
    "division": "Division",
    "legal_entity_name": "Legal Entity Name",
    "unit": "Unit",
}


def test_percent_difference_handles_zero_baseline():
    assert percent_difference(0, 0) == 0
    assert percent_difference(10, 0) == float("inf")
    assert percent_difference(None, 10) is None


def test_percent_difference_preserves_decrease_direction():
    assert percent_difference(75, 100) == -0.25


def test_year_over_year_class_uses_default_thresholds():
    assert year_over_year_class(0.10) == "yoy-good"
    assert year_over_year_class(0.30) == "yoy-watch"
    assert year_over_year_class(0.50) == "yoy-warning"
    assert year_over_year_class(0.51) == "yoy-alert"
    assert year_over_year_class(None) == "yoy-missing"


def test_build_year_over_year_aggregates_current_and_previous_by_facility_month():
    facilities = pd.DataFrame([
        {"division": "Division A", "legal_entity_name": "Entity A", "unit": "Unit A"},
    ])
    current = pd.DataFrame([
        {
            "Division": "Division A",
            "Legal Entity Name": "Entity A",
            "Unit": "Unit A",
            "Consumption start date": "2025-06-01",
            "Amount of energy consumed": 60,
        },
        {
            "Division": "Division A",
            "Legal Entity Name": "Entity A",
            "Unit": "Unit A",
            "Consumption start date": "2025-06-01",
            "Amount of energy consumed": 40,
        },
    ])
    previous = pd.DataFrame([
        {
            "Division": "Division A",
            "Legal Entity Name": "Entity A",
            "Unit": "Unit A",
            "Consumption start date": "2025-06-01",
            "Amount of energy consumed": 80,
        },
    ])

    result = build_year_over_year(
        facilities,
        current,
        previous,
        [pd.Timestamp(2025, 6, 1)],
        FACILITY_COLUMNS,
        FACILITY_ALIASES,
    )

    cell = result.loc[0, "Jun 2025"]
    assert cell.current_value == 100
    assert cell.previous_value == 80
    assert cell.percent_difference == 0.25
    assert cell.css_class == "yoy-watch"

    export = year_over_year_export_df(result, [pd.Timestamp(2025, 6, 1)], FACILITY_COLUMNS)
    assert export.loc[0, "Jun 2025 Current"] == 100
    assert export.loc[0, "Jun 2025 Previous"] == 80
    assert export.loc[0, "Jun 2025 % Difference"] == 0.25


def test_build_year_over_year_matches_facility_names_with_display_format_differences():
    facilities = pd.DataFrame([
        {"division": "Stolt_SeaFarm", "legal_entity_name": "Stolt_Sea_Farm_S.A.", "unit": "Office A"},
    ])
    current = pd.DataFrame([
        {
            "Division": "Stolt SeaFarm",
            "Legal Entity Name": "Stolt Sea Farm S.A.",
            "Unit": "Office A",
            "Consumption start date": "2025-06-01",
            "Amount of energy consumed": 60,
        },
        {
            "Division": "Stolt_SeaFarm",
            "Legal Entity Name": "Stolt_Sea_Farm_S.A.",
            "Unit": "Office A",
            "Consumption start date": "2025-06-01",
            "Amount of energy consumed": 40,
        },
    ])
    previous = pd.DataFrame([
        {
            "Division": "Stolt_SeaFarm",
            "Legal Entity Name": "Stolt_Sea_Farm_S.A.",
            "Unit": "Office A",
            "Consumption start date": "2025-06-01",
            "Amount of energy consumed": 80,
        },
    ])

    result = build_year_over_year(
        facilities,
        current,
        previous,
        [pd.Timestamp(2025, 6, 1)],
        FACILITY_COLUMNS,
        FACILITY_ALIASES,
    )

    cell = result.loc[0, "Jun 2025"]
    assert cell.current_value == 100
    assert cell.previous_value == 80


def test_build_year_over_year_can_compare_to_prior_year_months():
    facilities = pd.DataFrame([
        {"division": "Division A", "legal_entity_name": "Entity A", "unit": "Unit A"},
    ])
    current = pd.DataFrame([
        {
            "Division": "Division A",
            "Legal Entity Name": "Entity A",
            "Unit": "Unit A",
            "Consumption start date": "2025-12-01",
            "Amount of energy consumed": 120,
        },
    ])
    previous = pd.DataFrame([
        {
            "Division": "Division A",
            "Legal Entity Name": "Entity A",
            "Unit": "Unit A",
            "Consumption start date": "2024-12-01",
            "Amount of energy consumed": 100,
        },
    ])

    result = build_year_over_year(
        facilities,
        current,
        previous,
        [pd.Timestamp(2025, 12, 1)],
        FACILITY_COLUMNS,
        FACILITY_ALIASES,
        previous_months=[pd.Timestamp(2024, 12, 1)],
    )

    cell = result.loc[0, "Dec 2025"]
    assert cell.current_value == 120
    assert cell.previous_value == 100
    assert cell.percent_difference == 0.20


def test_build_year_over_year_requires_prior_year_previous_data_dates():
    facilities = pd.DataFrame([
        {"division": "Division A", "legal_entity_name": "Entity A", "unit": "Unit A"},
    ])
    current = pd.DataFrame([
        {
            "Division": "Division A",
            "Legal Entity Name": "Entity A",
            "Unit": "Unit A",
            "Consumption start date": "2025-12-01",
            "Amount of energy consumed": 120,
        },
    ])
    previous = pd.DataFrame([
        {
            "Division": "Division A",
            "Legal Entity Name": "Entity A",
            "Unit": "Unit A",
            "Consumption start date": "2025-12-01",
            "Amount of energy consumed": 100,
        },
    ])

    result = build_year_over_year(
        facilities,
        current,
        previous,
        [pd.Timestamp(2025, 12, 1)],
        FACILITY_COLUMNS,
        FACILITY_ALIASES,
        previous_months=[pd.Timestamp(2024, 12, 1)],
    )

    cell = result.loc[0, "Dec 2025"]
    assert cell.current_value == 120
    assert cell.previous_value is None
    assert cell.percent_difference is None
    assert cell.status == "No previous data"


def test_high_variance_year_over_year_sorts_by_absolute_yoy_and_lists_sources():
    facilities = pd.DataFrame([
        {"division": "Division A", "legal_entity_name": "Entity A", "unit": "Unit Down"},
        {"division": "Division A", "legal_entity_name": "Entity A", "unit": "Unit Up"},
        {"division": "Division B", "legal_entity_name": "Entity B", "unit": "Unit Low"},
    ])
    current = pd.DataFrame([
        {
            "Division": "Division A",
            "Legal Entity Name": "Entity A",
            "Unit": "Unit Down",
            "Consumption start date": "2025-06-01",
            "Amount of energy consumed": 40,
            "source_files": "current-down-a.json; current-down-b.json",
            "sharepoint_link_1": "https://example.test/current-down-a.pdf",
            "sharepoint_link_2": "https://example.test/current-down-b.pdf",
        },
        {
            "Division": "Division A",
            "Legal Entity Name": "Entity A",
            "Unit": "Unit Up",
            "Consumption start date": "2025-06-01",
            "Amount of energy consumed": 160,
            "source_files": "current-up.json",
            "sharepoint_link_1": "https://example.test/current-up.pdf",
        },
        {
            "Division": "Division B",
            "Legal Entity Name": "Entity B",
            "Unit": "Unit Low",
            "Consumption start date": "2025-06-01",
            "Amount of energy consumed": 105,
            "source_files": "low.json",
        },
    ])
    previous = pd.DataFrame([
        {
            "Division": "Division A",
            "Legal Entity Name": "Entity A",
            "Unit": "Unit Down",
            "Consumption start date": "2024-06-01",
            "Amount of energy consumed": 100,
            "source_files": "previous-down.json",
            "sharepoint_link_1": "https://example.test/previous-down.pdf",
        },
        {
            "Division": "Division A",
            "Legal Entity Name": "Entity A",
            "Unit": "Unit Up",
            "Consumption start date": "2024-06-01",
            "Amount of energy consumed": 100,
            "source_files": "previous-up.json",
        },
        {
            "Division": "Division B",
            "Legal Entity Name": "Entity B",
            "Unit": "Unit Low",
            "Consumption start date": "2024-06-01",
            "Amount of energy consumed": 100,
            "source_files": "previous-low.json",
        },
    ])
    months = [pd.Timestamp(2025, 6, 1)]
    previous_months = [pd.Timestamp(2024, 6, 1)]

    yoy = build_year_over_year(
        facilities,
        current,
        previous,
        months,
        FACILITY_COLUMNS,
        FACILITY_ALIASES,
        previous_months=previous_months,
    )
    result = high_variance_year_over_year_df(
        yoy,
        current,
        previous,
        months,
        FACILITY_COLUMNS,
        FACILITY_ALIASES,
        previous_months=previous_months,
        minimum_abs_difference=0.10,
    )

    assert list(result["Unit"]) == ["Unit Down", "Unit Up"]
    assert list(result["YOY%"]) == ["-60%", "+60%"]
    assert result.loc[0, "Current Year files"] == "\n".join([
        "current-down-a.json",
        "current-down-b.json",
    ])
    assert result.loc[0, "Previous Year files"] == "\n".join([
        "previous-down.json",
    ])
    assert result.loc[0, "Current Year link 1"] == "https://example.test/current-down-a.pdf"
    assert result.loc[0, "Current Year link 2"] == "https://example.test/current-down-b.pdf"
    assert "Previous Year link 1" not in result.columns
    assert result.loc[0, "Previous Year amount"] == 100
    assert result.loc[0, "Current Year amount"] == 40


def test_energy_kpi_comparisons_keep_values_and_evidence_separate():
    from src.dashboard.year_over_year import normalize_reporting_data

    keys = [*FACILITY_COLUMNS, "kpi_component"]
    aliases = {**FACILITY_ALIASES, "kpi_component": "KPI Component"}
    base = {"Division": "D", "Legal Entity Name": "E", "Unit": "U"}
    current = pd.DataFrame([
        {**base, "KPI Component": "Purchased electricity", "Energy Unit": "MWh",
         "Amount of energy consumed": 2, "Consumption start date": "2026-01-01",
         "source_files": "electric.pdf", "sharepoint_link": "https://example.test/electric"},
        {**base, "KPI Component": "Purchased steam", "Energy Unit": "ton",
         "Amount of energy consumed": 1, "Consumption start date": "2026-01-01",
         "source_files": "steam.pdf", "sharepoint_link": "https://example.test/steam"},
        {**base, "KPI Component": "Purchased heat", "Energy Unit": "kWh",
         "Amount of energy consumed": 10, "Consumption start date": "2026-01-01"},
    ], index=[4, 7, 9])
    previous = current.iloc[:2].copy()
    previous["Consumption start date"] = "2025-01-01"
    previous["Amount of energy consumed"] = [1, 2]
    current = normalize_reporting_data(current)
    previous = normalize_reporting_data(previous)
    facilities = current[list(aliases.values())].rename(columns={v: k for k, v in aliases.items()})
    months = [pd.Timestamp("2026-01-01")]
    prior_months = [pd.Timestamp("2025-01-01")]
    result = build_year_over_year(facilities, current, previous, months, keys, aliases, prior_months)
    assert [cell.current_value for cell in result["Jan 2026"]] == [2000, 720, 10]
    assert [cell.previous_value for cell in result["Jan 2026"]] == [1000, 1440, None]
    variance = high_variance_year_over_year_df(result, current, previous, months, keys, aliases, prior_months)
    assert variance["KPI Component"].tolist() == ["Purchased electricity", "Purchased steam"]
    assert variance["Current Year files"].tolist() == ["electric.pdf", "steam.pdf"]
    assert variance["Current Year link 1"].tolist() == ["https://example.test/electric", "https://example.test/steam"]
    assert "KPI Component" in year_over_year_export_df(result, months, keys)
    pd.testing.assert_frame_equal(current, normalize_reporting_data(current))


def test_reporting_rejects_implicit_historical_units_and_classification():
    import pytest
    from src.dashboard.year_over_year import normalize_reporting_data

    row = {"Division": "D", "Legal Entity Name": "E", "Unit": "U",
           "KPI Component": "Purchased cool", "Energy Unit": "RTH",
           "Amount of energy consumed": 10, "Consumption start date": "2025-01-01"}
    assert normalize_reporting_data(pd.DataFrame([row])).iloc[0]["Amount of energy consumed"] == 6.2
    for column, invalid in [("Energy Unit", "mmBTU"), ("KPI Component", ""),
                            ("Amount of energy consumed", float("inf"))]:
        valid, issues = normalize_reporting_data(pd.DataFrame([row, {**row, column: invalid}]), return_issues=True)
        assert len(valid) == 1
        assert len(issues) == 1
        assert issues.mapping_message.str.contains("Missing/invalid").all()
    assert normalize_reporting_data(pd.DataFrame([row]).drop(columns="KPI Component")).empty
    solar = {**row, "Energy KPI": "Renewable energy production"}
    assert normalize_reporting_data(pd.DataFrame([row, solar]))["Amount of energy consumed"].sum() == 6.2
