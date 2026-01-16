from __future__ import annotations

import os
import hashlib
import re
from pathlib import Path
from urllib.parse import quote
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import Response
import psycopg

from ..db import get_conn
from ..models import (
    AdminAuditLogItemOut,
    AdminKpisLatestOut,
    AdminLoginIn,
    AdminLoginOut,
    AdminOrderSummaryOut,
    FinanceCustomerPnlOut,
    FinanceOrderPnlOut,
    FinanceProductPnlOut,
    FinanceSummaryOut,
    FunnelDailyMetricOut,
    FunnelPaymentFailureOut,
    FunnelProductLeakageOut,
    FunnelSummaryOut,
    JourneyEventOut,
    JourneySessionOut,
    ProductDetailOut,
)


router = APIRouter(prefix="/api/admin", tags=["api_admin"])


def _csv_escape(v) -> str:
    if v is None:
        s = ""
    else:
        s = str(v)
    if any(ch in s for ch in [",", "\n", "\r", '"']):
        s = '"' + s.replace('"', '""') + '"'
    return s


def _to_csv(columns: List[str], rows: List[tuple]) -> str:
    out = [",".join([_csv_escape(c) for c in columns])]
    for r in rows:
        out.append(",".join([_csv_escape(x) for x in r]))
    return "\n".join(out) + "\n"


def _require_admin(admin_key: str | None) -> None:
    expected = os.getenv("ADMIN_KEY", "admin")
    if admin_key != expected:
        raise HTTPException(status_code=403, detail="Admin access required")


def _stable_discount_pct(product_id: int) -> int:
    return [5, 8, 10, 12, 15, 18, 20][product_id % 7]


def _image_url(seed: str, label: str) -> str:
    bg = hashlib.md5(seed.encode("utf-8")).hexdigest()[:6]
    label_short = (label or "Product")[:32]
    words = [w for w in label_short.replace("/", " ").replace("-", " ").split() if w]
    mono = ((words[0][0] if words else "G") + (words[1][0] if len(words) > 1 else "")).upper()

    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' width='600' height='600' viewBox='0 0 600 600'>"
        "<defs>"
        f"<linearGradient id='bg' x1='0' y1='0' x2='1' y2='1'>"
        f"<stop offset='0' stop-color='#{bg}' stop-opacity='0.95'/>"
        "<stop offset='1' stop-color='#111827' stop-opacity='0.90'/>"
        "</linearGradient>"
        "</defs>"
        "<rect width='600' height='600' fill='url(#bg)'/>"
        "<circle cx='460' cy='170' r='110' fill='rgba(255,255,255,0.10)'/>"
        "<circle cx='160' cy='430' r='160' fill='rgba(255,255,255,0.08)'/>"
        "<rect x='55' y='420' width='490' height='120' rx='18' fill='rgba(17,24,39,0.55)'/>"
        f"<text x='300' y='285' text-anchor='middle' font-size='120' font-family='Arial, Helvetica, sans-serif' font-weight='700' fill='rgba(255,255,255,0.92)'>{mono}</text>"
        f"<text x='300' y='490' text-anchor='middle' font-size='30' font-family='Arial, Helvetica, sans-serif' fill='rgba(255,255,255,0.92)'>{label_short}</text>"
        "</svg>"
    )

    return "data:image/svg+xml;charset=utf-8," + quote(svg)


def _product_photo_url(
    seed: str,
    label: str,
    category_l1: str | None,
    category_l2: str | None,
    product_id: int | None = None,
    sku: str | None = None,
) -> str:
    root = Path(__file__).resolve().parents[2]
    assets = root / "frontend" / "assets" / "images" / "products"

    exts = [".jpg", ".jpeg", ".png", ".webp"]

    if product_id is not None:
        for ext in exts:
            name = f"product_{int(product_id)}{ext}"
            if (assets / name).exists():
                return f"/assets/images/products/{name}"

    if label:
        slug_us = re.sub(r"[^a-zA-Z0-9]+", "_", label.strip().lower()).strip("_")
        slug_ds = re.sub(r"[^a-zA-Z0-9]+", "-", label.strip().lower()).strip("-")
        for ext in exts:
            for name in [
                f"product_{slug_us}{ext}" if slug_us else "",
                f"product-{slug_ds}{ext}" if slug_ds else "",
            ]:
                if name and (assets / name).exists():
                    return f"/assets/images/products/{name}"

    if (assets / "placeholder.svg").exists():
        return "/assets/images/products/placeholder.svg"

    return _image_url(seed=seed, label=label)


