from __future__ import annotations

import os
from contextlib import contextmanager

import psycopg
from dotenv import load_dotenv


load_dotenv()


def _dsn() -> str:
    host = os.getenv("PGHOST", "localhost")
    port = int(os.getenv("PGPORT", "5432"))
    database = os.getenv("PGDATABASE", "globalcart")
    user = os.getenv("PGUSER", "globalcart")
    password = os.getenv("PGPASSWORD", "globalcart")

    return f"host={host} port={port} dbname={database} user={user} password={password}"


@contextmanager
def get_conn():
    conn = psycopg.connect(_dsn())
    try:
        yield conn
    finally:
        conn.close()
