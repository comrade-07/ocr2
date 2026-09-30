from io import BytesIO

import pandas as pd
import pytest
import yaml
from openpyxl import load_workbook

from src.audit.excel_export import excel_bytes
from src.audit.loader import load_audit_data, prepare_audit_data
from src.audit.models import ReportFilters
from src.audit.page import _detail_frames
from src.audit.pdf_export import pdf_bytes
from src.audit.report import build_report
from src.output.xlsx_writer import write_xlsx
from src.pipeline.run_gold_pipeline import gold_output_filename, run_gold_pipeline
from src.pipeline.run_silver_pipeline import (
    SILVER_AGGREGATED_COLUMNS,
    build_silver_proration_calculation,
    build_silver_proration_split,
    build_silver_prorated,
    run_silver_pipeline,
    silver_output_filename,
)
from src.transform.account_mapping import ACCOUNT_MAPPING_COLUMNS


def _invoice(name, start, end, **overrides):
    return {
        "invoice_id": name,
        "line_id": "1",
        "source_file": name + ".json",
        "division": "Division",
        "legal_entity": "Entity",
        "unit_name": "Unit",
        "supplier_name": "Supplier",
        "account_number": "00123",
        "consumption_start_date_1_normalized": start,
        "consumption_end_date_1_normalized": end,
        "aggregated_quantity_1": 3100,
        "consumption_quantity_unit": "KWH",
        **overrides,
    }


def _frames(records, manual=()):
    frames = {
        name: pd.DataFrame(rows).reindex(columns=SILVER_AGGREGATED_COLUMNS, fill_value="")
        for name, rows in (("aggregated", records), ("manual_mapping", manual))
    }
    for name, split, other in (
        ("aggregated", "proration_split", "manual_mapping"),
        ("manual_mapping", "manual_proration_split", "aggregated"),
    ):
        frames[split] = build_silver_proration_split(
            build_silver_proration_calculation(frames[name], other_invoices=frames[other])
        )
    return frames


def test_other_energy_type_or_unresolved_mapping_cannot_change_billing_dates():
    electricity = _invoice("electricity", "2026-01-20", "2026-02-19", activity_group="Electricity")
    steam = _invoice("steam", "2026-02-19", "2026-03-20", activity_group="Steam")
    for other in (steam, {**steam, "activity_group": "Electricity", "mapping_status": "AMBIGUOUS"}):
        calculation = build_silver_proration_calculation(pd.DataFrame([electricity]), other_invoices=pd.DataFrame([other]))
        assert set(calculation.date_1_effective_end) == {"2026-02-19"}
        assert set(calculation.date_1_resolution) == {"Insufficient history"}


def test_monthly_silver_keeps_energy_types_separate_even_with_same_account():
    frames = _frames([
        _invoice("electricity", "2026-01-01", "2026-01-31", activity_group="Electricity", aggregated_quantity_1=100),
        _invoice("steam", "2026-01-01", "2026-01-31", activity_group="Steam", aggregated_quantity_1=200),
    ])
    monthly = build_silver_prorated(frames["proration_split"]).set_index("activity_group")
    assert monthly.monthly_consumption.to_dict() == {"Electricity": 100, "Steam": 200}
    assert monthly.source_files.to_dict() == {"Electricity": "electricity.json", "Steam": "steam.json"}


