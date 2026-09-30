-- ---------------------------------------------------------------------------
-- Silver: deterministic matching and enrichment
-- ---------------------------------------------------------------------------

CREATE VIEW IF NOT EXISTS v_silver_scope2_mapping_candidates AS
SELECT
    o.ocr_record_id,
    m.mapping_id,
    1 AS match_priority,
    'account_number' AS match_method
FROM bronze_ocr_scope2 o
JOIN ref_facility_mapping m
    ON nullif(lower(trim(o.account_number)), '') = nullif(lower(trim(m.account_number)), '')
WHERE coalesce(m.active, 'Yes') IN ('Yes', 'Y', '1')

UNION ALL

SELECT
    o.ocr_record_id,
    m.mapping_id,
    2 AS match_priority,
    'unit_name' AS match_method
FROM bronze_ocr_scope2 o
JOIN ref_facility_mapping m
    ON nullif(lower(trim(o.unit_name)), '') = nullif(lower(trim(m.unit_name)), '')
WHERE coalesce(m.active, 'Yes') IN ('Yes', 'Y', '1')

UNION ALL

SELECT
    o.ocr_record_id,
    m.mapping_id,
    3 AS match_priority,
    'legal_entity' AS match_method
FROM bronze_ocr_scope2 o
JOIN ref_facility_mapping m
    ON nullif(lower(trim(o.legal_entity)), '') = nullif(lower(trim(m.legal_entity)), '')
WHERE coalesce(m.active, 'Yes') IN ('Yes', 'Y', '1');

CREATE VIEW IF NOT EXISTS v_silver_scope2_best_mapping AS
WITH ranked AS (
    SELECT
        c.*,
        row_number() OVER (
            PARTITION BY c.ocr_record_id
            ORDER BY c.match_priority, c.mapping_id
        ) AS rn,
        count(*) OVER (PARTITION BY c.ocr_record_id, c.match_priority) AS same_priority_candidate_count
    FROM v_silver_scope2_mapping_candidates c
)
SELECT
    o.ocr_record_id,
    r.mapping_id,
    r.match_method,
    r.match_priority,
    coalesce(r.same_priority_candidate_count, 0) AS same_priority_candidate_count,
    CASE
        WHEN r.mapping_id IS NULL THEN 1
        WHEN r.same_priority_candidate_count > 1 THEN 1
        ELSE 0
    END AS mapping_needs_review
FROM bronze_ocr_scope2 o
LEFT JOIN ranked r
    ON r.ocr_record_id = o.ocr_record_id
   AND r.rn = 1;

CREATE VIEW IF NOT EXISTS v_silver_scope2_enriched AS
SELECT
    o.ocr_record_id,
    bm.mapping_id,
    bm.match_method,
    bm.mapping_needs_review,

    o.source_file,
    o.source_path,
    o.sharepoint_link,

    coalesce(m.legal_entity, o.legal_entity) AS legal_entity,
    coalesce(m.unit_name, o.unit_name) AS unit_name,
    coalesce(m.supplier_name, o.supplier) AS supplier_name,
    coalesce(m.account_number, o.account_number) AS account_number,

    m.facility_type,
    m.facility_identifier,
    m.allocation,
    m.division_allocation,
    m.division_shorthand,
    coalesce(da.division, m.division) AS division,
    m.scope,
    m.activity_group,
    m.document_type,
    m.document_language,
    m.invoice_frequency,
    m.supplier_number_oracle,
    m.operating_unit_oracle,
    m.supplier_site_name_oracle,
    m.decimal_separator,
    m.date_format,
    m.currency,
    coalesce(q.energy_unit, m.consumption_unit, o.quantity_unit_1, o.quantity_unit_2) AS consumption_unit,

    o.invoice_date,
    o.invoice_date_normalized,
    o.total_amount,
    o.consumption_start_date_1,
    o.consumption_start_date_1_normalized,
    o.consumption_end_date_1,
    o.consumption_end_date_1_normalized,
    o.consumption_start_date_2,
    o.consumption_start_date_2_normalized,
    o.consumption_end_date_2,
    o.consumption_end_date_2_normalized,
    q.selected_quantity_column,
    q.amount_of_energy_consumed_raw,
    q.quantity_selection_reason,

    esa.energy_source_allocation_id,
    coalesce(esa.fossil_fuel_pct, 1.0) AS fossil_fuel_pct,
    coalesce(esa.renewable_energy_pct, 0.0) AS renewable_energy_pct,
    coalesce(esa.nuclear_pct, 0.0) AS nuclear_pct,

    c.contract_id,
    c.contractual_instruments,
    c.bundle_or_unbundle,
    c.energy_source AS contract_energy_source,
    c.energy_type AS contract_energy_type,
    c.energy_unit AS contract_energy_unit,
    c.co2e,
    c.co2e_unit,
    c.ch4,
    c.ch4_unit,
    c.co2,
    c.co2_unit,
    c.n2o,
    c.n2o_unit,

    o.document_confidence,
    o.status,
    o.needs_review AS ocr_needs_review,
    o.missing_fields,
    o.low_confidence_fields
FROM bronze_ocr_scope2 o
LEFT JOIN v_silver_scope2_best_mapping bm
    ON bm.ocr_record_id = o.ocr_record_id
LEFT JOIN ref_facility_mapping m
    ON m.mapping_id = bm.mapping_id
LEFT JOIN ref_division_allocation da
    ON lower(trim(da.legal_entity)) = lower(trim(coalesce(m.legal_entity, o.legal_entity)))
   AND (
        nullif(lower(trim(da.unit_name)), '') = nullif(lower(trim(coalesce(m.unit_name, o.unit_name))), '')
        OR nullif(lower(trim(da.facility_identifier)), '') = nullif(lower(trim(m.facility_identifier)), '')
   )
LEFT JOIN v_bronze_selected_energy_quantity q
    ON q.ocr_record_id = o.ocr_record_id
LEFT JOIN ref_energy_source_allocation esa
    ON lower(trim(esa.legal_entity)) = lower(trim(coalesce(da.legal_entity, m.legal_entity, o.legal_entity)))
   AND lower(trim(coalesce(esa.unit_name, ''))) = lower(trim(coalesce(da.unit_name, m.unit_name, o.unit_name, '')))
   AND lower(trim(coalesce(esa.supplier_name, ''))) = lower(trim(coalesce(m.supplier_name, o.supplier, '')))
   AND lower(trim(coalesce(esa.activity_group, ''))) = lower(trim(coalesce(m.activity_group, '')))
LEFT JOIN ref_contracts c
    ON lower(trim(c.legal_entity)) = lower(trim(coalesce(da.legal_entity, m.legal_entity, o.legal_entity)))
   AND lower(trim(coalesce(c.unit_name, ''))) = lower(trim(coalesce(da.unit_name, m.unit_name, o.unit_name, '')))
   AND lower(trim(coalesce(c.supplier_name, ''))) = lower(trim(coalesce(m.supplier_name, o.supplier, '')));
