# ESG SQLite Warehouse SQL

This folder keeps the database schema modular so Scope 1, Scope 2, water, and
waste can grow independently while sharing the same master reference tables.

## Layout

- `schema.sql` is the SQLite CLI entry point.
- `00_metadata.sql` creates warehouse metadata/load tracking tables.
- `01_shared_reference.sql` creates shared master data tables.
- `scope2/` contains Scope 2 tables, views, and data-quality checks.

## Build

From the project root:

```powershell
python -m src.database.build_schema
```

To choose a database path:

```powershell
python -m src.database.build_schema --db data/warehouse/esg.db
```

If using the SQLite CLI:

```powershell
sqlite3 data/warehouse/esg.db ".read database/schema.sql"
```

## Expansion Pattern

When adding a new ESG domain, create the same file pattern:

```text
database/scope1/10_scope1_tables.sql
database/scope1/20_scope1_bronze_views.sql
database/scope1/30_scope1_silver_views.sql
database/scope1/40_scope1_gold_views.sql
database/scope1/50_scope1_dq_views.sql
```

Then add those files to `SCHEMA_FILES` in `src/database/build_schema.py` and
to `database/schema.sql`.
