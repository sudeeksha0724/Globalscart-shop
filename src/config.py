from __future__ import annotations

import os
from pathlib import Path
from dataclasses import dataclass

from dotenv import load_dotenv


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class PostgresConfig:
    host: str = os.getenv("PGHOST", "localhost")
    port: int = int(os.getenv("PGPORT", "5432"))
    database: str = os.getenv("PGDATABASE", "globalcart")
    user: str = os.getenv("PGUSER", "globalcart")
    password: str = os.getenv("PGPASSWORD", "globalcart")

    def dsn(self) -> str:
        return (
            f"host={self.host} port={self.port} dbname={self.database} "
            f"user={self.user} password={self.password}"
        )

    def sqlalchemy_url(self) -> str:
        return f"postgresql+psycopg://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


@dataclass(frozen=True)
class Paths:
    project_root: str

    @property
    def data_raw_dir(self) -> str:
        return os.path.join(self.project_root, "data", "raw")

    @property
    def data_processed_dir(self) -> str:
        return os.path.join(self.project_root, "data", "processed")

    @property
    def reports_dir(self) -> str:
        return os.path.join(self.project_root, "reports")
