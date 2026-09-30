# Invoice Platform MVP

This project processes Azure Document Intelligence JSON files and exports a clean bronze CSV, bronze-based review checkpoints, duplicate and manual-entry queues, a local manual review app, and silver Excel workbooks.

The project is currently Excel-first. The earlier SQLite warehouse schema and builder are archived under `archive/sqlite_database/` for later use.

Scope 2 includes **Audit and Report → Allocation Report** for invoice-level monthly calculation verification, facility summaries, a paginated exception queue, and Excel/PDF exports. See [Audit report usage and architecture](docs/audit-report.md).

The pipeline reads raw OCR JSON files, extracts the configured invoice fields, adds confidence information, flags missing or low-confidence fields, detects duplicate OCR rows, and writes one CSV row per JSON file. Output folders are controlled from `config/settings.yaml`. The Streamlit review app reads those bronze OCR values directly, lets reviewers inspect invoice evidence, edit only failed fields, enter invoices that need full manual capture, and review duplicate rows separately.

## What It Produces

By default, the bronze output is written to:

```text
data/bronze/scope2_bronze.csv
```

By default, the silver-reviewed output, preserving approved/corrected data review values before normalization, is written to:

```text
data/silver/01_scope2_silver_reviewed.xlsx
```

By default, the silver-normalized output is written to:

```text
data/silver/02_scope2_silver_normalized.xlsx
```

By default, the silver-curated output is written to:

```text
data/silver/03_scope2_silver_curated.xlsx
```

By default, the silver-aggregated output is written to:

```text
data/silver/04_scope2_silver_aggregated.xlsx
```

By default, the silver-proration-calculation output is written to:

```text
data/silver/05_scope2_silver_proration_calculation.xlsx
```

By default, the silver-proration-split output is written to:

```text
data/silver/06_scope2_silver_proration_split.xlsx
```

By default, the silver-prorated monthly account/unit output is written to:

```text
data/silver/07_scope2_silver_prorated.xlsx
```

By default, the silver-business-mapping output is written to:

```text
data/silver/08_scope2_silver_business_mapping.xlsx
```

By default, the silver-template-preparation output is written to:

```text
data/silver/09_scope2_silver_template_preparation.xlsx
```

By default, the silver-template-output workbook is written to:

```text
data/silver/10_scope2_silver_template_output.xlsx
```

By default, the gold-template workbook is written to:

```text
data/gold/scope2_gold_template.xlsx
```

By default, review checkpoints are written to:

```text
data/output/checkpoints/scope2
```

The shared template has `category_checkpoint_dirs: true`, so checkpoints are separated by category. If that setting is disabled locally, checkpoints are written directly to `data/output/checkpoints`.

Step 0 review files are:

```text
data/output/checkpoints/scope2/step_0_flagged_duplicates_checkpoint.csv
data/output/checkpoints/scope2/step_0_manual_data_entry_queue.csv
data/output/checkpoints/scope2/step_0_manual_data_entry_decisions_checkpoint.csv
```

The pipeline writes the duplicate checkpoint and manual-entry queue. The manual-entry decisions file is created or updated by the review app when entries are saved.

Uploaded files that cannot go through OCR are stored under:

```text
data/manual_uploads/scope2
```

The project does not create copied JSON files in `data/bronze`. The raw JSON files stay in the source folder configured in your local `config/settings.yaml`.

## How It Works

