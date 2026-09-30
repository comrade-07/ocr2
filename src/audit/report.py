"""Prepare a single, consistently scoped report for the screen and exporters."""

from datetime import date, datetime
from dataclasses import replace
from urllib.parse import urlparse

import pandas as pd

from src.audit.checks import check_allocations
from src.audit.models import AuditData, AuditReport, ReportFilters, FACILITY_COLUMNS

DETAIL_COLUMNS = {
    "division": "Division",
    "legal_entity": "Legal entity",
    "unit_name": "Unit name",
    "kpi_component": "KPI Component",
    "account": "Account number",
    "month": "Reporting month",
    "supplier": "Supplier",
    "printed_start": "Invoice start",
    "printed_end": "Invoice end",
    "start": "Allocation start",
    "end": "Allocation end",
    "date_adjustment": "Date adjustment",
    "date_resolution": "Reason",
    "days": "Invoice days",
    "billed_original": "Original billed quantity",
    "original_unit": "Original unit",
    "factor": "kWh conversion factor",
    "billed_kwh": "Billed kWh",
    "month_days": "Days in month",
    "allocated_kwh": "Allocated kWh",
    "source_link": "Source",
    "source": "Data source",
    "period_id": "Invoice period reference",
}
SUMMARY_COLUMNS = {
    "division": "Division",
    "legal_entity": "Legal entity",
    "unit_name": "Unit name",
    "kpi_component": "KPI Component",
    "accounts": "Accounts",
    "month": "Reporting month",
    "allocated_kwh": "Allocated kWh",
    "invoice_periods": "Invoice periods",
    "excluded_quantities": "Quantities excluded from kWh total",
}
CASE_DISPLAY_COLUMNS = {
    "case_id": "Case",
    "issue": "Issue",
    "division": "Division",
    "legal_entity": "Legal entity",
    "unit_name": "Unit name",
    "kpi_component": "KPI Component",
    "account": "Account number",
    "month": "Reporting month",
    "status": "Status",
    "explanation": "Explanation",
    "next_step": "Next step",
}
MONTH_SPECIFIC_ISSUES = {
    "Missing coverage",
    "Overlapping billing periods",
    "Allocation calculation",
}
MISSING_SOURCE_LABEL = "SharePoint link unavailable"


def safe_link(value: object) -> bool:
    if not isinstance(value, str):
        return False
    scheme = urlparse(value).scheme.lower()
    return scheme in {"https", "http"}


def source_label(value: object) -> str:
    if safe_link(value):
        return str(value)
    return MISSING_SOURCE_LABEL


def scope_rows(frame: pd.DataFrame, filters: ReportFilters) -> pd.DataFrame:
    """Apply each selected hierarchy/account/source constraint to a new frame."""
    scoped_rows = frame.copy()
    filter_fields = (
        "facility",
        "division",
        "legal_entity",
        "unit_name",
        "kpi_component",
        "account",
        "source",
    )
    for field in filter_fields:
        selected_value = getattr(filters, field)
        if selected_value is None:
            continue
        matches_selection = scoped_rows[field] == selected_value
        scoped_rows = scoped_rows.loc[matches_selection]
    return scoped_rows


def reporting_months(filters: ReportFilters) -> list[pd.Period]:
    """Validate the month and construct calendar months in December–November order."""
    if filters.month is None:
        month_numbers = [12, *range(1, 12)]
    else:
        if filters.month < 1 or filters.month > 12:
            raise ValueError("Month must be between January and December.")
        month_numbers = [filters.month]
    months = []
    for month_number in month_numbers:
        if month_number == 12:
            calendar_year = filters.year - 1
        else:
            calendar_year = filters.year
        months.append(pd.Period(year=calendar_year, month=month_number, freq="M"))
    return months


def reporting_year(value: str | date | datetime | pd.Timestamp) -> int:
    calendar_date = pd.Timestamp(value)
    if calendar_date.month == 12:
        return calendar_date.year + 1
    return calendar_date.year


def reporting_period_label(filters: ReportFilters) -> str:
    months = reporting_months(filters)
    start_date = months[0].start_time
    end_date = months[-1].end_time
    return f"{start_date:%d %B %Y} to {end_date:%d %B %Y}"


def _relevant_period_ids(periods: pd.DataFrame, months: list[pd.Period]) -> set[str]:
    """Keep overlapping bills plus unknown dates so invalid records cannot disappear."""
    report_start = months[0].start_time
    report_end = months[-1].end_time
    missing_start = periods.start.isna()
    missing_end = periods.end.isna()
    dates_unknown = missing_start | missing_end | (periods.end < periods.start)
    starts_before_report_end = periods.start <= report_end
    ends_after_report_start = periods.end >= report_start
    overlaps_report = starts_before_report_end & ends_after_report_start
    relevant_rows = dates_unknown | overlaps_report
    return set(periods.loc[relevant_rows, "period_id"])


def _scope_cases(
    cases: pd.DataFrame, periods: pd.DataFrame, months: list[pd.Period]
) -> pd.DataFrame:
    """Select month-specific findings by month and invoice findings by parent period."""
    month_names = set()
    for month in months:
        month_names.add(str(month))
    relevant_period_ids = _relevant_period_ids(periods, months)
    selected_indices = []
    for case_index, case in cases.iterrows():
        if case.issue in MONTH_SPECIFIC_ISSUES:
            include_case = case.month in month_names
        else:
            matching_period_ids = set(case.period_ids).intersection(relevant_period_ids)
            include_case = len(matching_period_ids) > 0
        if include_case:
            selected_indices.append(case_index)
    scoped_cases = cases.loc[selected_indices].copy()
    sort_columns = [*FACILITY_COLUMNS, "kpi_component", "account", "month", "issue", "case_id"]
    scoped_cases = scoped_cases.sort_values(sort_columns, kind="stable")
    return scoped_cases.reset_index(drop=True)


