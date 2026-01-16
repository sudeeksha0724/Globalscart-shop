from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List

from fastapi import APIRouter, Header, HTTPException, Query
import psycopg

from ..db import get_conn
from ..models import CancelOrderIn, CancelOrderOut, CreateOrderRequest, OrderCreatedOut, OrdersByCustomerOut


router = APIRouter(tags=["orders"])


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _next_id(conn, table: str, id_col: str) -> int:
    with conn.cursor() as cur:
        cur.execute(f"SELECT COALESCE(MAX({id_col}), 0) + 1 FROM {table};")
        return int(cur.fetchone()[0])


def _pick_any(conn, table: str, id_col: str) -> int:
    with conn.cursor() as cur:
        cur.execute(f"SELECT {id_col} FROM {table} ORDER BY {id_col} LIMIT 1;")
        row = cur.fetchone()
        if row is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Missing required dimension data in {table}. "
                    "Run the data pipeline first to generate dimensions."
                ),
            )
        return int(row[0])


def _product_map(conn, product_ids: List[int]) -> Dict[int, dict]:
    if not product_ids:
        return {}

    placeholders = ",".join(["%s"] * len(product_ids))
    sql = f"""
        SELECT product_id, list_price, unit_cost
        FROM globalcart.dim_product
        WHERE product_id IN ({placeholders});
    """

    with conn.cursor() as cur:
        cur.execute(sql, tuple(product_ids))
        rows = cur.fetchall()

    out: Dict[int, dict] = {}
    for r in rows:
        out[int(r[0])] = {"list_price": float(r[1]), "unit_cost": float(r[2])}
    return out


def _stable_discount_pct(product_id: int) -> int:
    return [5, 8, 10, 12, 15, 18, 20][product_id % 7]


