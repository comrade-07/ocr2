from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from openpyxl import load_workbook

from src.audit.loader import prepare_audit_data, load_audit_data, input_paths
from src.audit.models import ReportFilters
from src.audit.report import build_report
from src.audit.report import report_description
from src.audit.excel_export import excel_bytes
from src.audit.pdf_export import pdf_bytes
from src.pipeline.run_silver_pipeline import (
    SILVER_AGGREGATED_COLUMNS,
    build_silver_proration_calculation,
    build_silver_proration_split,
    build_silver_prorated,
)


@pytest.mark.parametrize("unit,expected", [("kWh", 10), ("MWh", 10000), ("ton", 7200), ("RTH", 6.2)])
def test_audit_and_gold_use_identical_energy_conversion(unit, expected):
    from src.pipeline.run_gold_pipeline import build_gold_template

    data = prepare_audit_data(frames_for([invoice(
        aggregated_quantity_1=10, consumption_quantity_unit=unit,
    )]))
    gold = build_gold_template(pd.DataFrame([{
        "Amount of energy consumed": 10, "Energy Unit": unit,
    }]))
    assert data.periods.iloc[0].billed_kwh == pytest.approx(expected)
    assert data.allocations.allocated_kwh.sum() == pytest.approx(expected)
    assert gold.iloc[0]["Amount of energy consumed"] == pytest.approx(expected)


def test_audit_flags_ambiguous_mapping_with_complete_facility_fields():
    data = prepare_audit_data(frames_for([invoice(mapping_status="AMBIGUOUS")]))
    assert not data.periods.iloc[0].mapped


@pytest.mark.parametrize(
    "include,expected_sheets",
    [
        (
            "Full report",
            ["Summary", "Calculation Details", "Exceptions", "Report information"],
        ),
        ("Summary", ["Summary", "Report information"]),
        (
            "Summary and details",
            ["Summary", "Calculation Details", "Report information"],
        ),
    ],
)
def test_export_options_preserve_audit_inputs(
    include: str, expected_sheets: list[str]
) -> None:
    data = prepare_audit_data(frames_for([invoice()]))
    original_periods = data.periods.copy(deep=True)
    original_allocations = data.allocations.copy(deep=True)
    report = build_report(data, ReportFilters(2026, 12))
    original_details = report.details.copy(deep=True)
    original_summary = report.summary.copy(deep=True)
    original_cases = report.cases.copy(deep=True)

    workbook = load_workbook(BytesIO(excel_bytes(report, include)))
    assert workbook.sheetnames == expected_sheets
    assert pdf_bytes(report, include).startswith(b"%PDF")

    pd.testing.assert_frame_equal(data.periods, original_periods)
    pd.testing.assert_frame_equal(data.allocations, original_allocations)
    pd.testing.assert_frame_equal(report.details, original_details)
    pd.testing.assert_frame_equal(report.summary, original_summary)
    pd.testing.assert_frame_equal(report.cases, original_cases)


@pytest.mark.parametrize(
    "include,has_details,has_checks",
    [
        ("Full report", True, True),
        ("Summary and details", True, False),
        ("Summary", False, False),
    ],
)
def test_pdf_export_includes_requested_sections(
    monkeypatch: pytest.MonkeyPatch,
    include: str,
    has_details: bool,
    has_checks: bool,
) -> None:
    from reportlab.platypus import Flowable, Paragraph, SimpleDocTemplate

    report = build_report(
        prepare_audit_data(frames_for([invoice()])), ReportFilters(2026, 12)
    )
    paragraphs: list[str] = []
    original_build = SimpleDocTemplate.build

    def capture_content(
        document: SimpleDocTemplate, flowables: list[Flowable], **kwargs: Any
    ) -> None:
        # Inspect the document content before ReportLab consumes it during layout.
        for flowable in flowables:
            if isinstance(flowable, Paragraph):
                paragraphs.append(flowable.getPlainText())
        original_build(document, flowables, **kwargs)

    monkeypatch.setattr(SimpleDocTemplate, "build", capture_content)
    assert pdf_bytes(report, include).startswith(b"%PDF")
    assert "Facility summary" in paragraphs
    assert any(text.startswith("Unit name: Facility") for text in paragraphs) == has_details
    assert ("Checks and exceptions" in paragraphs) == has_checks
    assert "Report inputs" in paragraphs


