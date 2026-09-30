"""Read pipeline workbooks and translate their schema into audit records."""

from datetime import datetime, timezone
import hashlib
import math
from pathlib import Path

import pandas as pd

from src.audit.models import (
    AuditData,
    AuditRecord,
    FACILITY_COLUMNS,
    Settings,
    SourceFingerprint,
    SourceMetadata,
)
from src.core.path_settings import (
    category_checkpoint_output_dir,
    silver_excel_output_dir,
)
from src.pipeline.run_silver_pipeline import (
    DATE_RESOLUTION_FIELDS,
    _effective_consumption_quantity_unit,
    build_silver_proration_calculation,
    silver_output_filename,
)
from src.transform.account_mapping import SCOPE2_ACTIVITY_GROUPS
from src.transform.unit_conversion import kwh_conversion_factor

INPUT_LAYERS = (
    "aggregated",
    "proration_split",
    "manual_mapping",
    "manual_proration_split",
)
SOURCE_FLOWS = (
    ("Reviewed OCR", "aggregated", "proration_split"),
    ("Manual entry", "manual_mapping", "manual_proration_split"),
)
REQUIRED_INPUT_COLUMNS = (
    "account_number",
    "source_file",
    "aggregated_quantity_1",
    "consumption_start_date_1_normalized",
    "consumption_end_date_1_normalized",
)
REQUIRED_SPLIT_COLUMNS = (
    "proration_source_row_id",
    "proration_period_index",
    "quantity_proration",
    "date_month_proration",
    "date_split_start_proration",
    "date_split_end_proration",
    "date_split_days_proration",
    "date_total_days_proration",
    *[f"date_{field}_proration" for field in DATE_RESOLUTION_FIELDS],
)
PERIOD_COLUMNS = [
    "period_id",
    "invoice_id",
    "line_id",
    "source",
    "facility",
    *FACILITY_COLUMNS,
    "kpi_component",
    "mapped",
    "account",
    "supplier",
    "printed_start",
    "printed_end",
    "start",
    "end",
    "date_adjustment",
    "date_resolution",
    "date_resolution_reference",
    "date_provisional",
    "billed_original",
    "original_unit",
    "factor",
    "billed_kwh",
    "source_file",
    "source_link",
    "period_index",
]
ALLOCATION_COLUMNS = [
    *PERIOD_COLUMNS,
    "month",
    "segment_start",
    "segment_end",
    "days",
    "month_days",
    "allocated_original",
    "allocated_kwh",
]


def number(value: object) -> float | None:
    """Parse a finite quantity; invalid values remain unavailable rather than zero."""
    try:
        numeric_value = float(str(value).replace(",", ""))
    except (ValueError, TypeError):
        return None
    if not math.isfinite(numeric_value):
        return None
    return numeric_value


def date_value(value: object) -> datetime:
    """Return a pandas timestamp or NaT, both datetime-compatible scalar values."""
    if str(value).strip() == "":
        return pd.NaT
    return pd.to_datetime(value, errors="coerce")


def stable_id(*parts: object) -> str:
    """Keep the existing deterministic references stable across this refactor."""
    encoded_identity = repr(parts).encode("utf-8")
    return hashlib.sha256(encoded_identity).hexdigest()[:16]


def input_paths(root: Path, settings: Settings, category: str) -> dict[str, Path]:
    directory = silver_excel_output_dir(settings, category)
    if not directory.is_absolute():
        directory = root / directory
    paths = {}
    for layer in INPUT_LAYERS:
        paths[layer] = directory / silver_output_filename(category, layer)
    return paths


def source_fingerprint(paths: dict[str, Path]) -> SourceFingerprint:
    """Build cache keys using one stat result per existing file."""
    fingerprints = []
    for name, path in paths.items():
        if path.exists():
            file_stat = path.stat()
            fingerprint = (name, str(path), file_stat.st_mtime_ns, file_stat.st_size)
        else:
            fingerprint = (name, str(path), None, None)
        fingerprints.append(fingerprint)
    return tuple(fingerprints)