@router.post("/orders", response_model=OrderCreatedOut)
def create_order(req: CreateOrderRequest, admin_key: str | None = Header(None, alias="X-Admin-Key")):
    if not req.items:
        raise HTTPException(status_code=400, detail="Cart is empty")

    expected = os.getenv("ADMIN_KEY", "admin")
    if admin_key == expected:
        raise HTTPException(status_code=403, detail="Admins cannot place orders")

    now_ts = _utc_now()

    try:
        with get_conn() as conn:
            conn.execute("SET TIME ZONE 'UTC';", prepare=False)

            if req.customer_id is not None:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT geo_id FROM globalcart.dim_customer WHERE customer_id = %s",
                        (int(req.customer_id),),
                    )
                    row = cur.fetchone()
                if row is None:
                    raise HTTPException(status_code=400, detail="Invalid customer_id")
                customer_id = int(req.customer_id)
                geo_id = int(row[0])
            else:
                customer_id = _pick_any(conn, "globalcart.dim_customer", "customer_id")
                geo_id = _pick_any(conn, "globalcart.dim_geo", "geo_id")
            fc_id = _pick_any(conn, "globalcart.dim_fc", "fc_id")

            order_id = _next_id(conn, "globalcart.fact_orders", "order_id")
            payment_id = _next_id(conn, "globalcart.fact_payments", "payment_id")
            shipment_id = _next_id(conn, "globalcart.fact_shipments", "shipment_id")

            next_item_id = _next_id(conn, "globalcart.fact_order_items", "order_item_id")

            product_ids = [i.product_id for i in req.items]
            prod = _product_map(conn, product_ids)

            missing = [pid for pid in product_ids if pid not in prod]
            if missing:
                raise HTTPException(status_code=400, detail=f"Invalid product_ids: {missing}")

            gross_amount = 0.0
            discount_amount = 0.0
            tax_amount = 0.0
            net_amount = 0.0

            order_items_rows: List[tuple] = []

            for item in req.items:
                pid = item.product_id
                qty = int(item.qty)
                list_price = float(prod[pid]["list_price"])
                unit_cost = float(prod[pid]["unit_cost"])

                disc = _stable_discount_pct(pid)
                unit_sell = round(list_price * (1 - disc / 100.0), 2)

                line_gross = round(list_price * qty, 2)
                line_discount = round((list_price - unit_sell) * qty, 2)
                line_tax = round(0.07 * (unit_sell * qty), 2)
                line_net = round((unit_sell * qty) + line_tax, 2)

                gross_amount += line_gross
                discount_amount += line_discount
                tax_amount += line_tax
                net_amount += line_net

                order_items_rows.append(
                    (
                        next_item_id,
                        order_id,
                        pid,
                        qty,
                        round(list_price, 2),
                        unit_sell,
                        round(unit_cost, 2),
                        line_discount,
                        line_tax,
                        line_net,
                        now_ts,
                        now_ts,
                    )
                )
                next_item_id += 1

            gross_amount = round(gross_amount, 2)
            discount_amount = round(discount_amount, 2)
            tax_amount = round(tax_amount, 2)
            net_amount = round(net_amount, 2)

            order_sql = """
                INSERT INTO globalcart.fact_orders (
                    order_id, customer_id, geo_id, order_ts, order_status, channel, currency,
                    gross_amount, discount_amount, tax_amount, net_amount,
                    recipient_name, address_line1, address_line2, city, state, postal_code, country, phone,
                    created_at, updated_at
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s);
            """

            items_sql = """
                INSERT INTO globalcart.fact_order_items (
                    order_item_id, order_id, product_id, qty,
                    unit_list_price, unit_sell_price, unit_cost,
                    line_discount, line_tax, line_net_revenue,
                    created_at, updated_at
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s);
            """

            payment_sql = """
                INSERT INTO globalcart.fact_payments (
                    payment_id, order_id, payment_method, payment_status, payment_provider,
                    amount, authorized_ts, captured_ts, failure_reason, refund_amount,
                    chargeback_flag, created_at, updated_at
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s);
            """

            shipment_sql = """
                INSERT INTO globalcart.fact_shipments (
                    shipment_id, order_id, fc_id, carrier, shipped_ts,
                    promised_delivery_dt, delivered_dt, shipping_cost,
                    sla_breached_flag, created_at, updated_at
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s);
            """

            with conn.cursor() as cur:
                addr = req.address
                cur.execute(
                    order_sql,
                    (
                        order_id,
                        customer_id,
                        geo_id,
                        now_ts,
                        "PLACED",
                        req.channel,
                        req.currency or "INR",
                        gross_amount,
                        discount_amount,
                        tax_amount,
                        net_amount,
                        addr.recipient_name if addr else None,
                        addr.address_line1 if addr else None,
                        addr.address_line2 if addr else None,
                        addr.city if addr else None,
                        addr.state if addr else None,
                        addr.postal_code if addr else None,
                        addr.country if addr else None,
                        addr.phone if addr else None,
                        now_ts,
                        now_ts,
                    ),
                )

                for row in order_items_rows:
                    cur.execute(items_sql, row)

                cur.execute(
                    payment_sql,
                    (
                        payment_id,
                        order_id,
                        "UPI",
                        "CAPTURED",
                        "DEMO",
                        net_amount,
                        now_ts,
                        now_ts + timedelta(minutes=1),
                        None,
                        0.0,
                        False,
                        now_ts,
                        now_ts,
                    ),
                )

                cur.execute(
                    shipment_sql,
                    (
                        shipment_id,
                        order_id,
                        fc_id,
                        "Delhivery",
                        now_ts,
                        (now_ts + timedelta(days=3)).date(),
                        (now_ts + timedelta(days=3)).date(),
                        49.0,
                        False,
                        now_ts,
                        now_ts,
                    ),
                )

            conn.commit()
            return OrderCreatedOut(order_id=order_id, net_amount=net_amount)
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
                "Warehouse tables not found (missing globalcart schema/tables). "
                "Run: python3 -m src.run_sql --sql sql/00_schema.sql and load/generate data before placing orders."
            ),
        )