@pytest.mark.parametrize(
    "periods,expected_ends,expected_days",
    [
        (
            [("2026-01-20", "2026-02-19"), ("2026-02-20", "2026-03-19")],
            ["2026-02-19", "2026-03-19"], [31, 28],
        ),
        (
            [("2026-01-20", "2026-02-19"), ("2026-02-19", "2026-03-20"),
             ("2026-03-20", "2026-04-19")],
            ["2026-02-18", "2026-03-19", "2026-04-18"], [30, 29, 30],
        ),
        (
            [("2025-12-01", "2026-01-01"), ("2026-01-01", "2026-02-01")],
            ["2025-12-31", "2026-01-31"], [31, 31],
        ),
        (
            [("2025-12-01", "2025-12-31"), ("2026-01-05", "2026-01-31")],
            ["2025-12-31", "2026-01-31"], [31, 27],
        ),
        (
            [("2024-02-01", "2024-03-01"), ("2024-03-01", "2024-04-01")],
            ["2024-02-29", "2024-03-31"], [29, 31],
        ),
        (
            [("2026-01-01", "2026-01-31"), ("2026-02-01", "2026-03-01"),
             ("2026-03-01", "2026-03-31"), ("2026-04-01", "2026-04-30")],
            ["2026-01-31", "2026-02-28", "2026-03-31", "2026-04-30"], [31, 28, 31, 30],
        ),
    ],
)
def test_billing_conventions_preserve_quantities_and_printed_dates(periods, expected_ends, expected_days):
    original = pd.DataFrame([
        _invoice(str(index), start, end) for index, (start, end) in enumerate(periods)
    ])
    before = original.copy(deep=True)
    calculation = build_silver_proration_calculation(original)
    pd.testing.assert_frame_equal(original, before)
    resolved = calculation.drop_duplicates("proration_source_row_id")
    assert resolved.date_1_effective_end.tolist() == expected_ends
    assert resolved.date_1_total_days.tolist() == expected_days
    assert resolved.consumption_end_date_1_normalized.tolist() == [end for _, end in periods]
    splits = build_silver_proration_split(calculation)
    for _, group in splits.groupby("proration_source_row_id"):
        assert group.quantity_proration.sum() == pytest.approx(3100)
        assert group.date_split_days_proration.sum() == group.date_total_days_proration.iloc[0]


def test_missing_invoice_is_not_filled_and_late_arrival_rechecks_both_boundaries():
    first = _invoice("first", "2026-01-20", "2026-02-19")
    middle = _invoice("middle", "2026-02-19", "2026-03-20")
    last = _invoice("last", "2026-03-20", "2026-04-19")
    incomplete = build_silver_proration_calculation(pd.DataFrame([first, last]))
    before = incomplete.drop_duplicates("source_file").set_index("source_file")
    assert before.loc["first.json", "date_1_effective_end"] == "2026-02-19"
    assert before.loc["last.json", "date_1_effective_end"] == "2026-04-19"
    assert before.date_1_resolution.str.startswith("Gap").all()
    complete = build_silver_proration_calculation(pd.DataFrame([last, first, middle]))
    after = complete.drop_duplicates("source_file").set_index("source_file")
    assert after.loc["first.json", "date_1_effective_end"] == "2026-02-18"
    assert after.loc["middle.json", "date_1_effective_end"] == "2026-03-19"
    assert after.loc["last.json", "date_1_effective_end"] == "2026-04-18"
    assert after.loc["last.json", "date_1_provisional"] == "Yes"


@pytest.mark.parametrize(
    "start,end,effective_start,effective_end,days,adjustment,reason",
    [
        ("2025-12-31", "2026-01-31", "2026-01-01", "2026-01-31", 31, "Start +1 day", "Month-end dates"),
        ("2026-01-31", "2026-02-28", "2026-02-01", "2026-02-28", 28, "Start +1 day", "Month-end dates"),
        ("2024-01-31", "2024-02-29", "2024-02-01", "2024-02-29", 29, "Start +1 day", "Month-end dates"),
        ("2026-01-01", "2026-04-01", "2026-01-01", "2026-03-31", 90, "End −1 day", "Month-start dates"),
        ("2026-01-31", "2026-03-31", "2026-02-01", "2026-03-31", 59, "Start +1 day", "Month-end dates"),
        ("2026-01-31", "2026-03-01", "2026-01-31", "2026-03-01", 30, "None", "Insufficient history"),
        ("2026-01-01", "2026-01-01", "2026-01-01", "2026-01-01", 1, "None", "Single day"),
        ("2026-01-31", "2026-01-31", "2026-01-31", "2026-01-31", 1, "None", "Single day"),
    ],
)
def test_calendar_rules_do_not_require_neighbours(
    start, end, effective_start, effective_end, days, adjustment, reason,
):
    frames = _frames([_invoice("isolated", start, end)])
    splits = frames["proration_split"]
    assert splits.date_effective_start_proration.unique().tolist() == [effective_start]
    assert splits.date_effective_end_proration.unique().tolist() == [effective_end]
    assert splits.date_total_days_proration.unique().tolist() == [days]
    assert splits.date_adjustment_proration.unique().tolist() == [adjustment]
    assert splits.date_resolution_proration.unique().tolist() == [reason]
    assert splits.quantity_proration.sum() == pytest.approx(3100)
    report = build_report(prepare_audit_data(frames), ReportFilters(2026))
    assert not {"Allocation calculation", "Invoice reconciliation"}.intersection(report.cases.issue)


