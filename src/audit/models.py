from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, TypeAlias

import pandas as pd

# YAML settings and DataFrame rows are heterogeneous at their input boundaries.
AuditRecord: TypeAlias = dict[str, Any]
Settings: TypeAlias = dict[str, Any]
SourceMetadata: TypeAlias = dict[str, str]
FileFingerprint: TypeAlias = tuple[str, str, int | None, int | None]
SourceFingerprint: TypeAlias = tuple[FileFingerprint, ...]
ReviewNavigator: TypeAlias = Callable[[str, str, str], None]


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ReportFilters:
    """Year ending in November; month 12 selects December of the prior calendar year."""

    year: int
    month: int | None = None
    facility: str | None = None
    account: str | None = None
    source: str | None = None
    division: str | None = None
    legal_entity: str | None = None
    unit_name: str | None = None
    kpi_component: str | None = None


@dataclass
class AuditData:
    periods: pd.DataFrame
    allocations: pd.DataFrame
    sources: list[SourceMetadata] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class AuditReport:
    filters: ReportFilters
    details: pd.DataFrame
    summary: pd.DataFrame
    cases: pd.DataFrame
    sources: list[SourceMetadata]
    warnings: list[str]
    generated_at: str = field(default_factory=utc_timestamp)


FACILITY_COLUMNS = ["division", "legal_entity", "unit_name"]
CASE_COLUMNS = [
    "case_id",
    "issue",
    "facility",
    *FACILITY_COLUMNS,
    "kpi_component",
    "account",
    "month",
    "status",
    "explanation",
    "next_step",
    "period_ids",
    "source_files",
    "source_links",
]
