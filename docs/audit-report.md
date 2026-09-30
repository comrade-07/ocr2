# Audit and Report

Open **Scope 2 → Audit and Report → Allocation Report**. Filter by **Division → Legal entity → Unit name**, a reporting year, and a month or all months. Each hierarchy filter includes an All option; legal entities and units narrow to the selected parent. Incompatible child and account selections reset automatically when a parent changes. Blank mappings are selectable as Unmapped. KPI Component, account, and data-source filters are optional. These filters apply to the details, summaries, exceptions, and both exports.

The page presents calculation details, facility/month summaries, and a paginated exception queue. Exception filters and pagination only affect browsing; downloads contain all records in the report scope. Select a case to inspect its complete invoice allocation history or open the existing invoice review workflow. Completed manual entries can be opened from a case as well.

Division, legal entity, and unit name are separate fields in the tables and exports. Reports spanning multiple units are ordered by division, legal entity, and unit name; PDF unit sections show each hierarchy field separately. The report-level filters apply before checks are calculated, so exported exceptions belong only to the selected hierarchy. Source references come from the Silver `sharepoint_link` field. Excel includes clickable Source columns (numbered when a case references several documents); PDF includes clickable SharePoint document links. Missing links are identified explicitly and never replaced with OCR JSON filenames. JSON filenames remain internal lineage metadata only.

## Calculation and scope

- Reporting year 2026 covers **1 December 2025 through 30 November 2026**. The same December-to-November rule applies to every reporting year, including expected coverage checks. Month options are ordered December through November and display the actual calendar year. Selecting December under reporting year 2026 means December 2025. Export scope labels include the exact date range.
- The report displays pipeline allocations and independently checks the arithmetic. It never repairs a quantity silently.
- Effective allocation dates count inclusively. First-day-to-first-day periods exclude the end date; last-day-to-last-day periods exclude the start date, including February and leap years. These calendar rules do not require neighbouring invoices. Printed dates remain visible. Full-invoice reconciliation includes months outside the selected reporting year.
- Silver compares approved OCR and completed manual entries together, using the existing division, legal entity, unit, supplier, and account fields. Both invoice periods participate. Without an account number, invoices are not linked.
- For other periods, a shared date with the next invoice excludes the earlier invoice's end; next-day boundaries retain inclusive dates. The latest invoice follows its immediate non-conflicting neighbour's boundary pattern and is rechecked on rebuild. Without usable history, other periods retain inclusive dates. Gaps do not extend periods or invent consumption. Duplicate periods and larger overlaps override automatic adjustment and remain exceptions; same-day invoices retain one day and invalid dates are not repaired.
- Date adjustment and short reasons are carried through Silver and Gold. Internal supporting references and provisional status remain available in pipeline lineage, but are not shown as audit columns. The loader re-resolves dates from source history and rejects stale or inconsistent split metadata. Invoice arithmetic checks remain independent of stored allocations.
- Audit Excel uses separate Invoice start/end, Allocation start/end, Date adjustment, Reason, Invoice days, and Days in month columns. It retains hierarchy, supplier/account, original billed quantity/unit, kWh conversion factor, billed/allocated kWh, verification formulas, Source links, data source, and invoice period reference. Boundary evidence, supporting-invoice, and provisional-date columns are omitted. PDF separates invoice and allocation periods from adjustment/reason tags, and includes original quantities, conversion factors, data source, supplier, and references for all invoices in a second table.
- Date adjustment values are `None`, `Start +1 day`, and `End −1 day`. Reasons are `Month-start dates`, `Month-end dates`, `Shared date`, `Consecutive dates`, `Previous invoice pattern`, `Insufficient history`, `Gap`, `Overlap`, `Single day`, and `Invalid dates`. Invoice days means the adjusted allocation period's day count; Days in month means that invoice's allocated days within the reporting month.
- kWh, MWh, ton, and RTH use the same conversion rules as Gold: multiply by 1, 1,000, 720, and 0.62 respectively. The ton and RTH factors are business-specified. OCR descriptions are cleaned to extract one supported unit; when none is extracted, Silver uses the matched account mapping's consumption unit. Audit follows the same resolution for each billing period. Units unresolved after fallback (including mmBTU without a supported fallback) are visible as exceptions and excluded from kWh totals. Unresolved account mapping is flagged even when facility fields are populated.
- Billing-date resolution now separates activity groups as well as facility/supplier/account, and unresolved account mappings cannot provide neighbouring-invoice context. Audit coverage checks and summaries group by KPI Component; tables include this field after Unit name. Excel uses separate Summary, Details, and Exceptions sheets per energy type, while PDF uses separate KPI sections and unit totals. Unclassified older records are retained explicitly. Missing coverage is a question for the reviewer, not proof of missing consumption: audit checks inspect accounts present in source inputs; the Completeness dashboard separately uses mapping expectations and optional effective dates.
- Audit still verifies source consumption even when final templates exclude an invoice for missing or invalid energy-source allocation. Those flags are available in Step 8/9 and **Missing Mapping**. Compare audit and Gold totals over the same included accounts; audit allocation means monthly date proration, while energy-source allocation means the fossil/renewable/nuclear split.
- The inputs contain reviewed OCR and completed manual entries. This report does not establish that all expected facilities, pending invoices, or rejected records have been supplied.
- Cases are derived from current data. There is no stored acknowledgement, case-history workflow, or finalized-period lock in this version. A rebuild can change historical monthly allocations; retain previous exports when comparing reporting revisions.
- Facility identity uses division, legal entity, and unit name together.