@pytest.mark.parametrize(
    "periods,expected_days,expected_segments,reasons",
    [
        ([("2025-11-18", "2025-12-17"), ("2025-12-17", "2026-01-19")],
         [29, 33], [13, 16, 15, 18], ["Shared date", "Previous invoice pattern"]),
        ([("2025-11-22", "2025-12-18"), ("2025-12-19", "2026-01-16")],
         [27, 29], [9, 18, 13, 16], ["Consecutive dates", "Previous invoice pattern"]),
    ],
)
def test_user_validated_examples(periods, expected_days, expected_segments, reasons):
    frames = _frames([_invoice(str(index), start, end) for index, (start, end) in enumerate(periods)])
    splits = frames["proration_split"]
    assert splits.drop_duplicates("proration_source_row_id").date_total_days_proration.tolist() == expected_days
    assert splits.date_split_days_proration.tolist() == expected_segments
    assert splits.drop_duplicates("proration_source_row_id").date_resolution_proration.tolist() == reasons
    december = build_report(prepare_audit_data(frames), ReportFilters(2026, 12))
    assert december.cases.empty
    assert december.details.month_days.sum() == 31


@pytest.mark.parametrize("start,end", [("2026-12-31", "2026-01-31"), ("", "2026-01-31")])
def test_invalid_dates_are_not_repaired_by_calendar_rules(start, end):
    data = prepare_audit_data(_frames([_invoice("invalid", start, end)]))
    assert data.periods.date_resolution.tolist() == ["Invalid dates"]
    assert data.periods.date_adjustment.tolist() == ["None"]
    assert "Invalid invoice inputs" in set(build_report(data, ReportFilters(2026)).cases.issue)


@pytest.mark.parametrize("identity", ["supplier_name", "account_number", "unit_name", "division", "legal_entity"])
def test_different_billing_sequences_do_not_change_each_others_dates(identity):
    records = [
        _invoice("first", "2025-12-17", "2026-01-19"),
        _invoice("second", "2026-01-19", "2026-02-18", **{identity: "Different"}),
    ]
    result = build_silver_proration_calculation(pd.DataFrame(records))
    periods = result.drop_duplicates("source_file")
    assert periods.date_1_effective_end.tolist() == ["2026-01-19", "2026-02-18"]


def test_missing_account_does_not_link_unrelated_invoices():
    records = [
        _invoice("first", "2025-12-17", "2026-01-19", account_number=""),
        _invoice("second", "2026-01-19", "2026-02-18", account_number=""),
    ]
    periods = build_silver_proration_calculation(pd.DataFrame(records)).drop_duplicates("source_file")
    assert periods.date_1_effective_end.tolist() == ["2026-01-19", "2026-02-18"]


@pytest.mark.parametrize(
    "periods",
    [
        [("2026-01-01", "2026-02-01"), ("2026-01-01", "2026-02-01")],
        [("2026-01-01", "2026-02-01"), ("2026-01-20", "2026-02-20")],
        [("2026-01-01", "2026-02-01"), ("2026-02-01", "2026-02-01")],
    ],
)
def test_duplicate_overlapping_and_single_day_periods_are_not_shortened(periods):
    records = [_invoice(str(index), start, end) for index, (start, end) in enumerate(periods)]
    resolved = build_silver_proration_calculation(pd.DataFrame(records)).drop_duplicates("source_file")
    assert resolved.date_1_effective_end.tolist() == [end for _, end in periods]
    assert resolved.date_1_resolution.eq("Overlap").all()
    report = build_report(prepare_audit_data(_frames(records)), ReportFilters(2026))
    assert "Overlapping billing periods" in set(report.cases.issue)
    assert "Invoice reconciliation" not in set(report.cases.issue)


def test_second_invoice_period_participates_in_the_sequence():
    record = _invoice(
        "two-periods", "2025-12-01", "2026-01-01",
        consumption_start_date_2_normalized="2026-01-01",
        consumption_end_date_2_normalized="2026-02-01",
        aggregated_quantity_2=3.1,
        quantity_unit_2="MWH",
    )
    frames = _frames([record])
    splits = frames["proration_split"]
    assert splits.date_month_proration.tolist() == ["2025-12", "2026-01"]
    assert splits.quantity_proration.tolist() == pytest.approx([3100, 3.1])
    data = prepare_audit_data(frames)
    for month in (12, 1):
        report = build_report(data, ReportFilters(2026, month))
        assert report.cases.empty
        assert report.details.allocated_kwh.sum() == pytest.approx(3100)