def _read_workbooks(paths: dict[str, Path]) -> dict[str, pd.DataFrame]:
    """Check availability, read all inputs, then reject concurrent file changes."""
    missing_names = []
    for path in paths.values():
        if not path.exists():
            missing_names.append(path.name)
    if len(missing_names) > 0:
        raise ValueError(
            "Run the Silver pipeline to create the audit inputs: "
            + ", ".join(missing_names)
        )
    before_read = source_fingerprint(paths)
    frames = {}
    for name, path in paths.items():
        frames[name] = pd.read_excel(path, dtype=object, keep_default_na=False)
    after_read = source_fingerprint(paths)
    if before_read != after_read:
        raise ValueError(
            "The pipeline outputs changed while loading. Refresh after the run finishes."
        )
    return frames


def _source_metadata(paths: dict[str, Path]) -> list[SourceMetadata]:
    metadata = []
    for path in paths.values():
        modified_at = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        content_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        metadata.append(
            {
                "File": path.name,
                "Modified (UTC)": modified_at.isoformat(),
                "SHA256": content_hash,
            }
        )
    return metadata


def _freshness_warnings(
    root: Path, settings: Settings, category: str, paths: dict[str, Path]
) -> list[str]:
    """Compare checkpoint/output ages without rebuilding or modifying any inputs."""
    checkpoint_directory = category_checkpoint_output_dir(settings, category)
    if not checkpoint_directory.is_absolute():
        checkpoint_directory = root / checkpoint_directory
    newest_checkpoint_time = 0
    for checkpoint in checkpoint_directory.glob("*.csv"):
        newest_checkpoint_time = max(
            newest_checkpoint_time, checkpoint.stat().st_mtime_ns
        )
    output_times = {}
    for layer, path in paths.items():
        output_times[layer] = path.stat().st_mtime_ns
    warnings = []
    if newest_checkpoint_time > min(output_times.values()):
        warnings.append(
            "Review checkpoints are newer than the report inputs. Rebuild Silver before exporting."
        )
    for source_name, input_layer, split_layer in SOURCE_FLOWS:
        if output_times[input_layer] > output_times[split_layer]:
            warnings.append(
                "Some split outputs predate their inputs. Rebuild Silver before exporting."
            )
            break  # This warning describes the input set, not an individual source.
    return warnings


def load_audit_data(
    root: Path, settings: Settings, category: str = "scope2"
) -> AuditData:
    """Read, normalize, and annotate the report inputs; all operations are read-only."""
    paths = input_paths(root, settings, category)
    frames = _read_workbooks(paths)
    audit_data = prepare_audit_data(frames)
    audit_data.sources = _source_metadata(paths)
    audit_data.warnings = _freshness_warnings(root, settings, category, paths)
    return audit_data


def _validate_columns(
    frame: pd.DataFrame, required: tuple[str, ...], layer: str
) -> None:
    missing_columns = set(required) - set(frame.columns)
    if len(missing_columns) > 0:
        missing_description = ", ".join(sorted(missing_columns))
        raise ValueError(
            f"{layer} is missing {missing_description}. Rebuild Silver with the current app."
        )


def _invoice_identity(record: AuditRecord, source: str) -> tuple[str, str]:
    if source == "Manual entry":
        invoice_field = "manual_entry_invoice_id"
        line_field = "manual_entry_line_id"
    else:
        invoice_field = "invoice_id"
        line_field = "line_id"
    invoice_id = record.get(invoice_field, "")
    if invoice_id is None or invoice_id == "":
        invoice_id = record.get("source_file", "")
    line_id = record.get(line_field, "")
    if line_id is None or line_id == "":
        line_id = "1"
    return str(invoice_id), str(line_id)