def test_excel_preserves_literal_account_text_and_verification_formulas() -> None:
    record = invoice(account_number="=1+1")
    report = build_report(
        prepare_audit_data(frames_for([record])), ReportFilters(2026, 12)
    )
    workbook = load_workbook(BytesIO(excel_bytes(report)))
    details = workbook["Calculation Details"]
    headers = {}
    for cell in details[1]:
        headers[cell.value] = cell.column

    account_cell = details.cell(2, headers["Account number"])
    assert account_cell.value == "=1+1"
    assert account_cell.data_type == "s"
    for column in ("Recalculated kWh", "Difference kWh"):
        assert details.cell(2, headers[column]).data_type == "f"

    assert workbook["Summary"].freeze_panes == "D2"
    assert details.freeze_panes == "E2"
    assert workbook["Exceptions"].freeze_panes == "C2"


def invoice(**overrides):
    return {
        "invoice_id": "invoice-a",
        "line_id": "1",
        "division": "Division",
        "legal_entity": "Entity",
        "unit_name": "Facility",
        "account_number": "00123",
        "source_file": "invoice-a.json",
        "sharepoint_link": "https://example.com/a.pdf",
        "consumption_quantity_unit": "KWH",
        "consumption_start_date_1_normalized": "2025-12-16",
        "consumption_end_date_1_normalized": "2026-01-15",
        "aggregated_quantity_1": 3100,
        **overrides,
    }


def frames_for(records=None, manual=None):
    frames = {}
    for name, split, records in [
        ("aggregated", "proration_split", records or []),
        ("manual_mapping", "manual_proration_split", manual or []),
    ]:
        original = pd.DataFrame(records).reindex(
            columns=SILVER_AGGREGATED_COLUMNS, fill_value=""
        )
        frames[name] = original
    for _, name, split in (
        ("Reviewed OCR", "aggregated", "proration_split"),
        ("Manual entry", "manual_mapping", "manual_proration_split"),
    ):
        other_name = "manual_mapping" if name == "aggregated" else "aggregated"
        frames[split] = build_silver_proration_split(
            build_silver_proration_calculation(frames[name], other_invoices=frames[other_name])
        )
    return frames


def test_manual_upload_evidence_reaches_report_exports(tmp_path: Path) -> None:
    from src.review.evidence_links import build_upload_evidence_url
    from src.review.manual_data_entry import append_manual_upload_queue_row
    from src.pipeline.run_silver_pipeline import build_manual_data_entry_proration_input

    upload_directory = tmp_path / "uploads"
    saved_file = upload_directory / "20260915T000000Z_electricity.pdf"
    evidence_url = build_upload_evidence_url(
        saved_file,
        upload_directory,
        "https://tenant.sharepoint.com/sites/ESG/Evidence/scope2",
    )
    queue_path = tmp_path / "queue.csv"
    append_manual_upload_queue_row(
        queue_path,
        uploaded_file_name="electricity.pdf",
        stored_file_path=saved_file,
        uploaded_at="2026-09-15T00:00:00+00:00",
        sharepoint_link=evidence_url,
    )
    completed_entries = pd.read_csv(queue_path, dtype=object, keep_default_na=False)
    completed_values = {
        "manual_entry_status": "COMPLETED",
        "division": "North",
        "legal_entity_name": "Entity",
        "unit": "Unit A",
        "account_number": "00123",
        "consumption_start_date": "2025-12-16",
        "consumption_end_date": "2026-01-15",
        "amount_of_energy_consumed": "3100",
        "energy_unit": "KWH",
    }
    for field_name, value in completed_values.items():
        completed_entries[field_name] = value

    manual_mapping = build_manual_data_entry_proration_input(completed_entries)
    frames = frames_for()
    frames["manual_mapping"] = manual_mapping
    frames["manual_proration_split"] = build_silver_proration_split(
        build_silver_proration_calculation(manual_mapping)
    )
    report = build_report(
        prepare_audit_data(frames), ReportFilters(2026, 12, source="Manual entry")
    )
    assert report.details.source_link.tolist() == [evidence_url]
    assert report.cases.source_links.tolist() == [(evidence_url,)]

    workbook = load_workbook(BytesIO(excel_bytes(report)))
    for sheet_name in ("Calculation Details", "Exceptions"):
        evidence_cells = []
        for row in workbook[sheet_name].iter_rows(min_row=2):
            for cell in row:
                if cell.hyperlink is not None:
                    evidence_cells.append(cell)
        assert len(evidence_cells) == 1
        assert evidence_cells[0].value == "Open evidence file"
        assert evidence_cells[0].hyperlink.target == evidence_url

    pdf = pdf_bytes(report)
    assert pdf.count(evidence_url.encode("ascii")) == 3


