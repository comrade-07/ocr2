from pathlib import Path
from datetime import UTC, date, datetime
import html
import inspect
import os
import re
import subprocess
import sys

import pandas as pd
import streamlit as st

from src.core.config_loader import load_yaml
from src.core.path_settings import (
    bronze_output_dir,
    category_checkpoint_output_dir,
    gold_output_dir,
    manual_data_entry_upload_dir,
    silver_excel_output_dir,
)
from src.output.xlsx_writer import dataframe_to_xlsx_bytes
from src.audit.page import show_audit_report
from src.dashboard.year_over_year import (
    PREVIOUS_DATA_EXAMPLE_FILENAME,
    PREVIOUS_DATA_FILENAME,
    YOY_DIFFERENCE_THRESHOLDS,
    YearOverYearCell,
    build_year_over_year,
    high_variance_year_over_year_df,
    normalize_reporting_data,
    year_over_year_export_df,
)
from src.pipeline.run_gold_pipeline import gold_output_filename, run_gold_pipeline
from src.pipeline.run_silver_pipeline import run_silver_pipeline, silver_output_filename
from src.review.approved_silver import write_approved_silver_checkpoint
from src.review.categories import REVIEW_CATEGORIES, category_label
from src.review.duplicates import FLAGGED_DUPLICATES_FILENAME
from src.review.evidence_links import build_upload_evidence_url
from src.transform.account_mapping import (
    ACCOUNT_MAPPING_COLUMNS,
    OCR_CONTEXT_COLUMNS,
    SCOPE2_ACTIVITY_GROUPS,
    add_manual_unit_mapping_columns,
    load_account_mapping_table,
    manual_mapping_candidates,
)
from src.transform.unit_conversion import UNIT_CONVERSION_RULES, kwh_conversion_factor
from src.review.manual_decisions import (
    APPROVED_DECISIONS,
    DECISION_COLUMNS,
    MANUAL_OVERRIDE_ISSUE_PREFIX,
    MANUAL_REVIEW_DECISIONS_FILENAME,
    MANUALLY_REVIEWED_TAG,
    reopen_manual_decision_rows,
    reviewed_at_now,
)
from src.review.manual_data_entry import (
    append_manual_upload_queue_row,
    MANUAL_DATA_ENTRY_DECISIONS_FILENAME,
    MANUAL_DATA_ENTRY_FIELDS,
    MANUAL_DATA_ENTRY_QUEUE_FILENAME,
    MANUAL_ENTRY_SOURCE_UPLOAD,
    dropdown_config_path,
    entity_list_source_path,
    load_dropdown_config,
    load_entity_hierarchy,
    missing_manual_data_entry_fields,
)


ROOT_DIR = Path(__file__).parent
SETTINGS = load_yaml(ROOT_DIR / "config" / "settings.yaml")


def app_path(path: Path) -> Path:
    if path.is_absolute():
        return path
    return ROOT_DIR / path


APPROVED_SILVER_FILENAME = "step_5_approved_silver_checkpoint.csv"
STEP_2_FILENAME = "step_2_review_summary_checkpoint.csv"
STEP_3_FILENAME = "step_3_review_issues_checkpoint.csv"

DECISION_OPTIONS = ["APPROVED", "CORRECTED", "REJECTED", "NOT_APPLICABLE", "NEEDS_RETRAINING"]
MANUAL_ENTRY_COMPLETE_STATUS = "COMPLETED"
MANUAL_ENTRY_DATE_FIELDS = {
    "consumption_start_date",
    "consumption_end_date",
    "transaction_date",
}
MANUAL_ENTRY_NUMBER_FIELDS = {
    "amount_of_energy_consumed",
}
SUMMARY_FIELDS = [
    "source_file",
    "sharepoint_link",
    "source_path",
]
GOLD_TEMPLATE_SUPPLEMENTAL_COLUMNS = {
    "source_file",
    "source_files",
}
METADATA_FIELDS = {
    "source_file",
    "source_path",
    "sharepoint_link",
    "document_confidence",
    "status",
    "createdDateTime",
    "lastUpdatedDateTime",
    "apiVersion",
    "modelId",
    "needs_review",
    "missing_fields",
    "low_confidence_fields",
}
MISSING_MAPPING_COLUMNS = [
    "mapping_status",
    "mapping_method",
    "mapping_message",
    "business_mapping_issue",
    "KPI Component",
    "Energy Unit",
    "consumption_quantity_unit",
    "Consumption start date",
    "activity_group",
    "extracted_account_number",
    "source_file",
    "sharepoint_link",
    "legal_entity",
    "unit_name",
    "supplier",
    "invoice_date_normalized",
    "account_number",
]
APP_SECTION_GROUPS = {
    "Dashboard": [
        "Completeness Check",
        "Year-over-year",
        "High Variance",
    ],
    "Review and Approval": [
        "Manual Data Entry",
        "Data Approval",
        "Decision History",
        "Approved Data",
    ],
    "Monitoring and Controls": [
        "Missing Mapping",
        "Flagged Duplicates",
        "Mapping Sources",
    ],
    "Final Data": [
        "Template Output",
        "Previous Data",
    ],
    "Audit and Report": ["Allocation Report"],
}
APP_SECTIONS = [section for sections in APP_SECTION_GROUPS.values() for section in sections]
ACTIVE_SECTION_KEY = "active_review_app_section"
ACTIVE_CATEGORY_KEY = "active_review_app_category"
ACTIVE_PRIMARY_SECTION_KEY = "active_review_app_primary_section"
EXPANDED_PRIMARY_SECTION_KEY = "expanded_review_app_primary_section"
PRIMARY_SECTION_ICONS = {
    "Audit and Report": ":material/fact_check:",
    "Dashboard": ":material/dashboard:",
    "Review and Approval": ":material/rate_review:",
    "Monitoring and Controls": ":material/rule:",
    "Final Data": ":material/table_view:",
}

FACILITY_KEY_COLUMNS = ["division", "legal_entity_name", "unit"]
REPORT_KEY_COLUMNS = [*FACILITY_KEY_COLUMNS, "kpi_component"]
GOLD_FACILITY_COLUMN_ALIASES = {
    "division": "Division",
    "legal_entity_name": "Legal Entity Name",
    "unit": "Unit",
    "kpi_component": "KPI Component",
}
COMPLETENESS_DEFAULT_START = pd.Timestamp(2024, 12, 1)
COMPLETENESS_DEFAULT_END = pd.Timestamp(2025, 11, 1)
COMPLETENESS_DEFAULT_FISCAL_YEAR = 2025
PREVIOUS_DATA_FILENAMES_BY_CATEGORY = {
    "scope2": PREVIOUS_DATA_FILENAME,
}
PREVIOUS_DATA_EXAMPLE_FILENAMES_BY_CATEGORY = {
    "scope2": PREVIOUS_DATA_EXAMPLE_FILENAME,
}


st.set_page_config(page_title="ESG Document Intelligence", layout="wide")


def ensure_category_checkpoint_dirs() -> None:
    for category in REVIEW_CATEGORIES:
        app_path(category_checkpoint_output_dir(SETTINGS, category.key)).mkdir(parents=True, exist_ok=True)


ensure_category_checkpoint_dirs()


