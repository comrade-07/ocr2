"""Streamlit presentation. Audit calculations and exporters never import this module."""

from collections.abc import Callable, Sequence
from functools import partial
from math import ceil
from pathlib import Path
from types import ModuleType
from typing import TypeVar

import pandas as pd
import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from src.audit.excel_export import excel_bytes
from src.audit.loader import input_paths, load_audit_data, source_fingerprint
from src.audit.models import (
    AuditData,
    AuditReport,
    FACILITY_COLUMNS,
    ReportFilters,
    ReviewNavigator,
    Settings,
    SourceFingerprint,
)
from src.audit.report import (
    build_report,
    detail_table,
    reporting_months,
    reporting_period_label,
    reporting_year,
    safe_link,
    summary_table,
)
from src.core.path_settings import category_checkpoint_output_dir

SelectionValue = TypeVar("SelectionValue")
CACHE_SCHEMA_VERSION = 6
EXPORT_SCHEMA_VERSION = 11
DETAIL_DISPLAY_COLUMNS = [
    "Index",
    "Division",
    "Legal entity",
    "Unit name",
    "KPI Component",
    "Account number",
    "Reporting month",
    "Invoice period",
    "Allocation start",
    "Allocation end",
    "Date adjustment",
    "Reason",
    "Invoice days",
    "Billed kWh",
    "Days in month",
    "Allocated kWh",
    "Source",
]
ORIGINAL_QUANTITY_COLUMNS = [
    "Index",
    "Source",
    "KPI Component",
    "Original billed quantity",
    "Original unit",
    "kWh conversion factor",
    "Data source",
    "Invoice period reference",
    "Invoice start",
    "Invoice end",
    "Date adjustment",
    "Reason",
    "Supplier",
]


@st.cache_data(show_spinner=False)
def _load(
    root: str,
    settings: Settings,
    category: str,
    fingerprint: tuple[int, SourceFingerprint],
) -> AuditData:
    # The fingerprint participates in Streamlit's cache key even though loading only needs paths.
    return load_audit_data(Path(root), settings, category)


def _select(
    label: str,
    options: Sequence[SelectionValue],
    key: str,
    container: ModuleType | DeltaGenerator = st,
    format_func: Callable[[SelectionValue], str] = str,
) -> SelectionValue:
    """Reset invalid saved choices, then render a selector preserving the option's type."""
    current_selection = st.session_state.get(key)
    if current_selection not in options:
        st.session_state.pop(key, None)
    return container.selectbox(label, options, key=key, format_func=format_func)


def _hierarchy_label(value: str | None, all_label: str) -> str:
    if value is None:
        return all_label
    if value == "":
        return "Unmapped"
    return value


def _hierarchy_filters(
    periods: pd.DataFrame, prefix: str
) -> tuple[dict[str, str | None], pd.DataFrame]:
    """Render each hierarchy level using rows remaining after the preceding selection."""
    eligible_periods = periods
    selected_values = {}
    controls = st.columns(3)
    hierarchy_fields = (
        ("division", "Division", "All divisions"),
        ("legal_entity", "Legal entity", "All legal entities"),
        ("unit_name", "Unit name", "All units"),
    )
    for control, field_config in zip(controls, hierarchy_fields):
        field_name, label, all_label = field_config
        options = [None, *sorted(eligible_periods[field_name].unique())]
        # partial binds this label immediately instead of capturing a changing loop variable.
        label_formatter = partial(_hierarchy_label, all_label=all_label)
        selected_value = _select(
            label, options, prefix + "_" + field_name, control, label_formatter
        )
        selected_values[field_name] = selected_value
        if selected_value is not None:
            eligible_periods = eligible_periods[
                eligible_periods[field_name] == selected_value
            ]
    return selected_values, eligible_periods


