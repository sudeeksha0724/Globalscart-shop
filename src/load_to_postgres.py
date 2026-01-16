from __future__ import annotations

import argparse
from pathlib import Path

from .config import PostgresConfig
from .db import get_conn


TABLE_LOAD_ORDER = [
    ("globalcart.dim_geo", "dim_geo.csv"),
    ("globalcart.dim_fc", "dim_fc.csv"),
    ("globalcart.dim_customer", "dim_customer.csv"),
    ("globalcart.dim_product", "dim_product.csv"),
    ("globalcart.dim_date", "dim_date.csv"),
    ("globalcart.fact_orders", "fact_orders.csv"),
    ("globalcart.fact_order_items", "fact_order_items.csv"),
    ("globalcart.fact_payments", "fact_payments.csv"),
    ("globalcart.fact_funnel_events", "fact_funnel_events.csv"),
    ("globalcart.fact_shipments", "fact_shipments.csv"),
    ("globalcart.fact_returns", "fact_returns.csv"),
]


def _exec_file(conn, sql_path: Path) -> None:
    sql = sql_path.read_text(encoding="utf-8")
    conn.execute(sql, prepare=False)


def _copy_csv(conn, table: str, csv_path: Path) -> None:
    with csv_path.open("r", encoding="utf-8") as f:
        header = f.readline().strip()
        if not header:
            raise ValueError(f"Empty CSV: {csv_path}")
        cols = [c.strip() for c in header.split(",")]
        f.seek(0)

        col_list = ", ".join(cols)
        copy_sql = f"COPY {table} ({col_list}) FROM STDIN WITH (FORMAT csv, HEADER true)"

        with conn.cursor() as cur:
            with cur.copy(copy_sql) as copy:
                for line in f:
                    copy.write(line)


def load(raw_dir: Path, schema_sql: Path, truncate: bool) -> None:
    cfg = PostgresConfig()

    with get_conn(cfg) as conn:
        conn.execute("CREATE SCHEMA IF NOT EXISTS globalcart;", prepare=False)
        _exec_file(conn, schema_sql)

        if truncate:
            conn.execute(
                "TRUNCATE TABLE globalcart.fact_returns, globalcart.fact_shipments, globalcart.fact_funnel_events, globalcart.fact_payments, "
                "globalcart.fact_order_items, globalcart.fact_orders, "
                "globalcart.dim_date, globalcart.dim_product, globalcart.dim_customer, globalcart.dim_fc, globalcart.dim_geo CASCADE;",
                prepare=False)

        for table, fname in TABLE_LOAD_ORDER:
            p = raw_dir / fname
            if not p.exists():
                raise FileNotFoundError(f"Missing {p}. Generate data first.")
            _copy_csv(conn, table, p)

        conn.commit()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", default=str(Path(__file__).resolve().parents[1] / "data" / "raw"))
    parser.add_argument("--schema-sql", default=str(Path(__file__).resolve().parents[1] / "sql" / "00_schema.sql"))
    parser.add_argument("--truncate", action="store_true")
    args = parser.parse_args()

    load(raw_dir=Path(args.raw_dir), schema_sql=Path(args.schema_sql), truncate=args.truncate)


if __name__ == "__main__":
    main()
