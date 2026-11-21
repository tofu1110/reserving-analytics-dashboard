"""Run the SQL pipeline in DuckDB and export the results to CSV.

Executes every file in sql/ in name order, then writes the analysis tables
to data/processed/ for Python and Power BI.
"""

import os
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
SQL_DIR = ROOT / "sql"
OUT_DIR = ROOT / "data" / "processed"

EXPORT_TABLES = [
    "fact_triangle",
    "fact_premium",
    "dim_accident_year",
    "dq_summary",
    "dq_pair_flags",
    "ata_paid_sql",
]


def main() -> None:
    os.chdir(ROOT)  # SQL files use paths relative to the repo root
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect()  # in-memory database
    for sql_file in sorted(SQL_DIR.glob("*.sql")):
        print(f"Running {sql_file.name}")
        con.execute(sql_file.read_text(encoding="utf-8"))

    for table in EXPORT_TABLES:
        out_path = (OUT_DIR / f"{table}.csv").as_posix()
        con.execute(f"COPY {table} TO '{out_path}' (HEADER, DELIMITER ',')")

    print("\nData quality summary:")
    print(con.sql("SELECT * FROM dq_summary"))
    print(f"Exported {len(EXPORT_TABLES)} tables to data/processed/")


if __name__ == "__main__":
    main()