def _fetch_latest_kpis(conn, label: Optional[str] = None) -> AdminKpisLatestOut:
    if label:
        sql = """
            WITH latest AS (
                SELECT snapshot_ts
                FROM globalcart.vw_admin_kpis
                WHERE label = %s
                ORDER BY snapshot_ts DESC
                LIMIT 1
            )
            SELECT snapshot_ts, label, metric_name, metric_value
            FROM globalcart.vw_admin_kpis
            WHERE label = %s AND snapshot_ts = (SELECT snapshot_ts FROM latest)
            ORDER BY metric_name;
        """
        params = (label, label)
    else:
        sql = """
            WITH latest AS (
                SELECT snapshot_ts
                FROM globalcart.vw_admin_kpis
                ORDER BY snapshot_ts DESC
                LIMIT 1
            )
            SELECT snapshot_ts, label, metric_name, metric_value
            FROM globalcart.vw_admin_kpis
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
            detail="No KPI snapshots found yet.",
        )

    snap_ts = rows[0][0]
    snap_label = str(rows[0][1])
    metrics: Dict[str, float] = {str(r[2]): float(r[3]) for r in rows}

    if isinstance(snap_ts, datetime):
        snap_ts = snap_ts.isoformat()
    else:
        snap_ts = str(snap_ts)

    return AdminKpisLatestOut(
        snapshot_ts=snap_ts,
        label=snap_label,
        metrics=metrics,
        kpi_last_updated_at=snap_ts,
    )


def _demo_now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat()


def _demo_admin_kpis_latest(label: Optional[str] = None) -> AdminKpisLatestOut:
    ts = _demo_now_iso()
    lab = str(label) if label else "demo"
    metrics: Dict[str, float] = {
        "net_revenue_total": 6838551450.52,
        "orders_total": 51898.0,
        "refund_amount_total": 113293144.46,
        "shipping_cost_total": 449847.62,
        "conversion_rate": 0.6533,
        "cart_abandonment_rate": 0.1048,
        "payment_failure_rate": 0.0853,
        "revenue_lost_due_to_abandonment": 831276105.06,
        "revenue_lost_due_to_failures": 637263483.38,
    }
    return AdminKpisLatestOut(snapshot_ts=ts, label=lab, metrics=metrics, kpi_last_updated_at=ts)


def _demo_admin_orders(limit: int, offset: int) -> List[AdminOrderSummaryOut]:
    now = datetime.utcnow().replace(microsecond=0)
    rows: List[AdminOrderSummaryOut] = []
    n = int(min(max(limit, 1), 200))
    base = 12000 + int(offset)
    statuses = ["PLACED", "SHIPPED", "DELIVERED", "CANCELLED", "PAYMENT_FAILED"]
    channels = ["WEB", "APP"]
    for i in range(n):
        oid = base + i
        ts = (now - timedelta(minutes=27 * i)).isoformat()
        cid = int(7000 + (oid % 500))
        rows.append(
            AdminOrderSummaryOut(
                order_id=int(oid),
                customer_id=cid,
                customer_name=f"Customer {cid}",
                customer_email=f"customer{cid}@gmail.com",
                order_ts=ts,
                order_status=statuses[oid % len(statuses)],
                net_amount=float(250 + (oid % 8000) + ((oid % 10) * 0.15)),
                channel=channels[oid % len(channels)],
            )
        )
    return rows


def _demo_funnel_summary(window_days: int) -> FunnelSummaryOut:
    w = int(window_days)
    product_views = 10482
    add_to_cart = 5604
    checkout_started = 4120
    payment_attempts = 3988
    orders_placed = 3481
    conv = orders_placed / product_views if product_views else 0.0
    abandon = (add_to_cart - checkout_started) / add_to_cart if add_to_cart else 0.0
    pay_fail = 0.0853
    net_rev = 563183189.29
    lost_abandon = 61377523.22
    lost_fail = 43561694.99
    refunds = 13875248.10
    after = net_rev - refunds - lost_abandon - lost_fail
    return FunnelSummaryOut(
        window_days=w,
        product_views=int(product_views),
        add_to_cart=int(add_to_cart),
        checkout_started=int(checkout_started),
        payment_attempts=int(payment_attempts),
        orders_placed=int(orders_placed),
        conversion_rate=float(round(conv, 4)),
        cart_abandonment_rate=float(round(abandon, 4)),
        payment_failure_rate=float(round(pay_fail, 4)),
        net_revenue_ex_tax=float(net_rev),
        revenue_lost_cart_abandonment=float(lost_abandon),
        revenue_lost_payment_failures=float(lost_fail),
        refunds_leakage=float(refunds),
        net_revenue_after_leakage=float(after),
    )


def _demo_funnel_daily(window_days: int) -> List[FunnelDailyMetricOut]:
    now = datetime.utcnow().date()
    days = int(min(max(window_days, 1), 90))
    out: List[FunnelDailyMetricOut] = []
    for i in range(min(days, 14)):
        dt = (now - timedelta(days=i)).isoformat()
        views = 520 + (i * 17) % 200
        atc = 260 + (i * 11) % 120
        chk = 190 + (i * 9) % 80
        pay = 175 + (i * 7) % 70
        ords = 150 + (i * 5) % 60
        conv = ords / views if views else 0.0
        aband = (atc - chk) / atc if atc else 0.0
        pf = 0.08 + ((i % 3) * 0.006)
        out.append(
            FunnelDailyMetricOut(
                event_dt=dt,
                product_views=int(views),
                add_to_cart=int(atc),
                checkout_started=int(chk),
                payment_attempts=int(pay),
                orders_placed=int(ords),
                conversion_rate=float(round(conv, 4)),
                cart_abandonment_rate=float(round(aband, 4)),
                payment_failure_rate=float(round(pf, 4)),
            )
        )
    return out


def _demo_journey_sessions(limit: int, offset: int) -> List[JourneySessionOut]:
    now = datetime.utcnow().replace(microsecond=0)
    n = int(min(max(limit, 1), 200))
    off = int(offset)
    out: List[JourneySessionOut] = []
    channels = ["WEB", "APP"]
    devices = ["DESKTOP", "MOBILE"]
    for i in range(n):
        idx = off + i
        sid = f"demo_sess_{(120000 + idx):06d}"
        first = now - timedelta(minutes=(idx * 13) % (60 * 36))
        ev = 6 + (idx % 9)
        last = first + timedelta(minutes=(ev * 2) + (idx % 4))
        out.append(
            JourneySessionOut(
                session_id=sid,
                customer_id=int(7000 + (idx % 800)) if (idx % 6) else None,
                first_event_ts=first.isoformat(),
                last_event_ts=last.isoformat(),
                event_count=int(ev),
                channel=channels[idx % len(channels)],
                device=devices[idx % len(devices)],
            )
        )
    return out


def _demo_journey_events(session_id: str) -> List[JourneyEventOut]:
    now = datetime.utcnow().replace(microsecond=0)
    sid = str(session_id or "")
    base = abs(hash(sid)) % 100000
    first = now - timedelta(minutes=(base % 600) + 30)
    customer_id = int(7000 + (base % 800))
    stages = [
        "VIEW_PRODUCT",
        "ADD_TO_CART",
        "VIEW_CART",
        "CHECKOUT_STARTED",
        "PAYMENT_ATTEMPTED",
        "ORDER_PLACED",
    ]
    out: List[JourneyEventOut] = []
    for i, st in enumerate(stages):
        ts = (first + timedelta(minutes=i * 3)).isoformat()
        out.append(
            JourneyEventOut(
                event_id=int(900000 + base + i),
                event_ts=ts,
                session_id=sid,
                customer_id=customer_id,
                stage=st,
                channel="WEB",
                device="DESKTOP",
                product_id=int(1000 + (base % 300)) if st in ("VIEW_PRODUCT", "ADD_TO_CART") else None,
                order_id=int(12000 + (base % 300)) if st == "ORDER_PLACED" else None,
                failure_reason=None,
            )
        )
    return out


def _demo_product_leakage(limit: int, offset: int) -> List[FunnelProductLeakageOut]:
    n = int(min(max(limit, 1), 25))
    base = 1000 + int(offset)
    out: List[FunnelProductLeakageOut] = []
    for i in range(n):
        pid = base + i
        views = 900 - (i * 23)
        atc = max(0, int(views * 0.45))
        aband = max(0, int(atc * 0.22))
        fail = max(0, int((atc - aband) * 0.04))
        lost_abandon = float(9800 + (i * 731) % 24000)
        lost_fail = float(6200 + (i * 419) % 18000)
        out.append(
            FunnelProductLeakageOut(
                product_id=int(pid),
                product_name=f"Demo Product {pid}",
                product_views=int(max(0, views)),
                add_to_cart=int(atc),
                abandoned_adds=int(aband),
                revenue_lost_cart_abandonment=float(lost_abandon),
                failed_orders=int(fail),
                revenue_lost_payment_failures=float(lost_fail),
            )
        )
    return out


def _demo_payment_failures(window_days: int, limit: int, offset: int) -> List[FunnelPaymentFailureOut]:
    now = datetime.utcnow().date()
    n = int(min(max(limit, 1), 50))
    off = int(offset)
    methods = ["UPI", "CARD", "NETBANKING"]
    providers = ["Razorpay", "Stripe", "PayU"]
    reasons = ["INSUFFICIENT_FUNDS", "TIMEOUT", "BANK_DOWN", "INVALID_OTP", None]
    out: List[FunnelPaymentFailureOut] = []
    for i in range(n):
        idx = off + i
        dt = (now - timedelta(days=(idx % max(1, int(min(window_days, 30)))))).isoformat()
        failed = 12 + (idx * 3) % 60
        attempted = float(45000 + (idx * 771) % 190000)
        out.append(
            FunnelPaymentFailureOut(
                event_dt=dt,
                payment_method=methods[idx % len(methods)],
                payment_provider=providers[idx % len(providers)],
                failure_reason=reasons[idx % len(reasons)],
                failed_payments=int(failed),
                amount_attempted=float(attempted),
                revenue_at_risk_ex_tax=float(round(attempted * 0.92, 2)),
            )
        )
    return out


def _demo_audit_log(limit: int, offset: int) -> List[AdminAuditLogItemOut]:
    now = datetime.utcnow().replace(microsecond=0)
    n = int(min(max(limit, 1), 200))
    base = 12000 + int(offset)
    actions = ["STATUS_CHANGED", "CANCELLED"]
    reasons = ["NEW→PLACED", "PLACED→SHIPPED", "SHIPPED→DELIVERED", "Customer request"]
    actors = ["customer", "system"]
    out: List[AdminAuditLogItemOut] = []
    for i in range(n):
        oid = base + i
        out.append(
            AdminAuditLogItemOut(
                event_ts=(now - timedelta(minutes=19 * i)).isoformat(),
                order_id=int(oid),
                action=actions[oid % len(actions)],
                reason=reasons[oid % len(reasons)],
                actor_type=actors[oid % len(actors)],
            )
        )
    return out


@router.get("/bi/marts/{mart_name}.csv")
def export_bi_mart_csv(
    mart_name: str,
    limit: int = Query(50000, ge=1, le=200000),
    admin_key: str | None = Header(None, alias="X-Admin-Key"),
):
    try:
        _require_admin(admin_key)

        allowed = {
            "mart_exec_daily_kpis",
            "mart_finance_profitability",
            "mart_funnel_conversion",
            "mart_product_performance",
            "mart_customer_segments",
        }
        name = (mart_name or "").strip().lower()
        if name not in allowed:
            raise HTTPException(status_code=400, detail=f"Invalid mart_name. Allowed: {sorted(list(allowed))}")

        sql = f"SELECT * FROM globalcart.{name} LIMIT %s;"
        with get_conn() as conn:
            conn.execute("SET TIME ZONE 'UTC';", prepare=False)
            with conn.cursor() as cur:
                cur.execute(sql, (int(limit),))
                cols = [c.name for c in cur.description]
                rows = cur.fetchall()

        csv_text = _to_csv(cols, rows)
        return Response(
            content=csv_text,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={name}.csv"},
        )

    except psycopg.OperationalError:
        csv_text = "demo\nPostgreSQL unavailable\n"
        name = (mart_name or "").strip().lower() or "mart"
        return Response(
            content=csv_text,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={name}.csv"},
        )
    except (psycopg.errors.UndefinedTable, psycopg.errors.InvalidSchemaName):
        raise HTTPException(
            status_code=500,
            detail=(
                "BI marts not found (missing globalcart mart_* materialized views). "
                "Run: python3 -m src.run_sql --sql sql/06_bi_marts.sql"
            ),
        )


@router.post("/login", response_model=AdminLoginOut)
def admin_login(req: AdminLoginIn) -> AdminLoginOut:
    expected_user = os.getenv("ADMIN_USER", "admin")
    expected_password = os.getenv("ADMIN_PASSWORD", "admin")

    if req.username != expected_user or req.password != expected_password:
        raise HTTPException(status_code=401, detail="Invalid admin credentials")

    return AdminLoginOut(admin_key=os.getenv("ADMIN_KEY", "admin"))


@router.get("/kpis/latest", response_model=AdminKpisLatestOut)
def latest_kpis(label: str | None = Query(None), admin_key: str | None = Header(None, alias="X-Admin-Key")):
    try:
        _require_admin(admin_key)
        with get_conn() as conn:
            conn.execute("SET TIME ZONE 'UTC';", prepare=False)
            return _fetch_latest_kpis(conn, label=label)

    except psycopg.OperationalError:
        return _demo_admin_kpis_latest(label=label)
    except (psycopg.errors.UndefinedTable, psycopg.errors.InvalidSchemaName):
        raise HTTPException(
            status_code=500,
            detail=(
                "Admin views not found (missing globalcart.vw_admin_kpis). "
                "Run: python3 -m src.run_sql --sql sql/02_views.sql"
            ),
        )


@router.get("/audit-log", response_model=List[AdminAuditLogItemOut])
def audit_log(
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    admin_key: str | None = Header(None, alias="X-Admin-Key"),
):
    try:
        _require_admin(admin_key)
        with get_conn() as conn:
            conn.execute("SET TIME ZONE 'UTC';", prepare=False)
            with conn.cursor() as cur:
                cur.execute("SELECT to_regclass('globalcart.vw_admin_order_cancellations');")
                has_cancel = cur.fetchone()[0] is not None

                parts: List[str] = [
                    """
                    SELECT
                        o.order_ts AS event_ts,
                        o.order_id,
                        'STATUS_CHANGED' AS action,
                        'NEW→PLACED' AS reason,
                        'customer' AS actor_type
                    FROM globalcart.vw_admin_order_summary o
                    """,
                    """
                    SELECT
                        MAX(s.shipped_ts) AS event_ts,
                        s.order_id,
                        'STATUS_CHANGED' AS action,
                        'PLACED→SHIPPED' AS reason,
                        'system' AS actor_type
                    FROM globalcart.vw_admin_shipments s
                    WHERE s.shipped_ts IS NOT NULL
                    GROUP BY s.order_id
                    """,
                    """
                    SELECT
                        (MAX(s.delivered_dt)::timestamp) AS event_ts,
                        s.order_id,
                        'STATUS_CHANGED' AS action,
                        'SHIPPED→DELIVERED' AS reason,
                        'system' AS actor_type
                    FROM globalcart.vw_admin_shipments s
                    WHERE s.delivered_dt IS NOT NULL
                    GROUP BY s.order_id
                    """,
                ]

                if has_cancel:
                    parts.append(
                        """
                        SELECT
                            c.created_at AS event_ts,
                            c.order_id,
                            'CANCELLED' AS action,
                            c.reason AS reason,
                            'customer' AS actor_type
                        FROM globalcart.vw_admin_order_cancellations c
                        """
                    )

                sql = (
                    "WITH events AS (" + " UNION ALL ".join([f"({p.strip()})" for p in parts]) + ") "
                    "SELECT event_ts, order_id, action, reason, actor_type "
                    "FROM events "
                    "WHERE event_ts IS NOT NULL "
                    "ORDER BY event_ts DESC "
                    "LIMIT %s OFFSET %s;"
                )

                cur.execute(sql, (int(limit), int(offset)))
                rows = cur.fetchall()

        out: List[AdminAuditLogItemOut] = []
        for r in rows:
            ts = r[0].isoformat() if hasattr(r[0], "isoformat") else str(r[0])
            out.append(
                AdminAuditLogItemOut(
                    event_ts=ts,
                    order_id=int(r[1]),
                    action=str(r[2]),
                    reason=str(r[3]) if r[3] is not None else None,
                    actor_type=str(r[4]),
                )
            )
        return out

    except psycopg.OperationalError:
        return _demo_audit_log(limit=int(limit), offset=int(offset))
    except (psycopg.errors.UndefinedTable, psycopg.errors.InvalidSchemaName):
        raise HTTPException(
            status_code=500,
            detail=(
                "Admin views not found (missing globalcart.vw_admin_order_summary / globalcart.vw_admin_shipments). "
                "Run: python3 -m src.run_sql --sql sql/02_views.sql"
            ),
        )


@router.get("/orders", response_model=List[AdminOrderSummaryOut])
def orders_monitor(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin_key: str | None = Header(None, alias="X-Admin-Key"),
):
    try:
        _require_admin(admin_key)
        with get_conn() as conn:
            conn.execute("SET TIME ZONE 'UTC';", prepare=False)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        o.order_id,
                        o.customer_id,
                        COALESCE(NULLIF(u.display_name, ''), NULLIF(fo.recipient_name, '')) AS customer_name,
                        u.email,
                        o.order_ts,
                        o.order_status,
                        o.net_amount,
                        o.channel
                    FROM globalcart.vw_admin_order_summary o
                    LEFT JOIN globalcart.app_users u
                      ON u.customer_id = o.customer_id
                    LEFT JOIN globalcart.fact_orders fo
                      ON fo.order_id = o.order_id
                    ORDER BY order_ts DESC
                    LIMIT %s OFFSET %s;
                    """,
                    (int(limit), int(offset)),
                )
                rows = cur.fetchall()

        out: List[AdminOrderSummaryOut] = []
        for r in rows:
            ts = r[4].isoformat() if hasattr(r[4], "isoformat") else str(r[4])
            out.append(
                AdminOrderSummaryOut(
                    order_id=int(r[0]),
                    customer_id=int(r[1]),
                    customer_name=str(r[2]) if r[2] is not None else None,
                    customer_email=str(r[3]) if r[3] is not None else None,
                    order_ts=ts,
                    order_status=str(r[5]),
                    net_amount=float(r[6]),
                    channel=str(r[7]) if r[7] is not None else None,
                )
            )
        return out

    except psycopg.OperationalError:
        return _demo_admin_orders(limit=int(limit), offset=int(offset))
    except (psycopg.errors.UndefinedTable, psycopg.errors.InvalidSchemaName):
        raise HTTPException(
            status_code=500,
            detail=(
                "Admin views not found (missing globalcart.vw_admin_order_summary). "
                "Run: python3 -m src.run_sql --sql sql/02_views.sql"
            ),
        )