def _paged(frame: pd.DataFrame, prefix: str) -> pd.DataFrame:
    """Paginate the display only; the full report remains available to the exporters."""
    if frame.empty:
        st.info("No records match this selection.")
        return frame
    controls = st.columns([1, 1, 3])
    page_size = controls[0].selectbox(
        "Rows per page", [10, 25, 50], key=prefix + "_size"
    )
    page_count = ceil(len(frame) / page_size)
    selected_page = _select(
        "Page", list(range(1, page_count + 1)), prefix + "_page", controls[1]
    )
    controls[2].caption(
        f"{len(frame):,} matching records · Page {selected_page} of {page_count}"
    )
    first_row = (selected_page - 1) * page_size
    end_row = selected_page * page_size
    return frame.iloc[first_row:end_row]


def _tracked_paths(root: Path, settings: Settings, category: str) -> dict[str, Path]:
    paths = input_paths(root, settings, category)
    checkpoint_directory = category_checkpoint_output_dir(settings, category)
    if not checkpoint_directory.is_absolute():
        checkpoint_directory = root / checkpoint_directory
    for checkpoint in checkpoint_directory.glob("*.csv"):
        paths[f"checkpoint_{checkpoint.name}"] = checkpoint
    return paths


def _year_options(periods: pd.DataFrame) -> list[int]:
    dates = pd.concat([periods.start, periods.end]).dropna()
    if dates.empty:
        return [reporting_year(pd.Timestamp.today())]
    first_year = reporting_year(dates.min())
    last_year = reporting_year(dates.max())
    return list(range(last_year, first_year - 1, -1))


def _period_filters(periods: pd.DataFrame, prefix: str) -> tuple[int, int | None]:
    controls = st.columns(2)
    year = _select(
        "Reporting year", _year_options(periods), prefix + "_year", controls[0]
    )
    month_labels = {0: "All months"}
    for period in reporting_months(ReportFilters(year)):
        month_labels[period.month] = period.strftime("%B %Y")
    month = controls[1].selectbox(
        "Reporting month",
        list(month_labels),
        format_func=month_labels.__getitem__,
        key=prefix + "_month",
    )
    if month == 0:
        return year, None
    return year, month


def _additional_filters(
    periods: pd.DataFrame, prefix: str
) -> tuple[str | None, str | None]:
    with st.expander("More report filters"):
        controls = st.columns(2)
        account_options = ["All accounts", *sorted(periods.account.unique())]
        account = _select(
            "Account number", account_options, prefix + "_account", controls[0]
        )
        source_options = ["All included entries", "Reviewed OCR", "Manual entry"]
        source = _select("Data source", source_options, prefix + "_source", controls[1])
    if account == "All accounts":
        account = None
    if source == "All included entries":
        source = None
    return account, source


def _report_filters(periods: pd.DataFrame, prefix: str) -> ReportFilters:
    hierarchy, eligible_periods = _hierarchy_filters(periods, prefix)
    year, month = _period_filters(periods, prefix)
    component = _select("KPI Component", ["All energy KPIs", *sorted(eligible_periods.kpi_component.unique())],
                        prefix + "_kpi", st)
    if component != "All energy KPIs":
        eligible_periods = eligible_periods.loc[eligible_periods.kpi_component == component]
    account, source = _additional_filters(eligible_periods, prefix)
    year_label = reporting_period_label(ReportFilters(year))
    st.caption(f"Reporting year {year}: {year_label}")
    return ReportFilters(
        year=year,
        month=month,
        kpi_component=None if component == "All energy KPIs" else component,
        account=account,
        source=source,
        division=hierarchy["division"],
        legal_entity=hierarchy["legal_entity"],
        unit_name=hierarchy["unit_name"],
    )


