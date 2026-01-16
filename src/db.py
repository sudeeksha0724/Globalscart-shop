from __future__ import annotations

from contextlib import contextmanager

import psycopg
from sqlalchemy import create_engine

from .config import PostgresConfig


def get_engine(cfg: PostgresConfig):
    return create_engine(cfg.sqlalchemy_url(), future=True)


@contextmanager
def get_conn(cfg: PostgresConfig):
    conn = psycopg.connect(cfg.dsn())
    try:
        yield conn
    finally:
        conn.close()