@router.get("/journey/sessions", response_model=List[JourneySessionOut])
def journey_sessions(
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    window_hours: int = Query(72, ge=1, le=24 * 30),
    customer_id: int | None = Query(None, ge=1),
    admin_key: str | None = Header(None, alias="X-Admin-Key"),
):
    try:
        _require_admin(admin_key)

        where = "WHERE event_ts >= (NOW() AT TIME ZONE 'UTC') - (%s * INTERVAL '1 hour')"
        params: list = [int(window_hours)]
        if customer_id is not None:
            where += " AND customer_id = %s"
            params.append(int(customer_id))

        sql = f"""
            SELECT
                session_id,
                MAX(customer_id) AS customer_id,
                MIN(event_ts) AS first_event_ts,
                MAX(event_ts) AS last_event_ts,
                COUNT(*) AS event_count,
                MAX(channel) AS channel,
                MAX(device) AS device
            FROM globalcart.fact_funnel_events
            {where}
            GROUP BY session_id
            ORDER BY last_event_ts DESC
            LIMIT %s OFFSET %s;
        """
        params.extend([int(limit), int(offset)])

        with get_conn() as conn:
            conn.execute("SET TIME ZONE 'UTC';", prepare=False)
            with conn.cursor() as cur:
                cur.execute(sql, tuple(params))
                rows = cur.fetchall()

        out: List[JourneySessionOut] = []
        for r in rows:
            first_ts = r[2].isoformat() if hasattr(r[2], "isoformat") else str(r[2])
            last_ts = r[3].isoformat() if hasattr(r[3], "isoformat") else str(r[3])
            out.append(
                JourneySessionOut(
                    session_id=str(r[0]),
                    customer_id=int(r[1]) if r[1] is not None else None,
                    first_event_ts=first_ts,
                    last_event_ts=last_ts,
                    event_count=int(r[4]),
                    channel=str(r[5]) if r[5] is not None else None,
                    device=str(r[6]) if r[6] is not None else None,
                )
            )
        return out

    except (psycopg.errors.UndefinedTable, psycopg.errors.InvalidSchemaName):
        raise HTTPException(
            status_code=500,
            detail=(
                "Funnel table not found (missing globalcart.fact_funnel_events). "
                "Run: python3 -m src.run_sql --sql sql/00_schema.sql"
            ),
        )