def _show_metrics(report: AuditReport) -> None:
    metrics = st.columns(3)
    total_quantity = report.details.allocated_kwh.sum(min_count=1)
    if pd.notna(total_quantity):
        total_label = f"{total_quantity:,.2f}"
    else:
        total_label = "Unavailable"
    if report.details.kpi_component.nunique() <= 1:
        metrics[0].metric("Allocated kWh", total_label)
    else:
        for component, rows in report.details.groupby("kpi_component"):
            quantity = rows.allocated_kwh.sum(min_count=1)
            metrics[0].metric(component + " (kWh)", f"{quantity:,.2f}" if pd.notna(quantity) else "Unavailable")
    metrics[1].metric("Invoice periods in detail", report.details.period_id.nunique())
    metrics[2].metric("Cases needing review", len(report.cases))
    if report.details.allocated_kwh.isna().any():
        st.warning(
            "The kWh total is partial: some quantities could not be converted or calculated. See Checks & exceptions."
        )
    st.caption(
        "Allocated kWh = billed kWh ÷ invoice days × days in month. "
        "Invoice days count effective allocation dates inclusively. "
        "Previous invoice pattern means the treatment is rechecked when the next invoice arrives. "
        "Billed kWh repeats across months; only allocated kWh should be totalled."
    )


def _date_label(value: pd.Timestamp) -> str:
    if pd.isna(value):
        return "Unknown"
    return value.strftime("%Y-%m-%d")


def _link_or_none(value: object) -> str | None:
    if safe_link(value):
        return str(value)
    return None


def _detail_frames(report: AuditReport) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Prepare the compact view alongside the full original-quantity display."""
    full_details = detail_table(report)
    billing_period_labels = []
    for start_date, end_date in zip(
        full_details["Invoice start"], full_details["Invoice end"]
    ):
        billing_period_labels.append(
            _date_label(start_date) + " to " + _date_label(end_date)
        )
    full_details["Invoice period"] = billing_period_labels
    compact_details = full_details[DETAIL_DISPLAY_COLUMNS].copy()
    if report.filters.month is not None:
        compact_details = compact_details.drop(columns="Reporting month")
    return full_details, compact_details


def _show_details(report: AuditReport, prefix: str) -> None:
    full_details, compact_details = _detail_frames(report)
    displayed_rows = _paged(compact_details, prefix + "_details").copy()
    if not displayed_rows["Source"].map(safe_link).all():
        st.caption("Rows with a blank Source have no usable SharePoint link.")
    displayed_rows["Source"] = displayed_rows["Source"].map(_link_or_none)
    source_column = st.column_config.LinkColumn(
        "Source", display_text="Open SharePoint document"
    )
    st.dataframe(
        displayed_rows,
        hide_index=True,
        use_container_width=True,
        column_config={"Source": source_column},
    )
    with st.expander("Original billed quantities and invoice references"):
        original_quantities = full_details.loc[
            displayed_rows.index, ORIGINAL_QUANTITY_COLUMNS
        ]
        st.dataframe(original_quantities, hide_index=True, use_container_width=True)


def _case_filters(cases: pd.DataFrame, prefix: str) -> pd.DataFrame:
    """Filter the browsing queue independently from the report's export scope."""
    controls = st.columns(2)
    issue = _select(
        "Issue type",
        ["All issues", *sorted(cases.issue.unique())],
        prefix + "_issue",
        controls[0],
    )
    account = _select(
        "Case account",
        ["All accounts", *sorted(cases.account.unique())],
        prefix + "_case_account",
        controls[1],
    )
    search_text = st.text_input(
        "Search account or SharePoint link", key=prefix + "_case_search"
    ).strip()
    matching_cases = cases.copy()
    if issue != "All issues":
        matching_cases = matching_cases[matching_cases.issue == issue]
    if account != "All accounts":
        matching_cases = matching_cases[matching_cases.account == account]
    if search_text != "":
        account_matches = matching_cases.account.str.contains(
            search_text, case=False, regex=False
        )
        link_text = matching_cases.source_links.map(" ".join)
        link_matches = link_text.str.contains(search_text, case=False, regex=False)
        matches_search = account_matches | link_matches
        matching_cases = matching_cases[matches_search]
    order = _select(
        "Sort cases by", ["Division", "Reporting month", "Issue"], prefix + "_case_sort"
    )
    selected_sort_column = {
        "Division": "division",
        "Reporting month": "month",
        "Issue": "issue",
    }[order]
    sort_columns = [selected_sort_column]
    for column in [*FACILITY_COLUMNS, "kpi_component", "case_id"]:
        if column not in sort_columns:
            sort_columns.append(column)
    return matching_cases.sort_values(sort_columns, kind="stable")