def test_ocr_and_manual_boundaries_reach_audit_screen_and_exports(tmp_path):
    first = _invoice("ocr", "2025-12-01", "2026-01-01")
    second = _invoice(
        "manual", "2026-01-01", "2026-02-01",
        manual_entry_invoice_id="manual", manual_entry_line_id="1",
    )
    frames = _frames([first], [second])
    # Exercise real Excel date serialization and readback used by the audit loader.
    for name, frame in frames.items():
        path = write_xlsx(frame, tmp_path, name + ".xlsx")
        frames[name] = pd.read_excel(path, dtype=object, keep_default_na=False)
    data = prepare_audit_data(frames)
    assert data.periods.end.tolist() == [pd.Timestamp("2025-12-31"), pd.Timestamp("2026-01-31")]
    assert data.periods.date_provisional.tolist() == ["No", "No"]
    for month in (12, 1):
        report = build_report(data, ReportFilters(2026, month))
        assert report.cases.empty
        assert report.details.allocated_kwh.sum() == pytest.approx(3100)
        full, compact = _detail_frames(report)
        assert full["Reason"].eq("Month-start dates").all()
        assert "Allocation end" in compact.columns
        workbook = load_workbook(BytesIO(excel_bytes(report)))
        headers = [cell.value for cell in workbook["Calculation Details"][1]]
        assert {"Invoice end", "Allocation end", "Date adjustment", "Reason", "Invoice days", "Days in month", "Original billed quantity", "Original unit", "kWh conversion factor", "Data source", "Invoice period reference"} <= set(headers)
        assert not {"Boundary evidence", "Supporting invoice", "Provisional dates", "Days", "Date treatment"}.intersection(headers)
        assert pdf_bytes(report).startswith(b"%PDF")
    monthly = build_silver_prorated(frames["proration_split"])
    assert monthly.covered_days_in_month.tolist() == [31]
    assert monthly.complete_month_data_captured.tolist() == [True]


def test_january_gap_remains_four_uncovered_days():
    frames = _frames([
        _invoice("december", "2025-12-01", "2025-12-31"),
        _invoice("january", "2026-01-05", "2026-01-31"),
    ])
    report = build_report(prepare_audit_data(frames), ReportFilters(2026, 1))
    assert report.details.allocated_kwh.sum() == pytest.approx(3100)
    assert report.details.month_days.tolist() == [27]
    assert report.cases.issue.tolist() == ["Missing coverage"]
    assert report.cases.explanation.iloc[0].startswith("4 of 31")


def test_audit_rejects_stale_or_modified_effective_dates():
    frames = _frames([
        _invoice("first", "2025-12-01", "2026-01-01"),
        _invoice("second", "2026-01-01", "2026-02-01"),
    ])
    frames["proration_split"].loc[0, "date_effective_end_proration"] = "2026-01-01"
    with pytest.raises(ValueError, match="billing date resolution. Rebuild Silver"):
        prepare_audit_data(frames)


def test_audit_still_detects_incorrect_allocations_after_date_resolution():
    frames = _frames([
        _invoice("first", "2025-12-01", "2026-01-01"),
        _invoice("second", "2026-01-01", "2026-02-01"),
    ])
    frames["proration_split"].loc[0, "quantity_proration"] = 3200
    report = build_report(prepare_audit_data(frames), ReportFilters(2026, 12))
    assert set(report.cases.issue) == {"Allocation calculation", "Invoice reconciliation"}


def test_legacy_splits_require_rebuild_instead_of_silent_reinterpretation():
    frames = _frames([_invoice("old", "2025-12-01", "2026-01-01")])
    frames["proration_split"] = frames["proration_split"].drop(columns="date_effective_end_proration")
    with pytest.raises(ValueError, match="Rebuild Silver"):
        prepare_audit_data(frames)