def _sum_available(values: pd.Series) -> float:
    # min_count prevents an entirely unavailable group from looking like zero use.
    return values.sum(min_count=1)


def _count_unavailable(values: pd.Series) -> int:
    return int(values.isna().sum())


def _build_summary(details: pd.DataFrame) -> pd.DataFrame:
    """Aggregate within the exact hierarchy/month; named aggregations declare each measure."""
    grouping_columns = [*FACILITY_COLUMNS, "kpi_component", "month"]
    grouped_details = details.groupby(grouping_columns, dropna=False, sort=True)
    summary = grouped_details.agg(
        accounts=("account", "nunique"),
        allocated_kwh=("allocated_kwh", _sum_available),
        invoice_periods=("period_id", "nunique"),
        excluded_quantities=("allocated_kwh", _count_unavailable),
    )
    return summary.reset_index()


def build_report(data: AuditData, filters: ReportFilters) -> AuditReport:
    """Scope entities, check full invoices, then restrict displayed months and summarize."""
    months = reporting_months(filters)
    periods = scope_rows(data.periods, filters)
    allocations = scope_rows(data.allocations, filters)
    # Check before month filtering: a bill can extend outside the reporting year.
    all_cases = check_allocations(periods, allocations, months)
    cases = _scope_cases(all_cases, periods, months)
    month_names = []
    for month in months:
        month_names.append(str(month))
    selected_months = allocations.month.isin(month_names)
    details = allocations.loc[selected_months].copy()
    sort_columns = [*FACILITY_COLUMNS, "kpi_component", "account", "month", "start", "period_id"]
    details = details.sort_values(sort_columns, kind="stable").reset_index(drop=True)
    summary = _build_summary(details)
    return AuditReport(
        filters=filters,
        details=details,
        summary=summary,
        cases=cases,
        sources=data.sources,
        warnings=data.warnings,
    )


def detail_table(report: AuditReport) -> pd.DataFrame:
    details = report.details.reindex(columns=DETAIL_COLUMNS).copy()
    details = details.rename(columns=DETAIL_COLUMNS)
    details.insert(0, "Index", range(1, len(details) + 1))
    details["Source"] = details["Source"].map(source_label)
    return details


def summary_table(report: AuditReport) -> pd.DataFrame:
    return report.summary.rename(columns=SUMMARY_COLUMNS)


def cases_table(report: AuditReport) -> pd.DataFrame:
    """Expand each case's valid document links into separate, clickable source columns."""
    internal_columns = ["period_ids", "facility", "source_files", "source_links"]
    display_cases = report.cases.drop(columns=internal_columns).rename(
        columns=CASE_DISPLAY_COLUMNS
    )
    links_by_case = []
    maximum_sources = 1
    for source_links in report.cases.source_links:
        valid_links = []
        for link in source_links:
            if safe_link(link):
                valid_links.append(link)
        links_by_case.append(valid_links)
        maximum_sources = max(maximum_sources, len(valid_links))
    for source_index in range(maximum_sources):
        column_values = []
        for valid_links in links_by_case:
            if source_index < len(valid_links):
                source_value = valid_links[source_index]
            elif len(valid_links) == 0 and source_index == 0:
                source_value = MISSING_SOURCE_LABEL
            else:
                source_value = ""
            column_values.append(source_value)
        display_cases[f"Source {source_index + 1}"] = column_values
    return display_cases


def report_description(report: AuditReport) -> str:
    """Describe selected entities and the actual calendar dates used by both exports."""
    filters = report.filters
    hierarchy_labels = []
    hierarchy_fields = (
        ("Division", filters.division, "All divisions"),
        ("Legal entity", filters.legal_entity, "All legal entities"),
        ("Unit name", filters.unit_name, "All units"),
        ("KPI Component", filters.kpi_component, "All energy KPIs"),
    )
    for label, selected_value, all_label in hierarchy_fields:
        if selected_value is None:
            hierarchy_labels.append(all_label)
        elif selected_value == "":
            hierarchy_labels.append(f"{label}: Unmapped")
        else:
            hierarchy_labels.append(f"{label}: {selected_value}")
    if filters.facility is not None:
        hierarchy_labels.insert(0, filters.facility)
    if filters.account is None or filters.account == "":
        account_label = "All accounts"
    else:
        account_label = filters.account
    if filters.source is None or filters.source == "":
        source_description = "All included entries"
    else:
        source_description = filters.source
    hierarchy = " | ".join(hierarchy_labels)
    period_label = reporting_period_label(filters)
    return f"{hierarchy} | Reporting year {filters.year}: {period_label} | {account_label} | {source_description}"


def reports_by_kpi(report: AuditReport) -> list[tuple[str, AuditReport]]:
    components = sorted(set(report.details.kpi_component) | set(report.cases.kpi_component))
    if not components:
        return [("Unclassified", report)]
    return [
        (component, replace(
            report,
            filters=replace(report.filters, kpi_component=component),
            details=report.details.loc[report.details.kpi_component == component],
            summary=report.summary.loc[report.summary.kpi_component == component],
            cases=report.cases.loc[report.cases.kpi_component == component],
        ))
        for component in components
    ]
