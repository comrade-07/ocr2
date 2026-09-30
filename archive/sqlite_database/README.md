# Archived SQLite Database Work

This folder parks the earlier SQLite warehouse work while the program starts with the simpler Excel-first pipeline.

Archived contents:

- `database/`: SQL schema files and the original database README.
- `src/database/`: Python schema builder that used the standard-library `sqlite3` module.

There were no third-party SQLite packages in `requirements.txt`; the only runtime import was Python's built-in `sqlite3`.

To restore this work later, move:

- `archive/sqlite_database/database` back to `database`
- `archive/sqlite_database/src/database` back to `src/database`

Then re-check any README paths before running:

```powershell
.\.venv\Scripts\python.exe -m src.database.build_schema
```
