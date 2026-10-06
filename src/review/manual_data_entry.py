from io import BytesIO
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from src.core.blob_storage import download_blob_bytes
from src.core.config_loader import load_yaml
from src.review.confidence_config import ConfidenceConfig


MANUAL_DATA_ENTRY_QUEUE_FILENAME = "step_0_manual_data_entry_queue.csv"
MANUAL_DATA_ENTRY_DECISIONS_FILENAME = (
    "step_0_manual_data_entry_decisions_checkpoint.csv"
)

MASTER_ENTITY_LIST_FILENAME = "master_entity_list.csv"

MANUAL_ENTRY_SOURCE_OCR_LOW_CONFIDENCE = (
    "OCR_LOW_DOCUMENT_CONFIDENCE"
)

MANUAL_ENTRY_SOURCE_UPLOAD = "USER_UPLOAD"

MANUAL_ENERGY_MAPPING_FIELDS = [
    "activity_group",
    "account_number",
]

MANUAL_DATA_ENTRY_FIELDS = [
    "data_quality",
    "division",
    "legal_entity_name",
    "unit",
    "consumption_start_date",
    "consumption_end_date",
    "transaction_date",
    "amount_of_energy_consumed",
    "energy_unit",
]


def missing_manual_data_entry_fields(
    values: Mapping[str, Any],
) -> list[str]:
    return [
        field_name
        for field_name in MANUAL_DATA_ENTRY_FIELDS
        if _is_blank(values.get(field_name))
    ]


def build_manual_data_entry_queue_rows(
    bronze_df: pd.DataFrame,
    config: ConfidenceConfig,
) -> list[dict[str, Any]]:
    rows = []

    threshold = config.document_confidence_threshold

    if threshold <= 0:
        return rows

    for index, row in enumerate(
        bronze_df.to_dict("records"),
        start=1,
    ):
        document_confidence = _coerce_confidence(
            row.get("document_confidence")
        )

        if (
            document_confidence is None
            or document_confidence >= threshold
        ):
            continue

        rows.append(
            _queue_row(
                row,
                index,
                document_confidence,
                threshold,
            )
        )

    return rows