def test_cross_year_reconciles_full_invoice_before_filtering():
    report = build_report(
        prepare_audit_data(frames_for([invoice()])), ReportFilters(2026, 12)
    )
    assert report.details.allocated_kwh.tolist() == [1600]
    assert "Invoice reconciliation" not in set(report.cases.issue)
    assert "Missing coverage" in set(report.cases.issue)


@pytest.mark.parametrize(
    "start,end,quantity,expected",
    [
        ("2024-02-01", "2024-02-29", 290, 290),
        ("2024-02-29", "2024-03-01", 20, 10),
        ("2024-02-29", "2024-02-29", 10, 10),
    ],
)
def test_inclusive_day_boundaries(start, end, quantity, expected):
    record = invoice(
        consumption_start_date_1_normalized=start,
        consumption_end_date_1_normalized=end,
        aggregated_quantity_1=quantity,
    )
    report = build_report(
        prepare_audit_data(frames_for([record])), ReportFilters(2024, 2)
    )
    assert report.details.allocated_kwh.sum() == expected
    assert "Allocation calculation" not in set(report.cases.issue)


def test_manual_and_second_period_have_distinct_references():
    record = invoice(
        consumption_start_date_2_normalized="2025-12-01",
        consumption_end_date_2_normalized="2025-12-31",
        aggregated_quantity_2=31,
        quantity_unit_2="MWH",
    )
    manual = invoice(manual_entry_invoice_id="manual-a", manual_entry_line_id="1")
    data = prepare_audit_data(frames_for([record], [manual]))
    assert data.periods.period_id.nunique() == 3
    report = build_report(data, ReportFilters(2026, 12))
    assert report.details.allocated_kwh.sum() == 34200
    assert "Overlapping billing periods" in set(report.cases.issue)


def test_missing_and_changed_allocations_create_cases():
    frames = frames_for([invoice()])
    frames["proration_split"] = frames["proration_split"].iloc[:1].copy()
    frames["proration_split"].loc[0, "quantity_proration"] = 999
    report = build_report(prepare_audit_data(frames), ReportFilters(2026, 12))
    assert {
        "Invoice reconciliation",
        "Missing or repeated allocation",
        "Allocation calculation",
    } <= set(report.cases.issue)
    assert report.details.allocated_kwh.tolist() == [999]  # Never silently repaired.


def test_invalid_invoice_and_unit_are_not_silently_zero():
    data = prepare_audit_data(
        frames_for(
            [
                invoice(
                    consumption_start_date_1_normalized="",
                    consumption_quantity_unit="GJ",
                )
            ]
        )
    )
    report = build_report(data, ReportFilters(2026, 12))
    assert {"Invalid invoice inputs", "Unsupported energy unit"} <= set(
        report.cases.issue
    )
    assert report.details.empty