1. `main.py` starts the pipeline.
2. `config/settings.yaml` defines the input and output folders for your own computer.
3. `src/extract/json_reader.py` finds and reads each `.json` file.
4. `config/field_mapping/scope2_fields.yaml` maps OCR field names to standard column names.
5. `src/transform/field_mapper.py` and `src/transform/field_extractor.py` extract field values and confidence scores.
6. `src/transform/confidence_extractor.py` identifies missing and low-confidence fields.
7. `src/pipeline/run_pipeline.py` builds one output row per JSON file and adds content/business duplicate keys.
8. `src/output/csv_writer.py` exports the final CSV.
9. `src/pipeline/run_review_pipeline.py` reads bronze and creates duplicate, manual data-entry, field quality, review summary, review issue, manual decision, and approved review checkpoints.
10. `review_app.py` opens a local data-entry app for manual review using raw OCR values from bronze, category-specific checkpoints, and manual-entry forms.
11. `src/pipeline/run_silver_pipeline.py` reads the approved review checkpoint and writes `silver_reviewed`.
12. `src/pipeline/run_silver_pipeline.py` then adds normalized fields and writes `silver_normalized`.
13. `src/pipeline/run_silver_pipeline.py` selects the curated columns from `silver_normalized` and writes `silver_curated`.
14. `src/pipeline/run_silver_pipeline.py` aggregates curated quantities and writes `silver_aggregated`.
15. `src/pipeline/run_silver_pipeline.py` calculates row-level monthly proration and writes `silver_proration_calculation`.
16. `src/pipeline/run_silver_pipeline.py` stacks period 1 and period 2 proration columns into shared proration fields and writes `silver_proration_split`.
17. `src/pipeline/run_silver_pipeline.py` aggregates prorated consumption by `account_number`, `unit_name`, and month, then writes `silver_prorated` with a full-month completeness check.
18. `src/pipeline/run_silver_pipeline.py` maps the monthly prorated rows into the business template and writes `silver_business_mapping`.
19. `src/pipeline/run_silver_pipeline.py` builds from `silver_business_mapping`, unpivots energy allocation percentages and solar values into template-ready Energy KPI rows, and writes `silver_template_preparation`.
20. `src/pipeline/run_silver_pipeline.py` filters zero-consumption Energy KPI rows from `silver_template_preparation` and writes `silver_template_output`.
21. `src/pipeline/run_gold_pipeline.py` applies unit conversions from `src/transform/unit_conversion.py` to `silver_template_output`, writes `gold_template`, and writes `gold_template_aggregated` for dashboard year-over-year reporting.
22. `src/output/xlsx_writer.py` exports Silver and Gold layers as Excel workbooks.

## Configuration

The shared settings template is:

```text
config/settings.example.yaml
```

Copy it to this local file:

```text
config/settings.yaml
```

`config/settings.yaml` is ignored by Git so each computer can keep its own path.

Home/testing input folders:

```yaml
raw_json_scope1: "data/source/scope1"
raw_json_scope2: "data/source"
raw_json_water: "data/source/water"
raw_json_waste: "data/source/waste"
```

Put local test JSON files in `data/source`. Raw JSON files are ignored by Git.

Work input folder example:

```yaml
raw_json_scope2: "C:/Users/My PC/SharePoint/raw_json"
```

Current output folders:

```yaml
bronze_output: "data/bronze"
silver_excel_output: "data/silver"
review_checkpoint_output: "data/output/checkpoints"
manual_data_entry_uploads: "data/manual_uploads"
category_checkpoint_dirs: true
gold_output: "data/gold"

# Waste-specific output folders; Scope 2 continues to use the paths above.
bronze_output_waste: "data/bronze/waste"
silver_excel_output_waste: "data/silver/waste"
review_checkpoint_output_waste: "data/output/checkpoints/waste"
manual_data_entry_uploads_waste: "data/manual_uploads/waste"
gold_output_waste: "data/gold/waste"
```

Change `silver_excel_output` to move the finished numbered Excel workbooks.

Waste output keys end in `_waste`, so Waste files can be moved independently without changing the Scope 2 paths or naming convention. The Waste bronze output is written to `data/bronze/waste/waste_bronze.csv` by default.

Use `category_checkpoint_dirs: true` to keep Scope 1, Scope 2, Water, and Waste review files in separate folders under `review_checkpoint_output`.

Manual data-entry dropdowns for Scope 2 are configured in:

