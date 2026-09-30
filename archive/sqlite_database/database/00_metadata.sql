/*
  ESG OCR SQLite warehouse layout

  Purpose
  -------
  Store shared ESG master/reference tables and domain-specific OCR outputs
  first, then produce bronze, silver, and gold outputs using SQL views.

  Design notes
  ------------
  - Wide tables are intentional. The source workbook is small and business users
    will maintain it directly.
  - Every persisted table has a surrogate integer primary key plus a natural
    key or uniqueness rule where the data supports it.
  - Foreign-key columns are included where useful, but the matching views do
    not require the ETL loader to know those IDs up front.
  - Scope 2 matching priority is account_number, then unit_name, then legal_entity.
  - Scope 1, water, and waste should reuse the shared reference tables and add
    their own bronze/silver/gold domain views.
  - SQLite does not include a built-in MD5/SHA function, so portable unique
    business keys are normalized concatenations. If the loader provides hashes,
    add them as extra columns without changing the view contracts.
*/

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- ---------------------------------------------------------------------------
-- Warehouse metadata
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS wh_schema_version (
    version_id INTEGER PRIMARY KEY,
    version_name TEXT NOT NULL UNIQUE,
    applied_at_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    notes TEXT
);

INSERT OR IGNORE INTO wh_schema_version (version_id, version_name, notes)
VALUES (1, 'esg_sqlite_warehouse_v1', 'Initial ESG warehouse layout with shared facility mapping and Scope 2 OCR/template outputs.');

CREATE TABLE IF NOT EXISTS etl_load_batch (
    load_batch_id INTEGER PRIMARY KEY,
    source_name TEXT NOT NULL,
    source_path TEXT,
    source_sheet TEXT,
    loaded_at_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    loaded_by TEXT,
    row_count INTEGER,
    notes TEXT,
    UNIQUE (source_name, source_path, source_sheet, loaded_at_utc)
);