def test_two_facilities_with_same_name_stay_separate_and_mixed_units_not_summed():
    records = [
        invoice(),
        invoice(
            invoice_id="b",
            division="Other",
            aggregated_quantity_1=2,
            consumption_quantity_unit="MWH",
        ),
        invoice(
            invoice_id="c", aggregated_quantity_1=3, consumption_quantity_unit="MWH"
        ),
    ]
    frames = frames_for(records)
    monthly = build_silver_prorated(frames["proration_split"])
    assert len(monthly) == 6
    report = build_report(prepare_audit_data(frames), ReportFilters(2026, 12))
    assert (
        len(report.summary[["division", "legal_entity", "unit_name"]].drop_duplicates())
        == 2
    )
    assert report.summary.allocated_kwh.sum() == pytest.approx((3100 + 5000) * 16 / 31)


def test_excel_exports_all_cases_and_preserves_account_and_formulas():
    records = [
        invoice(
            invoice_id=f"bill-{i}",
            account_number=f"{i:05}",
            source_file="=HYPERLINK(1)",
        )
        for i in range(55)
    ]
    report = build_report(
        prepare_audit_data(frames_for(records)), ReportFilters(2026, 12)
    )
    workbook = load_workbook(BytesIO(excel_bytes(report)))
    assert workbook["Exceptions"].max_row == 56
    details = workbook["Calculation Details"]
    headers = {c.value: c.column for c in details[1]}
    assert details.cell(2, headers["Account number"]).value == "00000"
    assert details.cell(2, headers["Recalculated kWh"]).data_type == "f"
    assert "Source file" not in headers
    assert details.cell(2, headers["Source"]).data_type == "s"
    assert (
        details.cell(2, headers["Source"]).hyperlink.target
        == "https://example.com/a.pdf"
    )


def test_pdf_can_paginate_many_cases():
    report = build_report(
        prepare_audit_data(
            frames_for(
                [
                    invoice(invoice_id=f"bill-{i}", account_number=f"{i:05}")
                    for i in range(55)
                ]
            )
        ),
        ReportFilters(2026, 12),
    )
    payload = pdf_bytes(report)
    assert payload.startswith(b"%PDF")
    assert len(payload) > 10000


def test_empty_inputs_are_supported():
    report = build_report(prepare_audit_data(frames_for()), ReportFilters(2026, 12))
    assert report.details.empty
    assert report.cases.empty
    assert excel_bytes(report)
    assert pdf_bytes(report)


def test_loader_rejects_old_schema_and_detects_stale_outputs(tmp_path):
    frames = frames_for([invoice()])
    paths = input_paths(tmp_path, {}, "scope2")
    for name, path in paths.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        frames[name].to_excel(path, index=False)
    data = load_audit_data(tmp_path, {})
    assert len(data.sources) == 4
    checkpoint = tmp_path / "data/output/checkpoints/scope2/decisions.csv"
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_text("invoice_id\na\n")
    assert load_audit_data(tmp_path, {}).warnings
    frames["proration_split"].drop(columns="proration_period_index").to_excel(
        paths["proration_split"], index=False
    )
    with pytest.raises(ValueError, match="Rebuild Silver"):
        load_audit_data(tmp_path, {})


def test_page_filters_pagination_and_exports(tmp_path):
    from streamlit.testing.v1 import AppTest

    frames = frames_for(
        [
            invoice(invoice_id=f"invoice-{i}", account_number=f"{i:05}")
            for i in range(55)
        ]
    )
    for name, path in input_paths(tmp_path, {}, "scope2").items():
        path.parent.mkdir(parents=True, exist_ok=True)
        frames[name].to_excel(path, index=False)
    app = AppTest.from_string(
        "from src.audit.page import show_audit_report\n"
        f"show_audit_report('scope2', {str(tmp_path)!r}, {{}})\n"
    ).run()
    assert not app.exception
    app.selectbox(key="audit_scope2_year").select(2026).run()
    app.selectbox(key="audit_scope2_month").select(12).run()
    app.radio(key="audit_scope2_view").set_value("Checks & exceptions").run()
    assert not app.exception
    assert len(app.dataframe[0].value) == 10
    app.selectbox(key="audit_scope2_cases_page").select(6).run()
    assert len(app.dataframe[0].value) == 5
    app.text_input(key="audit_scope2_case_search").set_value("00054").run()
    assert len(app.dataframe[0].value) == 1
    app.button(key="audit_scope2_prepare").click().run()
    assert not app.exception
    payload = app.session_state["audit_scope2_download"][1]
    assert load_workbook(BytesIO(payload))["Exceptions"].max_row == 56
    app.selectbox(key="audit_scope2_format").select("PDF").run()
    app.button(key="audit_scope2_prepare").click().run()
    assert not app.exception
    assert app.session_state["audit_scope2_download"][1].startswith(b"%PDF")


