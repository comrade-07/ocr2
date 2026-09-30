import argparse
import sqlite3
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATABASE_DIR = PROJECT_ROOT / "database"
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "warehouse" / "esg.db"

SCHEMA_FILES = [
    DATABASE_DIR / "00_metadata.sql",
    DATABASE_DIR / "01_shared_reference.sql",
    DATABASE_DIR / "scope2" / "10_scope2_tables.sql",
    DATABASE_DIR / "scope2" / "20_scope2_bronze_views.sql",
    DATABASE_DIR / "scope2" / "30_scope2_silver_views.sql",
    DATABASE_DIR / "scope2" / "40_scope2_gold_views.sql",
    DATABASE_DIR / "scope2" / "50_scope2_dq_views.sql",
]


def build_schema(db_path: Path = DEFAULT_DB_PATH) -> Path:
    """Create or update the SQLite warehouse schema."""
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as connection:
        for sql_file in SCHEMA_FILES:
            sql = sql_file.read_text(encoding="utf-8")
            connection.executescript(sql)

    return db_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the ESG SQLite warehouse schema.")
    parser.add_argument(
        "--db",
        default=str(DEFAULT_DB_PATH),
        help="SQLite database path. Defaults to data/warehouse/esg.db.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    db_path = build_schema(Path(args.db))
    print(f"ESG warehouse schema built: {db_path}")


if __name__ == "__main__":
    main()
