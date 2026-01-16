from __future__ import annotations

from datetime import datetime
import os
from typing import Dict, Optional

from fastapi import APIRouter, Header, HTTPException, Query
import psycopg

from ..db import get_conn
from ..models import KpisLatestOut


router = APIRouter(prefix="/kpis", tags=["kpis"])


def _fetch_latest_kpis(conn, label: Optional[str] = None) -> KpisLatestOut:
    if label:
        sql = """
            WITH latest AS (
                SELECT snapshot_ts
                FROM globalcart.kpi_snapshots
                WHERE label = %s
                ORDER BY snapshot_ts DESC
                LIMIT 1
            )
            SELECT snapshot_ts, label, metric_name, metric_value
            FROM globalcart.kpi_snapshots
            WHERE label = %s AND snapshot_ts = (SELECT snapshot_ts FROM latest)
            ORDER BY metric_name;
        """
        params = (label, label)
    else:
        sql = """
            WITH latest AS (
                SELECT snapshot_ts
                FROM globalcart.kpi_snapshots
                ORDER BY snapshot_ts DESC
                LIMIT 1
            )
            SELECT snapshot_ts, label, metric_name, metric_value
            FROM globalcart.kpi_snapshots
            WHERE snapshot_ts = (SELECT snapshot_ts FROM latest)
            ORDER BY metric_name;
        """
        params = ()

    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    if not rows:
        raise HTTPException(
            status_code=404,
            detail=(
                "No KPI snapshots found yet."
            ),
        )

    snap_ts = rows[0][0]
    snap_label = str(rows[0][1])
    metrics: Dict[str, float] = {str(r[2]): float(r[3]) for r in rows}

    if isinstance(snap_ts, datetime):
        snap_ts = snap_ts.isoformat()
    else:
        snap_ts = str(snap_ts)

    return KpisLatestOut(snapshot_ts=snap_ts, label=snap_label, metrics=metrics)


@router.get("/latest", response_model=KpisLatestOut)
def latest_kpis(label: str | None = Query(None), admin_key: str | None = Header(None, alias="X-Admin-Key")):
    try:
        expected = os.getenv("ADMIN_KEY", "admin")
        if admin_key != expected:
            raise HTTPException(status_code=403, detail="Admin access required")
        with get_conn() as conn:
            conn.execute("SET TIME ZONE 'UTC';", prepare=False)
            return _fetch_latest_kpis(conn, label=label)
    except psycopg.OperationalError:
        raise HTTPException(
            status_code=503,
            detail=(
                "PostgreSQL connection failed. Set PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD in globalcart-360/.env "
                "and ensure PostgreSQL is running."
            ),
        )
    except (psycopg.errors.UndefinedTable, psycopg.errors.InvalidSchemaName):
        raise HTTPException(
            status_code=500,
            detail=(
                "Warehouse tables not found (missing globalcart.kpi_snapshots). "
                "Run the SQL setup to create required objects."
            ),
        )