def inject_modern_styles() -> None:
    st.markdown(
        """
        <style>
        :root {
            --app-bg: #f5f8fc;
            --panel-bg: #fbfcff;
            --panel-border: #d7e2f0;
            --panel-soft: #edf4fb;
            --text-main: #142033;
            --text-muted: #5f7088;
            --accent: #1d4ed8;
            --active: #f59e0b;
            --accent-soft: #e8f0ff;
            --accent-strong: #0f2f67;
            --warm: #b7791f;
            --success: #0f766e;
        }
        .stApp {
            background:
                radial-gradient(circle at 16% 6%, rgba(29, 78, 216, 0.10), transparent 28%),
                linear-gradient(180deg, #fbfcfe 0%, var(--app-bg) 100%);
            color: var(--text-main);
        }
        [data-testid="stSidebar"] {
            background: var(--panel-bg);
            border-right: 1px solid var(--panel-border);
        }
        [data-testid="stSidebarHeader"] {
            align-items: center;
            border-bottom: 1px solid var(--panel-border);
            min-height: 3.2rem;
            position: relative;
        }
        [data-testid="stSidebarHeader"]::before {
            content: "ESG Document Intelligence";
            color: var(--text-main);
            font-size: 0.95rem;
            font-weight: 850;
            left: 1rem;
            line-height: 1.15;
            max-width: 12rem;
            position: absolute;
            top: 50%;
            transform: translateY(-50%);
        }
        [data-testid="stHeader"] {
            background: var(--panel-bg);
            border-bottom: 1px solid var(--panel-border);
        }
        [data-testid="stDecoration"] {
            background: var(--accent);
        }
        header[data-testid="stHeader"]::before {
            background: var(--panel-bg);
        }
        [data-testid="stToolbar"],
        [data-testid="stStatusWidget"],
        [data-testid="stMainMenu"] {
            color: var(--text-main);
        }
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h2,
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h3 {
            letter-spacing: 0;
        }
        div[data-testid="stButton"] > button,
        div[data-testid="stDownloadButton"] > button {
            border-radius: 8px;
            border: 1px solid var(--panel-border);
            box-shadow: none;
            font-weight: 650;
        }
        div[data-testid="stButton"] > button:hover,
        div[data-testid="stDownloadButton"] > button:hover {
            border-color: var(--accent);
            color: var(--accent-strong);
        }
        section[data-testid="stSidebar"] div[data-testid="stButton"] > button[kind="primary"] {
            background: transparent !important;
            border: 0 !important;
            border-radius: 0 !important;
            color: var(--accent-strong);
            box-shadow: none !important;
        }
        section[data-testid="stSidebar"] div[data-testid="stButton"] > button[kind="secondary"] {
            background: transparent !important;
            border: 0 !important;
            border-radius: 0 !important;
            color: var(--text-main);
            box-shadow: none !important;
        }
        section[data-testid="stSidebar"] div[data-testid="stButton"] > button {
            justify-content: flex-start !important;
            padding-left: 0.65rem;
            padding-right: 0.65rem;
            text-align: left !important;
        }
        section[data-testid="stSidebar"] div[class*="st-key-primary_nav_"] [data-testid="stTooltipHoverTarget"] {
            justify-content: flex-start !important;
        }
        section[data-testid="stSidebar"] div[class*="st-key-primary_nav_"] button {
            background: transparent !important;
            border: 0 !important;
            border-radius: 0 !important;
            box-shadow: none !important;
            justify-content: flex-start !important;
            text-align: left !important;
        }
        section[data-testid="stSidebar"] div[data-testid="stButton"] > button > div,
        section[data-testid="stSidebar"] div[class*="st-key-primary_nav_"] button > div,
        section[data-testid="stSidebar"] div[data-testid="stButton"] > button span[data-has-shortcut],
        section[data-testid="stSidebar"] div[class*="st-key-primary_nav_"] button span[data-has-shortcut],
        section[data-testid="stSidebar"] div[data-testid="stButton"] > button [data-testid="stMarkdownContainer"],
        section[data-testid="stSidebar"] div[class*="st-key-primary_nav_"] button [data-testid="stMarkdownContainer"],
        section[data-testid="stSidebar"] div[data-testid="stButton"] > button p {
            justify-content: flex-start !important;
            text-align: left !important;
            width: 100% !important;
        }
        section[data-testid="stSidebar"] div[class*="st-key-primary_nav_"] button {
            color: var(--text-main);
            padding-right: 2rem;
            position: relative;
        }
        section[data-testid="stSidebar"] div[class*="st-key-primary_nav_"] button[kind="primary"] {
            color: var(--active);
            background: transparent !important;
        }
        section[data-testid="stSidebar"] div[class*="st-key-primary_nav_"] button p {
            font-size: 14px;
            font-weight: 400;
        }
        section[data-testid="stSidebar"] div[class*="primary_nav_"][class*="_expanded"] button::after,
        section[data-testid="stSidebar"] div[class*="primary_nav_"][class*="_collapsed"] button::after {
            border-bottom: 2px solid currentColor;
            border-right: 2px solid currentColor;
            content: "";
            height: 0.42rem;
            position: absolute;
            right: 0.7rem;
            top: 50%;
            width: 0.42rem;
        }
        section[data-testid="stSidebar"] div[class*="primary_nav_"][class*="_expanded"] button::after {
            transform: translateY(-70%) rotate(45deg);
        }
        section[data-testid="stSidebar"] div[class*="primary_nav_"][class*="_collapsed"] button::after {
            transform: translateY(-50%) rotate(-45deg);
        }
        section[data-testid="stSidebar"] div[class*="st-key-nav_"] button {
            padding-left: 2.7rem;
            color: var(--text-muted);
        }
        section[data-testid="stSidebar"] div[class*="st-key-nav_"] button p {
            font-size: 14px;
            font-weight: 400;
        }
        section[data-testid="stSidebar"] div[class*="st-key-nav_"] button[kind="primary"] {
            color: var(--active);
            background: transparent !important;
        }
        section[data-testid="stSidebar"] div[data-testid="stButton"] > button:hover,
        section[data-testid="stSidebar"] div[class*="st-key-primary_nav_"] button:hover,
        section[data-testid="stSidebar"] div[class*="st-key-nav_"] button:hover {
            background: var(--accent-soft) !important;
            border-radius: 8px !important;
            color: var(--accent-strong) !important;
        }
        section[data-testid="stSidebar"] div[class*="st-key-primary_nav_"]:hover button,
        section[data-testid="stSidebar"] div[class*="st-key-nav_"]:hover button {
            background: var(--accent-soft) !important;
            border-radius: 8px !important;
            color: var(--accent-strong) !important;
        }
        div[class*="st-key-header_pipeline_button"] button,
        div[class*="st-key-header_refresh_reports_button"] button,
        div[class*="st-key-refresh_mapping_sources_button"] button {
            background: transparent !important;
            border: 0 !important;
            border-radius: 0 !important;
            box-shadow: none !important;
            color: var(--text-main);
            font-size: 14px;
            font-weight: 400;
            justify-content: flex-start !important;
            min-height: 2.25rem;
            padding: 0.35rem 0.65rem;
            text-align: left !important;
        }
        div[class*="st-key-refresh_mapping_sources_button"] {
            display: flex;
            justify-content: flex-start;
            width: fit-content;
        }
        div[class*="st-key-refresh_mapping_sources_button"] button {
            width: auto !important;
        }
        div[class*="st-key-header_pipeline_button"] button:hover,
        div[class*="st-key-header_refresh_reports_button"] button:hover,
        div[class*="st-key-refresh_mapping_sources_button"] button:hover,
        div[class*="st-key-header_pipeline_button"] button:focus,
        div[class*="st-key-header_refresh_reports_button"] button:focus,
        div[class*="st-key-refresh_mapping_sources_button"] button:focus {
            background: var(--accent-soft) !important;
            border-radius: 8px !important;
            color: var(--accent-strong) !important;
        }
        div[class*="st-key-template_output_download_excel"] button {
            background: transparent !important;
            border: 0 !important;
            border-radius: 0 !important;
            box-shadow: none !important;
            color: var(--text-main);
            font-size: 14px;
            font-weight: 400;
            min-height: 2.25rem;
            padding: 0.35rem 0.65rem;
        }
        div[class*="st-key-template_output_download_excel"] button:hover,
        div[class*="st-key-template_output_download_excel"] button:focus {
            background: var(--accent-soft) !important;
            border-radius: 8px !important;
            color: var(--accent-strong) !important;
        }
        .landing-hero {
            padding: 0 0 14px;
        }
        .landing-hero h1 {
            font-size: clamp(2rem, 3vw, 3.2rem);
            line-height: 1.05;
            margin: 0 0 8px;
            letter-spacing: 0;
        }
        .landing-hero p {
            color: var(--text-muted);
            font-size: 1rem;
            margin: 0;
            max-width: 840px;
        }
        .category-card {
            min-height: 214px;
            padding: 16px;
            border: 1px solid var(--panel-border);
            border-radius: 8px;
            background: #ffffff;
            box-shadow: 0 8px 20px rgba(20, 32, 51, 0.055);
            margin-bottom: 8px;
            transition: border-color 160ms ease, box-shadow 160ms ease, transform 160ms ease;
        }
        .category-card:hover {
            border-color: #a9bdd8;
            box-shadow: 0 12px 28px rgba(20, 32, 51, 0.09);
            transform: translateY(-1px);
        }
        .category-card-top {
            align-items: flex-start;
            display: flex;
            gap: 10px;
            justify-content: space-between;
            margin-bottom: 8px;
        }
        .category-card-title {
            color: var(--text-main);
            font-size: 1.1rem;
            font-weight: 800;
            line-height: 1.2;
        }
        .category-card-copy {
            color: var(--text-muted);
            font-size: 0.92rem;
            line-height: 1.35;
            min-height: 48px;
        }
        .status-badge {
            border-radius: 999px;
            font-size: 0.72rem;
            font-weight: 800;
            line-height: 1;
            padding: 6px 8px;
            white-space: nowrap;
        }
        .status-ready {
            background: #e7f8f3;
            color: #0f766e;
        }
        .status-watch {
            background: #fff7ed;
            color: #b45309;
        }
        .status-blocked {
            background: #fef2f2;
            color: #b42318;
        }
        .status-empty {
            background: #eef2f7;
            color: #475467;
        }
        .category-card-stats {
            display: grid;
            gap: 8px;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            margin-top: 14px;
        }
        .category-stat {
            background: #f8fafd;
            border: 1px solid #e5edf7;
            border-radius: 7px;
            min-width: 0;
            padding: 9px 10px;
        }
        .category-stat-value {
            color: var(--text-main);
            font-size: 1.08rem;
            font-weight: 850;
            line-height: 1.1;
        }
        .category-stat-label {
            color: var(--text-muted);
            font-size: 0.74rem;
            font-weight: 700;
            line-height: 1.2;
            margin-top: 3px;
        }
        .category-card-footer {
            border-top: 1px solid #edf2f7;
            color: var(--text-muted);
            font-size: 0.78rem;
            font-weight: 650;
            line-height: 1.3;
            margin-top: 14px;
            padding-top: 10px;
        }
        div[class*="st-key-landing_"] button {
            background: #ffffff !important;
            border: 1px solid #c8d6e8 !important;
            border-radius: 8px !important;
            box-shadow: none !important;
            color: var(--accent-strong) !important;
            font-size: 0.92rem;
            font-weight: 750;
            min-height: 2.45rem;
        }
        div[class*="st-key-landing_"] button:hover,
        div[class*="st-key-landing_"] button:focus {
            background: var(--accent-soft) !important;
            border-color: #9db6d8 !important;
            color: var(--accent-strong) !important;
        }
        .sidebar-kicker {
            color: var(--text-muted);
            font-size: 0.78rem;
            font-weight: 800;
            letter-spacing: 0;
            margin: 14px 0 4px;
        }
        .muted-caption {
            color: var(--text-muted);
            font-size: 0.9rem;
        }
        .completeness-table-wrap {
            border: 1px solid var(--panel-border);
            border-radius: 8px;
            max-height: 68vh;
            overflow: auto;
            background: #ffffff;
        }
        table.completeness-table {
            border-collapse: separate;
            border-spacing: 0;
            min-width: 1120px;
            width: 100%;
        }
        .completeness-table th,
        .completeness-table td {
            border-bottom: 1px solid #e6edf6;
            border-right: 1px solid #e6edf6;
            font-size: 0.78rem;
            line-height: 1.2;
            padding: 8px 9px;
            text-align: center;
            white-space: nowrap;
        }
        .completeness-table th {
            background: #f4f7fb;
            color: var(--text-main);
            font-weight: 800;
            position: sticky;
            top: 0;
            z-index: 3;
        }
        .completeness-table .facility-col {
            background: #ffffff;
            color: var(--text-main);
            left: 0;
            max-width: 230px;
            min-width: 190px;
            overflow: hidden;
            position: sticky;
            text-align: left;
            text-overflow: ellipsis;
            z-index: 2;
        }
        .completeness-table th.facility-col {
            background: #f4f7fb;
            z-index: 4;
        }
        .completeness-table .meta-col {
            color: var(--text-muted);
            text-align: left;
        }
        .complete-good {
            background: #b8ead2;
            color: #0f5f45;
            font-weight: 800;
        }
        .complete-half {
            background: #f4dd80;
            color: #7a3f0a;
            font-weight: 800;
        }
        .complete-quarter {
            background: #f4b272;
            color: #8a2f0d;
            font-weight: 800;
        }
        .complete-low {
            background: #f4a3a3;
            color: #8f1d1d;
            font-weight: 800;
        }
        .complete-none {
            background: #f1f5f9;
            color: #64748b;
        }
        .yoy-good {
            background: #b8ead2;
            color: #0f5f45;
            font-weight: 800;
        }
        .yoy-watch {
            background: #f4dd80;
            color: #7a3f0a;
            font-weight: 800;
        }
        .yoy-warning {
            background: #f4b272;
            color: #8a2f0d;
            font-weight: 800;
        }
        .yoy-alert {
            background: #f4a3a3;
            color: #8f1d1d;
            font-weight: 800;
        }
        .yoy-missing {
            background: #f1f5f9;
            color: #64748b;
        }
        @media (prefers-color-scheme: dark) {
            :root {
                --app-bg: #0c1424;
                --panel-bg: #111b2e;
                --panel-border: #263a5c;
                --panel-soft: #172642;
                --text-main: #edf4ff;
                --text-muted: #afbdd2;
                --accent: #8bb8ff;
                --active: #fbbf24;
                --accent-soft: #172b4d;
                --accent-strong: #cfe0ff;
            }
            .stApp {
                background:
                    radial-gradient(circle at 16% 6%, rgba(139, 184, 255, 0.10), transparent 28%),
                    linear-gradient(180deg, #0c1424 0%, #09111f 100%);
            }
            .category-card {
                background: #14213a;
                box-shadow: none;
            }
            .category-stat {
                background: #101b30;
            }
            .category-card-footer {
                border-top-color: #263a5c;
            }
            .completeness-table-wrap,
            .completeness-table .facility-col {
                background: #14213a;
            }
            .completeness-table th,
            .completeness-table th.facility-col {
                background: #101b30;
            }
            .completeness-table th,
            .completeness-table td {
                border-color: #263a5c;
            }
            div[class*="st-key-landing_"] button {
                background: #101b30 !important;
                border-color: #365078 !important;
                color: #cfe0ff !important;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def category_checkpoint_dir(category_key: str) -> Path:
    return app_path(category_checkpoint_output_dir(SETTINGS, category_key))


def category_paths(category_key: str) -> dict[str, Path]:
    checkpoint_dir = category_checkpoint_dir(category_key)
    bronze_dir = app_path(bronze_output_dir(SETTINGS, category_key))
    silver_dir = app_path(silver_excel_output_dir(SETTINGS, category_key))
    gold_dir = app_path(gold_output_dir(SETTINGS, category_key))
    previous_data_filename = PREVIOUS_DATA_FILENAMES_BY_CATEGORY.get(
        category_key,
        f"{category_key}_previous_data.xlsx",
    )
    previous_data_example_filename = PREVIOUS_DATA_EXAMPLE_FILENAMES_BY_CATEGORY.get(
        category_key,
        f"{category_key}_previous_data.example.xlsx",
    )
    return {
        "checkpoint_dir": checkpoint_dir,
        "bronze": bronze_dir / f"{category_key}_bronze.csv",
        "silver_reviewed": silver_dir / silver_output_filename(category_key, "reviewed"),
        "silver_normalized": silver_dir / silver_output_filename(category_key, "normalized"),
        "silver_manual_mapping": silver_dir / silver_output_filename(category_key, "manual_mapping"),
        "silver_business_mapping": silver_dir / silver_output_filename(category_key, "business_mapping"),
        "summary": checkpoint_dir / STEP_2_FILENAME,
        "issues": checkpoint_dir / STEP_3_FILENAME,
        "duplicates": checkpoint_dir / FLAGGED_DUPLICATES_FILENAME,
        "decisions": checkpoint_dir / MANUAL_REVIEW_DECISIONS_FILENAME,
        "manual_data_entry_queue": checkpoint_dir / MANUAL_DATA_ENTRY_QUEUE_FILENAME,
        "manual_data_entry_decisions": checkpoint_dir / MANUAL_DATA_ENTRY_DECISIONS_FILENAME,
        "approved": checkpoint_dir / APPROVED_SILVER_FILENAME,
        "gold_template": gold_dir / gold_output_filename(category_key, "template"),
        "gold_template_aggregated": gold_dir / gold_output_filename(category_key, "template_aggregated"),
        "previous_data": gold_dir / previous_data_filename,
        "previous_data_example": gold_dir / previous_data_example_filename,
    }


def friendly_field_name(field_name: object) -> str:
    return str(field_name).replace("_", " ").strip().title()


def read_csv(path: str) -> pd.DataFrame:
    file_path = Path(path)
    if not file_path.exists():
        return pd.DataFrame()
    return _read_csv_cached(str(file_path), file_path.stat().st_mtime_ns, file_path.stat().st_size)


@st.cache_data(show_spinner=False)
def _read_csv_cached(path: str, modified_time_ns: int, file_size: int) -> pd.DataFrame:
    file_path = Path(path)
    try:
        return pd.read_csv(file_path, dtype=object, keep_default_na=False, encoding="utf-8-sig")
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def read_excel(path: str) -> pd.DataFrame:
    file_path = Path(path)
    if not file_path.exists():
        return pd.DataFrame()
    return _read_excel_cached(str(file_path), file_path.stat().st_mtime_ns, file_path.stat().st_size)


@st.cache_data(show_spinner=False)
def _read_excel_cached(path: str, modified_time_ns: int, file_size: int) -> pd.DataFrame:
    file_path = Path(path)
    return pd.read_excel(file_path, dtype=object, keep_default_na=False)


def read_excel_fresh(path: str) -> pd.DataFrame:
    file_path = Path(path)
    if not file_path.exists():
        return pd.DataFrame()
    return pd.read_excel(file_path, dtype=object, keep_default_na=False)


def normalize_lookup_value(value: object) -> str:
    return " ".join(str(value or "").strip().lower().split())


def normalize_facility_value(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip().casefold().replace("_", " ")
    text = re.sub(r"[.'`]", "", text)
    text = re.sub(r"[\W_]+", " ", text, flags=re.UNICODE)
    return " ".join(text.split())


def truthy_value(value: object) -> bool:
    return normalize_lookup_value(value) in {"1", "true", "yes", "y", "active"}


def month_start(value: object) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    return pd.Timestamp(timestamp.year, timestamp.month, 1)


def completeness_month_starts(
    start_month: object | None = None,
    end_month: object | None = None,
    as_of: date | None = None,
) -> list[pd.Timestamp]:
    if as_of is not None and start_month is None and end_month is None:
        start_month = pd.Timestamp(as_of.year - 1, 12, 1)
        end_month = pd.Timestamp(as_of.year, 11, 1)

    start = month_start(start_month or COMPLETENESS_DEFAULT_START)
    end = month_start(end_month or COMPLETENESS_DEFAULT_END)
    if start > end:
        return []

    months = []
    current = start
    while current <= end:
        months.append(current)
        current = current + pd.DateOffset(months=1)
    return months


def completeness_month_label(month_start: pd.Timestamp) -> str:
    return month_start.strftime("%b %Y")


def fiscal_year_for_month(value: object) -> int:
    month = month_start(value)
    return month.year + 1 if month.month == 12 else month.year


def fiscal_year_months(fiscal_year: int) -> list[pd.Timestamp]:
    return completeness_month_starts(
        pd.Timestamp(fiscal_year - 1, 12, 1),
        pd.Timestamp(fiscal_year, 11, 1),
    )


def completeness_month_options(category_key: str) -> list[pd.Timestamp]:
    current_year = date.today().year
    option_start = min(COMPLETENESS_DEFAULT_START, pd.Timestamp(current_year - 1, 12, 1))
    option_end = max(COMPLETENESS_DEFAULT_END, pd.Timestamp(current_year, 11, 1))
    gold_df = read_excel(str(category_paths(category_key)["gold_template"]))

    if not gold_df.empty and "Consumption start date" in gold_df.columns:
        gold_months = pd.to_datetime(gold_df["Consumption start date"], errors="coerce").dropna()
        if not gold_months.empty:
            option_start = min(option_start, month_start(gold_months.min()))
            option_end = max(option_end, month_start(gold_months.max()))

    return completeness_month_starts(option_start, option_end)


def completeness_fiscal_year_options(category_key: str) -> list[int]:
    return sorted({fiscal_year_for_month(month) for month in completeness_month_options(category_key)})


def numeric_ratio(numerator: object, denominator: object) -> float:
    covered = pd.to_numeric(pd.Series([numerator]), errors="coerce").fillna(0).iloc[0]
    calendar = pd.to_numeric(pd.Series([denominator]), errors="coerce").fillna(0).iloc[0]
    if float(calendar) <= 0:
        return 0.0
    return max(0.0, min(float(covered) / float(calendar), 1.0))


def completeness_class(ratio: float) -> str:
    if ratio >= 1:
        return "complete-good"
    if ratio >= 0.5:
        return "complete-half"
    if ratio >= 0.25:
        return "complete-quarter"
    return "complete-low"


def facility_key_from_row(row: pd.Series, columns: dict[str, str]) -> tuple[str, str, str]:
    return tuple(normalize_facility_value(row.get(columns[column], "")) for column in FACILITY_KEY_COLUMNS)


def facility_dropdown_source_path(category_key: str = "scope2") -> Path:
    dropdown_config = load_dropdown_config(dropdown_config_path(ROOT_DIR / "config", category_key))
    return entity_list_source_path(ROOT_DIR / "config", dropdown_config)


def load_master_facilities() -> pd.DataFrame:
    master_path = facility_dropdown_source_path()
    master_stat = master_path.stat() if master_path.exists() else None

    return _load_master_facilities_cached(
        master_path=str(master_path),
        modified_time=master_stat.st_mtime if master_stat else 0,
    )


@st.cache_data(show_spinner=False)
def _load_master_facilities_cached(
    master_path: str,
    modified_time: float,
) -> pd.DataFrame:
    # modified_time is included to invalidate the cache when the CSV changes.
    master_df = read_csv(master_path)

    if master_df.empty:
        return master_df

    column_lookup = {
        normalize_lookup_value(column).replace(" ", "_"): column
        for column in master_df.columns
    }

    if any(column not in column_lookup for column in FACILITY_KEY_COLUMNS):
        return pd.DataFrame()

    result = master_df.copy()

    if "active" in column_lookup:
        active_column = column_lookup["active"]
        result = result[result[active_column].map(truthy_value)]

    result = result.rename(
        columns={
            column_lookup[column]: column
            for column in FACILITY_KEY_COLUMNS
        }
    )

    result = (
        result[[*FACILITY_KEY_COLUMNS]]
        .drop_duplicates()
        .sort_values(FACILITY_KEY_COLUMNS)
    )

    return result.reset_index(drop=True)


def load_reporting_accounts(include_issues: bool = False) -> pd.DataFrame:
    """Use the existing account mapping to define active facility/KPI expectations."""
    mapping = load_account_mapping_table(ROOT_DIR / "config").copy()
    mapping = mapping[mapping.activity_group.isin(SCOPE2_ACTIVITY_GROUPS)].copy()
    mapping = mapping.rename(columns={"legal_entity": "legal_entity_name", "unit_name": "unit"})
    mapping["kpi_component"] = "Purchased " + mapping.activity_group.str.lower()
    master = load_master_facilities()
    active_keys = {facility_key_from_row(row, {column: column for column in FACILITY_KEY_COLUMNS})
                   for _, row in master.iterrows()}
    mapping = mapping.loc[[facility_key_from_row(row, {column: column for column in FACILITY_KEY_COLUMNS})
                           in active_keys for _, row in mapping.iterrows()]].copy()
    mapping["account_number"] = mapping.account_number.map(normalize_lookup_value)
    mapping["mapping_message"] = ""
    mapping.loc[mapping.account_number.eq(""), "mapping_message"] = "Missing expected account number"
    for column in ("effective_start_date", "effective_end_date"):
        values = mapping.get(column, pd.Series("", index=mapping.index)).fillna("")
        parsed = pd.to_datetime(values, errors="coerce")
        invalid_date = values.astype(str).str.strip().ne("") & parsed.isna()
        mapping.loc[invalid_date, "mapping_message"] = f"Invalid {column} in the shared account mapping"
        mapping[column] = parsed.dt.normalize()
    mapping.loc[mapping.effective_end_date < mapping.effective_start_date, "mapping_message"] = "Account effective end date precedes its start date"
    keys = mapping[REPORT_KEY_COLUMNS].map(normalize_facility_value)
    keys["account_number"] = mapping.account_number
    mapping.loc[keys.duplicated(keep=False), "mapping_message"] = "Duplicate facility/KPI/account rows in the shared mapping"
    return mapping if include_issues else mapping.loc[mapping.mapping_message.eq("")].copy()


def build_gold_completeness(
    category_key: str,
    start_month: object | None = None,
    end_month: object | None = None,
    as_of: date | None = None,
) -> tuple[pd.DataFrame, list[pd.Timestamp], int]:
    months = completeness_month_starts(start_month, end_month, as_of)
    accounts = load_reporting_accounts()
    business = read_excel(str(category_paths(category_key)["silver_business_mapping"]))
    required_columns = {*GOLD_FACILITY_COLUMN_ALIASES.values(), "Account number", "Energy Unit",
                        "business_mapping_issue", "proration_split_keys"}
    if not business.empty and not required_columns.issubset(business.columns):
        raise ValueError("Completeness inputs lack current KPI, account or allocation metadata. Rebuild Silver and Gold.")
    coverage = {}
    for _, row in business.iterrows():
        if str(row.get("business_mapping_issue", "")).strip():
            continue
        if kwh_conversion_factor(row.get("Energy Unit", "")) is None:
            continue
        key = tuple(normalize_facility_value(row.get(GOLD_FACILITY_COLUMN_ALIASES[column], ""))
                    for column in REPORT_KEY_COLUMNS)
        account = normalize_lookup_value(row.get("Account number", ""))
        days = coverage.setdefault((key, account), set())
        # Lineage contains exact segments from both OCR and manual monthly rollups.
        # Unioning dates avoids counting overlapping invoices or allocation rows twice.
        for split_key in str(row.get("proration_split_keys", "")).split(";"):
            fields = split_key.strip().rsplit("|", 3)
            if len(fields) != 4:
                continue
            start, end = pd.to_datetime(fields[-2:], errors="coerce")
            if pd.notna(start) and pd.notna(end) and start <= end:
                days.update(pd.date_range(start.normalize(), end.normalize()))
    records = []
    facilities_with_data = set()
    for identity, group in accounts.groupby(REPORT_KEY_COLUMNS, sort=True, dropna=False):
        record = dict(zip(REPORT_KEY_COLUMNS, identity))
        key = tuple(normalize_facility_value(value) for value in identity)
        for month in months:
            covered = expected = 0
            for _, account in group.iterrows():
                start = max(month, account.effective_start_date) if pd.notna(account.effective_start_date) else month
                month_end = month + pd.offsets.MonthEnd(0)
                end = min(month_end, account.effective_end_date) if pd.notna(account.effective_end_date) else month_end
                expected_days = set(pd.date_range(start, end)) if start <= end else set()
                expected += len(expected_days)
                covered += len(expected_days & coverage.get((key, account.account_number), set()))
            record[completeness_month_label(month)] = {
                "ratio": covered / expected if expected else float("nan"),
                "covered_days": covered, "calendar_days": expected,
            }
            if covered:
                facilities_with_data.add(key[:3])
        records.append(record)
    return (pd.DataFrame(records, columns=[*REPORT_KEY_COLUMNS, *[completeness_month_label(m) for m in months]]),
            months, len(facilities_with_data))


def completeness_export_df(completeness_df: pd.DataFrame, months: list[pd.Timestamp]) -> pd.DataFrame:
    result = completeness_df[[*REPORT_KEY_COLUMNS]].rename(
        columns={
            "division": "Division",
            "legal_entity_name": "Legal Entity Name",
            "unit": "Unit",
            "kpi_component": "KPI Component",
        }
    )
    for month in months:
        label = completeness_month_label(month)
        result[label] = completeness_df[label].map(lambda value: round(float(value.get("ratio", 0.0)), 4))
    return result


def render_completeness_heatmap(completeness_df: pd.DataFrame, months: list[pd.Timestamp]) -> None:
    header_cells = [
        '<th class="facility-col">Division</th>',
        '<th class="meta-col">Legal Entity</th>',
        '<th class="meta-col">Unit</th>',
        '<th class="meta-col">KPI Component</th>',
        *[f"<th>{safe_html(completeness_month_label(month))}</th>" for month in months],
    ]
    body_rows = []
    for _, row in completeness_df.iterrows():
        cells = [
            f'<td class="facility-col" title="{safe_html(row.get("division", ""))}">{safe_html(row.get("division", ""))}</td>',
            f'<td class="meta-col">{safe_html(row.get("legal_entity_name", ""))}</td>',
            f'<td class="meta-col">{safe_html(row.get("unit", ""))}</td>',
            f'<td class="meta-col">{safe_html(row.get("kpi_component", ""))}</td>',
        ]
        for month in months:
            label = completeness_month_label(month)
            value = row.get(label, {"ratio": 0.0, "covered_days": 0, "calendar_days": month.days_in_month})
            ratio = float(value.get("ratio", 0.0))
            covered_days = value.get("covered_days", 0)
            calendar_days = value.get("calendar_days", month.days_in_month)
            display_value = "N/A" if pd.isna(ratio) else ("100%" if ratio >= 1 else f"{ratio:.0%}")
            title = f"{covered_days} of {calendar_days} expected account-days" if calendar_days else "Outside account effective dates"
            cells.append(f'<td class="{completeness_class(ratio)}" title="{safe_html(title)}">{display_value}</td>')
        body_rows.append(f"<tr>{''.join(cells)}</tr>")

    st.markdown(
        f"""
        <div class="completeness-table-wrap">
            <table class="completeness-table">
                <thead><tr>{''.join(header_cells)}</tr></thead>
                <tbody>{''.join(body_rows)}</tbody>
            </table>
        </div>
        """,
        unsafe_allow_html=True,
    )


@st.cache_data(show_spinner=False)
def load_mapping_sources() -> list[dict[str, str]]:
    config_path = ROOT_DIR / "config" / "mapping_files.yaml"
    if not config_path.exists():
        config_path = ROOT_DIR / "config" / "mapping_files.example.yaml"

    config = load_yaml(config_path)
    sources = []
    for source_key, item in (config.get("mapping_files") or {}).items():
        workbook_path = Path(item.get("path", ""))
        if not workbook_path.is_absolute():
            workbook_path = ROOT_DIR / workbook_path
        sources.append(
            {
                "key": str(source_key),
                "name": friendly_field_name(source_key),
                "file_name": workbook_path.name,
                "source_type": str(item.get("sheet_name", "")) or "Workbook",
                "path": str(workbook_path.resolve()),
            }
        )
    facility_dropdown_path = facility_dropdown_source_path()
    sources.append(
        {
            "key": "facility_dropdown",
            "name": "Facility Dropdown",
            "file_name": facility_dropdown_path.name,
            "source_type": "CSV",
            "path": str(facility_dropdown_path.resolve()),
        }
    )
    return sources


def open_mapping_file(path: str) -> tuple[bool, str]:
    mapping_path = Path(path)
    if not mapping_path.exists():
        return False, f"Mapping source not found: {mapping_path}"
    try:
        if sys.platform.startswith("win"):
            os.startfile(mapping_path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(mapping_path)])
        else:
            subprocess.Popen(["xdg-open", str(mapping_path)])
    except Exception as exc:
        return False, f"Could not open mapping source: {exc}"
    return True, f"Opened {mapping_path.name}. Save changes, then refresh this app."


def clear_cached_data() -> None:
    _read_csv_cached.clear()
    _read_excel_cached.clear()
    load_mapping_sources.clear()


def run_pipeline(category_key: str) -> tuple[bool, str]:
    result = subprocess.run(
        [sys.executable, "main.py", "--category", category_key],
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    output = "\n".join(part for part in [result.stdout, result.stderr] if part)
    return result.returncode == 0, output


def refresh_reports(category_key: str) -> tuple[bool, str]:
    try:
        run_silver_pipeline(config_dir=ROOT_DIR / "config", invoice_type=category_key)
        output = run_gold_pipeline(config_dir=ROOT_DIR / "config", invoice_type=category_key)
    except Exception as exc:
        return False, str(exc)
    finally:
        # A failed build may still have changed some output files.
        clear_cached_data()
    return True, str(output)


def show_saved_message(message: str) -> None:
    st.session_state["review_saved_message"] = message
    st.rerun()


def load_data(category_key: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    paths = category_paths(category_key)
    summary_df = read_csv(str(paths["summary"]))
    issues_df = read_csv(str(paths["issues"]))
    decisions_df = read_csv(str(paths["decisions"]))
    bronze_df = read_csv(str(paths["bronze"]))
    return summary_df, issues_df, decisions_df, bronze_df


def load_duplicate_data(category_key: str) -> pd.DataFrame:
    return read_csv(str(category_paths(category_key)["duplicates"]))


def line_key(row: pd.Series) -> tuple[str, str]:
    return str(row.get("invoice_id", "")), str(row.get("line_id", ""))


def data_line_key(row: pd.Series, index: int) -> tuple[str, str]:
    return str(row.get("invoice_id") or row.get("source_file") or ""), str(row.get("line_id") or index + 1)


def build_open_queue(
    summary_df: pd.DataFrame,
    issues_df: pd.DataFrame,
    decisions_df: pd.DataFrame,
) -> pd.DataFrame:
    if summary_df.empty or issues_df.empty:
        return pd.DataFrame(columns=summary_df.columns)

    approved_issue_ids = set()
    if not decisions_df.empty:
        approved_decisions = decisions_df[
            decisions_df["review_decision"].astype(str).str.upper().isin(APPROVED_DECISIONS)
        ]
        approved_issue_ids = set(approved_decisions["issue_id"].astype(str))

    open_issues = issues_df[~issues_df["issue_id"].astype(str).isin(approved_issue_ids)]
    open_keys = {
        (str(row["invoice_id"]), str(row["line_id"]))
        for _, row in open_issues.iterrows()
    }

    return summary_df[
        summary_df.apply(lambda row: line_key(row) in open_keys, axis=1)
    ].copy()


def build_invoice_options(summary_df: pd.DataFrame) -> list[tuple[str, str]]:
    options = []
    for _, row in summary_df.iterrows():
        options.append((str(row.get("invoice_id", "")), str(row.get("line_id", ""))))
    return options


def selected_summary_row(summary_df: pd.DataFrame, option: tuple[str, str]) -> pd.Series:
    invoice_id, line_id = option
    return summary_df[
        (summary_df["invoice_id"].astype(str) == invoice_id)
        & (summary_df["line_id"].astype(str) == line_id)
    ].iloc[0]


def invoice_option_label(option: tuple[str, str]) -> str:
    invoice_id, line_id = option
    return invoice_id if line_id in ("", "1") else f"{invoice_id} - line {line_id}"


def selected_data_row(data_df: pd.DataFrame, invoice_id: str, line_id: str) -> pd.Series | None:
    for index, row in data_df.iterrows():
        if data_line_key(row, index) == (invoice_id, line_id):
            return row
    return None


def decisions_for_invoice(decisions_df: pd.DataFrame, invoice_id: str, line_id: str) -> pd.DataFrame:
    if decisions_df.empty:
        return pd.DataFrame()
    return decisions_df[
        (decisions_df["invoice_id"].astype(str) == invoice_id)
        & (decisions_df["line_id"].astype(str) == line_id)
    ].copy()


def issues_for_invoice(issues_df: pd.DataFrame, invoice_id: str, line_id: str) -> pd.DataFrame:
    if issues_df.empty:
        return pd.DataFrame()
    return issues_df[
        (issues_df["invoice_id"].astype(str) == invoice_id)
        & (issues_df["line_id"].astype(str) == line_id)
    ].copy()


def update_decision(
    decisions_df: pd.DataFrame,
    issue_id: str,
    corrected_value: str,
    review_decision: str,
    reviewed_by: str,
    review_comment: str,
    issue_row: pd.Series | None = None,
) -> pd.DataFrame:
    updated_df = decisions_df.copy()
    for column in DECISION_COLUMNS:
        if column not in updated_df.columns:
            updated_df[column] = ""

    mask = updated_df["issue_id"].astype(str) == issue_id
    if not mask.any():
        issue = issue_row if issue_row is not None else pd.Series(dtype=object)
        new_row = {
            "decision_id": f"decision_{issue_id}",
            "issue_id": issue_id,
            "invoice_id": issue.get("invoice_id", ""),
            "line_id": issue.get("line_id", ""),
            "field_name": issue.get("field_name", ""),
            "original_value": issue.get("ocr_value", ""),
            "corrected_value": "",
            "review_decision": "",
            "review_tag": "",
            "reviewed_by": "",
            "reviewed_at": "",
            "review_comment": "",
        }
        updated_df = pd.concat([updated_df, pd.DataFrame([new_row])], ignore_index=True, sort=False)
        mask = updated_df["issue_id"].astype(str) == issue_id

    updated_df.loc[mask, "corrected_value"] = corrected_value
    updated_df.loc[mask, "review_decision"] = review_decision
    updated_df.loc[mask, "review_tag"] = MANUALLY_REVIEWED_TAG
    updated_df.loc[mask, "reviewed_by"] = reviewed_by
    updated_df.loc[mask, "reviewed_at"] = reviewed_at_now()
    updated_df.loc[mask, "review_comment"] = review_comment
    return updated_df


def synthetic_override_issue(
    invoice_id: str,
    line_id: str,
    field_name: str,
    original_value: object,
) -> pd.Series:
    safe_field_name = re.sub(r"[^A-Za-z0-9_]+", "_", field_name).strip("_")
    safe_invoice = re.sub(r"[^A-Za-z0-9_]+", "_", invoice_id).strip("_")
    safe_line = re.sub(r"[^A-Za-z0-9_]+", "_", line_id).strip("_") or "1"
    return pd.Series(
        {
            "issue_id": f"{MANUAL_OVERRIDE_ISSUE_PREFIX}{safe_invoice}_{safe_line}_{safe_field_name}",
            "invoice_id": invoice_id,
            "line_id": line_id,
            "field_name": field_name,
            "ocr_value": original_value,
            "issue_type": "Manual override",
            "confidence": "",
            "threshold": "",
        }
    )


def save_decisions(decisions_df: pd.DataFrame, category_key: str) -> None:
    decisions_file = category_paths(category_key)["decisions"]
    decisions_file.parent.mkdir(parents=True, exist_ok=True)
    decisions_df.to_csv(decisions_file, index=False, encoding="utf-8-sig")


def save_manual_data_entry_decisions(decisions_df: pd.DataFrame, category_key: str) -> None:
    decisions_file = category_paths(category_key)["manual_data_entry_decisions"]
    decisions_file.parent.mkdir(parents=True, exist_ok=True)
    decisions_df.to_csv(decisions_file, index=False, encoding="utf-8-sig")


def save_manual_data_entry_queue(queue_df: pd.DataFrame, category_key: str) -> None:
    queue_file = category_paths(category_key)["manual_data_entry_queue"]
    queue_file.parent.mkdir(parents=True, exist_ok=True)
    queue_df.to_csv(queue_file, index=False, encoding="utf-8-sig")


def load_manual_data_entry_data(category_key: str) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    paths = category_paths(category_key)
    queue_df = read_csv(str(paths["manual_data_entry_queue"]))
    decisions_df = read_csv(str(paths["manual_data_entry_decisions"]))
    try:
        dropdown_config = load_dropdown_config(dropdown_config_path(ROOT_DIR / "config", category_key))
        entity_hierarchy = load_entity_hierarchy(ROOT_DIR / "config", dropdown_config)
        if entity_hierarchy:
            dropdown_config.setdefault("validation", {})["division_legal_entity_unit"] = entity_hierarchy
    except FileNotFoundError:
        dropdown_config = {"fields": {}, "validation": {}}
    if category_key == "scope2":
        dropdown_config.setdefault("fields", {}).setdefault("energy_unit", {})["options"] = [
            rule.from_unit for rule in UNIT_CONVERSION_RULES
        ]
    return queue_df, decisions_df, dropdown_config


def manual_entry_key(row: pd.Series) -> tuple[str, str]:
    return str(row.get("invoice_id", "")), str(row.get("line_id", ""))


def build_open_manual_entry_queue(queue_df: pd.DataFrame, decisions_df: pd.DataFrame) -> pd.DataFrame:
    if queue_df.empty:
        return queue_df.copy()
    completed_keys = set()
    if not decisions_df.empty and "manual_entry_status" in decisions_df.columns:
        completed = decisions_df[
            decisions_df["manual_entry_status"].astype(str).str.upper() == MANUAL_ENTRY_COMPLETE_STATUS
        ]
        completed_keys = {manual_entry_key(row) for _, row in completed.iterrows()}
    return queue_df[
        queue_df.apply(lambda row: manual_entry_key(row) not in completed_keys, axis=1)
    ].copy()


def upsert_manual_data_entry_decision(
    decisions_df: pd.DataFrame,
    source_row: pd.Series,
    entered_values: dict[str, object],
    reviewed_by: str,
    review_comment: str,
) -> pd.DataFrame:
    base_row = source_row.to_dict()
    base_row.update(entered_values)
    base_row["manual_entry_status"] = MANUAL_ENTRY_COMPLETE_STATUS
    base_row["reviewed_by"] = reviewed_by
    base_row["reviewed_at"] = reviewed_at_now()
    base_row["review_comment"] = review_comment

    if decisions_df.empty:
        return pd.DataFrame([base_row])

    updated_df = decisions_df.copy()
    key = manual_entry_key(pd.Series(base_row))
    mask = updated_df.apply(lambda row: manual_entry_key(row) == key, axis=1)
    if mask.any():
        for column, value in base_row.items():
            if column not in updated_df.columns:
                updated_df[column] = ""
            updated_df.loc[mask, column] = value
        return updated_df

    return pd.concat([updated_df, pd.DataFrame([base_row])], ignore_index=True, sort=False)


def manual_upload_dir(category_key: str) -> Path:
    paths = SETTINGS.get("paths", {})
    upload_dir = app_path(manual_data_entry_upload_dir(SETTINGS, category_key))
    if f"manual_data_entry_uploads_{category_key}" in paths:
        return upload_dir
    return upload_dir / category_key


def save_manual_upload(uploaded_file, category_key: str) -> Path:
    upload_dir = manual_upload_dir(category_key)
    upload_dir.mkdir(parents=True, exist_ok=True)
    uploaded_at = datetime.now(UTC).replace(microsecond=0).strftime("%Y%m%dT%H%M%SZ")
    safe_name = safe_uploaded_filename(uploaded_file.name)
    target = upload_dir / f"{uploaded_at}_{safe_name}"
    evidence_settings = SETTINGS.get("manual_upload_evidence", {})
    folder_urls = evidence_settings.get("sharepoint_folder_urls", {})
    folder_url = folder_urls.get(category_key, "")
    sharepoint_link = build_upload_evidence_url(target, upload_dir, folder_url)
    target.write_bytes(uploaded_file.getbuffer())
    append_manual_upload_queue_row(
        category_paths(category_key)["manual_data_entry_queue"],
        uploaded_file_name=uploaded_file.name,
        stored_file_path=target,
        uploaded_at=datetime.now(UTC).replace(microsecond=0).isoformat(),
        sharepoint_link=sharepoint_link,
    )
    return target


def safe_uploaded_filename(filename: str) -> str:
    path = Path(filename)
    safe_stem = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in path.stem).strip("_")
    safe_suffix = "".join(char if char.isalnum() or char == "." else "" for char in path.suffix)
    return f"{safe_stem or 'uploaded_invoice'}{safe_suffix}"


def refresh_approved_silver(
    data_df: pd.DataFrame,
    summary_df: pd.DataFrame,
    decisions_df: pd.DataFrame,
    category_key: str,
) -> Path:
    checkpoint_dir = category_paths(category_key)["checkpoint_dir"]
    return write_approved_silver_checkpoint(
        data_df,
        summary_df.to_dict("records"),
        decisions_df.to_dict("records"),
        checkpoint_dir,
    )


def show_invoice_summary(summary_row: pd.Series, data_row: pd.Series | None) -> None:
    status = str(summary_row.get("review_status", ""))
    severity = str(summary_row.get("review_severity", ""))
    st.markdown(
        f"""
        <div style="border:1px solid #d0d7de; border-radius:6px; padding:12px 14px; margin:0 0 14px 0; overflow:hidden;">
            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap:12px; align-items:stretch;">
                <div style="min-width:0;">
                    <div style="font-size:13px; color:#475467; font-weight:600; margin-bottom:5px;">Status</div>
                    <div style="font-size:16px; line-height:1.25; font-weight:700; color:{_status_color(status)}; overflow-wrap:anywhere;">{status}</div>
                </div>
                <div style="min-width:0;">
                    <div style="font-size:13px; color:#475467; font-weight:600; margin-bottom:5px;">Severity</div>
                    <div style="font-size:16px; line-height:1.25; font-weight:700; color:{_severity_color(severity)}; overflow-wrap:anywhere;">{severity}</div>
                </div>
                <div style="min-width:0; text-align:left;">
                    <div style="font-size:13px; color:#475467; font-weight:600; margin-bottom:5px;">Review Issues</div>
                    <div style="font-size:22px; line-height:1.1; font-weight:800; color:#175cd3; overflow-wrap:anywhere;">{summary_row.get("review_issue_count", "")}</div>
                </div>
                <div style="min-width:0; text-align:left;">
                    <div style="font-size:13px; color:#475467; font-weight:600; margin-bottom:5px;">Critical Issues</div>
                    <div style="font-size:22px; line-height:1.1; font-weight:800; color:#b42318; overflow-wrap:anywhere;">{summary_row.get("critical_issue_count", "")}</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if data_row is None:
        st.warning("No matching Bronze row was found for this invoice.")
        return

    link = str(data_row.get("sharepoint_link", "")).strip()
    if link:
        st.link_button("Open Source File", link)
    else:
        source_path = str(data_row.get("source_path", "")).strip()
        if source_path:
            st.caption(f"Source path: {source_path}")

    detail_rows = build_invoice_detail_rows(data_row, summary_row)
    st.subheader("Invoice Details")
    details_df = pd.DataFrame(detail_rows)
    st.table(details_df)


def build_invoice_detail_rows(data_row: pd.Series, summary_row: pd.Series | None = None) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    low_confidence_fields = _split_field_list(summary_row.get("low_confidence_fields", "")) if summary_row is not None else set()
    missing_required_fields = _split_field_list(summary_row.get("missing_required_fields", "")) if summary_row is not None else set()
    failed_fields = _split_field_list(summary_row.get("failed_fields", "")) if summary_row is not None else set()

    for field in SUMMARY_FIELDS:
        if field in data_row.index:
            rows.append(
                {
                    "Field": friendly_field_name(field),
                    "Value": data_row.get(field, ""),
                    "Confidence": "",
                    "Review Status": "",
                }
            )

    for field in data_row.index:
        field_name = str(field)
        if field_name in METADATA_FIELDS or field_name.endswith("_confidence") or field_name.endswith("_normalized"):
            continue
        confidence_field = f"{field_name}_confidence"
        if confidence_field not in data_row.index:
            continue
        rows.append(
            {
                "Field": friendly_field_name(field_name),
                "Value": data_row.get(field_name, ""),
                "Confidence": data_row.get(confidence_field, ""),
                "Review Status": _field_review_status(field_name, low_confidence_fields, missing_required_fields, failed_fields),
            }
        )
    return rows


def editable_ocr_fields(data_row: pd.Series | None) -> list[str]:
    if data_row is None:
        return []
    fields = []
    for field in data_row.index:
        field_name = str(field)
        if field_name in METADATA_FIELDS or field_name.endswith("_confidence") or field_name.endswith("_normalized"):
            continue
        if f"{field_name}_confidence" in data_row.index:
            fields.append(field_name)
    return fields


def _split_field_list(value: object) -> set[str]:
    return {field.strip() for field in str(value or "").split(";") if field.strip()}


def _field_review_status(
    field_name: str,
    low_confidence_fields: set[str],
    missing_required_fields: set[str],
    failed_fields: set[str],
) -> str:
    if field_name in missing_required_fields:
        return "Missing Required"
    if field_name in low_confidence_fields:
        return "Low Confidence"
    if field_name in failed_fields:
        return "Review Required"
    return "Pass"


def _status_color(status: str) -> str:
    if status == "BLOCKED":
        return "#b42318"
    if status == "REVIEW_REQUIRED":
        return "#b54708"
    if status == "AUTO_RESOLVED_WITH_WARNING":
        return "#175cd3"
    if status == "AUTO_APPROVED":
        return "#067647"
    return "#24292f"


def _severity_color(severity: str) -> str:
    if severity == "HIGH":
        return "#b54708"
    if severity == "MEDIUM":
        return "#175cd3"
    if severity == "LOW":
        return "#067647"
    return "#24292f"


def show_review_form(
    invoice_issues: pd.DataFrame,
    invoice_decisions: pd.DataFrame,
    decisions_df: pd.DataFrame,
    data_df: pd.DataFrame,
    summary_df: pd.DataFrame,
    summary_row: pd.Series,
    data_row: pd.Series | None,
    category_key: str,
) -> None:
    reviewer_name = st.text_input("Reviewer", value=st.session_state.get("reviewer_name", ""))
    st.session_state["reviewer_name"] = reviewer_name

    updated_decisions = decisions_df.copy()
    if invoice_issues.empty:
        st.success("No editable failed fields for this invoice.")
    else:
        st.subheader("Failed Fields")
        for _, issue in invoice_issues.iterrows():
            issue_id = str(issue["issue_id"])
            decision = invoice_decisions[invoice_decisions["issue_id"].astype(str) == issue_id]
            decision_row = decision.iloc[0] if not decision.empty else pd.Series(dtype=object)
            field_name = str(issue.get("field_name", ""))
            field_label = friendly_field_name(field_name)
            current_decision = str(decision_row.get("review_decision", "") or "")
            decision_index = DECISION_OPTIONS.index(current_decision) if current_decision in DECISION_OPTIONS else 0
            corrected_default = str(decision_row.get("corrected_value", "") or issue.get("ocr_value", "") or "")

            with st.form(key=f"issue_form_{issue_id}", border=True):
                cols = st.columns([1.2, 1, 1])
                cols[0].markdown(f"**{field_label}**")
                cols[1].caption(f"Issue: {issue.get('issue_type', '')}")
                cols[2].caption(f"Confidence: {issue.get('confidence', '')} / {issue.get('threshold', '')}")

                st.text_input("OCR value", value=str(issue.get("ocr_value", "")), disabled=True, key=f"ocr_{issue_id}")
                corrected_value = st.text_input(
                    "Corrected value",
                    value=corrected_default,
                    key=f"corrected_{issue_id}",
                )
                review_decision = st.selectbox(
                    "Decision",
                    DECISION_OPTIONS,
                    index=decision_index,
                    key=f"decision_{issue_id}",
                )
                review_comment = st.text_area(
                    "Comment",
                    value=str(decision_row.get("review_comment", "")),
                    key=f"comment_{issue_id}",
                )

                if st.form_submit_button("Save Field"):
                    updated_decisions = update_decision(
                        updated_decisions,
                        issue_id,
                        corrected_value,
                        review_decision,
                        reviewer_name,
                        review_comment,
                        issue,
                    )
                    save_decisions(updated_decisions, category_key)
                    refresh_approved_silver(data_df, summary_df, updated_decisions, category_key)
                    show_saved_message(f"Saved {field_label} as {review_decision}. Refresh Reports to update reports.")

    show_manual_override_form(
        invoice_decisions,
        updated_decisions,
        data_df,
        summary_df,
        summary_row,
        data_row,
        reviewer_name,
        category_key,
    )


def show_manual_override_form(
    invoice_decisions: pd.DataFrame,
    decisions_df: pd.DataFrame,
    data_df: pd.DataFrame,
    summary_df: pd.DataFrame,
    summary_row: pd.Series,
    data_row: pd.Series | None,
    reviewer_name: str,
    category_key: str,
) -> None:
    fields = editable_ocr_fields(data_row)
    if not fields or data_row is None:
        return

    st.subheader("Override Approved Data")
    invoice_id, line_id = line_key(summary_row)
    selected_field = st.selectbox(
        "Field",
        fields,
        format_func=friendly_field_name,
        key=f"override_field_{invoice_id}_{line_id}",
    )
    original_value = data_row.get(selected_field, "")
    override_issue = synthetic_override_issue(invoice_id, line_id, selected_field, original_value)
    issue_id = str(override_issue["issue_id"])
    existing = invoice_decisions[invoice_decisions["issue_id"].astype(str) == issue_id]
    existing_row = existing.iloc[0] if not existing.empty else pd.Series(dtype=object)
    current_decision = str(existing_row.get("review_decision", "CORRECTED") or "CORRECTED")
    decision_index = DECISION_OPTIONS.index(current_decision) if current_decision in DECISION_OPTIONS else DECISION_OPTIONS.index("CORRECTED")
    corrected_default = str(existing_row.get("corrected_value", original_value) or "")

    with st.form(key=f"override_form_{issue_id}", border=True):
        confidence = data_row.get(f"{selected_field}_confidence", "")
        cols = st.columns([1.2, 1])
        cols[0].markdown(f"**{friendly_field_name(selected_field)}**")
        cols[1].caption(f"Confidence: {confidence}")
        st.text_input("OCR value", value=str(original_value or ""), disabled=True, key=f"override_ocr_{issue_id}")
        corrected_value = st.text_input(
            "Corrected value",
            value=corrected_default,
            key=f"override_corrected_{issue_id}",
        )
        review_decision = st.selectbox(
            "Decision",
            DECISION_OPTIONS,
            index=decision_index,
            key=f"override_decision_{issue_id}",
        )
        review_comment = st.text_area(
            "Comment",
            value=str(existing_row.get("review_comment", "")),
            key=f"override_comment_{issue_id}",
        )
        st.caption("Use CORRECTED with a blank corrected value to intentionally clear a bad OCR value.")

        if st.form_submit_button("Save Override"):
            updated_decisions = update_decision(
                decisions_df,
                issue_id,
                corrected_value,
                review_decision,
                reviewer_name,
                review_comment,
                override_issue,
            )
            save_decisions(updated_decisions, category_key)
            refresh_approved_silver(data_df, summary_df, updated_decisions, category_key)
            show_saved_message(f"Saved override for {friendly_field_name(selected_field)}. Refresh Reports to update reports.")


def selected_category_key() -> str | None:
    selected_key = st.session_state.get(ACTIVE_CATEGORY_KEY)
    valid_keys = {category.key for category in REVIEW_CATEGORIES}
    return selected_key if selected_key in valid_keys else None


def select_category(category_key: str) -> None:
    st.session_state[ACTIVE_CATEGORY_KEY] = category_key
    if st.session_state.get(ACTIVE_SECTION_KEY) not in APP_SECTIONS:
        st.session_state[ACTIVE_SECTION_KEY] = APP_SECTIONS[0]


def return_home() -> None:
    st.session_state[ACTIVE_CATEGORY_KEY] = None


def safe_html(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def count_rows(df: pd.DataFrame) -> int:
    return 0 if df.empty else len(df)


def latest_modified_at(paths: list[Path]) -> datetime | None:
    timestamps = [path.stat().st_mtime for path in paths if path.exists()]
    if not timestamps:
        return None
    return datetime.fromtimestamp(max(timestamps))


def format_latest_modified(value: datetime | None) -> str:
    if value is None:
        return "No checkpoints"
    return value.strftime("%b %d, %H:%M")


def missing_mapping_count(category_key: str) -> int:
    return count_rows(load_missing_mapping_rows(category_key, include_all_categories=False))


def category_dashboard_summary(category_key: str) -> dict[str, object]:
    paths = category_paths(category_key)
    summary_df, issues_df, decisions_df, bronze_df = load_data(category_key)
    open_queue_df = build_open_queue(summary_df, issues_df, decisions_df)
    manual_queue_df, manual_decisions_df, _ = load_manual_data_entry_data(category_key)
    open_manual_df = build_open_manual_entry_queue(manual_queue_df, manual_decisions_df)
    duplicate_df = load_duplicate_data(category_key)
    approved_df = read_csv(str(paths["approved"]))

    high_severity_count = 0
    if not open_queue_df.empty and "review_severity" in open_queue_df.columns:
        high_severity_count = int((open_queue_df["review_severity"].astype(str).str.upper() == "HIGH").sum())

    counts = {
        "records": count_rows(bronze_df) or count_rows(summary_df),
        "open_reviews": count_rows(open_queue_df),
        "high_severity": high_severity_count,
        "manual_entries": count_rows(open_manual_df),
        "missing_mapping": missing_mapping_count(category_key),
        "duplicates": count_rows(duplicate_df),
        "approved": count_rows(approved_df),
    }

    if counts["records"] == 0 and counts["manual_entries"] == 0:
        status_label = "No data"
        status_class = "status-empty"
    elif counts["high_severity"] > 0 or counts["missing_mapping"] > 0:
        status_label = "Needs attention"
        status_class = "status-blocked"
    elif counts["open_reviews"] > 0 or counts["manual_entries"] > 0 or counts["duplicates"] > 0:
        status_label = "In progress"
        status_class = "status-watch"
    else:
        status_label = "Ready"
        status_class = "status-ready"

    latest = latest_modified_at(
        [
            paths["summary"],
            paths["issues"],
            paths["decisions"],
            paths["manual_data_entry_queue"],
            paths["manual_data_entry_decisions"],
            paths["approved"],
            paths["duplicates"],
            paths["gold_template"],
            paths["gold_template_aggregated"],
        ]
    )

    return {
        "category_key": category_key,
        "status_label": status_label,
        "status_class": status_class,
        "latest_modified": latest,
        **counts,
    }


def dashboard_summaries() -> list[dict[str, object]]:
    return [category_dashboard_summary(category.key) for category in REVIEW_CATEGORIES]


def render_workspace_summary(summaries: list[dict[str, object]]) -> None:
    totals = [
        ("Streams", len(summaries)),
        ("Open Reviews", sum(int(summary["open_reviews"]) for summary in summaries)),
        ("Manual Entry", sum(int(summary["manual_entries"]) for summary in summaries)),
        ("Mapping Gaps", sum(int(summary["missing_mapping"]) for summary in summaries)),
        ("Approved Rows", sum(int(summary["approved"]) for summary in summaries)),
    ]
    for column, (label, value) in zip(st.columns(len(totals)), totals, strict=True):
        column.metric(label, value)


def render_category_card(category, summary: dict[str, object], copy: str) -> None:
    status_label = safe_html(summary["status_label"])
    status_class = safe_html(summary["status_class"])
    latest = format_latest_modified(summary["latest_modified"])
    st.markdown(
        f"""
        <div class="category-card">
            <div class="category-card-top">
                <div class="category-card-title">{safe_html(category.label)}</div>
                <div class="status-badge {status_class}">{status_label}</div>
            </div>
            <div class="category-card-copy">{safe_html(copy)}</div>
            <div class="category-card-stats">
                <div class="category-stat">
                    <div class="category-stat-value">{int(summary["open_reviews"])}</div>
                    <div class="category-stat-label">Open reviews</div>
                </div>
                <div class="category-stat">
                    <div class="category-stat-value">{int(summary["manual_entries"])}</div>
                    <div class="category-stat-label">Manual entry</div>
                </div>
                <div class="category-stat">
                    <div class="category-stat-value">{int(summary["missing_mapping"])}</div>
                    <div class="category-stat-label">Mapping gaps</div>
                </div>
                <div class="category-stat">
                    <div class="category-stat-value">{int(summary["approved"])}</div>
                    <div class="category-stat-label">Approved rows</div>
                </div>
            </div>
            <div class="category-card-footer">Updated {safe_html(latest)} - {int(summary["duplicates"])} duplicate flags</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def show_landing_page() -> None:
    summaries = dashboard_summaries()
    summary_by_category = {str(summary["category_key"]): summary for summary in summaries}
    st.markdown(
        """
        <div class="landing-hero">
            <h1>ESG Document Intelligence</h1>
            <p>Review OCR outputs, clear manual entry queues, resolve mapping gaps, and publish approved ESG data into final templates.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    render_workspace_summary(summaries)
    columns = st.columns(4)
    category_copy = {
        "scope1": "Review direct emissions records and supporting source data.",
        "scope2": "Review purchased energy invoices, mappings, and template output.",
        "water": "Review water consumption records and required mappings.",
        "waste": "Review waste activity records and approval checkpoints.",
    }
    for index, category in enumerate(REVIEW_CATEGORIES):
        with columns[index % len(columns)]:
            render_category_card(
                category,
                summary_by_category[category.key],
                category_copy.get(category.key, "Review OCR records and approvals."),
            )
            if st.button(
                f"Open {category.label}",
                key=f"landing_{category.key}",
                icon=":material/arrow_forward:",
                use_container_width=True,
            ):
                select_category(category.key)
                st.rerun()


def add_category_column(df: pd.DataFrame, category_key: str) -> pd.DataFrame:
    if df.empty:
        return df
    result = df.copy()
    result.insert(0, "category", category_label(category_key))
    return result


def load_approved_overview(selected_key: str, include_all_categories: bool) -> pd.DataFrame:
    category_keys = [category.key for category in REVIEW_CATEGORIES] if include_all_categories else [selected_key]
    approved_frames = []
    for category_key in category_keys:
        approved_df = read_csv(str(category_paths(category_key)["approved"]))
        if not approved_df.empty:
            approved_frames.append(add_category_column(approved_df, category_key))
    if not approved_frames:
        return pd.DataFrame()
    return pd.concat(approved_frames, ignore_index=True, sort=False)


def load_missing_mapping_rows(selected_key: str, include_all_categories: bool) -> pd.DataFrame:
    category_keys = [category.key for category in REVIEW_CATEGORIES] if include_all_categories else [selected_key]
    missing_frames = []
    for category_key in category_keys:
        paths = category_paths(category_key)
        if category_key == "scope2":
            try:
                accounts = load_reporting_accounts(include_issues=True)
                gaps = accounts.loc[accounts.mapping_message.ne("")].rename(columns={
                    "legal_entity_name": "legal_entity", "unit": "unit_name",
                }).copy()
                gaps["mapping_status"] = "REPORTING_MAPPING"
                missing_frames.append(add_category_column(gaps, category_key))
            except (OSError, ValueError, KeyError):
                pass  # Invoice-level issues remain available if the reference file is unavailable.
            for layer in ("previous_data", "gold_template"):
                if layer not in paths:
                    continue
                _, gaps = normalize_reporting_data(read_excel(str(paths[layer])), return_issues=True)
                if not gaps.empty:
                    gaps = gaps.rename(columns={"Legal Entity Name": "legal_entity", "Unit": "unit_name",
                                                "Account number": "account_number", "source_files": "source_file"})
                    gaps["mapping_status"] = "REPORTING_DATA"
                    gaps["mapping_message"] = layer + ": " + gaps["mapping_message"]
                    missing_frames.append(add_category_column(gaps, category_key))
        normalized_df = read_excel(str(paths["silver_normalized"]))
        manual_df = read_excel(str(paths["silver_manual_mapping"]))
        business_path = paths.get("silver_business_mapping")
        business_df = read_excel(str(business_path)) if business_path is not None else pd.DataFrame()
        if "business_mapping_issue" in business_df.columns:
            business_gaps = business_df[business_df["business_mapping_issue"].fillna("").astype(str).str.strip().ne("")].copy()
            if not business_gaps.empty:
                business_gaps = business_gaps.rename(columns={
                    "source_files": "source_file", "sharepoint_link_1": "sharepoint_link",
                    "Legal Entity Name": "legal_entity", "Unit": "unit_name",
                    "Supplier Name": "supplier", "Account number": "account_number",
                    "Energy Type": "activity_group",
                })
                business_gaps["mapping_status"] = "BUSINESS_MAPPING"
                missing_frames.append(add_category_column(business_gaps, category_key))
        normalized_df = pd.concat([normalized_df, manual_df], ignore_index=True, sort=False).fillna("")
        if normalized_df.empty:
            continue
        mapping_columns = [
            column
            for column in ACCOUNT_MAPPING_COLUMNS
            if column not in OCR_CONTEXT_COLUMNS and column in normalized_df.columns
        ]
        if not mapping_columns:
            continue
        missing_mask = normalized_df[mapping_columns].apply(
            lambda row: all(str(value or "").strip() == "" for value in row),
            axis=1,
        )
        if "mapping_status" in normalized_df.columns:
            missing_mask |= ~normalized_df["mapping_status"].isin(["", "MAPPED"])
        if category_key == "scope2" and "consumption_quantity_unit" in normalized_df.columns:
            invalid_unit = normalized_df["consumption_quantity_unit"].map(kwh_conversion_factor).isna()
            missing_mask |= invalid_unit
            normalized_df.loc[invalid_unit, "mapping_message"] = "Energy unit: no supported extracted or mapped unit"
        missing_df = normalized_df[missing_mask].copy()
        if not missing_df.empty:
            missing_frames.append(add_category_column(missing_df, category_key))
    if not missing_frames:
        return pd.DataFrame()
    return pd.concat(missing_frames, ignore_index=True, sort=False)


def curate_missing_mapping_columns(df: pd.DataFrame) -> pd.DataFrame:
    available_columns = [column for column in MISSING_MAPPING_COLUMNS if column in df.columns]
    return df.loc[:, available_columns].copy()


def overview_export_filename(category_key: str, include_all_categories: bool) -> str:
    scope = "all_categories" if include_all_categories else category_key
    return f"{scope}_approved_data_overview.xlsx"


def missing_mapping_export_filename(category_key: str, include_all_categories: bool) -> str:
    scope = "all_categories" if include_all_categories else category_key
    return f"{scope}_missing_mapping.xlsx"


def apply_overview_search(df: pd.DataFrame, search_text: str) -> pd.DataFrame:
    if not search_text.strip():
        return df
    search_lower = search_text.strip().lower()
    return df[
        df.astype(str).apply(
            lambda row: row.str.lower().str.contains(search_lower, regex=False).any(),
            axis=1,
        )
    ]


def apply_column_filters(df: pd.DataFrame, filters: dict[str, str]) -> pd.DataFrame:
    filtered_df = df
    for column, filter_text in filters.items():
        if filter_text.strip():
            filter_lower = filter_text.strip().lower()
            filtered_df = filtered_df[
                filtered_df[column].astype(str).str.lower().str.contains(filter_lower, regex=False, na=False)
            ]
    return filtered_df


def overview_filter_prefix(category_key: str, include_all_categories: bool, namespace: str = "overview") -> str:
    return f"{namespace}_filter_{category_key}_{int(include_all_categories)}_"


def clear_overview_column_filters(prefix: str) -> None:
    for key in list(st.session_state.keys()):
        if key.startswith(prefix) and not key.endswith("clear"):
            st.session_state[key] = ""


def show_overview_column_filters(
    df: pd.DataFrame,
    category_key: str,
    include_all_categories: bool,
    namespace: str = "overview",
) -> dict[str, str]:
    prefix = overview_filter_prefix(category_key, include_all_categories, namespace)
    filters: dict[str, str] = {}

    with st.expander("Column filters"):
        if st.button("Clear column filters", key=f"{prefix}clear", use_container_width=True):
            clear_overview_column_filters(prefix)

        filter_columns = st.columns(3)
        for index, column in enumerate(df.columns):
            key = f"{prefix}{index}"
            with filter_columns[index % len(filter_columns)]:
                filters[column] = st.text_input(str(column), key=key, placeholder="Contains...")

    return filters


def show_data_overview(category_key: str) -> None:
    include_all = st.toggle("Show all categories", value=True)
    approved_df = load_approved_overview(category_key, include_all)
    if approved_df.empty:
        st.info("No approved rows are available yet.")
        return

    status_counts = approved_df["approval_status"].value_counts() if "approval_status" in approved_df else pd.Series(dtype=int)
    metric_cols = st.columns(3)
    metric_cols[0].metric("Approved Rows", len(approved_df))
    metric_cols[1].metric("Auto Approved", int(status_counts.get("AUTO_APPROVED", 0)))
    metric_cols[2].metric("Manually Approved", int(status_counts.get("MANUALLY_APPROVED", 0)))

    search_text = st.text_input("Search approved data", "")
    column_filters = show_overview_column_filters(approved_df, category_key, include_all)
    filtered_df = apply_column_filters(apply_overview_search(approved_df, search_text), column_filters)

    st.caption(f"Showing {len(filtered_df)} of {len(approved_df)} approved rows")
    st.download_button(
        "Download Excel",
        data=dataframe_to_xlsx_bytes(filtered_df, sheet_name="Approved Data"),
        file_name=overview_export_filename(category_key, include_all),
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
    st.dataframe(filtered_df, hide_index=True, use_container_width=True)


def show_missing_mapping(category_key: str) -> None:
    include_all = st.toggle("Show all categories", value=True, key=f"{category_key}_missing_mapping_all")
    missing_df = curate_missing_mapping_columns(load_missing_mapping_rows(category_key, include_all))
    if missing_df.empty:
        st.success("No missing mapping rows were found.")
        return

    metric_cols = st.columns(2)
    metric_cols[0].metric("Missing Rows", len(missing_df))
    if "category" in missing_df.columns:
        metric_cols[1].metric("Categories", missing_df["category"].nunique())
    else:
        metric_cols[1].metric("Categories", 1)

    search_text = st.text_input("Search missing mapping", "", key=f"{category_key}_missing_mapping_search")
    column_filters = show_overview_column_filters(missing_df, category_key, include_all, namespace="missing_mapping")
    filtered_df = apply_column_filters(apply_overview_search(missing_df, search_text), column_filters)

    st.caption(f"Showing {len(filtered_df)} of {len(missing_df)} missing mapping rows")
    st.download_button(
        "Download Excel",
        data=dataframe_to_xlsx_bytes(filtered_df, sheet_name="Missing Mapping"),
        file_name=missing_mapping_export_filename(category_key, include_all),
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
    column_config = {}
    if "sharepoint_link" in filtered_df.columns:
        column_config["sharepoint_link"] = st.column_config.LinkColumn(
            "sharepoint_link",
            display_text="Open file",
        )
    st.dataframe(
        filtered_df,
        column_config=column_config,
        hide_index=True,
        use_container_width=True,
    )


def show_mapping_sources() -> None:
    mapping_sources = load_mapping_sources()
    if not mapping_sources:
        st.info("No mapping workbook configuration was found.")
        return

    if st.button(
        "Refresh mapping list",
        key="refresh_mapping_sources_button",
        icon=":material/refresh:",
    ):
        load_mapping_sources.clear()
        clear_cached_data()
        st.rerun()

    st.caption("Open a mapping source, edit it in its desktop app, then save the file.")
    for source in mapping_sources:
        workbook_path = Path(source["path"])
        row_cols = st.columns([1.5, 1.2, 0.75], vertical_alignment="center")
        row_cols[0].markdown(f"**{source['name']}**")
        row_cols[1].caption(source["source_type"])

        if workbook_path.exists():
            if row_cols[2].button(
                "Open",
                key=f"open_mapping_source_{source['key']}",
                icon=":material/open_in_new:",
                use_container_width=True,
            ):
                opened, message = open_mapping_file(source["path"])
                if opened:
                    st.success(message)
                else:
                    st.error(message)
        else:
            row_cols[2].button(
                "Missing",
                key=f"missing_mapping_source_{source['key']}",
                icon=":material/error:",
                disabled=True,
                use_container_width=True,
            )


def curate_template_output_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    column_lookup = {str(column).strip().lower(): column for column in df.columns}
    start_column = column_lookup.get("data quality")
    end_column = column_lookup.get("contractual_instruments")
    if start_column is None or end_column is None:
        return df
    start_index = df.columns.get_loc(start_column)
    end_index = df.columns.get_loc(end_column)
    if start_index > end_index:
        return df
    selected_columns = list(df.columns[start_index : end_index + 1])
    selected_lookup = {str(column).strip().lower() for column in selected_columns}
    for column in df.columns:
        normalized_column = str(column).strip().lower()
        if normalized_column in selected_lookup:
            continue
        if normalized_column in GOLD_TEMPLATE_SUPPLEMENTAL_COLUMNS or _is_sharepoint_link_column(column):
            selected_columns.append(column)
            selected_lookup.add(normalized_column)
    return df.loc[:, selected_columns].copy()


def _is_sharepoint_link_column(column: object) -> bool:
    column_text = str(column).strip().lower()
    return column_text == "sharepoint_link" or re.fullmatch(r"sharepoint_link_\d+", column_text) is not None


def show_template_output(category_key: str) -> None:
    template_df = curate_template_output_columns(read_excel(str(category_paths(category_key)["gold_template"])))
    if template_df.empty:
        st.info(f"No gold template output is available for {category_label(category_key)} yet.")
        return

    metric_cols = st.columns(2)
    metric_cols[0].metric("Rows", len(template_df))
    metric_cols[1].metric("Columns", len(template_df.columns))

    column_filters = show_overview_column_filters(
        template_df,
        category_key,
        include_all_categories=False,
        namespace="template_output",
    )
    filtered_df = apply_column_filters(template_df, column_filters)
    st.caption(f"Showing {len(filtered_df)} of {len(template_df)} template rows")
    st.download_button(
        "Download Excel",
        icon=":material/download:",
        data=dataframe_to_xlsx_bytes(filtered_df, sheet_name="Template Output"),
        file_name=f"{category_key}_gold_template_output.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="template_output_download_excel",
    )
    st.dataframe(filtered_df, hide_index=True, use_container_width=True)


def show_previous_data(category_key: str) -> None:
    paths = category_paths(category_key)
    previous_path = paths["previous_data"]
    example_path = paths["previous_data_example"]
    current_template_df = curate_template_output_columns(read_excel(str(paths["gold_template"])))
    previous_df = curate_template_output_columns(read_excel(str(previous_path)))

    action_cols = st.columns([1, 1, 2], vertical_alignment="bottom")
    if not current_template_df.empty:
        action_cols[0].download_button(
            "Download Current Template Output",
            icon=":material/download:",
            data=dataframe_to_xlsx_bytes(current_template_df, sheet_name="Previous Data"),
            file_name=previous_path.name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="previous_data_current_template_download",
            use_container_width=True,
        )
    if example_path.exists():
        action_cols[1].download_button(
            "Download Blank Previous Data Template",
            icon=":material/download:",
            data=example_path.read_bytes(),
            file_name=example_path.name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="previous_data_example_download",
            use_container_width=True,
        )

    uploaded_previous = action_cols[2].file_uploader(
        "Upload Previous Data",
        type=["xlsx"],
        key="previous_data_upload",
        help=f"Saved to data/gold/{previous_path.name}.",
    )
    if uploaded_previous is not None:
        try:
            normalize_reporting_data(pd.read_excel(uploaded_previous, keep_default_na=False))
        except (ValueError, KeyError) as exc:
            st.error(str(exc))
            return
        previous_path.parent.mkdir(parents=True, exist_ok=True)
        previous_path.write_bytes(uploaded_previous.getbuffer())
        clear_cached_data()
        st.success(f"Uploaded {previous_path.name}.")
        st.rerun()

    if previous_df.empty:
        st.info(f"No previous data workbook is available yet. Upload {previous_path.name} to enable comparison.")
        return

    metric_cols = st.columns(2)
    metric_cols[0].metric("Rows", len(previous_df))
    metric_cols[1].metric("Columns", len(previous_df.columns))

    column_filters = show_overview_column_filters(
        previous_df,
        category_key,
        include_all_categories=False,
        namespace="previous_data",
    )
    filtered_df = apply_column_filters(previous_df, column_filters)
    st.caption(f"Showing {len(filtered_df)} of {len(previous_df)} previous rows")
    st.download_button(
        "Download Previous Data Excel",
        icon=":material/download:",
        data=dataframe_to_xlsx_bytes(filtered_df, sheet_name="Previous Data"),
        file_name=previous_path.name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="previous_data_download_excel",
    )
    st.dataframe(filtered_df, hide_index=True, use_container_width=True)


def show_completeness_check(category_key: str) -> None:
    fiscal_year_options = completeness_fiscal_year_options(category_key)
    default_fiscal_year_index = (
        fiscal_year_options.index(COMPLETENESS_DEFAULT_FISCAL_YEAR)
        if COMPLETENESS_DEFAULT_FISCAL_YEAR in fiscal_year_options
        else 0
    )

    range_cols = st.columns([1, 1, 1, 1], vertical_alignment="bottom")
    selected_fiscal_year = range_cols[0].selectbox(
        "Fiscal Year",
        fiscal_year_options,
        index=default_fiscal_year_index,
        format_func=lambda fiscal_year: f"FY {fiscal_year}",
        key="completeness_fiscal_year",
    )
    month_options = fiscal_year_months(selected_fiscal_year)
    selected_start_month = range_cols[1].selectbox(
        "Start Date",
        month_options,
        index=0,
        format_func=completeness_month_label,
        key=f"completeness_start_month_{selected_fiscal_year}",
    )
    selected_end_month = range_cols[2].selectbox(
        "End Date",
        month_options,
        index=len(month_options) - 1,
        format_func=completeness_month_label,
        key=f"completeness_end_month_{selected_fiscal_year}",
    )

    if selected_start_month > selected_end_month:
        st.warning("Select a start month that is before or equal to the end month.")
        return

    try:
        completeness_df, months, gold_facility_count = build_gold_completeness(
            category_key, selected_start_month, selected_end_month,
        )
    except (ValueError, FileNotFoundError, KeyError) as exc:
        st.warning(str(exc))
        return
    if completeness_df.empty:
        st.info("No active facilities were found in the master entity list.")
        return

    month_labels = [completeness_month_label(month) for month in months]
    total_cells = len(completeness_df) * len(months)
    complete_cells = sum(
        1
        for label in month_labels
        for value in completeness_df[label]
        if float(value.get("ratio", 0.0)) >= 1
    )
    partial_cells = sum(
        1
        for label in month_labels
        for value in completeness_df[label]
        if 0 < float(value.get("ratio", 0.0)) < 1
    )

    metric_cols = st.columns(4)
    metric_cols[0].metric("Facilities", len(completeness_df[FACILITY_KEY_COLUMNS].drop_duplicates()))
    metric_cols[1].metric("Facilities With Data", gold_facility_count)
    metric_cols[2].metric("Complete Months", complete_cells)
    metric_cols[3].metric("Partial Months", partial_cells)

    selected_kpi = st.selectbox("KPI Component", ["All", *sorted(completeness_df["kpi_component"].unique())],
                                key="completeness_kpi_filter")
    if selected_kpi != "All":
        completeness_df = completeness_df.loc[completeness_df["kpi_component"] == selected_kpi]

    divisions = sorted(value for value in completeness_df["division"].astype(str).unique() if value)
    controls = st.columns([1, 1, 0.8], vertical_alignment="bottom")
    selected_division = controls[0].selectbox("Division", ["All", *divisions], key="completeness_division_filter")
    search_text = controls[1].text_input("Facility Search", key="completeness_facility_search")
    export_df = completeness_export_df(completeness_df, months)
    controls[2].download_button(
        "Download Excel",
        icon=":material/download:",
        data=dataframe_to_xlsx_bytes(export_df, sheet_name="Completeness"),
        file_name=f"{category_key}_gold_completeness_check.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="completeness_download_excel",
        use_container_width=True,
    )

    filtered_df = completeness_df.copy()
    if selected_division != "All":
        filtered_df = filtered_df[filtered_df["division"].astype(str) == selected_division]
    if search_text.strip():
        search_value = normalize_lookup_value(search_text)
        search_blob = (
            filtered_df["unit"].astype(str)
            + " "
            + filtered_df["legal_entity_name"].astype(str)
            + " "
            + filtered_df["division"].astype(str)
        ).map(normalize_lookup_value)
        filtered_df = filtered_df[search_blob.str.contains(search_value, regex=False)]

    st.caption(
        f"Coverage window: {month_labels[0]} to {month_labels[-1]}. "
        "Coverage combines valid OCR/manual invoice dates for every mapped account within each KPI. "
        "Missing allocations are excluded; N/A means outside account effective dates."
    )

    if filtered_df.empty:
        st.info("No facilities match the current filters.")
        return
    render_completeness_heatmap(filtered_df, months)


def show_year_over_year(category_key: str) -> None:
    fiscal_year_options = completeness_fiscal_year_options(category_key)
    default_fiscal_year_index = (
        fiscal_year_options.index(COMPLETENESS_DEFAULT_FISCAL_YEAR)
        if COMPLETENESS_DEFAULT_FISCAL_YEAR in fiscal_year_options
        else 0
    )

    range_cols = st.columns([1, 1, 1, 1], vertical_alignment="bottom")
    selected_fiscal_year = range_cols[0].selectbox(
        "Fiscal Year",
        fiscal_year_options,
        index=default_fiscal_year_index,
        format_func=lambda fiscal_year: f"FY {fiscal_year}",
        key="yoy_fiscal_year",
    )
    month_options = fiscal_year_months(selected_fiscal_year)
    selected_start_month = range_cols[1].selectbox(
        "Start Date",
        month_options,
        index=0,
        format_func=completeness_month_label,
        key=f"yoy_start_month_{selected_fiscal_year}",
    )
    selected_end_month = range_cols[2].selectbox(
        "End Date",
        month_options,
        index=len(month_options) - 1,
        format_func=completeness_month_label,
        key=f"yoy_end_month_{selected_fiscal_year}",
    )

    if selected_start_month > selected_end_month:
        st.warning("Select a start month that is before or equal to the end month.")
        return

    try:
        master_df = load_reporting_accounts()[REPORT_KEY_COLUMNS].drop_duplicates()
    except (ValueError, FileNotFoundError, KeyError):
        master_df = pd.DataFrame(columns=REPORT_KEY_COLUMNS)

    paths = category_paths(category_key)
    current_template_path = paths["gold_template_aggregated"]
    current_df = curate_template_output_columns(read_excel_fresh(str(current_template_path)))
    previous_df = curate_template_output_columns(read_excel_fresh(str(paths["previous_data"])))
    try:
        current_df = normalize_reporting_data(current_df)
        previous_df = normalize_reporting_data(previous_df)
    except ValueError as exc:
        st.warning(str(exc))
        return
    if current_df.empty:
        st.info(
            f"No aggregated gold template output is available for {category_label(category_key)} yet. "
            "Run the pipeline to generate it."
        )
        return
    if previous_df.empty:
        st.caption("Previous data is unavailable. Current approved values remain visible; comparisons show N/A.")

    st.caption(
        f"YOY source: {len(current_df)} current rows from {current_template_path.name}; "
        f"{len(previous_df)} previous rows from {paths['previous_data'].name}."
    )

    observed = pd.concat([current_df, previous_df], ignore_index=True).reindex(
        columns=list(GOLD_FACILITY_COLUMN_ALIASES.values())
    ).rename(columns={value: key for key, value in GOLD_FACILITY_COLUMN_ALIASES.items()})
    master_df = pd.concat([master_df, observed], ignore_index=True).drop_duplicates(REPORT_KEY_COLUMNS)
    months = completeness_month_starts(selected_start_month, selected_end_month)
    previous_months = [month - pd.DateOffset(years=1) for month in months]
    yoy_df = build_year_over_year(
        master_df,
        current_df,
        previous_df,
        months,
        REPORT_KEY_COLUMNS,
        GOLD_FACILITY_COLUMN_ALIASES,
        previous_months=previous_months,
    )
    if yoy_df.empty:
        st.info("No active facilities were found in the master entity list.")
        return

    month_labels = [completeness_month_label(month) for month in months]
    cells = [cell for label in month_labels for cell in yoy_df[label]]
    compared_cells = [cell for cell in cells if cell.percent_difference is not None]
    high_variance_cells = [
        cell
        for cell in compared_cells
        if not pd.isna(cell.percent_difference) and abs(float(cell.percent_difference)) > YOY_DIFFERENCE_THRESHOLDS[0][0]
    ]

    metric_cols = st.columns(4)
    metric_cols[0].metric("Facilities", len(yoy_df[FACILITY_KEY_COLUMNS].drop_duplicates()))
    metric_cols[1].metric("Compared Months", len(compared_cells))
    metric_cols[2].metric("Over 10%", len(high_variance_cells))
    metric_cols[3].metric("Missing Prior", sum(1 for cell in cells if cell.status == "No previous data"))

    selected_kpi = st.selectbox("KPI Component", ["All", *sorted(yoy_df["kpi_component"].unique())],
                                key="yoy_kpi_filter")
    if selected_kpi != "All":
        yoy_df = yoy_df.loc[yoy_df["kpi_component"] == selected_kpi]

    divisions = sorted(value for value in yoy_df["division"].astype(str).unique() if value)
    controls = st.columns([1, 1, 0.8], vertical_alignment="bottom")
    selected_division = controls[0].selectbox("Division", ["All", *divisions], key="yoy_division_filter")
    search_text = controls[1].text_input("Facility Search", key="yoy_facility_search")
    export_df = year_over_year_export_df(yoy_df, months, REPORT_KEY_COLUMNS)
    controls[2].download_button(
        "Download Excel",
        icon=":material/download:",
        data=dataframe_to_xlsx_bytes(export_df, sheet_name="Year-over-year"),
        file_name=f"{category_key}_gold_year_over_year.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="yoy_download_excel",
        use_container_width=True,
    )

    filtered_df = yoy_df.copy()
    if selected_division != "All":
        filtered_df = filtered_df[filtered_df["division"].astype(str) == selected_division]
    if search_text.strip():
        search_value = normalize_lookup_value(search_text)
        search_blob = (
            filtered_df["unit"].astype(str)
            + " "
            + filtered_df["legal_entity_name"].astype(str)
            + " "
            + filtered_df["division"].astype(str)
        ).map(normalize_lookup_value)
        filtered_df = filtered_df[search_blob.str.contains(search_value, regex=False)]

    previous_month_labels = [completeness_month_label(month) for month in previous_months]
    st.caption(
        f"Comparing {month_labels[0]} to {month_labels[-1]} "
        f"to {previous_month_labels[0]} to {previous_month_labels[-1]}."
    )

    if filtered_df.empty:
        st.info("No facilities match the current filters.")
        return
    render_year_over_year_heatmap(filtered_df, months)


def show_high_variance(category_key: str) -> None:
    fiscal_year_options = completeness_fiscal_year_options(category_key)
    default_fiscal_year_index = (
        fiscal_year_options.index(COMPLETENESS_DEFAULT_FISCAL_YEAR)
        if COMPLETENESS_DEFAULT_FISCAL_YEAR in fiscal_year_options
        else 0
    )

    range_cols = st.columns([1, 1, 1, 1], vertical_alignment="bottom")
    selected_fiscal_year = range_cols[0].selectbox(
        "Fiscal Year",
        fiscal_year_options,
        index=default_fiscal_year_index,
        format_func=lambda fiscal_year: f"FY {fiscal_year}",
        key="high_variance_fiscal_year",
    )
    month_options = fiscal_year_months(selected_fiscal_year)
    selected_start_month = range_cols[1].selectbox(
        "Start Date",
        month_options,
        index=0,
        format_func=completeness_month_label,
        key=f"high_variance_start_month_{selected_fiscal_year}",
    )
    selected_end_month = range_cols[2].selectbox(
        "End Date",
        month_options,
        index=len(month_options) - 1,
        format_func=completeness_month_label,
        key=f"high_variance_end_month_{selected_fiscal_year}",
    )

    if selected_start_month > selected_end_month:
        st.warning("Select a start month that is before or equal to the end month.")
        return

    try:
        master_df = load_reporting_accounts()[REPORT_KEY_COLUMNS].drop_duplicates()
    except (ValueError, FileNotFoundError, KeyError):
        master_df = pd.DataFrame(columns=REPORT_KEY_COLUMNS)

    paths = category_paths(category_key)
    current_template_path = paths["gold_template_aggregated"]
    current_df = curate_template_output_columns(read_excel_fresh(str(current_template_path)))
    previous_df = curate_template_output_columns(read_excel_fresh(str(paths["previous_data"])))
    try:
        current_df = normalize_reporting_data(current_df)
        previous_df = normalize_reporting_data(previous_df)
    except ValueError as exc:
        st.warning(str(exc))
        return
    if current_df.empty:
        st.info(
            f"No aggregated gold template output is available for {category_label(category_key)} yet. "
            "Run the pipeline to generate it."
        )
        return
    if previous_df.empty:
        st.caption("No valid previous data is available for variance comparisons.")

    observed = pd.concat([current_df, previous_df], ignore_index=True).reindex(
        columns=list(GOLD_FACILITY_COLUMN_ALIASES.values())
    ).rename(columns={value: key for key, value in GOLD_FACILITY_COLUMN_ALIASES.items()})
    master_df = pd.concat([master_df, observed], ignore_index=True).drop_duplicates(REPORT_KEY_COLUMNS)
    months = completeness_month_starts(selected_start_month, selected_end_month)
    previous_months = [month - pd.DateOffset(years=1) for month in months]
    yoy_df = build_year_over_year(
        master_df,
        current_df,
        previous_df,
        months,
        REPORT_KEY_COLUMNS,
        GOLD_FACILITY_COLUMN_ALIASES,
        previous_months=previous_months,
    )
    high_variance_df = high_variance_year_over_year_df(
        yoy_df,
        current_df,
        previous_df,
        months,
        REPORT_KEY_COLUMNS,
        GOLD_FACILITY_COLUMN_ALIASES,
        previous_months=previous_months,
        minimum_abs_difference=YOY_DIFFERENCE_THRESHOLDS[0][0],
    )

    metric_cols = st.columns(3)
    metric_cols[0].metric("High Variance Rows", len(high_variance_df))
    metric_cols[1].metric("Facilities", len(high_variance_df[["Division", "Legal Entity", "Unit"]].drop_duplicates()) if not high_variance_df.empty else 0)
    metric_cols[2].metric("Threshold", f">{YOY_DIFFERENCE_THRESHOLDS[0][0]:.0%}")

    selected_kpi = st.selectbox("KPI Component", ["All", *sorted(high_variance_df["KPI Component"].unique())],
                                key="high_variance_kpi_filter")
    if selected_kpi != "All":
        high_variance_df = high_variance_df.loc[high_variance_df["KPI Component"] == selected_kpi]

    divisions = sorted(value for value in high_variance_df["Division"].astype(str).unique() if value)
    controls = st.columns([1, 1, 0.8], vertical_alignment="bottom")
    selected_division = controls[0].selectbox("Division", ["All", *divisions], key="high_variance_division_filter")
    search_text = controls[1].text_input("Facility Search", key="high_variance_facility_search")
    controls[2].download_button(
        "Download Excel",
        icon=":material/download:",
        data=dataframe_to_xlsx_bytes(high_variance_df, sheet_name="High Variance"),
        file_name=f"{category_key}_gold_high_variance_yoy.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="high_variance_download_excel",
        use_container_width=True,
    )

    filtered_df = high_variance_df.copy()
    if selected_division != "All":
        filtered_df = filtered_df[filtered_df["Division"].astype(str) == selected_division]
    if search_text.strip():
        search_value = normalize_lookup_value(search_text)
        search_blob = (
            filtered_df["Unit"].astype(str)
            + " "
            + filtered_df["Legal Entity"].astype(str)
            + " "
            + filtered_df["Division"].astype(str)
        ).map(normalize_lookup_value)
        filtered_df = filtered_df[search_blob.str.contains(search_value, regex=False)]

    month_labels = [completeness_month_label(month) for month in months]
    previous_month_labels = [completeness_month_label(month) for month in previous_months]
    st.caption(
        f"Comparing {month_labels[0]} to {month_labels[-1]} "
        f"to {previous_month_labels[0]} to {previous_month_labels[-1]}. "
        "Sorted by absolute YOY variance, so decreases and increases of the same size rank together."
    )

    if filtered_df.empty:
        st.info("No high-variance facilities match the current filters.")
        return
    link_column_config = {
        column: st.column_config.LinkColumn(column, display_text="Open file")
        for column in filtered_df.columns
        if str(column).startswith("Current Year link ")
    }
    st.dataframe(
        filtered_df,
        column_config=link_column_config,
        hide_index=True,
        use_container_width=True,
    )


def render_year_over_year_heatmap(year_over_year_df: pd.DataFrame, months: list[pd.Timestamp]) -> None:
    header_cells = [
        '<th class="facility-col">Division</th>',
        '<th class="meta-col">Legal Entity</th>',
        '<th class="meta-col">Unit</th>',
        '<th class="meta-col">KPI Component</th>',
        *[f"<th>{safe_html(completeness_month_label(month))}</th>" for month in months],
    ]
    body_rows = []
    for _, row in year_over_year_df.iterrows():
        cells = [
            f'<td class="facility-col" title="{safe_html(row.get("division", ""))}">{safe_html(row.get("division", ""))}</td>',
            f'<td class="meta-col">{safe_html(row.get("legal_entity_name", ""))}</td>',
            f'<td class="meta-col">{safe_html(row.get("unit", ""))}</td>',
            f'<td class="meta-col">{safe_html(row.get("kpi_component", ""))}</td>',
        ]
        for month in months:
            label = completeness_month_label(month)
            cell = row.get(label)
            if not isinstance(cell, YearOverYearCell):
                cell = YearOverYearCell(None, None, None, "yoy-missing", "No data")
            display_value = _year_over_year_display(cell)
            title = _year_over_year_title(cell)
            cells.append(f'<td class="{cell.css_class}" title="{safe_html(title)}">{display_value}</td>')
        body_rows.append(f"<tr>{''.join(cells)}</tr>")

    st.markdown(
        f"""
        <div class="completeness-table-wrap">
            <table class="completeness-table">
                <thead><tr>{''.join(header_cells)}</tr></thead>
                <tbody>{''.join(body_rows)}</tbody>
            </table>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _year_over_year_display(cell: YearOverYearCell) -> str:
    if cell.percent_difference is None:
        return "N/A"
    if cell.percent_difference == float("inf"):
        return ">999%"
    return f"{cell.percent_difference:+.0%}"


def _year_over_year_title(cell: YearOverYearCell) -> str:
    return (
        f"{cell.status}; current={cell.current_value if cell.current_value is not None else 'N/A'}; "
        f"previous={cell.previous_value if cell.previous_value is not None else 'N/A'}"
    )


def decision_option_label(row: pd.Series) -> str:
    invoice_id = str(row.get("invoice_id", ""))
    line_id = str(row.get("line_id", ""))
    field_name = friendly_field_name(row.get("field_name", ""))
    decision = str(row.get("review_decision", ""))
    suffix = "" if line_id in ("", "1") else f" - line {line_id}"
    return f"{invoice_id}{suffix} / {field_name} / {decision}"


def manual_override_option_label(row: pd.Series) -> str:
    invoice_id = str(row.get("invoice_id", ""))
    line_id = str(row.get("line_id", ""))
    field_name = friendly_field_name(row.get("field_name", ""))
    reviewed_at = str(row.get("reviewed_at", ""))
    suffix = "" if line_id in ("", "1") else f" - line {line_id}"
    label_parts = [f"{invoice_id}{suffix}", field_name]
    if reviewed_at:
        label_parts.append(reviewed_at)
    return " / ".join(label_parts)


def add_decision_type_column(decisions_df: pd.DataFrame) -> pd.DataFrame:
    result = decisions_df.copy()
    if "issue_id" not in result.columns:
        result.insert(0, "decision_type", "Review issue")
        return result
    decision_types = result["issue_id"].astype(str).map(
        lambda issue_id: "Manual override" if issue_id.startswith(MANUAL_OVERRIDE_ISSUE_PREFIX) else "Review issue"
    )
    result.insert(0, "decision_type", decision_types)
    return result


def delete_manual_override_rows(decisions_df: pd.DataFrame, issue_id: str) -> pd.DataFrame:
    if decisions_df.empty or "issue_id" not in decisions_df.columns:
        return decisions_df.copy()
    return decisions_df[decisions_df["issue_id"].astype(str) != str(issue_id)].reset_index(drop=True)


def manual_entry_decision_option_label(row: pd.Series) -> str:
    invoice_id, line_id = manual_entry_key(row)
    source = str(row.get("manual_entry_source", "") or row.get("source_file", ""))
    status = str(row.get("manual_entry_status", ""))
    suffix = "" if line_id in ("", "1") else f" - line {line_id}"
    label_parts = [f"{invoice_id}{suffix}"]
    if source:
        label_parts.append(source)
    if status:
        label_parts.append(status)
    return " / ".join(label_parts)


def manual_entry_key_mask(df: pd.DataFrame, invoice_id: str, line_id: str) -> pd.Series:
    if df.empty:
        return pd.Series([], dtype=bool)
    return (
        df.get("invoice_id", pd.Series([""] * len(df), index=df.index)).astype(str).eq(str(invoice_id))
        & df.get("line_id", pd.Series([""] * len(df), index=df.index)).astype(str).eq(str(line_id))
    )


def removable_manual_upload_file(queue_row: pd.Series, category_key: str) -> Path | None:
    if str(queue_row.get("manual_entry_source", "")) != MANUAL_ENTRY_SOURCE_UPLOAD:
        return None
    source_path = str(queue_row.get("source_path", "")).strip()
    if not source_path:
        return None
    upload_file = Path(source_path)
    if not upload_file.exists() or not upload_file.is_file():
        return None
    try:
        upload_file.resolve().relative_to(manual_upload_dir(category_key).resolve())
    except ValueError:
        return None
    return upload_file


def delete_manual_entry_records(
    queue_df: pd.DataFrame,
    decisions_df: pd.DataFrame,
    invoice_id: str,
    line_id: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series | None]:
    queue_mask = manual_entry_key_mask(queue_df, invoice_id, line_id)
    decision_mask = manual_entry_key_mask(decisions_df, invoice_id, line_id)
    queue_row = queue_df.loc[queue_mask].iloc[0] if queue_mask.any() else None
    updated_queue_df = queue_df.loc[~queue_mask].copy() if not queue_df.empty else queue_df.copy()
    updated_decisions_df = decisions_df.loc[~decision_mask].copy() if not decisions_df.empty else decisions_df.copy()
    return (
        updated_queue_df.reset_index(drop=True),
        updated_decisions_df.reset_index(drop=True),
        queue_row,
    )


def show_decision_management(category_key: str) -> None:
    summary_df, _, decisions_df, bronze_df = load_data(category_key)
    if decisions_df.empty or "review_decision" not in decisions_df.columns:
        st.info("No manual decision checkpoint is available yet.")
        filtered_df = pd.DataFrame()
    else:
        decision_statuses = ["ALL", *sorted(decisions_df["review_decision"].astype(str).unique().tolist())]
        control_cols = st.columns([1, 2])
        selected_status = control_cols[0].selectbox("Decision", decision_statuses, key=f"{category_key}_decision_status")
        search_text = control_cols[1].text_input("Search decisions", key=f"{category_key}_decision_search")

        filtered_df = decisions_df.copy()
        if selected_status != "ALL":
            filtered_df = filtered_df[filtered_df["review_decision"].astype(str) == selected_status]
        filtered_df = apply_overview_search(filtered_df, search_text)
        display_df = add_decision_type_column(filtered_df)

        display_columns = [
            "decision_type",
            "issue_id",
            "invoice_id",
            "line_id",
            "field_name",
            "original_value",
            "corrected_value",
            "review_decision",
            "review_tag",
            "reviewed_by",
            "reviewed_at",
            "review_comment",
        ]
        available_columns = [column for column in display_columns if column in display_df.columns]
        st.caption(f"Showing {len(filtered_df)} of {len(decisions_df)} decision rows")
        st.dataframe(display_df[available_columns], hide_index=True, use_container_width=True)

    st.divider()
    reopen_header_cols = st.columns([1, 0.24], vertical_alignment="center")
    reopen_header_cols[0].subheader("Reopen Approved Field")
    reopen_button_slot = reopen_header_cols[1].empty()
    if filtered_df.empty or "review_decision" not in filtered_df.columns:
        st.info("No approved decisions match the current filters.")
    elif summary_df.empty or bronze_df.empty:
        st.info("Run the pipeline first to generate the summary and bronze checkpoints.")
    else:
        approved_df = filtered_df[
            filtered_df["review_decision"].astype(str).str.upper().isin(APPROVED_DECISIONS)
        ].copy()
        if approved_df.empty:
            st.info("No approved decisions match the current filters.")
        else:
            approved_df = approved_df.sort_values(["invoice_id", "line_id", "field_name"])
            issue_ids = approved_df["issue_id"].astype(str).tolist()
            selected_issue_id = st.selectbox(
                "Field",
                issue_ids,
                format_func=lambda issue_id: decision_option_label(
                    approved_df[approved_df["issue_id"].astype(str) == str(issue_id)].iloc[0]
                ),
                key=f"{category_key}_reopen_issue_id",
            )
            selected_row = approved_df[approved_df["issue_id"].astype(str) == str(selected_issue_id)].iloc[0]
            detail_cols = st.columns(2)
            detail_cols[0].text_input("Original value", value=str(selected_row.get("original_value", "")), disabled=True)
            detail_cols[1].text_input("Corrected value", value=str(selected_row.get("corrected_value", "")), disabled=True)

            if reopen_button_slot.button("Reopen Field", type="primary", use_container_width=True):
                reopened_rows = reopen_manual_decision_rows(decisions_df.to_dict("records"), [selected_issue_id])
                updated_decisions = pd.DataFrame(reopened_rows, columns=decisions_df.columns)
                save_decisions(updated_decisions, category_key)
                refresh_approved_silver(bronze_df, summary_df, updated_decisions, category_key)
                show_saved_message("Field reopened. You can edit it now; Refresh Reports to update reports.")

    show_manual_override_delete_management(category_key, decisions_df, summary_df, bronze_df)
    show_manual_entry_delete_management(category_key)


def show_manual_override_delete_management(
    category_key: str,
    decisions_df: pd.DataFrame,
    summary_df: pd.DataFrame,
    bronze_df: pd.DataFrame,
) -> None:
    st.divider()
    delete_header_cols = st.columns([1, 0.24], vertical_alignment="center")
    delete_header_cols[0].subheader("Delete Manual Override")
    delete_button_slot = delete_header_cols[1].empty()

    if decisions_df.empty or "issue_id" not in decisions_df.columns:
        st.info("No manual override rows are available to delete.")
        return

    override_df = decisions_df[
        decisions_df["issue_id"].astype(str).str.startswith(MANUAL_OVERRIDE_ISSUE_PREFIX)
    ].copy()
    if override_df.empty:
        st.info("No manual override rows are available to delete.")
        return
    if summary_df.empty or bronze_df.empty:
        st.info("Run the pipeline first to generate the summary and bronze checkpoints.")
        return

    override_df = override_df.sort_values(["invoice_id", "line_id", "field_name", "reviewed_at"])
    issue_ids = override_df["issue_id"].astype(str).tolist()
    selected_issue_id = st.selectbox(
        "Manual override",
        issue_ids,
        format_func=lambda issue_id: manual_override_option_label(
            override_df[override_df["issue_id"].astype(str) == str(issue_id)].iloc[0]
        ),
        key=f"{category_key}_delete_manual_override_issue_id",
    )
    selected_row = override_df[override_df["issue_id"].astype(str) == str(selected_issue_id)].iloc[0]

    detail_columns = [
        "invoice_id",
        "line_id",
        "field_name",
        "original_value",
        "corrected_value",
        "review_decision",
        "reviewed_by",
        "reviewed_at",
        "review_comment",
    ]
    detail_df = pd.DataFrame([selected_row.to_dict()])
    available_detail_columns = [column for column in detail_columns if column in detail_df.columns]
    st.dataframe(detail_df[available_detail_columns], hide_index=True, use_container_width=True)

    confirm_delete = st.checkbox(
        "Delete this manual override from decision history and restore the pipeline value.",
        key=f"{category_key}_confirm_delete_manual_override",
    )
    if delete_button_slot.button(
        "Delete Override",
        type="primary",
        use_container_width=True,
        disabled=not confirm_delete,
    ):
        updated_decisions = delete_manual_override_rows(decisions_df, selected_issue_id)
        save_decisions(updated_decisions, category_key)
        refresh_approved_silver(bronze_df, summary_df, updated_decisions, category_key)
        show_saved_message("Manual override deleted. Refresh Reports to update reports.")


def show_manual_entry_delete_management(category_key: str) -> None:
    st.divider()
    delete_header_cols = st.columns([1, 0.24], vertical_alignment="center")
    delete_header_cols[0].subheader("Delete Manual Data Entry")
    delete_button_slot = delete_header_cols[1].empty()

    queue_df, manual_decisions_df, _ = load_manual_data_entry_data(category_key)
    if queue_df.empty and manual_decisions_df.empty:
        st.info("No manual data entry rows are available to delete.")
        return

    option_rows = manual_entry_delete_option_rows(queue_df, manual_decisions_df)
    if not option_rows:
        st.info("No manual data entry rows are available to delete.")
        return

    option_keys = [manual_entry_key(pd.Series(row)) for row in option_rows]
    selected_key = st.selectbox(
        "Manual entry",
        option_keys,
        format_func=lambda key: manual_entry_decision_option_label(
            pd.Series(option_rows[option_keys.index(key)])
        ),
        key=f"{category_key}_delete_manual_entry_key",
    )
    selected_row = pd.Series(option_rows[option_keys.index(selected_key)])
    selected_invoice_id, selected_line_id = selected_key
    queue_mask = manual_entry_key_mask(queue_df, selected_invoice_id, selected_line_id)
    selected_queue_row = queue_df.loc[queue_mask].iloc[0] if queue_mask.any() else pd.Series(dtype=object)
    upload_file = removable_manual_upload_file(selected_queue_row, category_key)

    detail_columns = [
        "invoice_id",
        "line_id",
        "manual_entry_source",
        "manual_entry_status",
        "source_file",
        "original_file_name",
        "reviewed_by",
        "reviewed_at",
    ]
    detail_df = pd.DataFrame([selected_row.to_dict()])
    available_detail_columns = [column for column in detail_columns if column in detail_df.columns]
    st.dataframe(detail_df[available_detail_columns], hide_index=True, use_container_width=True)
    if upload_file is not None:
        st.caption(f"Uploaded file will also be deleted: {upload_file}")

    confirm_delete = st.checkbox(
        "Delete this manual entry from the queue and completed-entry checkpoint.",
        key=f"{category_key}_confirm_delete_manual_entry",
    )
    if delete_button_slot.button(
        "Delete Entry",
        type="primary",
        use_container_width=True,
        disabled=not confirm_delete,
    ):
        deleted_completed_entry = manual_entry_key_mask(
            manual_decisions_df,
            selected_invoice_id,
            selected_line_id,
        ).any()
        updated_queue_df, updated_manual_decisions_df, queue_row = delete_manual_entry_records(
            queue_df,
            manual_decisions_df,
            selected_invoice_id,
            selected_line_id,
        )
        file_delete_warning = ""
        upload_file = removable_manual_upload_file(queue_row, category_key) if queue_row is not None else None
        if upload_file is not None:
            try:
                upload_file.unlink()
            except OSError as exc:
                file_delete_warning = f" Uploaded file could not be deleted: {exc}"

        save_manual_data_entry_queue(updated_queue_df, category_key)
        save_manual_data_entry_decisions(updated_manual_decisions_df, category_key)
        message = "Manual entry deleted."
        if deleted_completed_entry:
            message += " Refresh Reports to update reports."
        show_saved_message(message + file_delete_warning)


def manual_entry_delete_option_rows(
    queue_df: pd.DataFrame,
    manual_decisions_df: pd.DataFrame,
) -> list[dict[str, object]]:
    rows_by_key: dict[tuple[str, str], dict[str, object]] = {}
    for _, row in queue_df.iterrows():
        rows_by_key[manual_entry_key(row)] = row.to_dict()
    for _, row in manual_decisions_df.iterrows():
        key = manual_entry_key(row)
        merged_row = rows_by_key.get(key, {}).copy()
        merged_row.update(row.to_dict())
        rows_by_key[key] = merged_row
    return list(rows_by_key.values())


def show_page_header(category_key: str, active_section: str) -> None:
    top_cols = st.columns([1, 0.18, 0.25], vertical_alignment="center")
    top_cols[0].title(active_section)
    top_cols[0].caption(category_label(category_key))
    if top_cols[1].button(
        "Pipeline",
        icon=":material/sync:",
        help="Import new or changed source JSON and rebuild checkpoints and reports",
        key="header_pipeline_button",
        use_container_width=True,
    ):
        ok, output = run_pipeline(category_key)
        clear_cached_data()
        if ok:
            st.success("Pipeline refreshed.")
        else:
            st.error("Pipeline failed.")
        with st.expander("Pipeline output", expanded=not ok):
            st.code(output or "No output.")

    if top_cols[2].button(
        "Refresh Reports",
        icon=":material/cached:",
        help="Rebuild Silver and Gold from saved approvals and completed manual entries",
        key="header_refresh_reports_button",
        use_container_width=True,
    ):
        with st.spinner("Refreshing reports..."):
            ok, output = refresh_reports(category_key)
        if ok:
            st.success("Silver and Gold reports refreshed.")
        else:
            st.error("Report refresh failed. Some outputs may be partially updated. Resolve the error and retry.")
            st.code(output)

    message = st.session_state.pop("review_saved_message", None)
    if message:
        st.success(message)
    if active_section in {
        "Allocation Report", "Completeness Check", "Year-over-year",
        "High Variance", "Missing Mapping", "Template Output", "Previous Data",
    }:
        st.caption("Reports reflect the last report refresh. After review changes, use Refresh Reports.")


def show_review_queue(category_key: str) -> None:
    selected_label = category_label(category_key)

    summary_df, issues_df, decisions_df, bronze_df = load_data(category_key)
    if summary_df.empty or issues_df.empty or decisions_df.empty or bronze_df.empty:
        st.info(f"Run the {selected_label} pipeline first to generate review checkpoints.")
        return

    target = st.session_state.pop(f"audit_{category_key}_review_target", None)
    if target:
        st.session_state[f"{category_key}_include_auto_approved_overrides"] = True
        st.session_state["selected_invoice_option"] = target
        st.session_state[f"{category_key}_review_status"] = "ALL"
        st.session_state[f"{category_key}_review_invoice"] = target
    st.subheader("Queue")
    open_queue_df = build_open_queue(summary_df, issues_df, decisions_df)
    include_approved = st.toggle(
        "Include approved rows for override",
        value=False,
        key=f"{category_key}_include_auto_approved_overrides",
    )
    base_queue_df = summary_df.copy() if include_approved else open_queue_df.copy()
    statuses = ["ALL", *sorted(base_queue_df["review_status"].dropna().unique().tolist())]
    if st.session_state.get(f"{category_key}_review_status") not in statuses:
        st.session_state[f"{category_key}_review_status"] = "ALL"
    queue_controls = st.columns([1, 2, 0.7, 0.7], vertical_alignment="bottom")
    selected_status = queue_controls[0].selectbox("Status", statuses, key=f"{category_key}_review_status")
    queue_df = base_queue_df.copy()
    if selected_status != "ALL":
        queue_df = queue_df[queue_df["review_status"] == selected_status]
    queue_df = queue_df.sort_values(["review_severity", "invoice_id"], ascending=[True, True])

    options = build_invoice_options(queue_df)
    if target and target not in options:
        st.warning("The invoice referenced by the audit is no longer in this review queue.")
        return
    if not options:
        st.info("No open invoices match this filter.")
        selected_option = None

    if options:
        current_option = st.session_state.get(
            f"{category_key}_review_invoice", st.session_state.get("selected_invoice_option")
        )
        if current_option not in options:
            current_option = options[0]
            st.session_state[f"{category_key}_review_invoice"] = current_option
        st.session_state["selected_invoice_option"] = current_option
        current_index = options.index(current_option)

        if queue_controls[2].button("Previous", disabled=current_index == 0, use_container_width=True):
            target_index = max(current_index - 1, 0)
            st.session_state["selected_invoice_option"] = options[target_index]
            st.session_state[f"{category_key}_review_invoice"] = options[target_index]
        if queue_controls[3].button("Next", disabled=current_index == len(options) - 1, use_container_width=True):
            target_index = min(current_index + 1, len(options) - 1)
            st.session_state["selected_invoice_option"] = options[target_index]
            st.session_state[f"{category_key}_review_invoice"] = options[target_index]

        current_option = st.session_state["selected_invoice_option"]
        current_index = options.index(current_option)
        selected_option = queue_controls[1].selectbox(
            "Invoice",
            options,
            index=current_index,
            format_func=invoice_option_label,
            key=f"{category_key}_review_invoice",
        )
        st.session_state["selected_invoice_option"] = selected_option
        selected_index = options.index(selected_option)
        st.caption(f"{selected_index + 1} of {len(options)} invoices in this queue")

    if selected_option is None:
        st.success("No open invoices match the current Data Approval queue filter.")
        return

    summary_row = selected_summary_row(queue_df, selected_option)
    invoice_id, line_id = line_key(summary_row)
    data_row = selected_data_row(bronze_df, invoice_id, line_id)
    invoice_issues = issues_for_invoice(issues_df, invoice_id, line_id)
    invoice_decisions = decisions_for_invoice(decisions_df, invoice_id, line_id)

    left, right = st.columns([1.15, 1])
    with left:
        st.subheader(selected_label)
        show_invoice_summary(summary_row, data_row)
        st.subheader("Current Decisions")
        if invoice_decisions.empty:
            st.caption("No decision rows found.")
        else:
            st.dataframe(
                invoice_decisions[
                    [
                        "field_name",
                        "review_decision",
                        "corrected_value",
                        "review_tag",
                        "reviewed_by",
                        "reviewed_at",
                    ]
                ],
                hide_index=True,
                use_container_width=True,
            )

    with right:
        show_review_form(
            invoice_issues,
            invoice_decisions,
            decisions_df,
            bronze_df,
            summary_df,
            summary_row,
            data_row,
            category_key,
        )


def manual_entry_option_label(option: tuple[str, str]) -> str:
    invoice_id, line_id = option
    return invoice_id if line_id in ("", "1") else f"{invoice_id} - line {line_id}"


def selected_manual_entry_row(queue_df: pd.DataFrame, option: tuple[str, str]) -> pd.Series:
    invoice_id, line_id = option
    return queue_df[
        (queue_df["invoice_id"].astype(str) == invoice_id)
        & (queue_df["line_id"].astype(str) == line_id)
    ].iloc[0]


def manual_entry_field_config(dropdown_config: dict, field_name: str) -> dict:
    return dropdown_config.get("fields", {}).get(field_name, {})


def manual_entry_field_label(dropdown_config: dict, field_name: str) -> str:
    return str(manual_entry_field_config(dropdown_config, field_name).get("label") or friendly_field_name(field_name))


def manual_entry_options(dropdown_config: dict, field_name: str) -> list[str]:
    options = manual_entry_field_config(dropdown_config, field_name).get("options", [])
    return [str(option) for option in options if str(option).strip()]


def hierarchy_options(dropdown_config: dict, division: str = "", legal_entity: str = "") -> tuple[list[str], list[str], list[str]]:
    hierarchy = dropdown_config.get("validation", {}).get("division_legal_entity_unit", {})
    if not isinstance(hierarchy, dict) or not hierarchy:
        return (
            manual_entry_options(dropdown_config, "division"),
            manual_entry_options(dropdown_config, "legal_entity_name"),
            manual_entry_options(dropdown_config, "unit"),
        )

    division_options = sorted(str(value) for value in hierarchy.keys())
    legal_entity_map = hierarchy.get(division, {}) if division else {}
    legal_entity_options = (
        sorted(str(value) for value in legal_entity_map.keys())
        if isinstance(legal_entity_map, dict) and legal_entity_map
        else manual_entry_options(dropdown_config, "legal_entity_name")
    )
    unit_options = legal_entity_map.get(legal_entity, []) if isinstance(legal_entity_map, dict) and legal_entity else []
    if not unit_options:
        unit_options = manual_entry_options(dropdown_config, "unit")
    return division_options, legal_entity_options, [str(value) for value in unit_options]


def select_dropdown(
    label: str,
    options: list[str],
    key: str,
    value: object = "",
    preserve_current: bool = True,
) -> str:
    current_value = str(value or "")
    current_choices = [current_value] if preserve_current or current_value in options else []
    choices = list(dict.fromkeys(["", *current_choices, *options]))
    index = choices.index(current_value) if current_value in choices else 0
    if key in st.session_state and st.session_state[key] not in choices:
        st.session_state[key] = ""
    kwargs = {
        "label": label,
        "options": choices,
        "index": index,
        "key": key,
    }
    if "accept_new_options" in inspect.signature(st.selectbox).parameters:
        kwargs["accept_new_options"] = True
    return str(st.selectbox(**kwargs) or "")


def select_manual_entry_date(
    label: str,
    key: str,
    value: object,
    dropdown_config: dict,
) -> str:
    selected_date = st.date_input(
        label,
        value=parse_manual_entry_date(value),
        format=manual_entry_date_display_format(dropdown_config),
        key=key,
    )
    if selected_date is None:
        return ""
    return selected_date.strftime(manual_entry_date_output_format(dropdown_config))


def select_manual_entry_number(label: str, key: str, value: object) -> str:
    parsed_value = parse_manual_entry_number(value)
    selected_number = st.number_input(
        label,
        value=parsed_value,
        key=key,
        step=1.0,
        format="%0.6f",
    )
    if selected_number is None:
        return ""
    return f"{selected_number:g}"


def parse_manual_entry_number(value: object) -> float | None:
    if value in (None, ""):
        return None
    parsed = pd.to_numeric(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return float(parsed)


def parse_manual_entry_date(value: object) -> date | None:
    if value in (None, ""):
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()


def manual_entry_date_output_format(dropdown_config: dict) -> str:
    return str(dropdown_config.get("manual_entry", {}).get("date_output_format") or "%Y-%m-%d")


def manual_entry_date_display_format(dropdown_config: dict) -> str:
    return str(dropdown_config.get("manual_entry", {}).get("date_display_format") or "YYYY-MM-DD")


def show_manual_data_entry_source(row: pd.Series) -> None:
    st.subheader("Source")
    metric_cols = st.columns(2)
    metric_cols[0].metric("Document Confidence", str(row.get("document_confidence", "")))
    metric_cols[1].metric("Threshold", str(row.get("document_confidence_threshold", "")))

    link = str(row.get("sharepoint_link", "")).strip()
    if link:
        st.link_button("Open evidence file", link)
        if row.get("manual_entry_source", "") == MANUAL_ENTRY_SOURCE_UPLOAD:
            st.caption("The evidence link becomes available after SharePoint sync completes.")
    elif str(row.get("source_path", "")).strip():
        st.caption(f"Source path: {row.get('source_path', '')}")

    st.table(pd.DataFrame([
        {"Field": "Invoice", "Value": row.get("invoice_id", "")},
        {"Field": "Manual entry source", "Value": row.get("manual_entry_source", "")},
        {"Field": "Original file name", "Value": row.get("original_file_name", "")},
        {"Field": "Uploaded at", "Value": row.get("uploaded_at", "")},
        {"Field": "Source file", "Value": row.get("source_file", "")},
        {"Field": "Status", "Value": row.get("manual_entry_status", "")},
    ]))


def show_manual_energy_mapping(
    entered_values: dict[str, object],
    existing_decision: pd.Series,
    invoice_id: str,
    line_id: str,
) -> dict[str, str]:
    selection = {"activity_group": "", "account_number": ""}
    if not all(entered_values.get(field) for field in ("division", "legal_entity_name", "unit")):
        st.info("Select Division, Legal Entity Name, and Unit to choose a KPI Component.")
        return selection
    try:
        table = load_account_mapping_table(ROOT_DIR / "config")
    except (OSError, ValueError, KeyError) as exc:
        st.error(f"Could not load account mapping: {exc}")
        return selection
    candidates = manual_mapping_candidates(table, {
        "division": entered_values["division"],
        "legal_entity": entered_values["legal_entity_name"],
        "unit_name": entered_values["unit"],
    })
    groups = [group for group in SCOPE2_ACTIVITY_GROUPS if group in candidates["activity_group"].values]
    labels = {f"Purchased {group.lower()}": group for group in groups}
    existing_group = str(existing_decision.get("activity_group", "") or "")
    label = select_dropdown(
        "KPI Component",
        list(labels),
        key=f"manual_entry_{invoice_id}_{line_id}_activity_group",
        value=f"Purchased {existing_group.lower()}" if existing_group else "",
        preserve_current=False,
    )
    if label not in labels:
        if not groups:
            st.warning("No Scope 2 energy accounts are mapped for this facility. Update the existing mapping workbook.")
        return selection
    selection["activity_group"] = labels[label]
    candidates = manual_mapping_candidates(candidates, selection)
    accounts = sorted({str(value).strip() for value in candidates["account_number"].dropna() if str(value).strip()})
    if len(accounts) == 1:
        selection["account_number"] = accounts[0]
        st.caption(f"Mapped account: {accounts[0]}")
    else:
        selection["account_number"] = select_dropdown(
            "Account number", accounts,
            key=f"manual_entry_{invoice_id}_{line_id}_account_number",
            value=existing_decision.get("account_number", ""),
            preserve_current=False,
        )
    if selection["account_number"]:
        matches = manual_mapping_candidates(candidates, selection)
        if len(matches) != 1:
            st.error("Multiple mapping rows match this account and KPI. Resolve the duplicates in the mapping workbook.")
            selection["account_number"] = ""
    return selection


def show_manual_data_entry_form(
    selected_row: pd.Series,
    decisions_df: pd.DataFrame,
    dropdown_config: dict,
    category_key: str,
) -> None:
    st.subheader("Manual Data Entry")
    reviewer_name = st.text_input("Reviewer", value=st.session_state.get("reviewer_name", ""), key="manual_entry_reviewer")
    st.session_state["reviewer_name"] = reviewer_name

    invoice_id, line_id = manual_entry_key(selected_row)
    existing_decision = pd.Series(dtype=object)
    if not decisions_df.empty:
        matches = decisions_df[
            (decisions_df["invoice_id"].astype(str) == invoice_id)
            & (decisions_df["line_id"].astype(str) == line_id)
        ]
        if not matches.empty:
            existing_decision = matches.iloc[0]

    entered_values: dict[str, object] = {}

    division_options, _, _ = hierarchy_options(dropdown_config)
    division = str(existing_decision.get("division", selected_row.get("division", "")) or "")
    legal_entity = str(existing_decision.get("legal_entity_name", selected_row.get("legal_entity_name", "")) or "")

    for field_name in MANUAL_DATA_ENTRY_FIELDS:
        if field_name == "division":
            division = select_dropdown(
                manual_entry_field_label(dropdown_config, "division"),
                division_options,
                key=f"manual_entry_{invoice_id}_{line_id}_division",
                value=division,
                preserve_current=False,
            )
            entered_values[field_name] = division
            continue
        if field_name == "legal_entity_name":
            _, legal_entity_options, _ = hierarchy_options(dropdown_config, division=division)
            legal_entity = select_dropdown(
                manual_entry_field_label(dropdown_config, "legal_entity_name"),
                legal_entity_options,
                key=f"manual_entry_{invoice_id}_{line_id}_legal_entity_name",
                value=legal_entity,
                preserve_current=False,
            )
            entered_values[field_name] = legal_entity
            continue
        if field_name == "unit":
            _, _, unit_options = hierarchy_options(dropdown_config, division=division, legal_entity=legal_entity)
            entered_values[field_name] = select_dropdown(
                manual_entry_field_label(dropdown_config, "unit"),
                unit_options,
                key=f"manual_entry_{invoice_id}_{line_id}_unit",
                value=existing_decision.get("unit", selected_row.get("unit", "")),
                preserve_current=False,
            )
            if category_key == "scope2":
                entered_values.update(show_manual_energy_mapping(
                    entered_values, existing_decision, invoice_id, line_id,
                ))
            continue
        if field_name in MANUAL_ENTRY_DATE_FIELDS:
            entered_values[field_name] = select_manual_entry_date(
                manual_entry_field_label(dropdown_config, field_name),
                key=f"manual_entry_{invoice_id}_{line_id}_{field_name}",
                value=existing_decision.get(field_name, selected_row.get(field_name, "")),
                dropdown_config=dropdown_config,
            )
            continue
        if field_name in MANUAL_ENTRY_NUMBER_FIELDS:
            entered_values[field_name] = select_manual_entry_number(
                manual_entry_field_label(dropdown_config, field_name),
                key=f"manual_entry_{invoice_id}_{line_id}_{field_name}",
                value=existing_decision.get(field_name, selected_row.get(field_name, "")),
            )
            continue
        entered_values[field_name] = select_dropdown(
            manual_entry_field_label(dropdown_config, field_name),
            manual_entry_options(dropdown_config, field_name),
            key=f"manual_entry_{invoice_id}_{line_id}_{field_name}",
            value=existing_decision.get(field_name, selected_row.get(field_name, "")),
        )

    review_comment = st.text_area(
        "Comment",
        value=str(existing_decision.get("review_comment", "")),
        key=f"manual_entry_{invoice_id}_{line_id}_comment",
    )
    if st.button("Save Manual Entry", type="primary", use_container_width=True):
        missing_fields = missing_manual_data_entry_fields(entered_values)
        if missing_fields:
            missing_labels = [
                manual_entry_field_label(dropdown_config, field_name)
                for field_name in missing_fields
            ]
            st.error(
                "Required field is blank: "
                + ", ".join(missing_labels)
                + ". Complete the required field before submitting."
            )
            return
        if category_key == "scope2":
            if not entered_values.get("activity_group") or not entered_values.get("account_number"):
                st.error("Select a KPI Component and a matching account before saving.")
                return
            if kwh_conversion_factor(entered_values.get("energy_unit")) is None:
                st.error("Select a supported Energy Unit: kWh, MWh, ton, or RTH.")
                return
            try:
                mapped = add_manual_unit_mapping_columns(pd.DataFrame([{
                    "division": entered_values["division"],
                    "legal_entity": entered_values["legal_entity_name"],
                    "unit_name": entered_values["unit"],
                    "activity_group": entered_values["activity_group"],
                    "account_number": entered_values["account_number"],
                }]), config_dir=ROOT_DIR / "config").iloc[0]
            except (OSError, ValueError, KeyError) as exc:
                st.error(f"Could not load account mapping: {exc}")
                return
            if mapped["mapping_status"] != "MAPPED":
                st.error(mapped["mapping_message"])
                return
        updated_decisions = upsert_manual_data_entry_decision(
            decisions_df,
            selected_row,
            entered_values,
            reviewer_name,
            review_comment,
        )
        save_manual_data_entry_decisions(updated_decisions, category_key)
        show_saved_message("Manual data entry saved. Refresh Reports to update reports.")


def show_manual_data_entry_queue(category_key: str) -> None:
    show_manual_upload_gateway(category_key)
    queue_df, decisions_df, dropdown_config = load_manual_data_entry_data(category_key)
    if queue_df.empty:
        st.info("No invoices are waiting for manual data entry.")
        return

    open_queue_df = build_open_manual_entry_queue(queue_df, decisions_df)
    open_entry_count = len(open_queue_df)
    target = st.session_state.get(f"audit_{category_key}_manual_target")
    if target:
        targeted_rows = queue_df[manual_entry_key_mask(queue_df, *target)]
        if targeted_rows.empty:
            st.warning("The invoice referenced by the audit is no longer in the manual entry queue.")
            st.session_state.pop(f"audit_{category_key}_manual_target", None)
        else:
            st.info("Opened from Audit and Report. This invoice may already be completed.")
            if st.button("Return to open manual entries", key=f"audit_{category_key}_close_manual"):
                st.session_state.pop(f"audit_{category_key}_manual_target", None)
                st.rerun()
            open_queue_df = targeted_rows
            st.session_state["selected_manual_entry_option"] = target
            st.session_state[f"{category_key}_manual_entry_invoice"] = target
    status_counts = {
        "Open": open_entry_count,
        "Completed": len(queue_df) - open_entry_count,
    }
    metric_cols = st.columns(2)
    metric_cols[0].metric("Open", status_counts["Open"])
    metric_cols[1].metric("Completed", status_counts["Completed"])

    if open_queue_df.empty:
        st.success("All manual data entry invoices are complete.")
        if not decisions_df.empty:
            st.dataframe(decisions_df, hide_index=True, use_container_width=True)
        return

    options = [manual_entry_key(row) for _, row in open_queue_df.iterrows()]
    current_option = st.session_state.get("selected_manual_entry_option")
    if current_option not in options:
        current_option = options[0]
        st.session_state["selected_manual_entry_option"] = current_option
    current_index = options.index(current_option)

    selected_option = st.selectbox(
        "Invoice",
        options,
        index=current_index,
        format_func=manual_entry_option_label,
        key=f"{category_key}_manual_entry_invoice",
    )
    st.session_state["selected_manual_entry_option"] = selected_option
    selected_row = selected_manual_entry_row(open_queue_df, selected_option)

    left, right = st.columns([0.9, 1.2])
    with left:
        show_manual_data_entry_source(selected_row)
    with right:
        show_manual_data_entry_form(selected_row, decisions_df, dropdown_config, category_key)


def show_manual_upload_gateway(category_key: str) -> None:
    with st.expander("Upload Unsupported Invoice File", expanded=False):
        st.caption(f"Upload folder: {manual_upload_dir(category_key)}")
        uploaded_file = st.file_uploader(
            "File",
            key=f"{category_key}_manual_upload",
            help="Upload an invoice file that OCR cannot accept. It will be added to this manual data entry queue.",
        )
        if uploaded_file is None:
            return
        if st.button("Add To Manual Entry Queue", type="primary", key=f"{category_key}_manual_upload_save"):
            try:
                stored_path = save_manual_upload(uploaded_file, category_key)
            except ValueError as error:
                st.error(f"Upload configuration error: {error}")
                return
            clear_cached_data()
            st.success(f"Added {uploaded_file.name} to manual data entry.")
            st.caption(f"Stored at: {stored_path}")
            st.rerun()


def show_flagged_duplicates(category_key: str) -> None:
    duplicate_df = load_duplicate_data(category_key)
    if duplicate_df.empty:
        st.info("No duplicate OCR rows are currently flagged.")
        return

    st.subheader("Flagged Duplicates")
    metric_cols = st.columns(2)
    metric_cols[0].metric("Duplicate Rows", len(duplicate_df))
    metric_cols[1].metric(
        "Duplicate Groups",
        duplicate_df.get("duplicate_group_id", pd.Series(dtype=object)).nunique(),
    )

    display_columns = [
        "duplicate_group_id",
        "duplicate_match_type",
        "source_file",
        "duplicate_of_source_file",
        "source_path",
        "sharepoint_link",
        "source_content_hash",
        "business_duplicate_key",
    ]
    available_columns = [column for column in display_columns if column in duplicate_df.columns]
    if available_columns:
        st.dataframe(duplicate_df[available_columns], hide_index=True, use_container_width=True)

    with st.expander("All Duplicate Data", expanded=False):
        st.dataframe(duplicate_df, hide_index=True, use_container_width=True)


def selected_app_section() -> str:
    if st.session_state.get(ACTIVE_SECTION_KEY) not in APP_SECTIONS:
        st.session_state[ACTIVE_SECTION_KEY] = APP_SECTIONS[0]
    return st.session_state[ACTIVE_SECTION_KEY]


def primary_section_for_app_section(section: str) -> str:
    for primary_section, sections in APP_SECTION_GROUPS.items():
        if section in sections:
            return primary_section
    return next(iter(APP_SECTION_GROUPS))


def selected_primary_section() -> str:
    active_section = selected_app_section()
    active_primary = primary_section_for_app_section(active_section)
    if st.session_state.get(ACTIVE_PRIMARY_SECTION_KEY) not in APP_SECTION_GROUPS:
        st.session_state[ACTIVE_PRIMARY_SECTION_KEY] = active_primary
    return st.session_state[ACTIVE_PRIMARY_SECTION_KEY]


def expanded_primary_section() -> str | None:
    if EXPANDED_PRIMARY_SECTION_KEY in st.session_state and st.session_state[EXPANDED_PRIMARY_SECTION_KEY] is None:
        return None
    expanded_section = st.session_state.get(EXPANDED_PRIMARY_SECTION_KEY)
    if expanded_section in APP_SECTION_GROUPS:
        return expanded_section
    active_primary = selected_primary_section()
    st.session_state[EXPANDED_PRIMARY_SECTION_KEY] = active_primary
    return active_primary


def toggle_primary_section(primary_section: str, sections: list[str]) -> None:
    if expanded_primary_section() == primary_section:
        st.session_state[EXPANDED_PRIMARY_SECTION_KEY] = None
        return
    st.session_state[EXPANDED_PRIMARY_SECTION_KEY] = primary_section
    st.session_state[ACTIVE_PRIMARY_SECTION_KEY] = primary_section
    if selected_app_section() not in sections:
        st.session_state[ACTIVE_SECTION_KEY] = sections[0]


def show_sidebar_navigation(category_key: str):
    with st.sidebar:
        if st.button("Home", icon=":material/home:", use_container_width=True):
            return_home()
            st.rerun()

        active_primary = selected_primary_section()
        expanded_primary = expanded_primary_section()
        for primary_section, sections in APP_SECTION_GROUPS.items():
            is_primary_active = active_primary == primary_section
            is_expanded = expanded_primary == primary_section
            state_suffix = "expanded" if is_expanded else "collapsed"
            if st.button(
                primary_section,
                key=f"primary_nav_{primary_section}_{state_suffix}",
                type="primary" if is_primary_active else "secondary",
                icon=PRIMARY_SECTION_ICONS.get(primary_section),
                help="Show or hide this section",
                use_container_width=True,
            ):
                toggle_primary_section(primary_section, sections)
                st.rerun()

            if is_expanded:
                for section in sections:
                    is_active = selected_app_section() == section
                    if st.button(
                        section,
                        key=f"nav_{section}",
                        type="primary" if is_active else "secondary",
                        use_container_width=True,
                    ):
                        st.session_state[ACTIVE_SECTION_KEY] = section
                        st.session_state[ACTIVE_PRIMARY_SECTION_KEY] = primary_section
                        st.session_state[EXPANDED_PRIMARY_SECTION_KEY] = primary_section
                        st.rerun()
    return selected_app_section()


def open_audit_invoice(category_key: str, source: str, invoice_id: str, line_id: str) -> None:
    """Navigation bridge: audit modules never import or mutate review internals."""
    manual = source == "Manual entry"
    target_key = f"audit_{category_key}_{'manual_target' if manual else 'review_target'}"
    st.session_state[target_key] = (invoice_id, line_id)
    st.session_state[ACTIVE_SECTION_KEY] = "Manual Data Entry" if manual else "Data Approval"
    st.session_state[ACTIVE_PRIMARY_SECTION_KEY] = "Review and Approval"
    st.session_state[EXPANDED_PRIMARY_SECTION_KEY] = "Review and Approval"
    st.rerun()


def main() -> None:
    inject_modern_styles()
    category_key = selected_category_key()
    if category_key is None:
        show_landing_page()
        return

    active_section = show_sidebar_navigation(category_key)
    show_page_header(category_key, active_section)
    if active_section == "Allocation Report":
        show_audit_report(
            category_key, ROOT_DIR, SETTINGS,
            open_review=lambda source, invoice, line: open_audit_invoice(
                category_key, source, invoice, line
            ),
        )
    elif active_section == "Completeness Check":
        show_completeness_check(category_key)
    elif active_section == "Year-over-year":
        show_year_over_year(category_key)
    elif active_section == "High Variance":
        show_high_variance(category_key)
    elif active_section == "Manual Data Entry":
        show_manual_data_entry_queue(category_key)
    elif active_section == "Flagged Duplicates":
        show_flagged_duplicates(category_key)
    elif active_section == "Data Approval":
        show_review_queue(category_key)
    elif active_section == "Decision History":
        show_decision_management(category_key)
    elif active_section == "Approved Data":
        show_data_overview(category_key)
    elif active_section == "Missing Mapping":
        show_missing_mapping(category_key)
    elif active_section == "Mapping Sources":
        show_mapping_sources()
    elif active_section == "Template Output":
        show_template_output(category_key)
    elif active_section == "Previous Data":
        show_previous_data(category_key)


if __name__ == "__main__":
    main()

