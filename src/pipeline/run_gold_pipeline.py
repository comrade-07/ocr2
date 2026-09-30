from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.core.config_loader import load_yaml
from src.core.logger import get_logger
from src.core.path_settings import gold_output_dir, silver_excel_output_dir
from src.output.xlsx_writer import write_xlsx
from src.pipeline.run_silver_pipeline import (
    DATE_RESOLUTION_FIELDS,
    DEFAULT_INVOICE_TYPE,
    SILVER_TEMPLATE_PREPARATION_KPI_COLUMNS,
    silver_output_filename,
)
from src.transform.unit_conversion import apply_unit_conversions, kwh_conversion_factor


logger = get_logger(__name__)

GOLD_TEMPLATE_AGGREGATION_KEYS = [
    "Division",
    "Legal Entity Name",
    "Unit",
    "Consumption start date",
    "KPI Component",
]

GOLD_TEMPLATE_AGGREGATED_SUM_COLUMNS = {
    "Amount of energy consumed",
    "Total amount of energy consumed",
}

SOLAR_ENERGY_KPIS = {
    "Renewable energy production",
    "Consumption of self-generated non-fuel renewable energy",
}
SOLAR_QUANTITY_COLUMNS = {"solar_export", "solar_total_generation", "total_solar_consumed"}
ALLOCATION_KPI_COLUMNS = {
    column: kpi for column, kpi, method in SILVER_TEMPLATE_PREPARATION_KPI_COLUMNS
    if method == "percentage"
}

GOLD_TEMPLATE_AGGREGATED_JOIN_COLUMNS = {
    "Energy KPI",
    "source_files",
    "proration_source_row_ids",
    "proration_split_keys",
    "approval_status",
    "manual_review_tag",
    "manual_data_entry_portion",
    "Original Energy Unit",
    "Account number",
    "Supplier Name",
    "business_mapping_issue",
    *[f"date_{field}_proration" for field in DATE_RESOLUTION_FIELDS],
}


def gold_output_filename(invoice_type: str, layer: str) -> str:
    return f"{invoice_type}_gold_{layer}.xlsx"


def run_gold_pipeline(
    config_dir: str | Path = "config",
    invoice_type: str | None = None,
    template_output_file: str | Path | None = None,
) -> Path:
    config_dir = Path(config_dir)
    settings = load_yaml(config_dir / "settings.yaml")
    invoice_type = invoice_type or settings.get("pipeline", {}).get("invoice_type", DEFAULT_INVOICE_TYPE)

    silver_dir = silver_excel_output_dir(settings, invoice_type)
    gold_dir = gold_output_dir(settings, invoice_type)
    template_output_path = (
        Path(template_output_file)
        if template_output_file is not None
        else silver_dir / silver_output_filename(invoice_type, "template_output")
    )

    if not template_output_path.exists():
        raise FileNotFoundError(f"Silver template output workbook does not exist: {template_output_path}")

    logger.info("Reading silver-template-output workbook for gold template from %s", template_output_path)
    template_output_df = pd.read_excel(
        template_output_path,
        sheet_name="SilverTemplateOutput",
        dtype=object,
        keep_default_na=False,
        engine="openpyxl",
    )
    gold_template_df = build_gold_template(template_output_df)
    gold_template_path = write_xlsx(
        gold_template_df,
        gold_dir,
        gold_output_filename(invoice_type, "template"),
        sheet_name="GoldTemplate",
    )
    logger.info("Wrote gold-template Excel workbook to %s", gold_template_path)

    gold_template_aggregated_df = build_gold_template_aggregated(gold_template_df)
    gold_template_aggregated_path = write_xlsx(
        gold_template_aggregated_df,
        gold_dir,
        gold_output_filename(invoice_type, "template_aggregated"),
        sheet_name="GoldTemplateAggregated",
    )
    logger.info("Wrote gold-template-aggregated Excel workbook to %s", gold_template_aggregated_path)
    return gold_template_path


