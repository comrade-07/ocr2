-- ---------------------------------------------------------------------------
-- Shared reference tables from workbook sheets
-- Used across Scope 1, Scope 2, water, waste, and future ESG domains.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS ref_facility_mapping (
    mapping_id INTEGER PRIMARY KEY,
    load_batch_id INTEGER REFERENCES etl_load_batch(load_batch_id),

    facility_type TEXT,
    facility_identifier TEXT,
    allocation TEXT,
    division_allocation TEXT,
    division_shorthand TEXT,
    division TEXT,
    legal_entity TEXT,
    unit_name TEXT,
    scope TEXT,
    activity_group TEXT,
    document_type TEXT,
    document_language TEXT,
    invoice_count INTEGER,
    invoice_frequency TEXT,
    account_number TEXT,
    supplier_name TEXT,
    supplier_number_oracle TEXT,
    operating_unit_oracle TEXT,
    supplier_site_name_oracle TEXT,
    ocr_trained TEXT,
    labeled_by TEXT,
    decimal_separator TEXT,
    date_format TEXT,
    currency TEXT,
    consumption_unit TEXT,
    last_date_reviewed TEXT,
    msm_facility_name TEXT,
    msm_organizational_unit TEXT,
    active TEXT DEFAULT 'Yes',

    mapping_business_key TEXT GENERATED ALWAYS AS (
        lower(trim(coalesce(account_number, ''))) || '|' ||
        lower(trim(coalesce(legal_entity, ''))) || '|' ||
        lower(trim(coalesce(unit_name, ''))) || '|' ||
        lower(trim(coalesce(supplier_name, ''))) || '|' ||
        lower(trim(coalesce(activity_group, '')))
    ) STORED,

    inserted_at_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at_utc TEXT,

    CHECK (active IS NULL OR active IN ('Yes', 'No', 'Y', 'N', '1', '0')),
    UNIQUE (mapping_business_key)
);

CREATE INDEX IF NOT EXISTS ix_ref_facility_mapping_account
ON ref_facility_mapping (lower(trim(account_number)));

CREATE INDEX IF NOT EXISTS ix_ref_facility_mapping_unit
ON ref_facility_mapping (lower(trim(unit_name)));

CREATE INDEX IF NOT EXISTS ix_ref_facility_mapping_legal_entity
ON ref_facility_mapping (lower(trim(legal_entity)));

CREATE INDEX IF NOT EXISTS ix_ref_facility_mapping_active
ON ref_facility_mapping (active);

CREATE TABLE IF NOT EXISTS ref_division_allocation (
    division_allocation_id INTEGER PRIMARY KEY,
    load_batch_id INTEGER REFERENCES etl_load_batch(load_batch_id),
    mapping_id INTEGER REFERENCES ref_facility_mapping(mapping_id),

    division TEXT NOT NULL,
    legal_entity TEXT NOT NULL,
    unit_name TEXT,
    facility_identifier TEXT,

    division_allocation_key TEXT GENERATED ALWAYS AS (
        lower(trim(coalesce(division, ''))) || '|' ||
        lower(trim(coalesce(legal_entity, ''))) || '|' ||
        lower(trim(coalesce(unit_name, ''))) || '|' ||
        lower(trim(coalesce(facility_identifier, '')))
    ) STORED,

    inserted_at_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at_utc TEXT,

    UNIQUE (division_allocation_key)
);

CREATE INDEX IF NOT EXISTS ix_ref_division_allocation_match
ON ref_division_allocation (lower(trim(legal_entity)), lower(trim(unit_name)), lower(trim(facility_identifier)));

CREATE TABLE IF NOT EXISTS ref_dropdowns (
    dropdown_id INTEGER PRIMARY KEY,
    load_batch_id INTEGER REFERENCES etl_load_batch(load_batch_id),

    energy_kpi TEXT,
    energy_type TEXT,
    kpi_component TEXT,
    contractual_instrument_used TEXT,

    inserted_at_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at_utc TEXT,

    UNIQUE (energy_kpi, energy_type, kpi_component, contractual_instrument_used)
);
