import pandas as pd
import pytest

from review_app import (
    add_decision_type_column,
    curate_template_output_columns,
    delete_manual_override_rows,
    update_decision,
)


def test_curate_template_output_columns_keeps_gold_source_links():
    df = pd.DataFrame([
        {
            "ignored_before": "before",
            "Data Quality": "Actual",
            "Division": "Division A",
            "contractual_instruments": "Green tariff",
            "source_files": "invoice-a.json; invoice-b.json",
            "sharepoint_link_1": "https://example.test/invoice-a.pdf",
            "sharepoint_link_2": "https://example.test/invoice-b.pdf",
            "manual_data_entry_portion": "",
        }
    ])

    result = curate_template_output_columns(df)

    assert list(result.columns) == [
        "Data Quality",
        "Division",
        "contractual_instruments",
        "source_files",
        "sharepoint_link_1",
        "sharepoint_link_2",
    ]


def test_update_decision_creates_missing_first_decision_row():
    issue = pd.Series({
        "issue_id": "issue_one_1_supplier",
        "invoice_id": "one.json",
        "line_id": "1",
        "field_name": "supplier",
        "ocr_value": "ACME",
    })

    updated = update_decision(
        pd.DataFrame(),
        issue_id="issue_one_1_supplier",
        corrected_value="ACME",
        review_decision="APPROVED",
        reviewed_by="Reviewer",
        review_comment="Looks good",
        issue_row=issue,
    )

    assert len(updated) == 1
    row = updated.iloc[0]
    assert row["decision_id"] == "decision_issue_one_1_supplier"
    assert row["invoice_id"] == "one.json"
    assert row["line_id"] == "1"
    assert row["field_name"] == "supplier"
    assert row["original_value"] == "ACME"
    assert row["corrected_value"] == "ACME"
    assert row["review_decision"] == "APPROVED"
    assert row["review_tag"] == "MANUALLY_REVIEWED"
    assert row["reviewed_by"] == "Reviewer"
    assert row["review_comment"] == "Looks good"


def test_add_decision_type_column_labels_manual_overrides():
    decisions = pd.DataFrame([
        {"issue_id": "issue_one_1_supplier", "field_name": "supplier"},
        {"issue_id": "override_one_1_total_amount", "field_name": "total_amount"},
    ])

    result = add_decision_type_column(decisions)

    assert list(result["decision_type"]) == ["Review issue", "Manual override"]


def test_delete_manual_override_rows_removes_selected_override_only():
    decisions = pd.DataFrame([
        {"issue_id": "issue_one_1_supplier", "field_name": "supplier"},
        {"issue_id": "override_one_1_total_amount", "field_name": "total_amount"},
        {"issue_id": "override_one_1_invoice_date", "field_name": "invoice_date"},
    ])

    result = delete_manual_override_rows(decisions, "override_one_1_total_amount")

    assert list(result["issue_id"]) == [
        "issue_one_1_supplier",
        "override_one_1_invoice_date",
    ]


def test_manual_kpi_choices_follow_mapping_workbook_and_refresh(monkeypatch):
    import review_app
    from streamlit.testing.v1 import AppTest

    table = pd.DataFrame([
        {"division": "Division", "legal_entity": "Entity", "unit_name": "Facility", "activity_group": "Electricity", "account_number": "001"},
        {"division": "Division", "legal_entity": "Entity", "unit_name": "Facility", "activity_group": "Steam", "account_number": "002"},
        {"division": "Division", "legal_entity": "Entity", "unit_name": "Other", "activity_group": "Heat", "account_number": "003"},
    ])
    monkeypatch.setattr(review_app, "load_account_mapping_table", lambda *args: table)
    app = AppTest.from_string(
        "import pandas as pd\n"
        "import streamlit as st\n"
        "from review_app import show_manual_energy_mapping\n"
        "selection = show_manual_energy_mapping(\n"
        "    {'division': 'Division', 'legal_entity_name': 'Entity', 'unit': 'Facility'},\n"
        "    pd.Series(dtype=object), 'invoice', '1')\n"
        "st.json(selection)\n"
    ).run()
    assert not app.exception
    assert app.selectbox[0].options == ["", "Purchased electricity", "Purchased steam"]
    app.selectbox[0].select("Purchased steam").run()
    assert "002" in app.caption[0].value

    table.loc[1, "account_number"] = "004"
    app.run()
    assert "004" in app.caption[0].value
    table.loc[1, "activity_group"] = "Cool"
    app.run()
    assert not app.exception
    assert app.selectbox[0].value == ""
    assert app.selectbox[0].options == ["", "Purchased electricity", "Purchased cool"]


