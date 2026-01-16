from __future__ import annotations

import argparse
from pathlib import Path

from .config import PostgresConfig
from .db import get_conn


def run_sql_file(sql_path: Path, stop_on_error: bool = False) -> None:
    sql = sql_path.read_text(encoding="utf-8")
    cfg = PostgresConfig()
    with get_conn(cfg) as conn:
        try:
            conn.execute(sql, prepare=False)
            conn.commit()
        except Exception as e:
            if stop_on_error:
                raise
            print(f"Error occurred: {e}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sql", required=True, help="Path to a .sql file")
    parser.add_argument("--stop-on-error", action="store_true", help="Stop execution on error")
    args = parser.parse_args()

    run_sql_file(Path(args.sql), stop_on_error=args.stop_on_error)


if __name__ == "__main__":
    main()
