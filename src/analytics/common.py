from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..config import Paths, PostgresConfig
from ..db import get_engine


def get_paths() -> Paths:
    project_root = str(Path(__file__).resolve().parents[2])
    return Paths(project_root=project_root)


def read_sql_df(sql: str) -> pd.DataFrame:
    cfg = PostgresConfig()
    engine = get_engine(cfg)
    return pd.read_sql(sql, engine)
