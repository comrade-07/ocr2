from pathlib import Path

import pandas as pd


FLAGGED_DUPLICATES_FILENAME = "step_0_flagged_duplicates_checkpoint.csv"
DUPLICATE_STATUS_COLUMN = "duplicate_status"
DUPLICATE_GROUP_COLUMN = "duplicate_group_id"
DUPLICATE_OF_SOURCE_FILE_COLUMN = "duplicate_of_source_file"
BUSINESS_DUPLICATE_KEY_COLUMN = "business_duplicate_key"
DUPLICATE_MATCH_TYPE_COLUMN = "duplicate_match_type"
SOURCE_CONTENT_HASH_COLUMN = "source_content_hash"

PRIMARY_DUPLICATE_STATUS = "PRIMARY"
FLAGGED_DUPLICATE_STATUS = "DUPLICATE"


def mark_duplicate_rows(records: list[dict]) -> list[dict]:
    primary_by_match_key = {}
    duplicate_index_by_match_key = {}
    marked_records = []

    for record in records:
        marked_record = record.copy()
        source_hash = str(marked_record.get(SOURCE_CONTENT_HASH_COLUMN) or "").strip()
        business_key = str(marked_record.get(BUSINESS_DUPLICATE_KEY_COLUMN) or "").strip()
        content_match_key = f"CONTENT_HASH:{source_hash}" if source_hash else ""
        business_match_key = f"BUSINESS_KEY:{business_key}" if business_key else ""
        match_key = ""
        match_type = ""

        if content_match_key and content_match_key in primary_by_match_key:
            match_key = content_match_key
            match_type = "CONTENT_HASH"
        elif business_match_key and business_match_key in primary_by_match_key:
            match_key = business_match_key
            match_type = "BUSINESS_KEY"
        elif content_match_key:
            match_key = content_match_key
            match_type = "CONTENT_HASH"
        elif business_match_key:
            match_key = business_match_key
            match_type = "BUSINESS_KEY"

        if not match_key:
            marked_record[DUPLICATE_STATUS_COLUMN] = PRIMARY_DUPLICATE_STATUS
            marked_record[DUPLICATE_GROUP_COLUMN] = ""
            marked_record[DUPLICATE_OF_SOURCE_FILE_COLUMN] = ""
            marked_record[DUPLICATE_MATCH_TYPE_COLUMN] = ""
            marked_records.append(marked_record)
            continue

        if match_key not in primary_by_match_key:
            source_file = str(marked_record.get("source_file", ""))
            duplicate_group_index = len(duplicate_index_by_match_key) + 1
            for key in (content_match_key, business_match_key):
                if key:
                    primary_by_match_key[key] = source_file
                    duplicate_index_by_match_key[key] = duplicate_group_index
            marked_record[DUPLICATE_STATUS_COLUMN] = PRIMARY_DUPLICATE_STATUS
            marked_record[DUPLICATE_OF_SOURCE_FILE_COLUMN] = ""
        else:
            marked_record[DUPLICATE_STATUS_COLUMN] = FLAGGED_DUPLICATE_STATUS
            marked_record[DUPLICATE_OF_SOURCE_FILE_COLUMN] = primary_by_match_key[match_key]

        marked_record[DUPLICATE_MATCH_TYPE_COLUMN] = match_type
        marked_record[DUPLICATE_GROUP_COLUMN] = f"DUP-{duplicate_index_by_match_key[match_key]:04d}"
        marked_records.append(marked_record)

    return marked_records


def split_duplicate_rows(bronze_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if bronze_df.empty or DUPLICATE_STATUS_COLUMN not in bronze_df.columns:
        return bronze_df.copy(), pd.DataFrame(columns=bronze_df.columns)

    duplicate_mask = bronze_df[DUPLICATE_STATUS_COLUMN].astype(str).str.upper() == FLAGGED_DUPLICATE_STATUS
    return bronze_df[~duplicate_mask].copy(), bronze_df[duplicate_mask].copy()


def write_flagged_duplicates_checkpoint(
    duplicates_df: pd.DataFrame,
    output_dir: str | Path,
    filename: str = FLAGGED_DUPLICATES_FILENAME,
) -> Path:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    target = output_path / filename
    duplicates_df.to_csv(target, index=False, encoding="utf-8-sig")
    return target
