-- ---------------------------------------------------------------------------
-- Scope 2 tables
-- Raw OCR output plus Scope 2-specific allocation and contract reference data.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS bronze_ocr_scope2 (
    ocr_record_id INTEGER PRIMARY KEY,
    load_batch_id INTEGER REFERENCES etl_load_batch(load_batch_id),

    source_file TEXT NOT NULL,
    source_path TEXT,
    sharepoint_link TEXT,

    legal_entity TEXT,
    legal_entity_confidence REAL,
    unit_name TEXT,
    unit_name_confidence REAL,
    supplier TEXT,
    supplier_confidence REAL,
    invoice_date TEXT,
    invoice_date_normalized TEXT,
    invoice_date_confidence REAL,
    account_number TEXT,
    account_number_confidence REAL,
    total_amount TEXT,
    total_amount_confidence REAL,

    consumption_start_date_1 TEXT,
    consumption_start_date_1_normalized TEXT,
    consumption_start_date_1_confidence REAL,
    consumption_end_date_1 TEXT,
    consumption_end_date_1_normalized TEXT,
    consumption_end_date_1_confidence REAL,
    consumption_start_date_2 TEXT,
    consumption_start_date_2_normalized TEXT,
    consumption_start_date_2_confidence REAL,
    consumption_end_date_2 TEXT,
    consumption_end_date_2_normalized TEXT,
    consumption_end_date_2_confidence REAL,

    quantity_1 TEXT,
    quantity_1_confidence REAL,
    quantity_2 TEXT,
    quantity_2_confidence REAL,
    quantity_3 TEXT,
    quantity_3_confidence REAL,
    quantity_4 TEXT,
    quantity_4_confidence REAL,
    quantity_5 TEXT,
    quantity_5_confidence REAL,
    quantity_6 TEXT,
    quantity_6_confidence REAL,
    quantity_unit_1 TEXT,
    quantity_unit_1_confidence REAL,
    quantity_unit_2 TEXT,
    quantity_unit_2_confidence REAL,

    sample_text TEXT,
    sample_text_confidence REAL,
    solar_export TEXT,
    solar_export_confidence REAL,
    solar_banking_charge TEXT,
    solar_banking_charge_confidence REAL,
    solar_total_generation TEXT,
    solar_total_generation_confidence REAL,

    document_confidence REAL,
    status TEXT,
    createdDateTime TEXT,
    lastUpdatedDateTime TEXT,
    apiVersion TEXT,
    modelId TEXT,
    needs_review INTEGER DEFAULT 0 CHECK (needs_review IN (0, 1)),
    missing_fields TEXT,
    low_confidence_fields TEXT,

    bronze_record_key TEXT GENERATED ALWAYS AS (
        lower(trim(coalesce(source_file, ''))) || '|' ||
        lower(trim(coalesce(account_number, ''))) || '|' ||
        lower(trim(coalesce(invoice_date_normalized, invoice_date, ''))) || '|' ||
        lower(trim(coalesce(total_amount, '')))
    ) STORED,

    inserted_at_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at_utc TEXT,

    UNIQUE (bronze_record_key)
);

CREATE INDEX IF NOT EXISTS ix_bronze_ocr_scope2_account
ON bronze_ocr_scope2 (lower(trim(account_number)));

CREATE INDEX IF NOT EXISTS ix_bronze_ocr_scope2_unit
ON bronze_ocr_scope2 (lower(trim(unit_name)));

CREATE INDEX IF NOT EXISTS ix_bronze_ocr_scope2_legal_entity
ON bronze_ocr_scope2 (lower(trim(legal_entity)));

CREATE TABLE IF NOT EXISTS ref_energy_source_allocation (
    energy_source_allocation_id INTEGER PRIMARY KEY,
    load_batch_id INTEGER REFERENCES etl_load_batch(load_batch_id),
    mapping_id INTEGER REFERENCES ref_facility_mapping(mapping_id),

    division TEXT,
    legal_entity TEXT,
    unit_name TEXT,
    facility_type TEXT,
    supplier_name TEXT,
    start_date TEXT,
    end_date TEXT,
    scope TEXT,
    activity_group TEXT,
    unit TEXT,
    fossil_fuel_pct REAL DEFAULT 0,
    renewable_energy_pct REAL DEFAULT 0,
    nuclear_pct REAL DEFAULT 0,

    energy_source_allocation_key TEXT GENERATED ALWAYS AS (
        lower(trim(coalesce(division, ''))) || '|' ||
        lower(trim(coalesce(legal_entity, ''))) || '|' ||
        lower(trim(coalesce(unit_name, ''))) || '|' ||
        lower(trim(coalesce(supplier_name, ''))) || '|' ||
        lower(trim(coalesce(start_date, ''))) || '|' ||
        lower(trim(coalesce(activity_group, '')))
    ) STORED,

    inserted_at_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at_utc TEXT,

    CHECK (fossil_fuel_pct BETWEEN 0 AND 1),
    CHECK (renewable_energy_pct BETWEEN 0 AND 1),
    CHECK (nuclear_pct BETWEEN 0 AND 1),
    CHECK ((fossil_fuel_pct + renewable_energy_pct + nuclear_pct) BETWEEN 0.99 AND 1.01),
    UNIQUE (energy_source_allocation_key)
);

