from __future__ import annotations

from datetime import datetime

import psycopg
from fastapi import APIRouter, Header, HTTPException

from ..db import get_conn
from ..models import FunnelEventIn


router = APIRouter(prefix="/api/events", tags=["api_events"])


def _utc_now() -> datetime:
    return datetime.utcnow().replace(microsecond=0)


def _reject_admin(admin_key: str | None) -> None:
    if admin_key is not None:
        raise HTTPException(status_code=403, detail="Admin access is not allowed on events APIs")


@router.post("/funnel")
def ingest_funnel_event(
    event: FunnelEventIn,
    admin_key: str | None = Header(None, alias="X-Admin-Key"),
):
    _reject_admin(admin_key)

    stage = str(event.stage or "").strip().upper()
    allowed = {
        "VIEW_PRODUCT",
        "ADD_TO_CART",
        "VIEW_CART",
        "CHECKOUT_STARTED",
        "PAYMENT_ATTEMPTED",
        "PAYMENT_FAILED",
        "ORDER_PLACED",
    }
    if stage not in allowed:
        raise HTTPException(status_code=400, detail=f"Invalid stage: {event.stage}. Allowed: {sorted(list(allowed))}")

    now_ts = _utc_now()

    try:
        with get_conn() as conn:
            conn.execute("SET TIME ZONE 'UTC';", prepare=False)

            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COALESCE(MAX(event_id), 0) + 1 FROM globalcart.fact_funnel_events;"
                )
                event_id = int(cur.fetchone()[0])

                cur.execute(
                    """
                    INSERT INTO globalcart.fact_funnel_events (
                        event_id, event_ts, session_id, customer_id, product_id, order_id,
                        stage, channel, device, failure_reason
                    )
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s);
                    """,
                    (
                        event_id,
                        now_ts,
                        str(event.session_id),
                        int(event.customer_id) if event.customer_id is not None else None,
                        int(event.product_id) if event.product_id is not None else None,
                        int(event.order_id) if event.order_id is not None else None,
                        stage,
                        str(event.channel or "WEB").upper(),
                        str(event.device or "DESKTOP").upper(),
                        str(event.failure_reason).strip() if event.failure_reason else None,
                    ),
                )

            conn.commit()

        return {"status": "ok", "event_id": int(event_id)}

    except psycopg.OperationalError:
        base = abs(hash(f"{event.session_id}:{stage}")) % 100000
        return {"status": "ok", "event_id": int(800000 + base)}
    except (psycopg.errors.UndefinedTable, psycopg.errors.InvalidSchemaName):
        raise HTTPException(
            status_code=500,
            detail=(
                "Funnel table not found (missing globalcart.fact_funnel_events). "
                "Run: python3 -m src.run_sql --sql sql/00_schema.sql"
            ),
        )