```text
config/dropdowns/scope2_dropdown.yaml
```

The Division -> Legal Entity -> Unit cascading dropdown is sourced from:

```text
config/reference/master_entity_list.csv
```

To process a different raw JSON folder for one run, pass a folder directly when running the pipeline.

## Run

From the project folder:

```powershell
.\.venv\Scripts\python.exe main.py
```

This builds bronze first, generates review checkpoints from raw OCR values, then builds Silver from the approved review checkpoint. Rows that pass review automatically flow through; failed rows flow through only after approved or corrected in the review app. The `silver_reviewed` workbook shows that reviewed handoff before normalization; `silver_normalized` is built from it; `silver_curated` is selected from `silver_normalized`; `silver_aggregated` is built from `silver_curated`; `silver_proration_calculation` is built from `silver_aggregated`; `silver_proration_split` stacks the period-specific proration fields; `silver_prorated` is the final monthly account/unit rollup. Manual-entry rows are mapped into `silver_manual_mapping` before manual proration starts, then flow through `silver_manual_proration_calculation`, `silver_manual_proration_split`, and `silver_manual_prorated`. `silver_business_mapping` combines automated prorated rows with manual prorated rows and maps that rollup into the business template; `silver_template_preparation` builds from `silver_business_mapping` and unpivots energy allocation percentages and solar values into template-ready Energy KPI rows; `silver_template_output` removes zero-consumption and flagged business-mapping rows; `gold_template` converts supported consumption and accompanying totals to kWh; `gold_template_aggregated` groups purchased consumption by division, legal entity, unit, consumption start month, and KPI Component.

To run with a specific input folder:

```powershell
.\.venv\Scripts\python.exe main.py --input "C:/Users/My PC/Desktop/raw_json"
```

To run a specific ESG category:

```powershell
.\.venv\Scripts\python.exe main.py --category scope2
```

Valid category keys are `scope1`, `scope2`, `water`, and `waste`. The current Silver normalization and proration logic is built around the Scope 2 workflow.

If dependencies need to be installed:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Manual Review App

Start the app from the project folder:

```powershell
.\.venv\Scripts\streamlit.exe run review_app.py
```

Or double-click from File Explorer:

```text
Start Review App.cmd
```

The app can refresh the pipeline from inside the page. It reads invoice details from:

```text
data/bronze/scope2_bronze.csv
```

It reads failed fields from:

```text
data/output/checkpoints/scope2/step_3_review_issues_checkpoint.csv
```

Reviewer decisions are saved to:

```text
data/output/checkpoints/scope2/step_4_manual_review_decisions_checkpoint.csv
```

Approved or corrected raw OCR rows are written to:

```text
data/output/checkpoints/scope2/step_5_approved_silver_checkpoint.csv
```

The `silver_reviewed` workbook is built from that approved checkpoint, not directly from bronze. The `silver_normalized` workbook is built from `silver_reviewed`.

The first `silver_normalized` mapping step uses `account_number` to match `mappings/mapping.xlsx` and add these columns in order:

- `division`
- `legal_entity`
- `unit_name`
- `supplier_name`
- `division_shorthand`
- `facility_type`
- `scope`
- `facility_identifier`
- `activity_group`
- `invoice_count`
- `invoice_frequency`
- `consumption_unit`
- `decimal_separator`
- `currency`

If `account_number` does not match, the mapping step falls back to matching reviewed OCR `unit_name` against `ocr_unit_name_list`. If that does not match, it falls back to matching reviewed OCR `legal_entity` against `ocr_legal_entity_name_list`. If no mapping row matches, reviewed OCR `legal_entity` and `unit_name` stay in place for follow-up mapping, while the other mapping-owned fields are left blank.