def test_navigation_bridge_opens_selected_invoice(monkeypatch):
    import review_app

    state = {}
    monkeypatch.setattr(review_app.st, "session_state", state)
    monkeypatch.setattr(review_app.st, "rerun", lambda: None)
    review_app.open_audit_invoice("scope2", "Reviewed OCR", "invoice-a", "2")
    assert state[review_app.ACTIVE_SECTION_KEY] == "Data Approval"
    assert state["audit_scope2_review_target"] == ("invoice-a", "2")
    review_app.open_audit_invoice("scope2", "Manual entry", "manual-b", "3")
    assert state[review_app.ACTIVE_SECTION_KEY] == "Manual Data Entry"
    assert state["audit_scope2_manual_target"] == ("manual-b", "3")


def test_hierarchy_filters_scope_details_checks_and_export():
    data = prepare_audit_data(
        frames_for(
            [
                invoice(
                    invoice_id="a",
                    division="North",
                    legal_entity="Entity A",
                    unit_name="Shared unit",
                ),
                invoice(
                    invoice_id="b",
                    division="South",
                    legal_entity="Entity B",
                    unit_name="Shared unit",
                ),
                invoice(
                    invoice_id="c",
                    division="North",
                    legal_entity="Entity C",
                    unit_name="Other unit",
                ),
            ]
        )
    )
    report = build_report(
        data,
        ReportFilters(
            2026, 12, division="North", legal_entity="Entity A", unit_name="Shared unit"
        ),
    )
    assert report.details.invoice_id.tolist() == ["a"]
    assert report.summary.allocated_kwh.sum() == 1600
    assert set(report.cases.facility) == {"North / Entity A / Shared unit"}
    assert (
        "Division: North | Legal entity: Entity A | Unit name: Shared unit"
        in report_description(report)
    )
    workbook = load_workbook(BytesIO(excel_bytes(report)))
    assert workbook["Calculation Details"].max_row == 2
    assert "Division: North" in workbook["Report information"]["B2"].value
    # Unmapped is an explicit value, distinct from the unfiltered None option.
    unmapped = prepare_audit_data(frames_for([invoice(division="")]))
    assert (
        len(build_report(unmapped, ReportFilters(2026, 12, division="")).details) == 1
    )


def test_hierarchy_selectors_cascade_and_reset_invalid_children(tmp_path):
    from streamlit.testing.v1 import AppTest

    frames = frames_for(
        [
            invoice(
                invoice_id="a",
                division="North",
                legal_entity="Entity A",
                unit_name="Unit A",
                account_number="001",
            ),
            invoice(
                invoice_id="b",
                division="South",
                legal_entity="Entity B",
                unit_name="Unit B",
                account_number="002",
            ),
        ]
    )
    for name, path in input_paths(tmp_path, {}, "scope2").items():
        path.parent.mkdir(parents=True, exist_ok=True)
        frames[name].to_excel(path, index=False)
    app = AppTest.from_string(
        "from src.audit.page import show_audit_report\n"
        f"show_audit_report('scope2', {str(tmp_path)!r}, {{}})\n"
    ).run()
    app.selectbox(key="audit_scope2_division").select("North").run()
    assert app.selectbox(key="audit_scope2_legal_entity").options == [
        "All legal entities",
        "Entity A",
    ]
    app.selectbox(key="audit_scope2_legal_entity").select("Entity A").run()
    app.selectbox(key="audit_scope2_unit_name").select("Unit A").run()
    app.selectbox(key="audit_scope2_account").select("001").run()
    app.selectbox(key="audit_scope2_division").select("South").run()
    assert not app.exception
    assert app.selectbox(key="audit_scope2_legal_entity").value is None
    assert app.selectbox(key="audit_scope2_unit_name").value is None
    assert app.selectbox(key="audit_scope2_account").value == "All accounts"
    assert app.selectbox(key="audit_scope2_unit_name").options == [
        "All units",
        "Unit B",
    ]