CREATE INDEX IF NOT EXISTS ix_ref_energy_source_allocation_match
ON ref_energy_source_allocation (
    lower(trim(legal_entity)),
    lower(trim(unit_name)),
    lower(trim(supplier_name)),
    lower(trim(activity_group))
);

CREATE TABLE IF NOT EXISTS ref_contracts (
    contract_id INTEGER PRIMARY KEY,
    load_batch_id INTEGER REFERENCES etl_load_batch(load_batch_id),
    mapping_id INTEGER REFERENCES ref_facility_mapping(mapping_id),

    division TEXT,
    legal_entity TEXT,
    unit_name TEXT,
    supplier_name TEXT,
    contract_start_date TEXT,
    contract_end_date TEXT,
    contractual_instruments TEXT,
    bundle_or_unbundle TEXT,
    energy_source TEXT,
    energy_type TEXT,
    energy_unit TEXT,
    co2e REAL,
    co2e_unit TEXT,
    ch4 REAL,
    ch4_unit TEXT,
    co2 REAL,
    co2_unit TEXT,
    hfcs REAL,
    hfcs_unit TEXT,
    n2o REAL,
    n2o_unit TEXT,
    nf3 REAL,
    nf3_unit TEXT,
    pfcs REAL,
    pfcs_unit TEXT,
    sf6 REAL,
    sf6_unit TEXT,
    otherghgs REAL,
    otherghgs_unit TEXT,

    contract_key TEXT GENERATED ALWAYS AS (
        lower(trim(coalesce(legal_entity, ''))) || '|' ||
        lower(trim(coalesce(unit_name, ''))) || '|' ||
        lower(trim(coalesce(supplier_name, ''))) || '|' ||
        lower(trim(coalesce(contract_start_date, ''))) || '|' ||
        lower(trim(coalesce(contract_end_date, ''))) || '|' ||
        lower(trim(coalesce(contractual_instruments, '')))
    ) STORED,

    inserted_at_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at_utc TEXT,

    UNIQUE (contract_key)
);

CREATE INDEX IF NOT EXISTS ix_ref_contracts_match
ON ref_contracts (lower(trim(legal_entity)), lower(trim(unit_name)), lower(trim(supplier_name)));

-- Scope 2 final upload template from the workbook.
-- This stores the expected gold output shape; generated rows come from views.
CREATE TABLE IF NOT EXISTS gold_template_scope2 (
    gold_template_scope2_id INTEGER PRIMARY KEY,
    load_batch_id INTEGER REFERENCES etl_load_batch(load_batch_id),

    data_quality TEXT,
    kpi_component TEXT,
    division TEXT,
    legal_entity_name TEXT,
    unit TEXT,
    consumption_start_date TEXT,
    consumption_end_date TEXT,
    transaction_date TEXT,
    energy_kpi TEXT,
    energy_type TEXT,
    purchased_or_acquired TEXT,
    amount_of_energy_consumed REAL,
    energy_unit TEXT,
    contractual_instrument_used TEXT,

    inserted_at_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at_utc TEXT
);


-- Optional manual override for cases where an OCR invoice has multiple
-- quantities and the correct consumption field cannot be inferred safely.
CREATE TABLE IF NOT EXISTS ocr_quantity_selection (
    quantity_selection_id INTEGER PRIMARY KEY,
    ocr_record_id INTEGER NOT NULL REFERENCES bronze_ocr_scope2(ocr_record_id) ON DELETE CASCADE,
    selected_quantity_column TEXT NOT NULL CHECK (selected_quantity_column IN ('quantity_1', 'quantity_2', 'quantity_3', 'quantity_4', 'quantity_5', 'quantity_6')),
    selected_quantity_unit_column TEXT CHECK (selected_quantity_unit_column IN ('quantity_unit_1', 'quantity_unit_2')),
    selected_by TEXT,
    selected_at_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    reason TEXT,
    UNIQUE (ocr_record_id)
);