After mapping, `total_amount` and `quantity_1` through `quantity_6` are cleaned using the mapped `decimal_separator`. `total_amount` first removes currency codes and currency symbols. Comma-decimal rows remove `.` thousands separators and convert `,` to `.`. Dot-decimal rows remove `,` thousands separators. Rows without a mapped decimal separator keep the reviewed OCR numeric values, except that `total_amount` still has currency units removed.

The normalized layer also adds `consumption_quantity_unit`. It extracts a single supported unit from descriptive OCR text (for example, `Consumption (kWh)` or `Total energy consumed [MWh]`). When no single valid unit is extracted, it falls back to the matched account mapping's `consumption_unit`. Cleaned unit fields contain only a supported unit or blank; original OCR text remains in Bronze and Silver Reviewed. Second billing periods use the same extraction and mapped-unit fallback, and audit uses the same resolved units. If neither source nor fallback supplies a supported unit, Gold publication is blocked.

Account mapping tries account number, OCR unit alias, then OCR legal-entity alias. Each match must identify a single mapping row; ambiguous matches do not fall through to a broader alias. `mapping_status`, `mapping_method`, `mapping_message`, and `extracted_account_number` are retained in the normalized and intermediate Silver layers. Resolved fallback accounts use the workbook account number while retaining the extracted value. Unresolved records appear under **Missing Mapping** and are excluded from monthly publishable results; correct the account through review or update the existing mapping workbook, then rebuild Silver.

Only failed fields from the review issues checkpoint are editable in the app. Saved fields are tagged as `MANUALLY_REVIEWED`.

Approved fields can be reopened from the review app if a reviewer needs to change a prior decision. Reopening marks the field as open again and rebuilds the Silver layers.

The app has review areas for Scope 1, Scope 2, Water, and Waste. Scope 2 currently has the full OCR-to-Silver workflow.

### Manual Data Entry

Invoices with `document_confidence` below the configured threshold are removed from the normal field-level review flow and added to:

```text
data/output/checkpoints/scope2/step_0_manual_data_entry_queue.csv
```

The threshold is controlled by `thresholds.document_confidence` in:

```text
config/confidence/scope2_confidence.yaml
```

Manual-entry rows capture these fields:

- `data_quality`
- `division`
- `legal_entity_name`
- `unit`
- `consumption_start_date`
- `consumption_end_date`
- `transaction_date`
- `amount_of_energy_consumed`
- `energy_unit`

Scope 2 also captures `activity_group` (displayed as KPI Component) and `account_number`. After selecting the facility, the form offers its Electricity, Steam, Heat, and Cool mappings from the same workbook used for OCR. A unique account is populated automatically; multiple accounts require a selection. Duplicate mapping rows or mismatched selections prevent saving. Changes to the workbook are read on the next form interaction.

Manual-entry rows match Division, Legal Entity, Unit, activity group, and selected account against the configured account mapping workbook and are written to `data/silver/07A_scope2_silver_manual_mapping.xlsx`. A valid entered consumption unit takes precedence; missing or unrecognized units use the matched mapping's consumption unit. Older checkpoints without an activity group retain unit-based matching only when it is unique (narrowed by account when available); ambiguous rows appear under **Missing Mapping**. The mapping layer carries account, supplier, activity group, facility, scope, and other fields needed by Silver Step 8. Mapped rows are prorated and routed into the same business-mapping logic as OCR rows. KPI Component and Energy Type are derived from the mapped activity group; allocations and contractual instruments still use the existing supporting workbooks.

Supported input units are `kWh`, `MWh`, `ton`, and `RTH`. The shared conversion rules in `src/transform/unit_conversion.py` multiply by 1, 1,000, 720, and 0.62 respectively to produce kWh. The ton and RTH factors are business-specified factors. The form uses these rules for its unit choices; `mmBTU` is no longer offered. Gold rejects unsupported units, and audit reports flag and exclude them from kWh totals. Original source quantities remain in Silver and audit; Gold retains Original Energy Unit and does not reconvert kWh values on repeat conversion.