def test_report_exports_separate_hierarchy_scope_issues_and_sharepoint_sources():
    from src.audit.report import detail_table, summary_table, cases_table

    records = [
        invoice(
            invoice_id="south",
            division="South",
            unit_name="Unit S",
            sharepoint_link="https://tenant.sharepoint.com/south.pdf",
        ),
        invoice(
            invoice_id="north-b",
            division="North",
            legal_entity="Entity B",
            unit_name="Unit B",
            sharepoint_link="https://tenant.sharepoint.com/north-b.pdf",
        ),
        invoice(
            invoice_id="north-a",
            division="North",
            legal_entity="Entity A",
            unit_name="Unit A",
            sharepoint_link="https://tenant.sharepoint.com/north-a.pdf",
        ),
    ]
    data = prepare_audit_data(frames_for(records))
    full = build_report(data, ReportFilters(2026, 12))
    assert full.details.invoice_id.tolist() == ["north-a", "north-b", "south"]
    assert full.cases.division.tolist() == ["North", "North", "South"]
    report = build_report(data, ReportFilters(2026, 12, division="North"))
    for frame in (detail_table(report), summary_table(report), cases_table(report)):
        assert all(
            column in frame for column in ("Division", "Legal entity", "Unit name")
        )
        assert "Facility" not in frame
        assert set(frame.Division) == {"North"}
    workbook = load_workbook(BytesIO(excel_bytes(report)))
    text = str([[cell.value for row in sheet for cell in row] for sheet in workbook])
    assert "invoice-a.json" not in text
    assert "south.pdf" not in text
    assert "Source file" not in text
    targets = [
        cell.hyperlink.target
        for sheet in workbook
        for row in sheet
        for cell in row
        if cell.hyperlink
    ]
    assert targets.count("https://tenant.sharepoint.com/north-a.pdf") == 2
    assert targets.count("https://tenant.sharepoint.com/north-b.pdf") == 2
    for sheet_name in ("Calculation Details", "Exceptions"):
        sheet = workbook[sheet_name]
        for row in sheet.iter_rows(min_row=2):
            for cell in row:
                if cell.hyperlink is not None:
                    assert cell.value == "Open evidence file"
                    assert cell.alignment.wrap_text is True
        assert sheet.sheet_format.defaultRowHeight == 15
        assert sheet.row_dimensions[2].height is None
    pdf = pdf_bytes(report)
    assert b"https://tenant.sharepoint.com/north-a.pdf" in pdf
    assert b"https://tenant.sharepoint.com/south.pdf" not in pdf


def test_missing_sharepoint_link_does_not_fall_back_to_json():
    from src.audit.report import detail_table, cases_table

    report = build_report(
        prepare_audit_data(frames_for([invoice(sharepoint_link="")])),
        ReportFilters(2026, 12),
    )
    assert detail_table(report).Source.tolist() == ["SharePoint link unavailable"]
    assert cases_table(report)["Source 1"].tolist() == ["SharePoint link unavailable"]
    assert "invoice-a.json" not in str(cases_table(report).to_dict())


def test_reporting_year_runs_from_previous_december_through_november():
    from src.audit.report import reporting_months, reporting_year

    records = [
        invoice(
            invoice_id="start-boundary",
            consumption_start_date_1_normalized="2025-11-30",
            consumption_end_date_1_normalized="2025-12-01",
            aggregated_quantity_1=20,
        ),
        invoice(
            invoice_id="end-boundary",
            consumption_start_date_1_normalized="2026-11-30",
            consumption_end_date_1_normalized="2026-12-01",
            aggregated_quantity_1=20,
        ),
    ]
    data = prepare_audit_data(frames_for(records))
    report = build_report(data, ReportFilters(2026))
    expected_months = ["2025-12", *[f"2026-{month:02}" for month in range(1, 12)]]
    assert [str(month) for month in reporting_months(report.filters)] == expected_months
    assert report.details.month.tolist() == ["2025-12", "2026-11"]
    assert report.details.allocated_kwh.sum() == 20
    assert set(report.cases.month) == set(expected_months)
    assert "Invoice reconciliation" not in set(report.cases.issue)
    assert reporting_year("2025-12-01") == 2026
    assert reporting_year("2026-11-30") == 2026
    assert reporting_year("2026-12-01") == 2027
    december = build_report(data, ReportFilters(2026, 12))
    assert december.details.month.tolist() == ["2025-12"]
    workbook = load_workbook(BytesIO(excel_bytes(report)))
    assert (
        "01 December 2025 to 30 November 2026"
        in workbook["Report information"]["B2"].value
    )