def test_missing_mapping_view_includes_manual_ambiguities(monkeypatch):
    import review_app

    frames = {
        "normalized": pd.DataFrame([{"source_file": "ocr.json", "mapping_status": "MAPPED", "activity_group": "Electricity"}]),
        "manual": pd.DataFrame([{"source_file": "steam.pdf", "mapping_status": "AMBIGUOUS", "mapping_message": "Multiple accounts", "activity_group": "Steam"}]),
    }
    monkeypatch.setattr(review_app, "category_paths", lambda key: {
        "silver_normalized": "normalized", "silver_manual_mapping": "manual",
    })
    monkeypatch.setattr(review_app, "read_excel", lambda path: frames[path])
    result = review_app.curate_missing_mapping_columns(review_app.load_missing_mapping_rows("scope2", False))
    assert result["source_file"].tolist() == ["steam.pdf"]
    assert result.loc[0, "mapping_status"] == "AMBIGUOUS"
    assert result.loc[0, "activity_group"] == "Steam"


def test_missing_mapping_view_shows_energy_allocation_flags(monkeypatch):
    import review_app

    frames = {
        "normalized": pd.DataFrame(), "manual": pd.DataFrame(),
        "business": pd.DataFrame([
            {"source_files": "steam.pdf", "Energy Type": "Steam", "Account number": "002", "business_mapping_issue": "Energy source allocation: missing allocation percentages"},
            {"source_files": "electricity.json", "Energy Type": "Electricity", "business_mapping_issue": ""},
        ]),
    }
    monkeypatch.setattr(review_app, "category_paths", lambda key: {
        "silver_normalized": "normalized", "silver_manual_mapping": "manual", "silver_business_mapping": "business",
    })
    monkeypatch.setattr(review_app, "read_excel", lambda path: frames[path])
    result = review_app.curate_missing_mapping_columns(review_app.load_missing_mapping_rows("scope2", False))
    assert result["source_file"].tolist() == ["steam.pdf"]
    assert result.loc[0, "account_number"] == "002"
    assert result.loc[0, "business_mapping_issue"].startswith("Energy source allocation:")