The Scope 2 expansion is being delivered in three checkpoints:

1. Mapping and entry (complete): shared workbook, ambiguity checks, manual KPI/account selection, supported units, shared Gold/audit conversion, and propagation of mapping status. Validation: 206 tests passed, including Streamlit form interaction and mapping refresh tests.
2. Processing (complete): KPI-separated date sequences and aggregation, energy-specific allocation/contract lookup, template handling, and consistent kWh totals throughout final outputs. Missing or invalid energy-source allocation is flagged and excluded for every KPI, including electricity.
3. Reporting (complete): KPI Component in Completeness, YoY, High Variance, and their exports; expected-account coverage; historical comparisons; and separate audit results by energy KPI.

All three checkpoints are complete. Existing source files and workbooks are not migrated automatically: update the shared account mapping and supporting allocation rows, then rebuild Silver and Gold before using the reports.

Completeness, YoY, and High Variance display and filter **KPI Component** after Unit and retain it in Excel downloads. Completeness expects only the facility/KPI/accounts listed in the shared account mapping for active master facilities. It unions exact OCR/manual invoice dates for each account, then divides covered account-days by expected account-days; one account cannot conceal another missing account. Missing/invalid allocation rows and unsupported units do not count toward coverage. Valid zero-consumption invoices do count. Optional `effective_start_date` and `effective_end_date` columns in that same mapping are inclusive; blanks mean all selected months, and periods outside those dates show N/A. Duplicate account/KPI mappings or invalid dates must be corrected before reporting.

Previous Data uploads require explicit Division, Legal Entity Name, Unit, KPI Component, Consumption start date, Amount of energy consumed, and Energy Unit. Historical quantities use the same four conversion factors and compare only within the same facility/KPI/month. Existing electricity-only workbooks must explicitly say Purchased electricity and their actual unit; missing history stays unavailable rather than becoming zero. Solar production/self-generation rows are excluded from purchased-consumption comparisons. No Energy Unit column is added to the three dashboard exports because all compared quantities are kWh.

Audit checks, summaries, filters, and exports retain KPI Component. Excel creates separate Summary, Details, and Exceptions sheets for each energy type; PDF creates separate KPI sections. Legacy inputs without a valid activity group remain explicitly Unclassified until rebuilt.

Billing-date sequences and Silver monthly rollups now include `activity_group`. Silver retains source units through monthly proration. Gold converts allocated consumption, the accompanying total, and solar energy quantities to kWh before aggregation by Division, Legal Entity, Unit, month, and KPI Component. Purchased-energy totals exclude solar-production and self-generation rows; allocation percentages are weighted by the aggregated purchased quantities. Source-level totals are not added repeatedly for each allocation row.

The existing energy-source allocation and contract workbooks can include `account_number` and `activity_group` alongside their facility/supplier/date keys. A unique account-and-activity match takes precedence over account-only, activity-only, and legacy unqualified electricity rows. Unqualified rows never supply steam, heat, or cooling mappings. Equally specific matches are flagged as ambiguous; conflicting qualifiers are not used. This does not change the primary account mapping workbook as the source of invoice energy classification.

All three allocation fractions (`fossil_fuel_%`, `renewable_energy_%`, `nuclear_%`) must be provided, between 0 and 1, and total 1 within 0.000001. Missing, ambiguous, or invalid allocation is retained with `business_mapping_issue` in Step 8/9 and the existing **Missing Mapping** view, then excluded from Step 10 and Gold. This applies to electricity, steam, heat, and cooling; no allocation is invented. A missing contract remains optional, but ambiguous contracts are flagged and withheld. Rebuild Silver and Gold after correcting supporting workbook rows. A dedicated missing-allocation view is deferred.

The review app can also upload unsupported invoice files and add them to the same manual-entry queue with `manual_entry_source` set to `USER_UPLOAD`. OCR low-document-confidence rows use `OCR_LOW_DOCUMENT_CONFIDENCE`.