def build_gold_template(template_output_df: pd.DataFrame) -> pd.DataFrame:
    template_output_df = template_output_df.copy()
    if "business_mapping_issue" in template_output_df.columns:
        template_output_df = template_output_df.loc[
            template_output_df["business_mapping_issue"].fillna("").astype(str).str.strip().eq("")
        ]
    if "Energy Unit" in template_output_df.columns:
        template_output_df = template_output_df.loc[template_output_df["Energy Unit"].map(kwh_conversion_factor).notna()]
    return apply_unit_conversions(
        template_output_df,
        additional_amount_columns=(
            "Total amount of energy consumed",
            "solar_export", "solar_total_generation", "total_solar_consumed",
        ),
    )


def build_gold_template_aggregated(gold_template_df: pd.DataFrame) -> pd.DataFrame:
    if gold_template_df.empty:
        return gold_template_df.copy()

    missing_keys = [column for column in GOLD_TEMPLATE_AGGREGATION_KEYS if column not in gold_template_df.columns]
    if missing_keys:
        return gold_template_df.copy()

    if "Energy Unit" in gold_template_df.columns:
        gold_template_df = gold_template_df.loc[
            gold_template_df["Energy Unit"].astype(str).str.strip().str.casefold().eq("kwh")
        ]
        if gold_template_df.empty:
            return gold_template_df.copy()

    rows = []
    for _, group_df in gold_template_df.groupby(GOLD_TEMPLATE_AGGREGATION_KEYS, dropna=False, sort=False):
        consumption_df = group_df
        if "Energy KPI" in group_df.columns:
            consumption_df = group_df[~group_df["Energy KPI"].isin(SOLAR_ENERGY_KPIS)]
        consumption_total = _sum_numbers(consumption_df["Amount of energy consumed"])
        source_columns = [column for column in (
            "Account number", "Supplier Name", "Original Energy Unit",
            "manual_data_entry_portion", "proration_split_keys", "source_files",
        ) if column in group_df.columns]
        source_df = group_df.drop_duplicates(source_columns) if source_columns else group_df
        row = group_df.iloc[0].copy()
        for column in gold_template_df.columns:
            if column in GOLD_TEMPLATE_AGGREGATION_KEYS:
                continue
            if column in GOLD_TEMPLATE_AGGREGATED_SUM_COLUMNS:
                row[column] = consumption_total
            elif column in ALLOCATION_KPI_COLUMNS and "Energy KPI" in consumption_df.columns:
                allocation_rows = consumption_df[consumption_df["Energy KPI"].eq(ALLOCATION_KPI_COLUMNS[column])]
                allocated = _sum_numbers(allocation_rows["Amount of energy consumed"])
                row[column] = (allocated or 0) / consumption_total if consumption_total not in ("", 0) else ""
            elif column in SOLAR_QUANTITY_COLUMNS:
                row[column] = _sum_numbers(source_df[column])
            elif column == "proration_component_count":
                row[column] = _sum_numbers(source_df[column])
            elif column == "source_file_count" and "source_files" in group_df.columns:
                row[column] = len([value for value in _unique_join(group_df["source_files"]).split(";") if value.strip()])
            elif column in GOLD_TEMPLATE_AGGREGATED_JOIN_COLUMNS or _is_numbered_sharepoint_link(column):
                row[column] = _unique_join(group_df[column])
            else:
                row[column] = _first_present(group_df[column])
        rows.append(row.to_dict())

    return pd.DataFrame(rows, columns=gold_template_df.columns)


def _sum_numbers(values: pd.Series) -> float | int | str:
    numeric_values = pd.to_numeric(values, errors="coerce")
    total = numeric_values.dropna().sum()
    if numeric_values.notna().any():
        return int(total) if float(total).is_integer() else float(total)
    return ""


def _first_present(values: pd.Series) -> object:
    for value in values:
        if not _is_blank(value):
            return value
    return ""


def _unique_join(values: pd.Series) -> str:
    unique_values = []
    seen = set()
    for value in values:
        for item in str(value or "").split(";"):
            text = item.strip()
            if not text:
                continue
            normalized = text.casefold()
            if normalized in seen:
                continue
            seen.add(normalized)
            unique_values.append(text)
    return "; ".join(unique_values)


def _is_blank(value: object) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return str(value).strip() == ""


def _is_numbered_sharepoint_link(column: object) -> bool:
    if not isinstance(column, str) or not column.startswith("sharepoint_link_"):
        return False
    return column.rsplit("_", 1)[1].isdigit()
