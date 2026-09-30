/*
  ESG SQLite warehouse schema entry point.

  Run from the project root with the SQLite CLI:
    sqlite3 data/warehouse/esg.db ".read database/schema.sql"

  For Python-based builds, use:
    python -m src.database.build_schema
*/

.read database/00_metadata.sql
.read database/01_shared_reference.sql
.read database/scope2/10_scope2_tables.sql
.read database/scope2/20_scope2_bronze_views.sql
.read database/scope2/30_scope2_silver_views.sql
.read database/scope2/40_scope2_gold_views.sql
.read database/scope2/50_scope2_dq_views.sql