## Input files and freshness

The loader reads the configured Silver directory via existing path helpers:

1. `04_scope2_silver_aggregated.xlsx`
2. `06_scope2_silver_proration_split.xlsx`
3. `07A_scope2_silver_manual_mapping.xlsx`
4. `07C_scope2_silver_manual_proration_split.xlsx`

Older files without explicit billing-period references and date-resolution fields must be regenerated using the current Silver pipeline. Rebuild Gold afterward to refresh templates and dashboard totals. Report visits and downloads never run the pipeline. The source filenames, modification times, and SHA-256 fingerprints are included in reports. File-change detection invalidates the page's cached inputs. Newer review checkpoints or splits older than their source inputs disable export until Silver is rebuilt. These are freshness checks, not a signed or transactional pipeline-run manifest.

PDF export requires `reportlab`, listed in `requirements.txt`. Install the updated project requirements on each deployment. Excel uses the app's existing `openpyxl` dependency. Spreadsheet verification formulas recalculate when the workbook opens in Excel; pipeline values and report totals are stored as numbers and do not depend on formula recalculation to display.

## Module boundaries

| Module | Responsibility |
| --- | --- |
| `src/audit/models.py` | Report filters and result structures |
| `src/audit/loader.py` | File I/O, schema validation, source provenance, normalization |
| `src/audit/report.py` | Scope filtering, summaries, shared export tables |
| `src/audit/checks.py` | Independent arithmetic, reconciliation, coverage, and input checks |
| `src/audit/page.py` | Streamlit controls, cache boundary, pagination, case details, downloads |
| `src/audit/excel_export.py` | Workbook presentation and visible verification formulas |
| `src/audit/pdf_export.py` | Printable tables and detailed case appendix |

The page receives a navigation callback from `review_app.py`; audit modules do not import the app or save approval decisions. The pipeline retains invoice/line identifiers and a billing-period index, and groups monthly quantities separately by energy unit and facility hierarchy to avoid summing unlike units.

## Verification

Run `python -m pytest -q`. Audit tests cover inclusive date boundaries, leap years, cross-year reconciliation, multiple billing periods, manual entries, mixed units, missing inputs and allocations, source identity, literal spreadsheet text, 55-case PDF/Excel exports, page filtering/pagination, and the navigation bridge.