def split_by_document_confidence(
    bronze_df: pd.DataFrame,
    config: ConfidenceConfig,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    threshold = config.document_confidence_threshold

    if (
        threshold <= 0
        or "document_confidence" not in bronze_df.columns
    ):
        return (
            bronze_df.copy(),
            bronze_df.iloc[0:0].copy(),
        )

    low_confidence_mask = bronze_df[
        "document_confidence"
    ].apply(
        lambda value: (
            confidence := _coerce_confidence(value)
        )
        is not None
        and confidence < threshold
    )

    return (
        bronze_df[~low_confidence_mask].copy(),
        bronze_df[low_confidence_mask].copy(),
    )


def write_manual_data_entry_queue(
    bronze_df: pd.DataFrame,
    config: ConfidenceConfig,
    output_dir: str | Path,
    filename: str = MANUAL_DATA_ENTRY_QUEUE_FILENAME,
) -> Path:
    output_path = Path(output_dir)
    output_path.mkdir(
        parents=True,
        exist_ok=True,
    )

    target = output_path / filename

    rows = build_manual_data_entry_queue_rows(
        bronze_df,
        config,
    )

    rows.extend(
        _existing_upload_queue_rows(target)
    )

    pd.DataFrame(
        rows,
        columns=_queue_columns(),
    ).to_csv(
        target,
        index=False,
        encoding="utf-8-sig",
    )

    return target


def prune_manual_data_entry_decisions(
    decisions_file: str | Path,
    queue_file: str | Path,
) -> Path:
    decisions_path = Path(decisions_file)
    queue_path = Path(queue_file)

    if not decisions_path.exists():
        return decisions_path

    decisions_df = _read_decisions(
        decisions_path
    )

    if decisions_df.empty:
        return decisions_path

    valid_keys = {
        _manual_entry_key(row)
        for row in _read_queue(
            queue_path
        ).to_dict("records")
    }

    keep_mask = decisions_df.apply(
        lambda row: (
            _manual_entry_key(row)
            in valid_keys
        ),
        axis=1,
    )

    pruned_df = decisions_df.loc[
        keep_mask
    ].copy()

    if len(pruned_df) != len(decisions_df):
        pruned_df.to_csv(
            decisions_path,
            index=False,
            encoding="utf-8-sig",
        )

    return decisions_path


def append_manual_upload_queue_row(
    queue_file: str | Path,
    uploaded_file_name: str,
    stored_file_path: str | Path,
    uploaded_at: str,
    sharepoint_link: str = "",
) -> Path:
    queue_path = Path(queue_file)

    queue_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    existing_df = _read_queue(
        queue_path
    )

    row = _manual_upload_queue_row(
        uploaded_file_name=uploaded_file_name,
        stored_file_path=stored_file_path,
        uploaded_at=uploaded_at,
        existing_rows=existing_df.to_dict(
            "records"
        ),
    )

    row["sharepoint_link"] = (
        sharepoint_link
    )

    updated_df = pd.concat(
        [
            existing_df,
            pd.DataFrame([row]),
        ],
        ignore_index=True,
        sort=False,
    )

    updated_df = updated_df.reindex(
        columns=_ordered_queue_columns(
            updated_df
        ),
        fill_value="",
    )

    updated_df.to_csv(
        queue_path,
        index=False,
        encoding="utf-8-sig",
    )

    return queue_path


def dropdown_config_path(
    config_dir: str | Path,
    invoice_type: str,
) -> Path:
    return (
        Path(config_dir)
        / "dropdowns"
        / f"{invoice_type}_dropdown.yaml"
    )


def master_entity_list_path(
    config_dir: str | Path,
) -> Path:
    return (
        Path(config_dir)
        / "reference"
        / MASTER_ENTITY_LIST_FILENAME
    )


def load_dropdown_config(
    path: str | Path,
) -> dict[str, Any]:
    return load_yaml(path)


def entity_list_source_path(
    config_dir: str | Path,
    dropdown_config: Mapping[str, Any],
) -> Path:
    entity_list_config = (
        dropdown_config
        .get("validation", {})
        .get("entity_list", {})
    )

    source = (
        entity_list_config.get("source")
        if isinstance(
            entity_list_config,
            dict,
        )
        else None
    )

    if source:
        return _resolve_config_reference_path(
            config_dir,
            source,
        )

    return master_entity_list_path(
        config_dir
    )


def load_entity_hierarchy(
    config_dir: str | Path,
    dropdown_config: Mapping[str, Any],
) -> dict[str, dict[str, list[str]]]:
    entity_list_config = (
        dropdown_config
        .get("validation", {})
        .get("entity_list", {})
    )

    if not isinstance(
        entity_list_config,
        dict,
    ):
        entity_list_config = {}

    blob_name = str(
        entity_list_config.get(
            "blob_name",
            "",
        )
    ).strip()

    if blob_name:
        csv_bytes = download_blob_bytes(
            blob_name
        )

        entity_df = pd.read_csv(
            BytesIO(csv_bytes),
            dtype=object,
            keep_default_na=False,
            encoding="utf-8-sig",
        )

    else:
        source_path = (
            entity_list_source_path(
                config_dir,
                dropdown_config,
            )
        )

        if not source_path.exists():
            return {}

        entity_df = pd.read_csv(
            source_path,
            dtype=object,
            keep_default_na=False,
            encoding="utf-8-sig",
        )

    return build_entity_hierarchy(
        entity_df,
        dropdown_config,
    )


def build_entity_hierarchy(
    entity_df: pd.DataFrame,
    dropdown_config: Mapping[str, Any],
) -> dict[str, dict[str, list[str]]]:
    entity_list_config = (
        dropdown_config
        .get("validation", {})
        .get("entity_list", {})
    )

    columns = (
        entity_list_config.get(
            "columns",
            {},
        )
        if isinstance(
            entity_list_config,
            dict,
        )
        else {}
    )

    active_column = str(
        columns.get(
            "active",
            "active",
        )
    )

    division_column = str(
        columns.get(
            "division",
            "division",
        )
    )

    legal_entity_column = str(
        columns.get(
            "legal_entity_name",
            "legal_entity_name",
        )
    )

    unit_column = str(
        columns.get(
            "unit",
            "unit",
        )
    )

    for column in (
        division_column,
        legal_entity_column,
        unit_column,
    ):
        if column not in entity_df.columns:
            raise ValueError(
                "Master entity list is missing "
                f"required column: {column}"
            )

    if active_column in entity_df.columns:
        entity_df = entity_df[
            entity_df[
                active_column
            ]
            .astype(str)
            .str.strip()
            .str.upper()
            .isin(
                {
                    "",
                    "Y",
                    "YES",
                    "TRUE",
                    "1",
                }
            )
        ]

    hierarchy: dict[
        str,
        dict[str, list[str]],
    ] = {}

    for _, row in entity_df.iterrows():
        division = str(
            row.get(
                division_column,
                "",
            )
        ).strip()

        legal_entity = str(
            row.get(
                legal_entity_column,
                "",
            )
        ).strip()

        unit = str(
            row.get(
                unit_column,
                "",
            )
        ).strip()

        if (
            not division
            or not legal_entity
            or not unit
        ):
            continue

        units = (
            hierarchy
            .setdefault(
                division,
                {},
            )
            .setdefault(
                legal_entity,
                [],
            )
        )

        if unit not in units:
            units.append(unit)

    return {
        division: {
            legal_entity: sorted(units)
            for legal_entity, units
            in sorted(
                legal_entities.items()
            )
        }
        for division, legal_entities
        in sorted(
            hierarchy.items()
        )
    }


def _resolve_config_reference_path(
    config_dir: str | Path,
    source: str,
) -> Path:
    source_path = Path(source)

    if source_path.is_absolute():
        return source_path

    return (
        Path(config_dir)
        / "dropdowns"
        / source_path
    ).resolve()


def _queue_row(
    row: Mapping[str, Any],
    index: int,
    document_confidence: float,
    threshold: float,
) -> dict[str, Any]:
    result = {
        "invoice_id": (
            row.get("invoice_id")
            or row.get("source_file")
            or ""
        ),
        "line_id": (
            row.get("line_id")
            or str(index)
        ),
        "source_file": row.get(
            "source_file",
            "",
        ),
        "source_path": row.get(
            "source_path",
            "",
        ),
        "sharepoint_link": row.get(
            "sharepoint_link",
            "",
        ),
        "document_confidence": (
            document_confidence
        ),
        "document_confidence_threshold": (
            threshold
        ),
        "manual_entry_status": "OPEN",
        "manual_entry_source": (
            MANUAL_ENTRY_SOURCE_OCR_LOW_CONFIDENCE
        ),
        "uploaded_at": "",
        "original_file_name": "",
    }

    for field_name in (
        MANUAL_DATA_ENTRY_FIELDS
    ):
        result[field_name] = ""

    return result


def _queue_columns() -> list[str]:
    return [
        "invoice_id",
        "line_id",
        "source_file",
        "source_path",
        "sharepoint_link",
        "document_confidence",
        "document_confidence_threshold",
        "manual_entry_status",
        "manual_entry_source",
        "uploaded_at",
        "original_file_name",
        *MANUAL_DATA_ENTRY_FIELDS,
        *MANUAL_ENERGY_MAPPING_FIELDS,
    ]


def _manual_upload_queue_row(
    uploaded_file_name: str,
    stored_file_path: str | Path,
    uploaded_at: str,
    existing_rows: list[
        Mapping[str, Any]
    ],
) -> dict[str, Any]:
    invoice_id = (
        _unique_manual_upload_invoice_id(
            uploaded_file_name,
            existing_rows,
        )
    )

    result = {
        "invoice_id": invoice_id,
        "line_id": "1",
        "source_file": uploaded_file_name,
        "source_path": str(
            stored_file_path
        ),
        "sharepoint_link": "",
        "document_confidence": "",
        "document_confidence_threshold": "",
        "manual_entry_status": "OPEN",
        "manual_entry_source": (
            MANUAL_ENTRY_SOURCE_UPLOAD
        ),
        "uploaded_at": uploaded_at,
        "original_file_name": (
            uploaded_file_name
        ),
    }

    for field_name in (
        MANUAL_DATA_ENTRY_FIELDS
    ):
        result[field_name] = ""

    return result


def _unique_manual_upload_invoice_id(
    uploaded_file_name: str,
    existing_rows: list[
        Mapping[str, Any]
    ],
) -> str:
    safe_name = "".join(
        char if char.isalnum() else "_"
        for char
        in Path(
            uploaded_file_name
        ).stem
    ).strip("_")

    safe_name = (
        safe_name
        or "uploaded_invoice"
    )

    existing_ids = {
        str(
            row.get(
                "invoice_id",
                "",
            )
        )
        for row in existing_rows
    }

    candidate = (
        f"manual_upload_{safe_name}"
    )

    if candidate not in existing_ids:
        return candidate

    suffix = 2

    while (
        f"{candidate}_{suffix}"
        in existing_ids
    ):
        suffix += 1

    return (
        f"{candidate}_{suffix}"
    )


def _existing_upload_queue_rows(
    path: Path,
) -> list[dict[str, Any]]:
    existing_df = _read_queue(path)

    if (
        existing_df.empty
        or "manual_entry_source"
        not in existing_df.columns
    ):
        return []

    upload_df = existing_df[
        existing_df[
            "manual_entry_source"
        ].astype(str)
        == MANUAL_ENTRY_SOURCE_UPLOAD
    ]

    return upload_df.to_dict(
        "records"
    )


def _read_queue(
    path: Path,
) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(
            columns=_queue_columns()
        )

    try:
        return pd.read_csv(
            path,
            dtype=object,
            keep_default_na=False,
            encoding="utf-8-sig",
        )

    except pd.errors.EmptyDataError:
        return pd.DataFrame(
            columns=_queue_columns()
        )


def _read_decisions(
    path: Path,
) -> pd.DataFrame:
    try:
        return pd.read_csv(
            path,
            dtype=object,
            keep_default_na=False,
            encoding="utf-8-sig",
        )

    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def _manual_entry_key(
    row: Mapping[str, Any],
) -> tuple[str, str]:
    return (
        str(
            row.get(
                "invoice_id",
                "",
            )
        ),
        str(
            row.get(
                "line_id",
                "",
            )
        ),
    )


def _is_blank(
    value: Any,
) -> bool:
    return (
        value is None
        or pd.isna(value)
        or str(value).strip() == ""
    )


def _ordered_queue_columns(
    df: pd.DataFrame,
) -> list[str]:
    columns = _queue_columns()

    for column in df.columns:
        if column not in columns:
            columns.append(column)

    return columns


def _coerce_confidence(
    value: Any,
) -> float | None:
    if value in (
        None,
        "",
    ):
        return None

    try:
        return float(value)

    except (
        TypeError,
        ValueError,
    ):
        return None