def _period_unit(record: AuditRecord, period_index: int) -> str:
    if period_index == 2:
        fallback = record.get("consumption_unit", "")
        if pd.isna(fallback) or not str(fallback).strip():
            fallback = record.get("consumption_quantity_unit", "")
        return _effective_consumption_quantity_unit(record.get("quantity_unit_2"), fallback)
    return str(record.get("consumption_quantity_unit", "")).strip()


def _converted_quantity(quantity: float | None, factor: float | None) -> float | None:
    if quantity is None:
        return None
    if factor is None:
        return None
    return quantity * factor


def _build_period(
    record: AuditRecord, source: str, period_index: int
) -> AuditRecord | None:
    """Translate one billing period; omit only an entirely absent second period."""
    start_value = record.get(f"consumption_start_date_{period_index}_normalized", "")
    end_value = record.get(f"consumption_end_date_{period_index}_normalized", "")
    quantity_value = record.get(f"aggregated_quantity_{period_index}", "")
    if period_index == 2:
        has_second_period_data = False
        for value in (start_value, end_value, quantity_value):
            if str(value).strip() != "":
                has_second_period_data = True
                break
        if not has_second_period_data:
            return None
    hierarchy = {}
    facility_labels = []
    is_mapped = record.get("mapping_status", "") in ("", "MAPPED")
    for column in FACILITY_COLUMNS:
        value = str(record.get(column, "")).strip()
        hierarchy[column] = value
        if value == "":
            is_mapped = False
            facility_labels.append("Unmapped")
        else:
            facility_labels.append(value)
    invoice_id, line_id = _invoice_identity(record, source)
    energy_unit = _period_unit(record, period_index)
    conversion_factor = kwh_conversion_factor(energy_unit)
    billed_quantity = number(quantity_value)
    return {
        "period_id": stable_id(source, invoice_id, line_id, period_index),
        "invoice_id": invoice_id,
        "line_id": line_id,
        "source": source,
        "facility": " / ".join(facility_labels),
        **hierarchy,
        "kpi_component": next((f"Purchased {group.lower()}" for group in SCOPE2_ACTIVITY_GROUPS
                               if group.casefold() == str(record.get("activity_group", "")).strip().casefold()),
                              "Unclassified"),
        "mapped": is_mapped,
        "account": str(record.get("account_number", "")),
        "supplier": str(record.get("supplier_name", "")).strip(),
        "printed_start": date_value(start_value),
        "printed_end": date_value(end_value),
        "start": date_value(record.get(f"date_{period_index}_effective_start") or start_value),
        "end": date_value(record.get(f"date_{period_index}_effective_end") or end_value),
        "date_resolution": record.get(f"date_{period_index}_resolution", ""),
        "date_adjustment": record.get(f"date_{period_index}_adjustment", "None"),
        "date_resolution_reference": record.get(f"date_{period_index}_resolution_reference", ""),
        "date_provisional": record.get(f"date_{period_index}_provisional", ""),
        "billed_original": billed_quantity,
        "original_unit": energy_unit,
        "factor": conversion_factor,
        "billed_kwh": _converted_quantity(billed_quantity, conversion_factor),
        "source_file": str(record.get("source_file", "")),
        "source_link": str(record.get("sharepoint_link", "")),
        "period_index": period_index,
    }


def _build_allocation(record: AuditRecord, parent: AuditRecord) -> AuditRecord:
    allocated_quantity = number(record.get("quantity_proration"))
    allocation = parent.copy()
    allocation.update(
        {
            "month": str(record.get("date_month_proration", "")),
            "segment_start": date_value(record.get("date_split_start_proration", "")),
            "segment_end": date_value(record.get("date_split_end_proration", "")),
            "days": number(record.get("date_total_days_proration")),
            "month_days": number(record.get("date_split_days_proration")),
            "allocated_original": allocated_quantity,
            "allocated_kwh": _converted_quantity(allocated_quantity, parent["factor"]),
        }
    )
    return allocation


