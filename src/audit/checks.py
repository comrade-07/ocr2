"""Independent allocation checks. Findings never modify the audited quantities."""

import math

import pandas as pd

from src.audit.loader import stable_id
from src.audit.models import AuditRecord, CASE_COLUMNS, FACILITY_COLUMNS

TOLERANCE_KWH = 0.01


def _different(left: float, right: float, factor: float = 1) -> bool:
    if pd.isna(factor):
        effective_factor = 1
    else:
        effective_factor = factor
    tolerance = TOLERANCE_KWH / effective_factor
    if pd.isna(left):
        return True
    if pd.isna(right):
        return True
    return not math.isclose(left, right, abs_tol=tolerance, rel_tol=1e-10)


class _CaseCollector:
    """Construct consistent case identities and source references for every check."""

    def __init__(self) -> None:
        self.records: list[AuditRecord] = []

    def add(
        self,
        issue: str,
        periods: pd.DataFrame,
        month: str,
        explanation: str,
        next_step: str,
    ) -> None:
        first_period = periods.iloc[0]
        period_ids = tuple(sorted(set(periods.period_id)))
        source_files = "; ".join(sorted(set(periods.source_file)))
        source_links = set()
        for link in periods.source_link:
            cleaned_link = str(link).strip()
            if cleaned_link != "":
                source_links.add(cleaned_link)
        case = {
            "case_id": "A-" + stable_id(issue, period_ids, month)[:10],
            "issue": issue,
            "facility": first_period.facility,
            "kpi_component": first_period.kpi_component,
            "account": first_period.account,
            "month": month,
            "status": "Needs review",
            "explanation": explanation,
            "next_step": next_step,
            "period_ids": period_ids,
            "source_files": source_files,
            "source_links": tuple(sorted(source_links)),
        }
        for column in FACILITY_COLUMNS:
            case[column] = first_period[column]
        self.records.append(case)

    def to_frame(self) -> pd.DataFrame:
        cases = pd.DataFrame(self.records, columns=CASE_COLUMNS)
        return cases.drop_duplicates("case_id")


def _valid_billing_dates(period: pd.Series) -> bool:
    if pd.isna(period.start):
        return False
    if pd.isna(period.end):
        return False
    return period.end >= period.start


def _period_label(period: pd.Series) -> str:
    if pd.isna(period.start):
        return "Unknown period"
    return period.start.strftime("%Y-%m")


def _check_invoice_inputs(
    period: pd.Series, records: pd.DataFrame, cases: _CaseCollector
) -> bool:
    """Record input problems and report whether dates/quantity permit arithmetic checks."""
    label = _period_label(period)
    mapping_missing = not period.mapped
    account_missing = period.account == ""
    if mapping_missing or account_missing:
        cases.add(
            "Missing mapping",
            records,
            label,
            "Facility hierarchy or account number is missing, or the account mapping is unresolved.",
            "Check the account mapping and rebuild Silver.",
        )
    valid_dates = _valid_billing_dates(period)
    quantity_missing = pd.isna(period.billed_original)
    if not valid_dates or quantity_missing:
        cases.add(
            "Invalid invoice inputs",
            records,
            label,
            "Billing dates are missing/reversed or the billed quantity is not numeric.",
            "Open the invoice review and correct the source fields.",
        )
    if pd.isna(period.factor):
        unit_label = period.original_unit
        if unit_label == "":
            unit_label = "Blank"
        cases.add(
            "Unsupported energy unit",
            records,
            label,
            f"'{unit_label}' cannot be reported as kWh. This quantity is excluded from kWh totals.",
            "Verify the billed unit and its mapping.",
        )
    if not valid_dates:
        return False
    if quantity_missing:
        return False
    return True


def _check_invoice_reconciliation(
    period: pd.Series,
    records: pd.DataFrame,
    allocations: pd.DataFrame,
    cases: _CaseCollector,
) -> None:
    """Compare full-period totals and expected month membership before report filtering."""
    label = _period_label(period)
    allocated_total = allocations.allocated_original.sum(min_count=1)
    total_differs = _different(allocated_total, period.billed_original, period.factor)
    if allocations.empty or total_differs:
        cases.add(
            "Invoice reconciliation",
            records,
            label,
            "Allocations across the full billing period do not equal the billed quantity, or are absent.",
            "Inspect all months for this invoice and rebuild Silver after correction.",
        )
    expected_months = pd.period_range(period.start, period.end, freq="M")
    expected_names = set()
    for month in expected_months:
        expected_names.add(str(month))
    month_membership_differs = set(allocations.month) != expected_names
    allocation_count_differs = len(allocations) != len(expected_names)
    if month_membership_differs or allocation_count_differs:
        cases.add(
            "Missing or repeated allocation",
            records,
            label,
            "Expected one allocation per billing period per calendar month; a month is missing, duplicated, or unexpected.",
            "Inspect the invoice's full allocation history and rebuild Silver.",
        )