@router.get("/products/{product_id}", response_model=ProductDetailOut)
def admin_product_detail(
    product_id: int,
    admin_key: str | None = Header(None, alias="X-Admin-Key"),
):
    _require_admin(admin_key)

    sql = """
        SELECT product_id, sku, product_name, category_l1, category_l2, brand, unit_cost, list_price
        FROM globalcart.vw_customer_products
        WHERE product_id = %s;
    """

    try:
        with get_conn() as conn:
            conn.execute("SET TIME ZONE 'UTC';", prepare=False)
            with conn.cursor() as cur:
                cur.execute(sql, (int(product_id),))
                row = cur.fetchone()

        if row is None:
            raise HTTPException(status_code=404, detail="Product not found")

        pid = int(row[0])
        sku = str(row[1])
        product_name = str(row[2])
        category_l1 = str(row[3])
        category_l2 = str(row[4])
        brand = str(row[5])
        list_price = float(row[7])

        disc = _stable_discount_pct(pid)
        sell_price = round(list_price * (1 - disc / 100.0), 2)

        stock_qty = 0 if (pid % 17 == 0) else (5 + (pid % 23))
        in_stock = stock_qty > 0

        return ProductDetailOut(
            product_id=pid,
            sku=sku,
            product_name=product_name,
            category_l1=category_l1,
            category_l2=category_l2,
            brand=brand,
            list_price=float(list_price),
            discount_pct=int(disc),
            sell_price=float(sell_price),
            image_url=_product_photo_url(
                seed=f"{sku}:{pid}",
                label=product_name,
                category_l1=category_l1,
                category_l2=category_l2,
                product_id=pid,
                sku=sku,
            ),
            description=f"{brand} {category_l2} in {category_l1}.",
            in_stock=bool(in_stock),
            stock_qty=int(stock_qty),
        )

    except psycopg.OperationalError:
        pid = int(product_id)
        brands = ["GlobalCart", "Nimbus", "Aurora", "Vertex", "Nova", "Atlas", "Pulse", "Zenith"]
        cats = [
            ("Electronics", ["Headphones", "Smartwatches", "Speakers", "Accessories"]),
            ("Home", ["Kitchen", "Decor", "Lighting", "Storage"]),
            ("Fashion", ["Sneakers", "Jackets", "Bags", "Watches"]),
            ("Beauty", ["Skincare", "Fragrance", "Makeup", "Haircare"]),
        ]
        c1, c2s = cats[pid % len(cats)]
        c2 = c2s[pid % len(c2s)]
        sku = f"SKU-{pid:05d}"
        brand = brands[pid % len(brands)]
        product_name = f"Demo Product {pid}"
        list_price = float(199 + (pid % 200) * 10)
        disc = _stable_discount_pct(pid)
        sell_price = round(list_price * (1 - disc / 100.0), 2)
        stock_qty = 0 if (pid % 17 == 0) else (5 + (pid % 23))
        in_stock = stock_qty > 0
        return ProductDetailOut(
            product_id=pid,
            sku=sku,
            product_name=product_name,
            category_l1=c1,
            category_l2=c2,
            brand=brand,
            list_price=float(list_price),
            discount_pct=int(disc),
            sell_price=float(sell_price),
            image_url=_product_photo_url(
                seed=f"{sku}:{pid}",
                label=product_name,
                category_l1=c1,
                category_l2=c2,
                product_id=pid,
                sku=sku,
            ),
            description=f"{brand} {c2} in {c1}.",
            in_stock=bool(in_stock),
            stock_qty=int(stock_qty),
        )
    except (psycopg.errors.UndefinedTable, psycopg.errors.InvalidSchemaName):
        raise HTTPException(
            status_code=500,
            detail=(
                "Warehouse tables not found (missing globalcart.dim_product). "
                "Run: python3 -m src.run_sql --sql sql/00_schema.sql and load/generate data before using the web demo."
            ),
        )