def _prepare_source(
    original: pd.DataFrame, splits: pd.DataFrame, source: str, split_layer: str,
    other_invoices: pd.DataFrame | None = None,
) -> tuple[list[AuditRecord], list[AuditRecord]]:
    """Index source periods, then attach each split to a validated parent record."""
    periods = []
    period_lookup = {}
    # Re-resolve from source history, never infer expected dates from saved splits.
    resolved = build_silver_proration_calculation(original, other_invoices=other_invoices)
    resolved = resolved.drop_duplicates("proration_source_row_id")
    resolution_columns = [
        f"date_{period_index}_{field}"
        for period_index in (1, 2) for field in DATE_RESOLUTION_FIELDS
    ]
    resolution_lookup = resolved.set_index("proration_source_row_id")[resolution_columns].to_dict("index")
    for row_number, record in enumerate(original.to_dict("records"), start=1):
        record.update(resolution_lookup[row_number])
        for period_index in (1, 2):
            period = _build_period(record, source, period_index)
            if period is None:
                continue
            periods.append(period)
            period_lookup[(row_number, period_index)] = period
    allocations = []
    for record in splits.to_dict("records"):
        source_row_id = number(record.get("proration_source_row_id"))
        period_index = number(record.get("proration_period_index"))
        parent = period_lookup.get((source_row_id, period_index))
        if parent is None:
            raise ValueError(
                f"{split_layer} contains a split without a matching invoice period. Rebuild Silver."
            )
        if str(record.get("source_file", "")) != parent["source_file"]:
            raise ValueError(
                f"{split_layer} references a different source invoice than its input. Rebuild Silver."
            )
        original_record = original.iloc[int(source_row_id) - 1]
        for field in ("activity_group", "account_number"):
            if field in splits.columns and str(record.get(field, "")).strip() != str(original_record.get(field, "")).strip():
                raise ValueError(f"{split_layer} has stale account or energy classification. Rebuild Silver.")
        for field in DATE_RESOLUTION_FIELDS:
            recorded = record.get(f"date_{field}_proration", "")
            expected = resolution_lookup[source_row_id][f"date_{int(period_index)}_{field}"]
            if field in {"effective_start", "effective_end"}:
                expected = date_value(expected)
                recorded = date_value(recorded)
                differs = not (pd.isna(recorded) and pd.isna(expected)) and recorded != expected
            else:
                differs = recorded != expected
            if differs:
                raise ValueError(
                    f"{split_layer} has stale or inconsistent billing date resolution. Rebuild Silver."
                )
        allocations.append(_build_allocation(record, parent))
    return periods, allocations


def prepare_audit_data(frames: dict[str, pd.DataFrame]) -> AuditData:
    """Validate both source flows, combine normalized records, and reject ambiguous IDs."""
    periods = []
    allocations = []
    for source, input_layer, split_layer in SOURCE_FLOWS:
        original = frames[input_layer]
        splits = frames[split_layer]
        _validate_columns(original, REQUIRED_INPUT_COLUMNS, input_layer)
        _validate_columns(splits, REQUIRED_SPLIT_COLUMNS, split_layer)
        source_periods, source_allocations = _prepare_source(
            original, splits, source, split_layer,
            other_invoices=pd.concat(
                [frames[layer] for _, layer, _ in SOURCE_FLOWS if layer != input_layer],
                ignore_index=True,
            ),
        )
        periods.extend(source_periods)
        allocations.extend(source_allocations)
    periods_frame = pd.DataFrame(periods, columns=PERIOD_COLUMNS)
    if periods_frame.period_id.duplicated().any():
        raise ValueError(
            "Invoice references are not unique. Review duplicate invoice/line references before reporting."
        )
    allocations_frame = pd.DataFrame(allocations, columns=ALLOCATION_COLUMNS)
    return AuditData(periods=periods_frame, allocations=allocations_frame)