def test_completeness_requires_every_account_and_unions_manual_ocr_dates(monkeypatch):
    import review_app as app

    base = {"division": "D", "legal_entity_name": "E", "unit": "U"}
    mapping_base = {"division": "D", "legal_entity": "E", "unit_name": "U"}
    mapping = pd.DataFrame([
        {**mapping_base, "activity_group": "Electricity", "account_number": "e1"},
        {**mapping_base, "activity_group": "Electricity", "account_number": "e2"},
        {**mapping_base, "activity_group": "Steam", "account_number": "s1",
         "effective_start_date": "2026-01-16"},
        {**mapping_base, "activity_group": "Heat", "account_number": "h1",
         "effective_start_date": "2026-02-01"},
    ])
    business_base = {"Division": "D", "Legal Entity Name": "E", "Unit": "U", "Energy Unit": "kWh",
                     "business_mapping_issue": ""}
    business = pd.DataFrame([
        {**business_base, "KPI Component": "Purchased electricity", "Account number": "e1",
         "proration_split_keys": "1|2026-01|2026-01-01|2026-01-20"},
        {**business_base, "KPI Component": "Purchased electricity", "Account number": "e1",
         "proration_split_keys": "2|2026-01|2026-01-15|2026-01-31"},
        {**business_base, "KPI Component": "Purchased electricity", "Account number": "e2",
         "business_mapping_issue": "Energy source allocation: missing",
         "proration_split_keys": "3|2026-01|2026-01-01|2026-01-31"},
        {**business_base, "KPI Component": "Purchased steam", "Account number": "s1",
         "proration_split_keys": "4|2026-01|2026-01-16|2026-01-31"},
    ])
    monkeypatch.setattr(app, "load_master_facilities", lambda: pd.DataFrame([base]))
    monkeypatch.setattr(app, "load_account_mapping_table", lambda *args: mapping)
    monkeypatch.setattr(app, "read_excel", lambda *args: business)
    result, months, count = app.build_gold_completeness("scope2", "2026-01-01", "2026-01-01")
    rows = result.set_index("kpi_component")["Jan 2026"]
    assert rows["Purchased electricity"] == {"ratio": 0.5, "covered_days": 31, "calendar_days": 62}
    assert rows["Purchased steam"] == {"ratio": 1.0, "covered_days": 16, "calendar_days": 16}
    assert pd.isna(rows["Purchased heat"]["ratio"])
    assert "Purchased cool" not in rows.index
    assert count == 1
    assert "KPI Component" in app.completeness_export_df(result, months)
    business.loc[2, "business_mapping_issue"] = ""
    result, _, _ = app.build_gold_completeness("scope2", "2026-01-01", "2026-01-01")
    assert result.set_index("kpi_component").loc["Purchased electricity", "Jan 2026"]["ratio"] == 1
    mapping.loc[3, "effective_end_date"] = "invalid"
    assert len(app.load_reporting_accounts()) == 3
    issues = app.load_reporting_accounts(include_issues=True)
    assert "effective_end_date" in issues.loc[3, "mapping_message"]


def test_energy_dashboard_pages_render_kpi_controls(monkeypatch):
    import review_app as app
    from streamlit.testing.v1 import AppTest

    monkeypatch.setattr(app, "load_reporting_accounts", lambda: pd.DataFrame([
        {"division": "D", "legal_entity_name": "E", "unit": "U", "kpi_component": "Purchased steam",
         "account_number": "s", "effective_start_date": pd.NaT, "effective_end_date": pd.NaT},
    ]))
    row = {"Division": "D", "Legal Entity Name": "E", "Unit": "U", "KPI Component": "Purchased steam",
           "Energy Unit": "kWh", "Amount of energy consumed": 720, "Consumption start date": "2026-01-01"}
    def read(path):
        if "previous" in path:
            return pd.DataFrame([
                {**row, "Amount of energy consumed": 360, "Consumption start date": "2025-01-01"},
                {**row, "Energy Unit": "mmBTU", "Consumption start date": "2025-01-01"},
            ])
        return pd.DataFrame([row, {**row, "KPI Component": ""}])
    monkeypatch.setattr(app, "read_excel_fresh", read)
    monkeypatch.setattr(app, "read_excel", lambda path: pd.DataFrame())
    monkeypatch.setattr(app, "completeness_fiscal_year_options", lambda key: [2026])
    monkeypatch.setattr(app, "fiscal_year_months", lambda year: [pd.Timestamp("2026-01-01")])
    for function in ("show_completeness_check", "show_year_over_year", "show_high_variance"):
        page = AppTest.from_string(f"import review_app as app\napp.{function}('scope2')").run()
        assert not page.exception
        assert any(widget.label == "KPI Component" for widget in page.selectbox)
        if function == "show_high_variance":
            assert page.dataframe[0].value["KPI Component"].tolist() == ["Purchased steam"]
        else:
            assert any("KPI Component" in element.value for element in page.markdown)


def test_duplicate_account_expectations_do_not_block_valid_data_or_monitoring(monkeypatch):
    import review_app as app

    master = pd.DataFrame([{"division": "D", "legal_entity_name": "E", "unit": "U"}])
    base = {"division": "D", "legal_entity": "E", "unit_name": "U", "activity_group": "Electricity"}
    mapping = pd.DataFrame([{**base, "account_number": account} for account in ("bad", "bad", "good")])
    monkeypatch.setattr(app, "load_master_facilities", lambda: master)
    monkeypatch.setattr(app, "load_account_mapping_table", lambda *args: mapping)
    monkeypatch.setattr(app, "read_excel", lambda *args: pd.DataFrame())
    assert app.load_reporting_accounts().account_number.tolist() == ["good"]
    report, months, _ = app.build_gold_completeness("scope2", "2026-01-01", "2026-01-01")
    assert len(report) == 1
    gaps = app.load_missing_mapping_rows("scope2", False)
    assert gaps.account_number.tolist() == ["bad", "bad"]
    assert gaps.mapping_message.str.contains("Duplicate").all()


