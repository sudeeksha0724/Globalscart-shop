from __future__ import annotations

import argparse
import os
from pathlib import Path

from .config import PostgresConfig
from .dedupe_products import dedupe_products
from .generate_data import generate
from .load_to_postgres import load
from .run_sql import run_sql_file
from .generate_excel_report import build_excel_report
from .analytics.eda import run as run_eda
from .analytics.rfm import run as run_rfm
from .analytics.outliers import run as run_outliers
from .analytics.churn_cohort import run as run_churn_cohort
from .analytics.forecasting import run as run_forecasting


def run_pipeline(scale: str, truncate: bool) -> None:
    root = Path(__file__).resolve().parents[1]
    raw_dir = root / "data" / "raw"

    os.makedirs(raw_dir, exist_ok=True)

    generate(scale_name=scale, out_dir=raw_dir, seed=42)

    load(
        raw_dir=raw_dir,
        schema_sql=root / "sql" / "00_schema.sql",
        truncate=truncate,
    )

    dedupe_products(PostgresConfig())

    run_sql_file(root / "sql" / "04_incremental_refresh.sql", stop_on_error=True)

    run_sql_file(root / "sql" / "02_views.sql", stop_on_error=True)

    run_eda()
    run_rfm()
    run_outliers()
    run_churn_cohort()
    run_forecasting()

    os.makedirs(root / "reports", exist_ok=True)
    build_excel_report(root / "reports" / "globalcart_management_report.xlsx")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scale", default="small", choices=["small", "medium", "large"])
    parser.add_argument("--truncate", action="store_true")
    args = parser.parse_args()

    run_pipeline(scale=args.scale, truncate=args.truncate)


if __name__ == "__main__":
    main()