def _check_monthly_allocation(
    period: pd.Series,
    records: pd.DataFrame,
    allocation: pd.Series,
    cases: _CaseCollector,
) -> None:
    """Recompute expected interval/day counts and compare them with the stored split."""
    try:
        allocation_month = pd.Period(allocation.month, freq="M")
    except (ValueError, TypeError):
        cases.add(
            "Invalid allocation month",
            records,
            _period_label(period),
            "An allocation has no valid reporting month.",
            "Correct dates and rebuild Silver.",
        )
        return
    expected_start = max(period.start, allocation_month.start_time)
    expected_end = min(period.end, allocation_month.end_time.normalize())
    expected_month_days = max(0, (expected_end - expected_start).days + 1)
    billing_days = (period.end - period.start).days + 1
    expected_quantity = period.billed_original / billing_days * expected_month_days
    mismatch = False
    comparisons = (
        (allocation.days, billing_days),
        (allocation.month_days, expected_month_days),
        (allocation.segment_start, expected_start),
        (allocation.segment_end, expected_end),
    )
    for recorded_value, expected_value in comparisons:
        if recorded_value != expected_value:
            mismatch = True
            break
    if _different(allocation.allocated_original, expected_quantity, period.factor):
        mismatch = True
    if mismatch:
        explanation = (
            f"Expected {expected_month_days} month days / {billing_days} invoice days "
            f"× {period.billed_original:,.6g} {period.original_unit} = {expected_quantity:,.6g} {period.original_unit}."
        )
        cases.add(
            "Allocation calculation",
            records,
            allocation.month,
            explanation,
            "Compare the billing dates, day counts, and allocated quantity with the invoice.",
        )


def _coverage_days(periods: pd.DataFrame, month: pd.Period) -> tuple[int, int]:
    """Use sets to count distinct covered days and overlapping days only once."""
    month_start = month.start_time
    month_end = month.end_time.normalize()
    covered_days: set[pd.Timestamp] = set()
    overlapping_days: set[pd.Timestamp] = set()
    for period in periods.itertuples():
        interval_start = max(period.start, month_start)
        interval_end = min(period.end, month_end)
        interval_days = set(pd.date_range(interval_start, interval_end))
        overlapping_days.update(covered_days.intersection(interval_days))
        covered_days.update(interval_days)
    return len(covered_days), len(overlapping_days)


def _check_coverage(
    periods: pd.DataFrame, months: list[pd.Period], cases: _CaseCollector
) -> None:
    """Check each billing sequence using resolved allocation dates."""
    grouped_periods = periods.groupby(
        [*FACILITY_COLUMNS, "kpi_component", "account", "supplier"], sort=True, dropna=False
    )
    for group_key, account_periods in grouped_periods:
        has_start = account_periods.start.notna()
        has_end = account_periods.end.notna()
        ordered_dates = account_periods.end >= account_periods.start
        valid_rows = has_start & has_end
        valid_rows = valid_rows & ordered_dates
        valid_periods = account_periods.loc[valid_rows]
        if valid_periods.empty:
            continue
        for month in months:
            starts_before_month_end = valid_periods.start <= month.end_time.normalize()
            ends_after_month_start = valid_periods.end >= month.start_time
            overlaps_month = starts_before_month_end & ends_after_month_start
            relevant_periods = valid_periods.loc[overlaps_month]
            covered_count, overlap_count = _coverage_days(relevant_periods, month)
            calendar_days = month.days_in_month
            missing_count = calendar_days - covered_count
            if missing_count > 0:
                if relevant_periods.empty:
                    evidence_periods = account_periods
                else:
                    evidence_periods = relevant_periods
                cases.add(
                    "Missing coverage",
                    evidence_periods,
                    str(month),
                    f"{missing_count} of {calendar_days} calendar days have no invoice coverage. Confirm whether the account was active during this month.",
                    "Check for another invoice, or confirm that no consumption was expected.",
                )
            if overlap_count > 0:
                cases.add(
                    "Overlapping billing periods",
                    relevant_periods,
                    str(month),
                    f"{overlap_count} calendar days occur in more than one billing period. Overlap may be legitimate for separate meters.",
                    "Compare the source invoices; do not remove a bill solely because dates overlap.",
                )


def check_allocations(
    periods: pd.DataFrame, allocations: pd.DataFrame, months: list[pd.Period]
) -> pd.DataFrame:
    """Run input, full-invoice, monthly arithmetic, and coverage checks in order."""
    cases = _CaseCollector()
    # Index once instead of scanning all allocations for every invoice period.
    allocations_by_period = {}
    for period_id, period_allocations in allocations.groupby("period_id", sort=False):
        allocations_by_period[period_id] = period_allocations
    empty_allocations = allocations.iloc[0:0]
    for period_index, period in periods.iterrows():
        records = periods.loc[[period_index]]
        period_allocations = allocations_by_period.get(
            period.period_id, empty_allocations
        )
        if not _check_invoice_inputs(period, records, cases):
            continue
        _check_invoice_reconciliation(period, records, period_allocations, cases)
        for allocation_index, allocation in period_allocations.iterrows():
            _check_monthly_allocation(period, records, allocation, cases)
    _check_coverage(periods, months, cases)
    return cases.to_frame()
