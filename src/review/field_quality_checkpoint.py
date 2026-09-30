from pathlib import Path

import pandas as pd

from src.review.confidence_config import ConfidenceConfig
from src.review.field_quality import build_field_quality_rows_from_records
from src.review.review_issues import build_review_issue_rows
from src.review.review_summary import build_review_summary_rows


STEP_1_FIELD_QUALITY_FILENAME = "step_1_field_quality_checkpoint.csv"
STEP_2_REVIEW_SUMMARY_FILENAME = "step_2_review_summary_checkpoint.csv"
STEP_3_REVIEW_ISSUES_FILENAME = "step_3_review_issues_checkpoint.csv"


def write_field_quality_checkpoint(
    silver_df: pd.DataFrame,
    config: ConfidenceConfig,
    output_dir: str | Path,
    filename: str = STEP_1_FIELD_QUALITY_FILENAME,
) -> Path:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    target = output_path / filename

    records = silver_df.to_dict("records")
    field_quality_rows = build_field_quality_rows_from_records(records, config)
    pd.DataFrame(field_quality_rows).to_csv(target, index=False, encoding="utf-8-sig")

    return target


def write_review_summary_checkpoint(
    field_quality_rows: list[dict],
    config: ConfidenceConfig,
    output_dir: str | Path,
    filename: str = STEP_2_REVIEW_SUMMARY_FILENAME,
) -> Path:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    target = output_path / filename

    review_summary_rows = build_review_summary_rows(field_quality_rows, config)
    pd.DataFrame(review_summary_rows).to_csv(target, index=False, encoding="utf-8-sig")

    return target


def write_review_issues_checkpoint(
    field_quality_rows: list[dict],
    config: ConfidenceConfig,
    output_dir: str | Path,
    filename: str = STEP_3_REVIEW_ISSUES_FILENAME,
) -> Path:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    target = output_path / filename

    review_issue_rows = build_review_issue_rows(field_quality_rows, config)
    pd.DataFrame(review_issue_rows).to_csv(target, index=False, encoding="utf-8-sig")

    return target