@router.get("/journey/session/{session_id}/events", response_model=List[JourneyEventOut])
def journey_session_events(
    session_id: str,
    admin_key: str | None = Header(None, alias="X-Admin-Key"),
):
    try:
        _require_admin(admin_key)
        sid = str(session_id or "").strip()
        if not sid:
            raise HTTPException(status_code=400, detail="session_id is required")
        if len(sid) > 64:
            raise HTTPException(status_code=400, detail="session_id too long")

        sql = """
            SELECT
                event_id,
                event_ts,
                session_id,
                customer_id,
                stage,
                channel,
                device,
                product_id,
                order_id,
                failure_reason
            FROM globalcart.fact_funnel_events
            WHERE session_id = %s
            ORDER BY event_ts ASC, event_id ASC;
        """
        with get_conn() as conn:
            conn.execute("SET TIME ZONE 'UTC';", prepare=False)
            with conn.cursor() as cur:
                cur.execute(sql, (sid,))
                rows = cur.fetchall()

        out: List[JourneyEventOut] = []
        for r in rows:
            ts = r[1].isoformat() if hasattr(r[1], "isoformat") else str(r[1])
            out.append(
                JourneyEventOut(
                    event_id=int(r[0]),
                    event_ts=ts,
                    session_id=str(r[2]),
                    customer_id=int(r[3]) if r[3] is not None else None,
                    stage=str(r[4]),
                    channel=str(r[5]) if r[5] is not None else None,
                    device=str(r[6]) if r[6] is not None else None,
                    product_id=int(r[7]) if r[7] is not None else None,
                    order_id=int(r[8]) if r[8] is not None else None,
                    failure_reason=str(r[9]) if r[9] is not None else None,
                )
            )
        return out

    except psycopg.OperationalError:
        return _demo_journey_events(session_id=session_id)
    except (psycopg.errors.UndefinedTable, psycopg.errors.InvalidSchemaName):
        raise HTTPException(
            status_code=500,
            detail=(
                "Funnel table not found (missing globalcart.fact_funnel_events). "
                "Run: python3 -m src.run_sql --sql sql/00_schema.sql"
            ),
        )
    except psycopg.Error as e:
        raise HTTPException(
            status_code=500,
            detail=f"Journey events query failed: {type(e).__name__}: {e}",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Journey events failed: {type(e).__name__}: {e}")


@router.get("/finance/summary", response_model=FinanceSummaryOut)
def finance_summary(admin_key: str | None = Header(None, alias="X-Admin-Key")):
    try:
        _require_admin(admin_key)
        sql = """
            SELECT
              COALESCE(COUNT(*),0) AS orders,
              COALESCE(SUM(revenue_ex_tax),0) AS revenue_ex_tax,
              COALESCE(SUM(cogs),0) AS cogs,
              COALESCE(SUM(gross_profit_ex_tax),0) AS gross_profit_ex_tax,
              COALESCE(SUM(shipping_cost),0) AS shipping_cost,
              COALESCE(SUM(gateway_fee_amount),0) AS gateway_fee_amount,
              COALESCE(SUM(refund_amount),0) AS refund_amount,
              COALESCE(SUM(net_profit_ex_tax),0) AS net_profit_ex_tax,
              CASE WHEN COALESCE(SUM(revenue_ex_tax),0) > 0
                THEN ROUND(100.0 * COALESCE(SUM(gross_profit_ex_tax),0) / NULLIF(COALESCE(SUM(revenue_ex_tax),0),0), 4)
                ELSE 0 END AS gross_margin_pct,
              CASE WHEN COALESCE(SUM(revenue_ex_tax),0) > 0
                THEN ROUND(100.0 * COALESCE(SUM(net_profit_ex_tax),0) / NULLIF(COALESCE(SUM(revenue_ex_tax),0),0), 4)
                ELSE 0 END AS net_margin_pct,
              COALESCE(SUM(CASE WHEN loss_order_flag THEN 1 ELSE 0 END),0) AS loss_orders,
              COALESCE(SUM(CASE WHEN discount_heavy_flag THEN 1 ELSE 0 END),0) AS discount_heavy_orders,
              COALESCE(SUM(CASE WHEN has_return_flag THEN 1 ELSE 0 END),0) AS return_orders,
              COALESCE(SUM(CASE WHEN sla_breached_flag THEN 1 ELSE 0 END),0) AS sla_breached_orders
            FROM globalcart.vw_finance_order_pnl;
        """
        with get_conn() as conn:
            conn.execute("SET TIME ZONE 'UTC';", prepare=False)
            with conn.cursor() as cur:
                cur.execute(sql)
                r = cur.fetchone()

        return FinanceSummaryOut(
            orders=int(r[0]),
            revenue_ex_tax=float(r[1]),
            cogs=float(r[2]),
            gross_profit_ex_tax=float(r[3]),
            shipping_cost=float(r[4]),
            gateway_fee_amount=float(r[5]),
            refund_amount=float(r[6]),
            net_profit_ex_tax=float(r[7]),
            gross_margin_pct=float(r[8]),
            net_margin_pct=float(r[9]),
            loss_orders=int(r[10]),
            discount_heavy_orders=int(r[11]),
            return_orders=int(r[12]),
            sla_breached_orders=int(r[13]),
        )

    except psycopg.OperationalError:
        return FinanceSummaryOut(
            orders=51898,
            revenue_ex_tax=6838551450.52,
            cogs=5025190148.75,
            gross_profit_ex_tax=1813361301.77,
            shipping_cost=449847.62,
            gateway_fee_amount=83127610.51,
            refund_amount=113293144.46,
            net_profit_ex_tax=1609200546.95,
            gross_margin_pct=26.52,
            net_margin_pct=23.52,
            loss_orders=294,
            discount_heavy_orders=1193,
            return_orders=702,
            sla_breached_orders=188,
        )
    except (psycopg.errors.UndefinedTable, psycopg.errors.InvalidSchemaName):
        raise HTTPException(
            status_code=500,
            detail=(
                "Finance views not found (missing globalcart.vw_finance_order_pnl). "
                "Run: python3 -m src.run_sql --sql sql/02_views.sql"
            ),
        )


@router.get("/finance/loss-orders", response_model=List[FinanceOrderPnlOut])
def finance_loss_orders(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin_key: str | None = Header(None, alias="X-Admin-Key"),
):
    try:
        _require_admin(admin_key)
        sql = """
            SELECT
              order_id, customer_id, order_ts, order_status,
              revenue_ex_tax, cogs, gross_profit_ex_tax,
              shipping_cost, gateway_fee_amount, refund_amount,
              net_profit_ex_tax, discount_amount,
              loss_order_flag, discount_heavy_flag, has_return_flag, sla_breached_flag
            FROM globalcart.vw_finance_order_pnl
            WHERE loss_order_flag = TRUE
            ORDER BY net_profit_ex_tax ASC
            LIMIT %s OFFSET %s;
        """
        with get_conn() as conn:
            conn.execute("SET TIME ZONE 'UTC';", prepare=False)
            with conn.cursor() as cur:
                cur.execute(sql, (int(limit), int(offset)))
                rows = cur.fetchall()

        out: List[FinanceOrderPnlOut] = []
        for r in rows:
            ts = r[2].isoformat() if hasattr(r[2], "isoformat") else str(r[2])
            out.append(
                FinanceOrderPnlOut(
                    order_id=int(r[0]),
                    customer_id=int(r[1]),
                    order_ts=ts,
                    order_status=str(r[3]),
                    revenue_ex_tax=float(r[4]),
                    cogs=float(r[5]),
                    gross_profit_ex_tax=float(r[6]),
                    shipping_cost=float(r[7]),
                    gateway_fee_amount=float(r[8]),
                    refund_amount=float(r[9]),
                    net_profit_ex_tax=float(r[10]),
                    discount_amount=float(r[11]),
                    loss_order_flag=bool(r[12]),
                    discount_heavy_flag=bool(r[13]),
                    has_return_flag=bool(r[14]),
                    sla_breached_flag=bool(r[15]),
                )
            )
        return out

    except psycopg.OperationalError:
        now = datetime.utcnow().replace(microsecond=0)
        n = int(min(max(limit, 1), 50))
        off = int(offset)
        demo: List[FinanceOrderPnlOut] = []
        for i in range(n):
            oid = 50000 + off + i
            revenue = float(1200 + (oid % 9000))
            cogs = float(revenue * (0.78 + ((oid % 7) * 0.01)))
            gp = float(revenue - cogs)
            ship = float(39 + (oid % 20))
            fee = float(round(revenue * 0.0175, 2))
            refund = float(0.0 if (oid % 5) else round(revenue * 0.15, 2))
            net = float(gp - ship - fee - refund)
            demo.append(
                FinanceOrderPnlOut(
                    order_id=int(oid),
                    customer_id=int(7000 + (oid % 5000)),
                    order_ts=(now - timedelta(hours=3 * i)).isoformat(),
                    order_status="DELIVERED" if (oid % 2) else "REFUNDED",
                    revenue_ex_tax=float(round(revenue, 2)),
                    cogs=float(round(cogs, 2)),
                    gross_profit_ex_tax=float(round(gp, 2)),
                    shipping_cost=float(round(ship, 2)),
                    gateway_fee_amount=float(round(fee, 2)),
                    refund_amount=float(round(refund, 2)),
                    net_profit_ex_tax=float(round(net, 2)),
                    discount_amount=float(round(revenue * 0.08, 2)),
                    loss_order_flag=bool(net < 0),
                    discount_heavy_flag=bool((oid % 9) == 0),
                    has_return_flag=bool(refund > 0),
                    sla_breached_flag=bool((oid % 13) == 0),
                )
            )
        return demo
    except (psycopg.errors.UndefinedTable, psycopg.errors.InvalidSchemaName):
        raise HTTPException(
            status_code=500,
            detail=(
                "Finance views not found (missing globalcart.vw_finance_order_pnl). "
                "Run: python3 -m src.run_sql --sql sql/02_views.sql"
            ),
        )


@router.get("/finance/top-products", response_model=List[FinanceProductPnlOut])
def finance_top_products(
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin_key: str | None = Header(None, alias="X-Admin-Key"),
):
    try:
        _require_admin(admin_key)
        sql = """
            SELECT
              fp.product_id,
              dp.product_name,
              fp.category_l1,
              fp.category_l2,
              fp.brand,
              fp.revenue_ex_tax,
              fp.net_profit_ex_tax,
              fp.net_margin_pct,
              fp.loss_product_flag
            FROM globalcart.vw_finance_product_pnl fp
            JOIN globalcart.dim_product dp ON dp.product_id = fp.product_id
            ORDER BY fp.net_profit_ex_tax DESC
            LIMIT %s OFFSET %s;
        """
        with get_conn() as conn:
            conn.execute("SET TIME ZONE 'UTC';", prepare=False)
            with conn.cursor() as cur:
                cur.execute(sql, (int(limit), int(offset)))
                rows = cur.fetchall()

        out: List[FinanceProductPnlOut] = []
        for r in rows:
            out.append(
                FinanceProductPnlOut(
                    product_id=int(r[0]),
                    product_name=str(r[1]),
                    category_l1=str(r[2]),
                    category_l2=str(r[3]),
                    brand=str(r[4]),
                    revenue_ex_tax=float(r[5]),
                    net_profit_ex_tax=float(r[6]),
                    net_margin_pct=float(r[7]),
                    loss_product_flag=bool(r[8]),
                )
            )
        return out

    except psycopg.OperationalError:
        n = int(min(max(limit, 1), 50))
        off = int(offset)
        brands = ["Nimbus", "Aurora", "Vertex", "Nova", "Atlas"]
        cats = [("Electronics", "Accessories"), ("Home", "Kitchen"), ("Fashion", "Bags"), ("Beauty", "Skincare")]
        demo: List[FinanceProductPnlOut] = []
        for i in range(n):
            pid = 1000 + off + i
            c1, c2 = cats[pid % len(cats)]
            rev = float(45000 + (pid % 200) * 775)
            net = float(rev * (0.18 + ((pid % 5) * 0.01)))
            margin = float(round((net / rev) * 100.0, 4)) if rev else 0.0
            demo.append(
                FinanceProductPnlOut(
                    product_id=int(pid),
                    product_name=f"Demo Product {pid}",
                    category_l1=c1,
                    category_l2=c2,
                    brand=brands[pid % len(brands)],
                    revenue_ex_tax=float(round(rev, 2)),
                    net_profit_ex_tax=float(round(net, 2)),
                    net_margin_pct=float(margin),
                    loss_product_flag=bool(net < 0),
                )
            )
        return demo
    except (psycopg.errors.UndefinedTable, psycopg.errors.InvalidSchemaName):
        raise HTTPException(
            status_code=500,
            detail=(
                "Finance views not found (missing globalcart.vw_finance_product_pnl). "
                "Run: python3 -m src.run_sql --sql sql/02_views.sql"
            ),
        )


@router.get("/finance/top-customers", response_model=List[FinanceCustomerPnlOut])
def finance_top_customers(
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin_key: str | None = Header(None, alias="X-Admin-Key"),
):
    try:
        _require_admin(admin_key)
        sql = """
            SELECT
              customer_id,
              acquisition_channel,
              region,
              country,
              orders,
              revenue_ex_tax,
              net_profit_ex_tax,
              net_margin_pct,
              loss_customer_flag
            FROM globalcart.vw_finance_customer_pnl
            ORDER BY net_profit_ex_tax DESC
            LIMIT %s OFFSET %s;
        """
        with get_conn() as conn:
            conn.execute("SET TIME ZONE 'UTC';", prepare=False)
            with conn.cursor() as cur:
                cur.execute(sql, (int(limit), int(offset)))
                rows = cur.fetchall()

        out: List[FinanceCustomerPnlOut] = []
        for r in rows:
            out.append(
                FinanceCustomerPnlOut(
                    customer_id=int(r[0]),
                    acquisition_channel=str(r[1]),
                    region=str(r[2]),
                    country=str(r[3]),
                    orders=int(r[4]),
                    revenue_ex_tax=float(r[5]),
                    net_profit_ex_tax=float(r[6]),
                    net_margin_pct=float(r[7]),
                    loss_customer_flag=bool(r[8]),
                )
            )
        return out

    except psycopg.OperationalError:
        n = int(min(max(limit, 1), 50))
        off = int(offset)
        channels = ["SEO", "ADS", "EMAIL", "REFERRAL"]
        regions = ["North", "South", "East", "West"]
        countries = ["IN", "US", "GB", "DE"]
        demo: List[FinanceCustomerPnlOut] = []
        for i in range(n):
            cid = 7000 + off + i
            orders = int(5 + (cid % 42))
            rev = float(12000 + (cid % 300) * 260)
            net = float(rev * (0.14 + ((cid % 6) * 0.01)))
            margin = float(round((net / rev) * 100.0, 4)) if rev else 0.0
            demo.append(
                FinanceCustomerPnlOut(
                    customer_id=int(cid),
                    acquisition_channel=channels[cid % len(channels)],
                    region=regions[cid % len(regions)],
                    country=countries[cid % len(countries)],
                    orders=int(orders),
                    revenue_ex_tax=float(round(rev, 2)),
                    net_profit_ex_tax=float(round(net, 2)),
                    net_margin_pct=float(margin),
                    loss_customer_flag=bool(net < 0),
                )
            )
        return demo
    except (psycopg.errors.UndefinedTable, psycopg.errors.InvalidSchemaName):
        raise HTTPException(
            status_code=500,
            detail=(
                "Finance views not found (missing globalcart.vw_finance_customer_pnl). "
                "Run: python3 -m src.run_sql --sql sql/02_views.sql"
            ),
        )


@router.get("/funnel/summary", response_model=FunnelSummaryOut)
def funnel_summary(
    window_days: int = Query(30, ge=1, le=365),
    admin_key: str | None = Header(None, alias="X-Admin-Key"),
):
    try:
        _require_admin(admin_key)
        sql = """
            WITH win AS (
              SELECT NOW() - (%s::int * INTERVAL '1 day') AS since_ts
            ),
            session_flags AS (
              SELECT
                e.session_id,
                BOOL_OR(e.stage = 'VIEW_PRODUCT') AS viewed,
                BOOL_OR(e.stage = 'ADD_TO_CART') AS added,
                BOOL_OR(e.stage = 'CHECKOUT_STARTED') AS checkout,
                BOOL_OR(e.stage = 'PAYMENT_ATTEMPTED') AS pay_attempt,
                BOOL_OR(e.stage = 'PAYMENT_FAILED') AS pay_failed,
                BOOL_OR(e.stage = 'ORDER_PLACED') AS ordered
              FROM globalcart.fact_funnel_events e
              CROSS JOIN win w
              WHERE e.event_ts >= w.since_ts
              GROUP BY 1
            ),
            funnel AS (
              SELECT
                COALESCE(COUNT(*) FILTER (WHERE viewed), 0) AS product_views,
                COALESCE(COUNT(*) FILTER (WHERE added), 0) AS add_to_cart,
                COALESCE(COUNT(*) FILTER (WHERE checkout), 0) AS checkout_started,
                COALESCE(COUNT(*) FILTER (WHERE pay_attempt), 0) AS payment_attempts,
                COALESCE(COUNT(*) FILTER (WHERE ordered), 0) AS orders_placed,
                COALESCE(COUNT(*) FILTER (WHERE pay_failed), 0) AS payment_failed,
                CASE WHEN COALESCE(COUNT(*) FILTER (WHERE viewed), 0) > 0
                  THEN ROUND(1.0 * COALESCE(COUNT(*) FILTER (WHERE ordered), 0) / NULLIF(COALESCE(COUNT(*) FILTER (WHERE viewed), 0), 0), 4)
                  ELSE 0 END AS conversion_rate,
                CASE WHEN COALESCE(COUNT(*) FILTER (WHERE added), 0) > 0
                  THEN ROUND(1.0 * (COALESCE(COUNT(*) FILTER (WHERE added), 0) - COALESCE(COUNT(*) FILTER (WHERE checkout), 0)) / NULLIF(COALESCE(COUNT(*) FILTER (WHERE added), 0), 0), 4)
                  ELSE 0 END AS cart_abandonment_rate,
                CASE WHEN COALESCE(COUNT(*) FILTER (WHERE pay_attempt), 0) > 0
                  THEN ROUND(1.0 * COALESCE(COUNT(*) FILTER (WHERE pay_failed), 0) / NULLIF(COALESCE(COUNT(*) FILTER (WHERE pay_attempt), 0), 0), 4)
                  ELSE 0 END AS payment_failure_rate
              FROM session_flags
            ),
            realized AS (
              SELECT COALESCE(SUM(o.net_amount - o.tax_amount), 0) AS net_revenue_ex_tax
              FROM globalcart.vw_orders_completed o
              CROSS JOIN win w
              WHERE o.order_ts >= w.since_ts
            ),
            refunds AS (
              SELECT COALESCE(SUM(r.refund_amount), 0) AS refunds_leakage
              FROM globalcart.fact_returns r
              CROSS JOIN win w
              WHERE r.return_ts >= w.since_ts
            ),
            failed_orders AS (
              SELECT DISTINCT e.order_id
              FROM globalcart.fact_funnel_events e
              CROSS JOIN win w
              WHERE e.stage = 'PAYMENT_FAILED'
                AND e.order_id IS NOT NULL
                AND e.event_ts >= w.since_ts
            ),
            rev_failures AS (
              SELECT COALESCE(SUM(i.qty * i.unit_sell_price), 0) AS revenue_lost_payment_failures
              FROM globalcart.fact_order_items i
              JOIN failed_orders fo ON fo.order_id = i.order_id
            ),
            sell_ratio AS (
              SELECT COALESCE(AVG(unit_sell_price / NULLIF(unit_list_price,0)), 0.88) AS ratio
              FROM globalcart.fact_order_items
            ),
            abandoned_sessions AS (
              SELECT e.session_id
              FROM globalcart.fact_funnel_events e
              CROSS JOIN win w
              WHERE e.event_ts >= w.since_ts
              GROUP BY e.session_id
              HAVING BOOL_OR(e.stage = 'ADD_TO_CART') AND NOT BOOL_OR(e.stage = 'ORDER_PLACED')
            ),
            abandoned_products AS (
              SELECT DISTINCT e.session_id, e.product_id
              FROM globalcart.fact_funnel_events e
              JOIN abandoned_sessions s ON s.session_id = e.session_id
              CROSS JOIN win w
              WHERE e.event_ts >= w.since_ts
                AND e.stage = 'ADD_TO_CART'
                AND e.product_id IS NOT NULL
            ),
            rev_abandon AS (
              SELECT COALESCE(SUM(dp.list_price * sr.ratio), 0) AS revenue_lost_cart_abandonment
              FROM abandoned_products ap
              JOIN globalcart.dim_product dp ON dp.product_id = ap.product_id
              CROSS JOIN sell_ratio sr
            )
            SELECT
              f.product_views,
              f.add_to_cart,
              f.checkout_started,
              f.payment_attempts,
              f.orders_placed,
              f.conversion_rate,
              f.cart_abandonment_rate,
              f.payment_failure_rate,
              r.net_revenue_ex_tax,
              ra.revenue_lost_cart_abandonment,
              rf.revenue_lost_payment_failures,
              rr.refunds_leakage,
              (
                r.net_revenue_ex_tax
                - COALESCE(rr.refunds_leakage, 0)
                - COALESCE(ra.revenue_lost_cart_abandonment, 0)
                - COALESCE(rf.revenue_lost_payment_failures, 0)
              ) AS net_revenue_after_leakage
            FROM funnel f
            CROSS JOIN realized r
            CROSS JOIN rev_abandon ra
            CROSS JOIN rev_failures rf
            CROSS JOIN refunds rr;
        """

        with get_conn() as conn:
            conn.execute("SET TIME ZONE 'UTC';", prepare=False)
            with conn.cursor() as cur:
                cur.execute(sql, (int(window_days),))
                r = cur.fetchone()

        return FunnelSummaryOut(
            window_days=int(window_days),
            product_views=int(r[0]),
            add_to_cart=int(r[1]),
            checkout_started=int(r[2]),
            payment_attempts=int(r[3]),
            orders_placed=int(r[4]),
            conversion_rate=float(r[5]),
            cart_abandonment_rate=float(r[6]),
            payment_failure_rate=float(r[7]),
            net_revenue_ex_tax=float(r[8]),
            revenue_lost_cart_abandonment=float(r[9]),
            revenue_lost_payment_failures=float(r[10]),
            refunds_leakage=float(r[11]),
            net_revenue_after_leakage=float(r[12]),
        )

    except psycopg.OperationalError:
        return _demo_funnel_summary(window_days=int(window_days))
    except (psycopg.errors.UndefinedTable, psycopg.errors.InvalidSchemaName):
        raise HTTPException(
            status_code=500,
            detail=(
                "Funnel views not found (missing globalcart.fact_funnel_events / related views). "
                "Run: python3 -m src.run_sql --sql sql/00_schema.sql && python3 -m src.run_sql --sql sql/02_views.sql"
            ),
        )


@router.get("/funnel/daily", response_model=List[FunnelDailyMetricOut])
def funnel_daily(
    window_days: int = Query(30, ge=1, le=365),
    admin_key: str | None = Header(None, alias="X-Admin-Key"),
):
    try:
        _require_admin(admin_key)
        sql = """
            SELECT
              event_dt,
              product_views,
              add_to_cart,
              checkout_started,
              payment_attempts,
              orders_placed,
              conversion_rate,
              cart_abandonment_rate,
              payment_failure_rate
            FROM globalcart.vw_funnel_daily_metrics
            WHERE event_dt >= (CURRENT_DATE - (%s::int * INTERVAL '1 day'))
            ORDER BY event_dt DESC;
        """
        with get_conn() as conn:
            conn.execute("SET TIME ZONE 'UTC';", prepare=False)
            with conn.cursor() as cur:
                cur.execute(sql, (int(window_days),))
                rows = cur.fetchall()

        out: List[FunnelDailyMetricOut] = []
        for r in rows:
            dt = r[0].isoformat() if hasattr(r[0], "isoformat") else str(r[0])
            out.append(
                FunnelDailyMetricOut(
                    event_dt=dt,
                    product_views=int(r[1]),
                    add_to_cart=int(r[2]),
                    checkout_started=int(r[3]),
                    payment_attempts=int(r[4]),
                    orders_placed=int(r[5]),
                    conversion_rate=float(r[6]),
                    cart_abandonment_rate=float(r[7]),
                    payment_failure_rate=float(r[8]),
                )
            )
        return out

    except psycopg.OperationalError:
        return _demo_funnel_daily(window_days=int(window_days))
    except (psycopg.errors.UndefinedTable, psycopg.errors.InvalidSchemaName):
        raise HTTPException(
            status_code=500,
            detail=(
                "Funnel views not found (missing globalcart.vw_funnel_daily_metrics). "
                "Run: python3 -m src.run_sql --sql sql/02_views.sql"
            ),
        )


@router.get("/funnel/product-leakage", response_model=List[FunnelProductLeakageOut])
def funnel_product_leakage(
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin_key: str | None = Header(None, alias="X-Admin-Key"),
):
    try:
        _require_admin(admin_key)
        sql = """
            SELECT
              product_id,
              product_name,
              product_views,
              add_to_cart,
              abandoned_adds,
              revenue_lost_cart_abandonment,
              failed_orders,
              revenue_lost_payment_failures
            FROM globalcart.vw_funnel_product_leakage
            ORDER BY (COALESCE(revenue_lost_cart_abandonment,0) + COALESCE(revenue_lost_payment_failures,0)) DESC
            LIMIT %s OFFSET %s;
        """
        with get_conn() as conn:
            conn.execute("SET TIME ZONE 'UTC';", prepare=False)
            with conn.cursor() as cur:
                cur.execute(sql, (int(limit), int(offset)))
                rows = cur.fetchall()

        out: List[FunnelProductLeakageOut] = []
        for r in rows:
            out.append(
                FunnelProductLeakageOut(
                    product_id=int(r[0]),
                    product_name=str(r[1]),
                    product_views=int(r[2]),
                    add_to_cart=int(r[3]),
                    abandoned_adds=int(r[4]),
                    revenue_lost_cart_abandonment=float(r[5]),
                    failed_orders=int(r[6]),
                    revenue_lost_payment_failures=float(r[7]),
                )
            )
        return out

    except psycopg.OperationalError:
        return _demo_product_leakage(limit=int(limit), offset=int(offset))
    except (psycopg.errors.UndefinedTable, psycopg.errors.InvalidSchemaName):
        raise HTTPException(
            status_code=500,
            detail=(
                "Funnel views not found (missing globalcart.vw_funnel_product_leakage). "
                "Run: python3 -m src.run_sql --sql sql/02_views.sql"
            ),
        )


@router.get("/funnel/payment-failures", response_model=List[FunnelPaymentFailureOut])
def funnel_payment_failures(
    window_days: int = Query(30, ge=1, le=365),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    admin_key: str | None = Header(None, alias="X-Admin-Key"),
):
    try:
        _require_admin(admin_key)
        sql = """
            SELECT
              event_dt,
              payment_method,
              payment_provider,
              failure_reason,
              failed_payments,
              amount_attempted,
              revenue_at_risk_ex_tax
            FROM globalcart.vw_funnel_payment_failures
            WHERE event_dt >= (CURRENT_DATE - (%s::int * INTERVAL '1 day'))
            ORDER BY failed_payments DESC
            LIMIT %s OFFSET %s;
        """
        with get_conn() as conn:
            conn.execute("SET TIME ZONE 'UTC';", prepare=False)
            with conn.cursor() as cur:
                cur.execute(sql, (int(window_days), int(limit), int(offset)))
                rows = cur.fetchall()

        out: List[FunnelPaymentFailureOut] = []
        for r in rows:
            dt = r[0].isoformat() if hasattr(r[0], "isoformat") else str(r[0])
            out.append(
                FunnelPaymentFailureOut(
                    event_dt=dt,
                    payment_method=str(r[1]),
                    payment_provider=str(r[2]),
                    failure_reason=str(r[3]) if r[3] is not None else None,
                    failed_payments=int(r[4]),
                    amount_attempted=float(r[5]),
                    revenue_at_risk_ex_tax=float(r[6]),
                )
            )
        return out

    except psycopg.OperationalError:
        return _demo_payment_failures(window_days=int(window_days), limit=int(limit), offset=int(offset))
    except (psycopg.errors.UndefinedTable, psycopg.errors.InvalidSchemaName):
        raise HTTPException(
            status_code=500,
            detail=(
                "Funnel views not found (missing globalcart.vw_funnel_payment_failures). "
                "Run: python3 -m src.run_sql --sql sql/02_views.sql"
            ),
        )