def test_refresh_reports_runs_silver_then_gold_without_importing_sources(monkeypatch):
    import review_app as app

    calls = []
    def silver(**kwargs):
        calls.append(("silver", kwargs))
    def gold(**kwargs):
        calls.append(("gold", kwargs))
        return "gold.xlsx"
    monkeypatch.setattr(app, "run_silver_pipeline", silver)
    monkeypatch.setattr(app, "run_gold_pipeline", gold)
    monkeypatch.setattr(app, "clear_cached_data", lambda: calls.append(("cache", {})))
    monkeypatch.setattr(app, "run_pipeline", lambda *args: pytest.fail("Must not reimport sources"))

    assert app.refresh_reports("scope2") == (True, "gold.xlsx")
    assert [name for name, _ in calls] == ["silver", "gold", "cache"]
    assert calls[0][1] == calls[1][1] == {"config_dir": app.ROOT_DIR / "config", "invoice_type": "scope2"}


@pytest.mark.parametrize("failed_stage", ["silver", "gold"])
def test_refresh_reports_failure_stops_build_and_reloads_outputs(monkeypatch, failed_stage):
    import review_app as app

    calls = []
    def build(stage):
        calls.append(stage)
        if stage == failed_stage:
            raise PermissionError("Workbook is open")
    monkeypatch.setattr(app, "run_silver_pipeline", lambda **kwargs: build("silver"))
    monkeypatch.setattr(app, "run_gold_pipeline", lambda **kwargs: build("gold"))
    monkeypatch.setattr(app, "clear_cached_data", lambda: calls.append("cache"))

    assert app.refresh_reports("scope2") == (False, "Workbook is open")
    assert calls == (["silver", "cache"] if failed_stage == "silver" else ["silver", "gold", "cache"])


@pytest.mark.parametrize("succeeded", [True, False])
def test_report_refresh_button_and_failure_message(monkeypatch, succeeded):
    import review_app as app
    from streamlit.testing.v1 import AppTest

    calls = []
    def refresh(category):
        calls.append(category)
        return succeeded, "test output"
    monkeypatch.setattr(app, "refresh_reports", refresh)
    monkeypatch.setattr(app, "run_pipeline", lambda *args: pytest.fail("Must not reimport sources"))
    page = AppTest.from_string("import review_app as app\napp.show_page_header('scope2', 'Template Output')").run()
    page.button(key="header_refresh_reports_button").click().run()
    assert not page.exception
    assert calls == ["scope2"]
    assert any("last report refresh" in item.value for item in page.caption)
    if succeeded:
        assert any("Silver and Gold reports refreshed" in item.value for item in page.success)
    else:
        assert any("partially updated" in item.value for item in page.error)
        assert not page.success


def test_save_confirmation_survives_rerun_without_building_reports(monkeypatch):
    import review_app as app
    from streamlit.testing.v1 import AppTest

    monkeypatch.setattr(app, "run_silver_pipeline", lambda **kwargs: pytest.fail("Save must not rebuild"))
    monkeypatch.setattr(app, "run_gold_pipeline", lambda **kwargs: pytest.fail("Save must not rebuild"))
    page = AppTest.from_string(
        "import review_app as app\n"
        "import streamlit as st\n"
        "app.show_page_header('scope2', 'Data Approval')\n"
        "if st.button('Save test'):\n"
        "    app.show_saved_message('Decision saved. Refresh Reports to update reports.')\n"
    ).run()
    page.button[-1].click().run()
    assert not page.exception
    assert any("Decision saved" in item.value for item in page.success)
    page.run()
    assert not page.success