@pytest.mark.parametrize(
    "ocr_dates,manual_dates,months,adjustment",
    [
        (("2025-12-01", "2026-01-01"), ("2026-01-01", "2026-02-01"),
         ["2025-12-01", "2026-01-01"], "End −1 day"),
        (("2025-12-31", "2026-01-31"), ("2026-01-31", "2026-02-28"),
         ["2026-01-01", "2026-02-01"], "Start +1 day"),
    ],
)
def test_pipeline_rebuild_carries_cross_source_resolution_through_gold(
    tmp_path, ocr_dates, manual_dates, months, adjustment,
):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    checkpoint_dir = tmp_path / "checkpoints" / "scope2"
    checkpoint_dir.mkdir(parents=True)
    settings = {"paths": {
        "silver_excel_output": str(tmp_path / "silver"),
        "gold_output": str(tmp_path / "gold"),
        "review_checkpoint_output": str(tmp_path / "checkpoints"),
    }}
    (config_dir / "settings.yaml").write_text(yaml.safe_dump(settings), encoding="utf-8")
    mapping = dict.fromkeys(ACCOUNT_MAPPING_COLUMNS, "")
    mapping.update({
        "account_number": "00123", "division": "Division", "legal_entity": "Entity",
        "unit_name": "Unit", "supplier_name": "Supplier", "consumption_unit": "KWH",
        "activity_group": "Electricity", "decimal_separator": ".",
    })
    lookup_config = {}
    for name, rows, keys in (
        ("mapping", [mapping], ["account_number"]),
        ("energy_source_allocation", [
            {"unit_name": "Unit", "supplier_name": "Supplier", "start_date": month,
             "fossil_fuel_%": 1, "renewable_energy_%": 0, "nuclear_%": 0}
            for month in months
        ], ["unit_name", "supplier_name", "start_date"]),
        ("contracts", [{
            "unit_name": "Unit", "supplier_name": "Supplier", "contract_start_date": "2025-12-01",
            "contractual_instruments": "None",
        }], ["unit_name", "supplier_name", "contract_start_date"]),
    ):
        path = tmp_path / (name + ".xlsx")
        frame = pd.DataFrame(rows)
        frame.to_excel(path, sheet_name=name, index=False)
        lookup_config[name] = {
            "path": str(path), "sheet_name": name,
            "delimiter": "_",
            "workbook_key_columns": keys, "ocr_key_fields": keys,
            "date_key_fields": [key for key in keys if key.endswith("date")],
        }
    (config_dir / "mapping_files.yaml").write_text(
        yaml.safe_dump({"mapping_files": lookup_config}), encoding="utf-8",
    )
    pd.DataFrame([{
        "invoice_id": "ocr", "line_id": "1", "source_file": "ocr.json",
        "account_number": "00123", "quantity_1": 3100, "quantity_unit_1": "KWH",
        "consumption_start_date_1": ocr_dates[0], "consumption_end_date_1": ocr_dates[1],
    }]).to_csv(checkpoint_dir / "step_5_approved_silver_checkpoint.csv", index=False)
    pd.DataFrame([{
        "invoice_id": "manual", "line_id": "1", "source_file": "manual.pdf",
        "manual_entry_status": "COMPLETED", "unit": "Unit",
        "consumption_start_date": manual_dates[0], "consumption_end_date": manual_dates[1],
        "amount_of_energy_consumed": 3100, "energy_unit": "KWH",
    }]).to_csv(checkpoint_dir / "step_0_manual_data_entry_decisions_checkpoint.csv", index=False)

    run_silver_pipeline(config_dir=config_dir)
    gold_path = run_gold_pipeline(config_dir=config_dir)
    gold = pd.read_excel(gold_path, keep_default_na=False)
    assert gold["Amount of energy consumed"].tolist() == pytest.approx([3100, 3100])
    assert pd.to_datetime(gold["Consumption start date"]).dt.strftime("%Y-%m-%d").tolist() == months
    assert pd.to_datetime(gold.date_effective_end_proration).dt.strftime("%Y-%m-%d").tolist() == [
        (pd.Timestamp(month) + pd.offsets.MonthEnd()).strftime("%Y-%m-%d") for month in months
    ]
    assert gold.date_adjustment_proration.tolist() == [adjustment, adjustment]
    assert gold.date_provisional_proration.tolist() == ["No", "No"]
    dashboard_input = pd.read_excel(
        tmp_path / "gold" / gold_output_filename("scope2", "template_aggregated"),
        keep_default_na=False,
    )
    assert dashboard_input["Amount of energy consumed"].tolist() == pytest.approx([3100, 3100])
    assert dashboard_input.date_provisional_proration.tolist() == ["No", "No"]
    assert dashboard_input.date_adjustment_proration.tolist() == [adjustment, adjustment]
    data = load_audit_data(tmp_path, settings)
    for month in months:
        assert build_report(data, ReportFilters(2026, pd.Timestamp(month).month)).cases.empty
    for layer in ("prorated", "manual_prorated"):
        monthly = pd.read_excel(tmp_path / "silver" / silver_output_filename("scope2", layer))
        assert monthly.complete_month_data_captured.tolist() == [True]
