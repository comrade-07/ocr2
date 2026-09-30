-- ---------------------------------------------------------------------------
-- Data-quality views for review queues
-- ---------------------------------------------------------------------------

CREATE VIEW IF NOT EXISTS v_dq_scope2_unmatched_ocr AS
SELECT *
FROM v_silver_scope2_enriched
WHERE mapping_id IS NULL OR mapping_needs_review = 1;

CREATE VIEW IF NOT EXISTS v_dq_energy_allocation_invalid AS
SELECT
    energy_source_allocation_id,
    division,
    legal_entity,
    unit_name,
    supplier_name,
    fossil_fuel_pct,
    renewable_energy_pct,
    nuclear_pct,
    fossil_fuel_pct + renewable_energy_pct + nuclear_pct AS total_pct
FROM ref_energy_source_allocation
WHERE (fossil_fuel_pct + renewable_energy_pct + nuclear_pct) NOT BETWEEN 0.99 AND 1.01;

CREATE VIEW IF NOT EXISTS v_dq_scope2_contracts_missing_for_market_based AS
SELECT *
FROM v_silver_scope2_enriched
WHERE lower(coalesce(scope, '')) = 'scope 2'
  AND lower(coalesce(activity_group, '')) = 'electricity'
  AND contract_id IS NULL;