def _show_case_evidence(case: pd.Series, data: AuditData) -> pd.DataFrame:
    """Show full billing history for the selected case, retaining out-of-scope months."""
    matching_periods = data.periods.period_id.isin(case.period_ids)
    periods = data.periods[matching_periods]
    columns = [
        "source_link",
        "printed_start",
        "printed_end",
        "start",
        "end",
        "date_resolution",
        "date_adjustment",
        "billed_original",
        "original_unit",
        "source",
    ]
    st.dataframe(periods[columns], hide_index=True, use_container_width=True)
    matching_allocations = data.allocations.period_id.isin(case.period_ids)
    allocations = data.allocations[matching_allocations]
    st.caption(
        "Full invoice allocation history, including months outside the report selection"
    )
    allocation_columns = ["source_link", "month", "days", "month_days", "allocated_kwh"]
    st.dataframe(
        allocations[allocation_columns], hide_index=True, use_container_width=True
    )
    for period in periods.itertuples():
        if safe_link(period.source_link):
            st.link_button("Open SharePoint document", period.source_link)
    return periods


def _show_review_navigation(
    periods: pd.DataFrame, prefix: str, open_review: ReviewNavigator | None
) -> None:
    if open_review is None:
        return
    if periods.empty:
        return
    selected_id = _select(
        "Invoice to review", periods.period_id.tolist(), prefix + "_review_period"
    )
    selected_period = periods[periods.period_id == selected_id].iloc[0]
    source_label = selected_period.source_link
    if source_label == "":
        source_label = "SharePoint link unavailable"
    st.caption(f"{source_label} · {selected_period.source}")
    if st.button("Go to invoice review", key=prefix + "_go_review"):
        open_review(
            selected_period.source, selected_period.invoice_id, selected_period.line_id
        )


def _show_cases(
    report: AuditReport,
    data: AuditData,
    prefix: str,
    open_review: ReviewNavigator | None,
) -> None:
    """Render counts, queue filters, one page, and the selected case's evidence."""
    cases = report.cases.copy()
    affected_unit_count = len(cases[FACILITY_COLUMNS].drop_duplicates())
    st.caption(
        f"{len(cases)} cases · {affected_unit_count} units affected. Cases are recalculated from the current inputs; acknowledgements are not stored."
    )
    if cases.empty:
        st.success(
            "No exceptions detected for these filters. This does not certify that every invoice was supplied."
        )
        return
    matching_cases = _case_filters(cases, prefix)
    displayed_cases = _paged(matching_cases, prefix + "_cases")
    if displayed_cases.empty:
        return
    columns = ["case_id", *FACILITY_COLUMNS, "account", "month", "issue"]
    labels = {
        "case_id": "Case",
        "division": "Division",
        "legal_entity": "Legal entity",
        "unit_name": "Unit name",
        "account": "Account number",
        "month": "Reporting month",
        "issue": "Issue",
    }
    st.dataframe(
        displayed_cases[columns].rename(columns=labels),
        hide_index=True,
        use_container_width=True,
    )
    selected_id = _select(
        "View case", displayed_cases.case_id.tolist(), prefix + "_chosen_case"
    )
    selected_case = displayed_cases[displayed_cases.case_id == selected_id].iloc[0]
    with st.container(border=True):
        st.subheader(selected_case.issue)
        st.write(selected_case.explanation)
        st.write("Next step: " + selected_case.next_step)
        periods = _show_case_evidence(selected_case, data)
        _show_review_navigation(periods, prefix, open_review)


def _export_payload(report: AuditReport, format_name: str, include: str) -> bytes:
    if format_name == "Excel":
        return excel_bytes(report, include)
    # Keep PDF dependency optional for users who only need screen/Excel reports.
    from src.audit.pdf_export import pdf_bytes

    return pdf_bytes(report, include)