def test_audit_separates_energy_kpi_checks_totals_and_exports(monkeypatch):
    from reportlab.platypus import Paragraph, SimpleDocTemplate

    records = [invoice(invoice_id=group, source_file=group + ".json", activity_group=group,
                       consumption_quantity_unit=unit, aggregated_quantity_1=10,
                       consumption_start_date_1_normalized="2026-01-01",
                       consumption_end_date_1_normalized="2026-02-01")
               for group, unit in [("Electricity", "kWh"), ("Steam", "ton"), ("Heat", "MWh"), ("Cool", "RTH")]]
    data = prepare_audit_data(frames_for(records))
    report = build_report(data, ReportFilters(2026, 1))
    assert "Overlapping billing periods" not in set(report.cases.issue)
    totals = report.summary.set_index("kpi_component").allocated_kwh.to_dict()
    assert totals == pytest.approx({"Purchased electricity": 10, "Purchased steam": 7200,
                                   "Purchased heat": 10000, "Purchased cool": 6.2})
    scoped = build_report(data, ReportFilters(2026, 1, kpi_component="Purchased steam"))
    assert scoped.details.kpi_component.unique().tolist() == ["Purchased steam"]
    workbook = load_workbook(BytesIO(excel_bytes(report)))
    for group in ("Electricity", "Steam", "Heat", "Cool"):
        details = workbook[group + " Details"]
        headers = {cell.value: cell.column for cell in details[1]}
        assert details.max_row == 2
        assert details.cell(2, headers["KPI Component"]).value == "Purchased " + group.lower()
        assert details.cell(2, headers["Recalculated kWh"]).data_type == "f"
        assert group + " Summary" in workbook.sheetnames
        assert group + " Exceptions" in workbook.sheetnames
    paragraphs = []
    original_build = SimpleDocTemplate.build
    def capture(document, flowables, **kwargs):
        paragraphs.extend(item.getPlainText() for item in flowables if isinstance(item, Paragraph))
        original_build(document, flowables, **kwargs)
    monkeypatch.setattr(SimpleDocTemplate, "build", capture)
    assert pdf_bytes(report).startswith(b"%PDF")
    for component in totals:
        assert component in paragraphs


def test_audit_rejects_stale_split_energy_classification():
    frames = frames_for([invoice(activity_group="Steam")])
    frames["proration_split"]["activity_group"] = "Electricity"
    with pytest.raises(ValueError, match="stale account or energy classification"):
        prepare_audit_data(frames)


@pytest.mark.parametrize("second_unit,expected", [("Total energy [MWh]", 10000), ("unreadable", 6.2), ("", 6.2)])
def test_second_period_extraction_and_account_fallback_agree_with_audit(second_unit, expected):
    frames = frames_for([invoice(
        consumption_quantity_unit="KWH", consumption_unit="RTH",
        quantity_unit_2=second_unit, aggregated_quantity_2=10,
        consumption_start_date_2_normalized="2026-02-01",
        consumption_end_date_2_normalized="2026-03-01",
    )])
    data = prepare_audit_data(frames)
    period = data.periods.loc[data.periods.period_index == 2].iloc[0]
    assert period.billed_kwh == pytest.approx(expected)
    assert data.allocations.loc[data.allocations.period_index == 2, "allocated_kwh"].sum() == pytest.approx(expected)
