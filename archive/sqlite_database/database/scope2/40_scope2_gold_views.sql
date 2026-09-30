-- ---------------------------------------------------------------------------
-- Gold: template output
-- Note: amount_of_energy_consumed_raw stays raw text in v1 because supplier
-- numeric formats differ by country. The next mature step is to add a loader
-- function or cleaned numeric column that respects decimal_separator.
-- ---------------------------------------------------------------------------

CREATE VIEW IF NOT EXISTS v_gold_scope2_template_output AS
WITH allocated AS (
    SELECT
        e.*,
        'Fossil Fuels' AS energy_kpi,
        e.fossil_fuel_pct AS allocation_pct
    FROM v_silver_scope2_enriched e
    WHERE e.fossil_fuel_pct > 0

    UNION ALL

    SELECT
        e.*,
        'Renewable sources' AS energy_kpi,
        e.renewable_energy_pct AS allocation_pct
    FROM v_silver_scope2_enriched e
    WHERE e.renewable_energy_pct > 0

    UNION ALL

    SELECT
        e.*,
        'Nuclear sources' AS energy_kpi,
        e.nuclear_pct AS allocation_pct
    FROM v_silver_scope2_enriched e
    WHERE e.nuclear_pct > 0
)
SELECT
    'Actual' AS "Data quality",
    CASE
        WHEN lower(coalesce(activity_group, '')) = 'electricity' THEN 'Purchased electricity'
        WHEN lower(coalesce(activity_group, '')) = 'steam' THEN 'Purchased steam'
        WHEN lower(coalesce(activity_group, '')) = 'cooling' THEN 'Purchased cool'
        WHEN lower(coalesce(activity_group, '')) = 'heating' THEN 'Purchased heat'
        ELSE coalesce(activity_group, 'Purchased electricity')
    END AS "KPI Component",
    division AS "Division",
    legal_entity AS "Legal Entity Name",
    unit_name AS "Unit",
    coalesce(consumption_start_date_1_normalized, consumption_start_date_1) AS "Consumption start date",
    coalesce(consumption_end_date_1_normalized, consumption_end_date_1) AS "Consumption end date",
    invoice_date_normalized AS "Transaction Date",
    energy_kpi AS "Energy KPI",
    coalesce(contract_energy_type, activity_group, 'Electricity') AS "Energy Type",
    'Purchased' AS "Purchased or acquired",
    amount_of_energy_consumed_raw AS "Amount of energy consumed",
    consumption_unit AS "Energy Unit",
    coalesce(contractual_instruments, 'No contractual instrument - emission factors unknown') AS "Contractual instrument used",

    -- Operational columns: keep these for audit/debug, drop them from the
    -- final upload SELECT if the receiving system requires exactly 14 columns.
    ocr_record_id,
    mapping_id,
    contract_id,
    energy_source_allocation_id,
    match_method,
    allocation_pct,
    selected_quantity_column,
    mapping_needs_review,
    ocr_needs_review
FROM allocated;

CREATE VIEW IF NOT EXISTS v_gold_scope2_template_output_upload AS
SELECT
    "Data quality",
    "KPI Component",
    "Division",
    "Legal Entity Name",
    "Unit",
    "Consumption start date",
    "Consumption end date",
    "Transaction Date",
    "Energy KPI",
    "Energy Type",
    "Purchased or acquired",
    "Amount of energy consumed",
    "Energy Unit",
    "Contractual instrument used"
FROM v_gold_scope2_template_output
WHERE coalesce(mapping_needs_review, 0) = 0
  AND coalesce(ocr_needs_review, 0) = 0;