def _show_download(
    payload: bytes, report: AuditReport, format_name: str, prefix: str
) -> None:
    if format_name == "Excel":
        extension = "xlsx"
        mime_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        extension = "pdf"
        mime_type = "application/pdf"
    if report.filters.month is None:
        month_label = "all"
    else:
        month_label = str(report.filters.month)
    filename = f"scope2_audit_{report.filters.year}_{month_label}.{extension}"
    st.download_button(
        "Download " + format_name,
        payload,
        file_name=filename,
        mime=mime_type,
        key=prefix + "_download_button",
    )


def _show_export(
    report: AuditReport, tracked_paths: dict[str, Path], prefix: str
) -> None:
    """Generate on demand and hide saved downloads whenever inputs or options change."""
    st.subheader("Export report")
    controls = st.columns([1, 2])
    format_name = controls[0].selectbox(
        "Format", ["Excel", "PDF"], key=prefix + "_format"
    )
    include = controls[1].selectbox(
        "Include",
        ["Full report", "Summary and details", "Summary"],
        key=prefix + "_include",
    )
    st.caption(
        "Export uses all records matching the report filters. Exception search, queue filters, and pagination do not change the export."
    )
    token = repr(
        (
            EXPORT_SCHEMA_VERSION,
            source_fingerprint(tracked_paths),
            report.filters,
            format_name,
            include,
        )
    )
    export_disabled = len(report.warnings) > 0
    prepare_requested = st.button(
        "Prepare download", key=prefix + "_prepare", disabled=export_disabled
    )
    if prepare_requested:
        try:
            payload = _export_payload(report, format_name, include)
        except ImportError:
            st.error(
                "PDF export requires ReportLab. Install the updated requirements.txt in the app environment."
            )
        else:
            st.session_state[prefix + "_download"] = (token, payload)
    saved_download = st.session_state.get(prefix + "_download")
    if saved_download is None:
        return
    saved_token, saved_payload = saved_download
    if saved_token != token:
        return
    _show_download(saved_payload, report, format_name, prefix)


def show_audit_report(
    category: str,
    root: str | Path,
    settings: Settings,
    open_review: ReviewNavigator | None = None,
) -> None:
    """Load inputs, collect filters, build one report, and dispatch its selected view."""
    if category != "scope2":
        st.info(
            "Allocation reports currently support Scope 2 purchased energy. Other categories use different quantities and reporting rules."
        )
        return
    prefix = "audit_" + category
    tracked_paths = _tracked_paths(Path(root), settings, category)
    try:
        fingerprint = (CACHE_SCHEMA_VERSION, source_fingerprint(tracked_paths))
        audit_data = _load(str(root), settings, category, fingerprint)
    except (ValueError, OSError, KeyError) as error:
        st.warning(f"Report unavailable. {error}")
        return
    st.caption(
        "Read-only verification of reviewed OCR and completed manual entries. Corrections remain in the review workflow."
    )
    if audit_data.periods.empty:
        st.info(
            "No reviewed invoice periods are available. No data is different from zero consumption."
        )
        return
    for warning in audit_data.warnings:
        st.warning(warning)
    if audit_data.periods.kpi_component.eq("Unclassified").any():
        st.warning("Some older inputs have no valid activity_group. They remain Unclassified; update the shared mapping and rebuild Silver.")
    filters = _report_filters(audit_data.periods, prefix)
    report = build_report(audit_data, filters)
    _show_metrics(report)
    view = st.radio(
        "Report view",
        ["Calculation details", "Facility summary", "Checks & exceptions"],
        horizontal=True,
        key=prefix + "_view",
    )
    if view == "Calculation details":
        _show_details(report, prefix)
    elif view == "Facility summary":
        st.dataframe(summary_table(report), hide_index=True, use_container_width=True)
    else:
        _show_cases(report, audit_data, prefix, open_review)
    with st.expander("Report inputs"):
        st.dataframe(
            pd.DataFrame(report.sources), hide_index=True, use_container_width=True
        )
    _show_export(report, tracked_paths, prefix)