def test_field_save_reopen_and_resave_without_report_refresh(monkeypatch, tmp_path):
    import review_app as app
    from streamlit.testing.v1 import AppTest

    paths = {
        "checkpoint_dir": tmp_path,
        "decisions": tmp_path / "decisions.csv",
        "approved": tmp_path / app.APPROVED_SILVER_FILENAME,
    }
    bronze = pd.DataFrame([
        {"invoice_id": "old.json", "line_id": "1", "quantity_1": "10"},
        {"invoice_id": "new.json", "line_id": "1", "quantity_1": "20"},
    ])
    summary = pd.DataFrame([
        {"invoice_id": name, "line_id": "1", "review_required": "True"}
        for name in ("old.json", "new.json")
    ])
    issues = pd.DataFrame([{
        "issue_id": "new_quantity", "invoice_id": "new.json", "line_id": "1",
        "field_name": "quantity_1", "ocr_value": "20",
    }])
    decisions = app.update_decision(
        pd.DataFrame(), "old_quantity", "15", "CORRECTED", "Reviewer", "",
        pd.Series({"invoice_id": "old.json", "line_id": "1", "field_name": "quantity_1", "ocr_value": "10"}),
    )
    monkeypatch.setattr(app, "category_paths", lambda category: paths)
    app.save_decisions(decisions, "scope2")
    monkeypatch.setattr(app, "load_data", lambda category: (
        summary, issues, app.read_csv(str(paths["decisions"])), bronze,
    ))
    monkeypatch.setattr(app, "run_silver_pipeline", lambda **kwargs: pytest.fail("Save must not rebuild"))
    monkeypatch.setattr(app, "run_gold_pipeline", lambda **kwargs: pytest.fail("Save must not rebuild"))
    monkeypatch.setattr(app, "show_manual_override_form", lambda *args: None)
    monkeypatch.setattr(app, "show_manual_override_delete_management", lambda *args: None)
    monkeypatch.setattr(app, "show_manual_entry_delete_management", lambda *args: None)
    script = (
        "import review_app as app\n"
        "import streamlit as st\n"
        "app.show_page_header('scope2', 'Data Approval')\n"
        "summary, issues, decisions, bronze = app.load_data('scope2')\n"
        "if st.radio('Page', ['Review', 'History']) == 'Review':\n"
        "    selected = decisions[decisions.invoice_id == 'new.json']\n"
        "    app.show_review_form(issues, selected, decisions, bronze, summary, summary.iloc[1], bronze.iloc[1], 'scope2')\n"
        "else:\n"
        "    app.show_decision_management('scope2')\n"
    )
    page = AppTest.from_string(script).run()
    page.text_input(key="corrected_new_quantity").set_value("25")
    page.selectbox(key="decision_new_quantity").select("CORRECTED")
    next(button for button in page.button if button.label == "Save Field").click().run()
    assert not page.exception
    approved = app.read_csv(str(paths["approved"]))
    assert dict(zip(approved.invoice_id, approved.quantity_1)) == {"old.json": "15", "new.json": "25"}
    assert any("Saved Quantity 1" in item.value for item in page.success)

    page.radio[0].set_value("History").run()
    page.selectbox(key="scope2_reopen_issue_id").select("new_quantity")
    next(button for button in page.button if button.label == "Reopen Field").click().run()
    assert not page.exception
    assert app.read_csv(str(paths["approved"])).invoice_id.tolist() == ["old.json"]
    saved = app.read_csv(str(paths["decisions"]))
    assert saved.loc[saved.issue_id == "new_quantity", "review_decision"].iloc[0] == ""

    page.radio[0].set_value("Review").run()
    page.text_input(key="corrected_new_quantity").set_value("30")
    page.selectbox(key="decision_new_quantity").select("CORRECTED")
    next(button for button in page.button if button.label == "Save Field").click().run()
    assert not page.exception
    approved = app.read_csv(str(paths["approved"]))
    assert dict(zip(approved.invoice_id, approved.quantity_1)) == {"old.json": "15", "new.json": "30"}