Manual-entry decisions are saved to:

```text
data/output/checkpoints/scope2/step_0_manual_data_entry_decisions_checkpoint.csv
```

### Duplicate Review

Bronze rows include duplicate metadata generated from the source OCR content hash and a normalized business key. The first row in each duplicate group is marked `PRIMARY`; later matching rows are marked `DUPLICATE`.

Duplicate rows are written to:

```text
data/output/checkpoints/scope2/step_0_flagged_duplicates_checkpoint.csv
```

Flagged duplicates are excluded from the normal review checkpoints and approved Silver handoff. The review app shows duplicate group, match type, source file, primary source file, and duplicate keys for follow-up.

## Output Columns

The bronze CSV includes:

- `invoice_id`
- `line_id`
- `source_file`
- `source_path`
- `source_content_hash`
- `business_duplicate_key`
- `duplicate_status`
- `duplicate_group_id`
- `duplicate_of_source_file`
- `duplicate_match_type`
- `sharepoint_link`
- extracted invoice fields, such as `legal_entity`, `supplier`, `total_amount`, and quantities
- confidence columns, such as `legal_entity_confidence`
- document metadata, including `document_confidence`, `status`, `createdDateTime`, `lastUpdatedDateTime`, `apiVersion`, and `modelId`
- `needs_review`
- `missing_fields`
- `low_confidence_fields`

Exact duplicate rows are still removed before export. Business/content duplicates are retained in bronze with duplicate metadata, then routed out of the normal review flow by the review pipeline.

The silver reviewed workbook preserves approved or corrected OCR values and adds `data_quality`, defaulting to `Actual` for OCR-sourced rows. The silver normalized workbook then adds normalized companion columns for these five business date fields only:

- `invoice_date_normalized`
- `consumption_start_date_1_normalized`
- `consumption_end_date_1_normalized`
- `consumption_start_date_2_normalized`
- `consumption_end_date_2_normalized`

Metadata dates such as `createdDateTime` and `lastUpdatedDateTime` are not normalized.

Raw date columns are kept as text in their extracted format. Normalized date columns are written as Excel dates with the display format `yyyy-mm-dd`.

In the silver Excel workbooks, non-empty `sharepoint_link` cells are written as clickable hyperlinks.

The silver workbook also cleans selected text fields:

- `legal_entity` and `unit_name`: trims leading/trailing spaces and punctuation, converts `-` and `_` to spaces, and applies proper casing.
- `supplier`: trims leading/trailing spaces and punctuation, converts `-` and `_` to spaces, and applies uppercase.
- `quantity_unit_1` and `quantity_unit_2`: keeps configured energy units such as KWH and MWH, removes non-energy units, and outputs uppercase.
- `consumption_quantity_unit`: keeps `quantity_unit_1` when present and otherwise uses the mapped `consumption_unit`.

## Common Issue

If the pipeline cannot write the CSV, close this file if it is open in Excel:

```text
data/bronze/scope2_bronze.csv
```

Then run the pipeline again.

## Saving reviews and refreshing reports

Field decisions and overrides update the existing manual-review decisions CSV and
approved checkpoint immediately. Manual entries update their own decisions CSV.
Reopened fields can be edited immediately, without refreshing reports. Saving,
reopening, and deleting review records no longer rebuild Silver workbooks.

After a batch of review changes, click **Refresh Reports** (formerly **App Data**)
to rebuild Silver and Gold from the saved approved checkpoint and completed manual
entries. Existing approvals remain included. This action does not reimport source
JSON or regenerate the review queues. Reports and Excel exports reflect the last
refresh until this action completes.

Use **Pipeline** to process new or changed source JSON, or changed extraction and
review rules. It continues to rebuild the source checkpoints and reporting layers.
If a report refresh fails, some workbooks may already have changed; resolve the
reported error and retry before using the outputs as a complete report set.