@router.get("/orders/by-customer/{customer_id}", response_model=OrdersByCustomerOut)
def orders_by_customer(customer_id: int, limit: int = Query(20, ge=1, le=100)):
    try:
        with get_conn() as conn:
            conn.execute("SET TIME ZONE 'UTC';", prepare=False)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT order_id, order_ts, order_status, net_amount
                    FROM globalcart.fact_orders
                    WHERE customer_id = %s
                    ORDER BY order_ts DESC
                    LIMIT %s;
                    """,
                    (int(customer_id), int(limit)),
                )
                rows = cur.fetchall()

                order_ids = [int(r[0]) for r in rows]
                items_by_order: Dict[int, List[dict]] = {oid: [] for oid in order_ids}

                if order_ids:
                    placeholders = ",".join(["%s"] * len(order_ids))
                    cur.execute(
                        f"""
                        SELECT oi.order_id, oi.product_id, p.product_name, oi.qty
                        FROM globalcart.fact_order_items oi
                        JOIN globalcart.dim_product p ON p.product_id = oi.product_id
                        WHERE oi.order_id IN ({placeholders})
                        ORDER BY oi.order_id, oi.order_item_id;
                        """,
                        tuple(order_ids),
                    )
                    item_rows = cur.fetchall()

                    for ir in item_rows:
                        oid = int(ir[0])
                        items_by_order.setdefault(oid, []).append(
                            {
                                "product_id": int(ir[1]),
                                "product_name": str(ir[2]),
                                "qty": int(ir[3]),
                            }
                        )

        orders = []
        for r in rows:
            oid = int(r[0])
            ts = r[1].isoformat() if hasattr(r[1], "isoformat") else str(r[1])
            orders.append(
                {
                    "order_id": oid,
                    "order_ts": ts,
                    "order_status": str(r[2]),
                    "net_amount": float(r[3]),
                    "items": items_by_order.get(oid, []),
                }
            )

        return {"customer_id": int(customer_id), "orders": orders}
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
                "Warehouse tables not found (missing globalcart schema/tables). "
                "Run: python3 -m src.run_sql --sql sql/00_schema.sql and load/generate data before tracking orders."
            ),
        )


@router.post("/orders/{order_id}/cancel", response_model=CancelOrderOut)
def cancel_order(order_id: int, req: CancelOrderIn, admin_key: str | None = Header(None, alias="X-Admin-Key")):
    expected = os.getenv("ADMIN_KEY", "admin")
    if admin_key == expected:
        raise HTTPException(status_code=403, detail="Admins cannot cancel orders")

    try:
        reason = str(req.reason or "").strip()
        if not reason:
            raise HTTPException(status_code=400, detail="Cancellation reason is required")

        with get_conn() as conn:
            conn.execute("SET TIME ZONE 'UTC';", prepare=False)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS globalcart.order_cancellations (
                        cancellation_id BIGSERIAL PRIMARY KEY,
                        order_id BIGINT NOT NULL,
                        customer_id BIGINT NOT NULL,
                        reason TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    );
                    """
                )

                cur.execute(
                    """
                    SELECT customer_id, order_status
                    FROM globalcart.fact_orders
                    WHERE order_id = %s;
                    """,
                    (int(order_id),),
                )
                row = cur.fetchone()

                if row is None:
                    raise HTTPException(status_code=404, detail="Order not found")

                if int(row[0]) != int(req.customer_id):
                    raise HTTPException(status_code=403, detail="Order does not belong to this customer")

                status = str(row[1])
                if status.upper() == "CANCELLED":
                    return CancelOrderOut(order_id=int(order_id), order_status=status)

                if status.upper() != "PLACED":
                    raise HTTPException(status_code=400, detail="Only PLACED orders can be cancelled")

                cur.execute(
                    """
                    UPDATE globalcart.fact_orders
                    SET order_status = 'CANCELLED', updated_at = NOW()
                    WHERE order_id = %s;
                    """,
                    (int(order_id),),
                )

                cur.execute(
                    """
                    INSERT INTO globalcart.order_cancellations (order_id, customer_id, reason)
                    VALUES (%s, %s, %s);
                    """,
                    (int(order_id), int(req.customer_id), reason),
                )
            conn.commit()
        return CancelOrderOut(order_id=int(order_id), order_status="CANCELLED")
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
                "Warehouse tables not found (missing globalcart schema/tables). "
                "Run: python3 -m src.run_sql --sql sql/00_schema.sql and load/generate data before cancelling orders."
            ),
        )
