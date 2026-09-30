from pathlib import Path

import pandas as pd

from src.core.config_loader import load_yaml
from src.core.logger import get_logger
from src.core.path_settings import bronze_output_dir, category_checkpoint_output_dir
from src.review.approved_silver import write_approved_silver_checkpoint
from src.review.confidence_config import confidence_config_path, load_confidence_config
from src.review.duplicates import split_duplicate_rows, write_flagged_duplicates_checkpoint
from src.review.field_quality import build_field_quality_rows_from_records
from src.review.field_quality_checkpoint import (
    write_field_quality_checkpoint,
    write_review_issues_checkpoint,
    write_review_summary_checkpoint,
)
from src.review.manual_decisions import (
    MANUAL_REVIEW_DECISIONS_FILENAME,
    load_manual_decision_rows,
    write_manual_decisions_checkpoint,
)
from src.review.manual_data_entry import (
    MANUAL_DATA_ENTRY_DECISIONS_FILENAME,
    prune_manual_data_entry_decisions,
    split_by_document_confidence,
    write_manual_data_entry_queue,
)
from src.review.review_issues import build_review_issue_rows
from src.review.review_summary import build_review_summary_rows

logger = get_logger(__name__)

DEFAULT_INVOICE_TYPE = "scope2"


def run_review_pipeline(
    config_dir: str | Path = "config",
    bronze_file: str | Path | None = None,
    invoice_type: str | None = None,
) -> dict[str, Path]:
    config_dir = Path(config_dir)
    settings = load_yaml(config_dir / "settings.yaml")
    invoice_type = invoice_type or settings.get("pipeline", {}).get("invoice_type", DEFAULT_INVOICE_TYPE)

    bronze_dir = bronze_output_dir(settings, invoice_type)
    checkpoint_dir = checkpoint_dir_for_invoice_type(settings, invoice_type)
    bronze_file = Path(bronze_file) if bronze_file is not None else bronze_dir / f"{invoice_type}_bronze.csv"
    confidence_config = load_confidence_config(confidence_config_path(config_dir, invoice_type))

    if not bronze_file.exists():
        raise FileNotFoundError(f"Bronze CSV does not exist: {bronze_file}")

    logger.info("Reading bronze CSV for review checkpoints from %s", bronze_file)
    bronze_df = pd.read_csv(bronze_file, dtype=object, keep_default_na=False, encoding="utf-8-sig")
    unique_bronze_df, duplicate_df = split_duplicate_rows(bronze_df)

    duplicates_path = write_flagged_duplicates_checkpoint(duplicate_df, checkpoint_dir)
    logger.info(
        "Wrote Step 0 flagged-duplicates checkpoint to %s with %s duplicate row(s)",
        duplicates_path,
        len(duplicate_df),
    )

    review_bronze_df, manual_entry_df = split_by_document_confidence(unique_bronze_df, confidence_config)

    manual_entry_path = write_manual_data_entry_queue(unique_bronze_df, confidence_config, checkpoint_dir)
    prune_manual_data_entry_decisions(
        checkpoint_dir / MANUAL_DATA_ENTRY_DECISIONS_FILENAME,
        manual_entry_path,
    )
    logger.info(
        "Wrote Step 0 manual-data-entry queue to %s with %s low-document-confidence row(s)",
        manual_entry_path,
        len(manual_entry_df),
    )

    field_quality_rows = build_field_quality_rows_from_records(
        review_bronze_df.to_dict("records"),
        confidence_config,
    )
    review_summary_rows = build_review_summary_rows(field_quality_rows, confidence_config)
    review_issue_rows = build_review_issue_rows(field_quality_rows, confidence_config)

    field_quality_path = write_field_quality_checkpoint(review_bronze_df, confidence_config, checkpoint_dir)
    logger.info("Wrote Step 1 field-quality checkpoint to %s", field_quality_path)

    summary_path = write_review_summary_checkpoint(
        field_quality_rows,
        confidence_config,
        checkpoint_dir,
    )
    logger.info("Wrote Step 2 review-summary checkpoint to %s", summary_path)

    issues_path = write_review_issues_checkpoint(
        field_quality_rows,
        confidence_config,
        checkpoint_dir,
    )
    logger.info("Wrote Step 3 review-issues checkpoint to %s", issues_path)

    decisions_path = write_manual_decisions_checkpoint(
        review_issue_rows,
        checkpoint_dir,
    )
    logger.info("Wrote Step 4 manual-review decisions checkpoint to %s", decisions_path)

    decision_rows = load_manual_decision_rows(checkpoint_dir / MANUAL_REVIEW_DECISIONS_FILENAME)
    approved_path = write_approved_silver_checkpoint(
        review_bronze_df,
        review_summary_rows,
        decision_rows,
        checkpoint_dir,
    )
    logger.info("Wrote Step 5 approved review checkpoint to %s", approved_path)

    return {
        "duplicates": duplicates_path,
        "manual_data_entry": manual_entry_path,
        "field_quality": field_quality_path,
        "summary": summary_path,
        "issues": issues_path,
        "decisions": decisions_path,
        "approved": approved_path,
    }


def checkpoint_dir_for_invoice_type(settings: dict, invoice_type: str) -> Path:
    return category_checkpoint_output_dir(settings, invoice_type)
