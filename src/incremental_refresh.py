from __future__ import annotations

import argparse
import io
import os
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from .config import PostgresConfig
from .db import get_conn
from .run_sql import run_sql_file


@dataclass(frozen=True)
class DeltaConfig:
    new_orders: int
    update_orders: int
    update_shipments: int
    late_returns: int


@dataclass(frozen=True)
class DimDeltaConfig:
    new_customers: int
    update_products: int


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _copy_df(conn, table: str, df: pd.DataFrame) -> None:
    if df.empty:
        return

    buf = io.StringIO()
    df.to_csv(buf, index=False)
    buf.seek(0)

    cols = ", ".join(df.columns.tolist())
    copy_sql = f"COPY {table} ({cols}) FROM STDIN WITH (FORMAT csv, HEADER true)"
    with conn.cursor() as cur:
        with cur.copy(copy_sql) as copy:
            copy.write(buf.getvalue())


def _dedupe_latest(df: pd.DataFrame, key_cols: list[str]) -> pd.DataFrame:
    if df.empty:
        return df
    if "updated_at" in df.columns:
        return df.sort_values("updated_at").drop_duplicates(subset=key_cols, keep="last")
    return df.drop_duplicates(subset=key_cols, keep="last")


def _read_df(conn, sql: str) -> pd.DataFrame:
    with conn.cursor() as cur:
        cur.execute(sql)
        rows = cur.fetchall()
        cols = [d.name for d in cur.description]
    return pd.DataFrame(rows, columns=cols)


def _scalar(conn, sql: str, params: tuple | None = None) -> float | int | str | None:
    with conn.cursor() as cur:
        cur.execute(sql, params or ())
        row = cur.fetchone()
        if row is None:
            return None
        return row[0]


def _ensure_incremental_objects() -> None:
    root = _project_root()
    run_sql_file(root / "sql" / "00_schema.sql", stop_on_error=True)
    run_sql_file(root / "sql" / "02_views.sql", stop_on_error=True)
    run_sql_file(root / "sql" / "04_incremental_refresh.sql", stop_on_error=True)


def _parse_since_ts(s: str | None) -> datetime:
    if not s:
        return datetime.utcnow() - timedelta(minutes=30)
    return datetime.fromisoformat(s)


def _get_or_init_watermark(conn, source_name: str, default_ts: datetime) -> datetime:
    existing = _scalar(
        conn,
        "SELECT last_processed_ts FROM globalcart.etl_watermarks WHERE source_name=%s",
        (source_name,),
    )

    if existing is None:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO globalcart.etl_watermarks(source_name, last_processed_ts) VALUES (%s, %s)",
                (source_name, default_ts),
            )
        conn.commit()
        return default_ts

    return pd.to_datetime(existing).to_pydatetime()


def _select_ids(conn) -> dict[str, int]:
    return {
        "max_order_id": int(_scalar(conn, "SELECT COALESCE(MAX(order_id),0) FROM globalcart.fact_orders")),
        "max_order_item_id": int(_scalar(conn, "SELECT COALESCE(MAX(order_item_id),0) FROM globalcart.fact_order_items")),
        "max_payment_id": int(_scalar(conn, "SELECT COALESCE(MAX(payment_id),0) FROM globalcart.fact_payments")),
        "max_event_id": int(_scalar(conn, "SELECT COALESCE(MAX(event_id),0) FROM globalcart.fact_funnel_events")),
        "max_shipment_id": int(_scalar(conn, "SELECT COALESCE(MAX(shipment_id),0) FROM globalcart.fact_shipments")),
        "max_return_id": int(_scalar(conn, "SELECT COALESCE(MAX(return_id),0) FROM globalcart.fact_returns")),
    }


def _generate_new_orders(
    conn,
    cfg: DeltaConfig,
    since_ts: datetime,
    now_ts: datetime,
    ids: dict[str, int],
    seed: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rng = random.Random(seed)
    np_rng = np.random.default_rng(seed)

    customers = _read_df(conn, "SELECT customer_id, geo_id FROM globalcart.dim_customer")
    geos = _read_df(conn, "SELECT geo_id, currency FROM globalcart.dim_geo")
    products = _read_df(conn, "SELECT product_id, unit_cost, list_price FROM globalcart.dim_product")
    fcs = _read_df(conn, "SELECT fc_id FROM globalcart.dim_fc")

    geo_currency = dict(zip(geos["geo_id"], geos["currency"]))

    order_statuses = ["CREATED", "CANCELLED", "DELIVERED", "COMPLETED"]
    status_probs = [0.10, 0.08, 0.50, 0.32]

    payment_methods = ["CARD", "UPI", "WALLET", "COD"]
    providers = ["VISA", "MASTERCARD", "PAYPAL", "STRIPE", "RAZORPAY"]
    channels = ["WEB", "APP"]
    carriers = ["DHL", "FEDEX", "UPS", "LOCAL_XPRESS"]

    next_order_id = ids["max_order_id"] + 1
    next_item_id = ids["max_order_item_id"] + 1
    next_payment_id = ids["max_payment_id"] + 1
    next_event_id = ids["max_event_id"] + 1
    next_shipment_id = ids["max_shipment_id"] + 1

    order_rows = []
    item_rows = []
    payment_rows = []
    shipment_rows = []
    funnel_rows = []

    total_seconds = max(int((now_ts - since_ts).total_seconds()), 1)

    for _ in range(cfg.new_orders):
        cust = customers.sample(n=1, random_state=rng.randint(1, 10_000)).iloc[0]
        customer_id = int(cust["customer_id"])
        geo_id = int(cust["geo_id"])
        currency = str(geo_currency.get(geo_id, "USD"))

        order_ts = since_ts + timedelta(seconds=rng.randrange(total_seconds))
        updated_at = now_ts

        status = str(np_rng.choice(order_statuses, p=status_probs))
        channel = channels[rng.randrange(len(channels))]

        device = "MOBILE" if (channel == "APP" or rng.random() < 0.65) else "DESKTOP"
        session_id = f"sess_inc_{next_order_id}_{rng.randrange(1_000_000_000):09d}"

        num_items = rng.randint(1, 4)
        chosen = products.sample(n=num_items, random_state=rng.randint(1, 10_000))

        gross = 0.0
        discount = 0.0
        tax = 0.0
        net = 0.0

        for _, p in chosen.iterrows():
            pid = int(p["product_id"])
            qty = rng.randint(1, 3)
            list_price = float(p["list_price"])
            unit_cost = float(p["unit_cost"])

            disc_pct = min(rng.uniform(0.02, 0.35), 0.55)
            unit_sell = round(list_price * (1.0 - disc_pct), 2)

            line_gross = round(list_price * qty, 2)
            line_discount = round((list_price - unit_sell) * qty, 2)
            line_tax = round(0.07 * (unit_sell * qty), 2)
            line_net = round((unit_sell * qty) + line_tax, 2)

            gross += line_gross
            discount += line_discount
            tax += line_tax
            net += line_net

            item_rows.append(
                {
                    "order_item_id": next_item_id,
                    "order_id": next_order_id,
                    "product_id": pid,
                    "qty": qty,
                    "unit_list_price": round(list_price, 2),
                    "unit_sell_price": unit_sell,
                    "unit_cost": round(unit_cost, 2),
                    "line_discount": line_discount,
                    "line_tax": line_tax,
                    "line_net_revenue": line_net,
                    "created_at": order_ts,
                    "updated_at": updated_at,
                }
            )
            next_item_id += 1

        session_start = order_ts - timedelta(minutes=rng.randint(3, 75))
        t = session_start
        viewed_products = chosen["product_id"].astype(int).tolist()
        if rng.random() < 0.45:
            extra_pid = int(products.sample(n=1, random_state=rng.randint(1, 10_000)).iloc[0]["product_id"])
            viewed_products.append(extra_pid)

        viewed_products = list(dict.fromkeys(viewed_products))
        for pid in viewed_products:
            for _ in range(rng.randint(1, 3)):
                t = t + timedelta(seconds=rng.randint(6, 35))
                funnel_rows.append(
                    {
                        "event_id": next_event_id,
                        "event_ts": t,
                        "session_id": session_id,
                        "customer_id": customer_id,
                        "product_id": int(pid),
                        "order_id": None,
                        "stage": "VIEW_PRODUCT",
                        "channel": channel,
                        "device": device,
                        "failure_reason": None,
                    }
                )
                next_event_id += 1

        for pid in chosen["product_id"].astype(int).tolist():
            if rng.random() < 0.92:
                t = t + timedelta(seconds=rng.randint(8, 55))
                funnel_rows.append(
                    {
                        "event_id": next_event_id,
                        "event_ts": t,
                        "session_id": session_id,
                        "customer_id": customer_id,
                        "product_id": int(pid),
                        "order_id": None,
                        "stage": "ADD_TO_CART",
                        "channel": channel,
                        "device": device,
                        "failure_reason": None,
                    }
                )
                next_event_id += 1

        t = t + timedelta(seconds=rng.randint(10, 70))
        funnel_rows.append(
            {
                "event_id": next_event_id,
                "event_ts": t,
                "session_id": session_id,
                "customer_id": customer_id,
                "product_id": None,
                "order_id": None,
                "stage": "VIEW_CART",
                "channel": channel,
                "device": device,
                "failure_reason": None,
            }
        )
        next_event_id += 1

        if rng.random() < 0.96:
            t = t + timedelta(seconds=rng.randint(12, 95))
            funnel_rows.append(
                {
                    "event_id": next_event_id,
                    "event_ts": t,
                    "session_id": session_id,
                    "customer_id": customer_id,
                    "product_id": None,
                    "order_id": None,
                    "stage": "CHECKOUT_STARTED",
                    "channel": channel,
                    "device": device,
                    "failure_reason": None,
                }
            )
            next_event_id += 1

        order_rows.append(
            {
                "order_id": next_order_id,
                "customer_id": customer_id,
                "geo_id": geo_id,
                "order_ts": order_ts,
                "order_status": status,
                "channel": channel,
                "currency": currency,
                "gross_amount": round(gross, 2),
                "discount_amount": round(discount, 2),
                "tax_amount": round(tax, 2),
                "net_amount": round(net, 2),
                "created_at": order_ts,
                "updated_at": updated_at,
            }
        )

        pay_method = payment_methods[rng.randrange(len(payment_methods))]
        provider = providers[rng.randrange(len(providers))]

        payment_status = "CAPTURED"
        failure_reason = None
        refund_amount = 0.0
        chargeback_flag = False

        if status == "CANCELLED":
            payment_status = np_rng.choice(["FAILED", "DECLINED"], p=[0.55, 0.45])
            failure_reason = str(np_rng.choice(["INSUFFICIENT_FUNDS", "NETWORK_ERROR", "FRAUD_FLAG", "BANK_DECLINE"]))

        t = t + timedelta(seconds=rng.randint(10, 75))
        funnel_rows.append(
            {
                "event_id": next_event_id,
                "event_ts": t,
                "session_id": session_id,
                "customer_id": customer_id,
                "product_id": None,
                "order_id": next_order_id,
                "stage": "PAYMENT_ATTEMPTED",
                "channel": channel,
                "device": device,
                "failure_reason": None,
            }
        )
        next_event_id += 1

        if payment_status in ("FAILED", "DECLINED"):
            t = t + timedelta(seconds=rng.randint(5, 45))
            funnel_rows.append(
                {
                    "event_id": next_event_id,
                    "event_ts": t,
                    "session_id": session_id,
                    "customer_id": customer_id,
                    "product_id": None,
                    "order_id": next_order_id,
                    "stage": "PAYMENT_FAILED",
                    "channel": channel,
                    "device": device,
                    "failure_reason": failure_reason,
                }
            )
            next_event_id += 1
        else:
            t = t + timedelta(seconds=rng.randint(5, 45))
            funnel_rows.append(
                {
                    "event_id": next_event_id,
                    "event_ts": t,
                    "session_id": session_id,
                    "customer_id": customer_id,
                    "product_id": None,
                    "order_id": next_order_id,
                    "stage": "ORDER_PLACED",
                    "channel": channel,
                    "device": device,
                    "failure_reason": None,
                }
            )
            next_event_id += 1

        gateway_fee_amount = 0.0
        if pay_method != "COD" and payment_status not in ("FAILED", "DECLINED"):
            fee_rate = rng.uniform(0.015, 0.025)
            if pay_method == "UPI":
                fee_rate = rng.uniform(0.010, 0.016)
            fixed_fee = rng.uniform(0.0, 6.0)
            gateway_fee_amount = round((net * fee_rate) + fixed_fee, 2)

        payment_rows.append(
            {
                "payment_id": next_payment_id,
                "order_id": next_order_id,
                "payment_method": pay_method,
                "payment_status": payment_status,
                "payment_provider": provider,
                "amount": round(net, 2),
                "gateway_fee_amount": gateway_fee_amount,
                "authorized_ts": order_ts + timedelta(minutes=rng.randint(0, 10)),
                "captured_ts": None if payment_status in ("FAILED", "DECLINED") else order_ts + timedelta(minutes=rng.randint(5, 30)),
                "failure_reason": failure_reason,
                "refund_amount": refund_amount,
                "chargeback_flag": chargeback_flag,
                "created_at": order_ts,
                "updated_at": updated_at,
            }
        )
        next_payment_id += 1

        if status in ("DELIVERED", "COMPLETED"):
            fc_id = int(fcs.sample(n=1, random_state=rng.randint(1, 10_000)).iloc[0]["fc_id"])
            carrier = carriers[rng.randrange(len(carriers))]
            promised_days = rng.randint(2, 6)
            delivered_delay = rng.choice([0, 0, 0, 1, 1, 2])
            promised_dt = (order_ts + timedelta(days=promised_days)).date()
            delivered_dt = (order_ts + timedelta(days=promised_days + delivered_delay)).date()
            sla_breached = delivered_dt > promised_dt

            shipment_rows.append(
                {
                    "shipment_id": next_shipment_id,
                    "order_id": next_order_id,
                    "fc_id": fc_id,
                    "carrier": carrier,
                    "shipped_ts": order_ts + timedelta(hours=rng.randint(4, 48)),
                    "promised_delivery_dt": promised_dt,
                    "delivered_dt": delivered_dt,
                    "shipping_cost": round(float(np_rng.lognormal(mean=2.1, sigma=0.35)), 2),
                    "sla_breached_flag": bool(sla_breached),
                    "created_at": order_ts,
                    "updated_at": updated_at,
                }
            )
            next_shipment_id += 1

        next_order_id += 1

    return (
        pd.DataFrame(order_rows),
        pd.DataFrame(item_rows),
        pd.DataFrame(payment_rows),
        pd.DataFrame(shipment_rows),
        (lambda df: df.assign(**{c: pd.to_numeric(df[c], errors="coerce").astype("Int64") for c in ["event_id", "customer_id", "product_id", "order_id"] if c in df.columns}) if not df.empty else df)(
            pd.DataFrame(funnel_rows)
        ),
    )


def _generate_updates_and_late_events(
    conn,
    cfg: DeltaConfig,
    now_ts: datetime,
    seed: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rng = random.Random(seed + 99)

    order_updates = _read_df(
        conn,
        """
        SELECT order_id, customer_id, geo_id, order_ts, order_status, channel, currency,
               gross_amount, discount_amount, tax_amount, net_amount, created_at, updated_at
        FROM globalcart.fact_orders
        WHERE order_status = 'DELIVERED'
        ORDER BY RANDOM()
        LIMIT 500
        """,
    )

    if not order_updates.empty:
        order_updates = order_updates.head(cfg.update_orders).copy()
        order_updates["order_status"] = "COMPLETED"
        order_updates["updated_at"] = now_ts

    shipment_updates = _read_df(
        conn,
        """
        SELECT shipment_id, order_id, fc_id, carrier, shipped_ts, promised_delivery_dt, delivered_dt,
               shipping_cost, sla_breached_flag, created_at, updated_at
        FROM globalcart.fact_shipments
        WHERE delivered_dt IS NOT NULL AND sla_breached_flag = FALSE
        ORDER BY RANDOM()
        LIMIT 500
        """,
    )

    if not shipment_updates.empty:
        shipment_updates = shipment_updates.head(cfg.update_shipments).copy()
        shipment_updates["delivered_dt"] = pd.to_datetime(shipment_updates["delivered_dt"]) + pd.to_timedelta(
            [rng.choice([1, 2, 3]) for _ in range(len(shipment_updates))], unit="D"
        )
        shipment_updates["delivered_dt"] = pd.to_datetime(shipment_updates["delivered_dt"]).dt.date
        shipment_updates["sla_breached_flag"] = True
        shipment_updates["updated_at"] = now_ts

    delayed_order_ids: set[int] = set(shipment_updates["order_id"].astype(int).tolist()) if not shipment_updates.empty else set()

    candidates = _read_df(
        conn,
        """
        SELECT
           i.order_item_id,
           i.order_id,
           i.product_id,
           i.line_net_revenue,
           o.order_ts,
           p.payment_id,
           p.payment_method,
           p.payment_provider,
           p.amount,
           p.gateway_fee_amount,
           p.authorized_ts,
           p.captured_ts,
           p.failure_reason,
           p.chargeback_flag,
           p.created_at
        FROM globalcart.fact_order_items i
        JOIN globalcart.fact_orders o ON o.order_id = i.order_id
        JOIN globalcart.fact_payments p ON p.order_id = o.order_id
        LEFT JOIN globalcart.fact_returns r ON r.order_item_id = i.order_item_id
        WHERE o.order_status IN ('DELIVERED','COMPLETED')
          AND r.return_id IS NULL
        ORDER BY RANDOM()
        LIMIT 2000
        """,
    )

    late = candidates.head(cfg.late_returns).copy() if not candidates.empty else pd.DataFrame()

    late_returns = []
    payment_updates = []
    order_status_updates = []

    if not late.empty:
        next_return_id = int(_scalar(conn, "SELECT COALESCE(MAX(return_id),0) FROM globalcart.fact_returns")) + 1
        reasons = ["DAMAGED", "NOT_AS_DESCRIBED", "SIZE_ISSUE", "LATE_DELIVERY", "QUALITY_ISSUE", "CHANGED_MIND"]

        for _, r in late.iterrows():
            order_item_id = int(r["order_item_id"])
            order_id = int(r["order_id"])
            product_id = int(r["product_id"])
            payment_id = int(r["payment_id"])

            line_net = float(r["line_net_revenue"]) if not pd.isna(r["line_net_revenue"]) else 0.0
            refund_amount = float(round(max(0.0, line_net * rng.uniform(0.85, 1.0)), 2))

            reason = reasons[rng.randrange(len(reasons))]
            if int(order_id) in delayed_order_ids:
                reason = "LATE_DELIVERY"

            late_returns.append(
                {
                    "return_id": next_return_id,
                    "order_id": order_id,
                    "order_item_id": order_item_id,
                    "product_id": product_id,
                    "return_ts": now_ts - timedelta(days=rng.randint(0, 5)),
                    "return_reason": reason,
                    "refund_amount": refund_amount,
                    "return_status": "REFUNDED",
                    "restocked_flag": bool(rng.random() < 0.65),
                    "created_at": now_ts,
                    "updated_at": now_ts,
                }
            )

            payment_updates.append(
                {
                    "payment_id": payment_id,
                    "order_id": order_id,
                    "payment_method": str(r["payment_method"]),
                    "payment_status": "REFUNDED",
                    "payment_provider": str(r["payment_provider"]),
                    "amount": float(r["amount"]),
                    "gateway_fee_amount": float(r["gateway_fee_amount"]) if not pd.isna(r["gateway_fee_amount"]) else 0.0,
                    "authorized_ts": r["authorized_ts"],
                    "captured_ts": r["captured_ts"],
                    "failure_reason": r["failure_reason"],
                    "refund_amount": refund_amount,
                    "chargeback_flag": bool(r["chargeback_flag"]),
                    "created_at": r["created_at"],
                    "updated_at": now_ts,
                }
            )

            next_return_id += 1

        returned_ids = late["order_id"].dropna().astype(int).unique().tolist()
        if returned_ids:
            returned_orders = _read_df(
                conn,
                f"""
                SELECT order_id, customer_id, geo_id, order_ts, order_status, channel, currency,
                       gross_amount, discount_amount, tax_amount, net_amount, created_at, updated_at
                FROM globalcart.fact_orders
                WHERE order_id IN ({', '.join(str(x) for x in returned_ids)})
                """,
            )
            if not returned_orders.empty:
                returned_orders = returned_orders.copy()
                returned_orders["order_status"] = "RETURNED"
                returned_orders["updated_at"] = now_ts
                order_status_updates = returned_orders.to_dict(orient="records")

    return (
        order_updates,
        shipment_updates,
        pd.DataFrame(late_returns),
        pd.DataFrame(order_status_updates),
    ), pd.DataFrame(payment_updates)


def _generate_dim_deltas(conn, dim_cfg: DimDeltaConfig, since_ts: datetime, now_ts: datetime, seed: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = random.Random(seed + 202)

    max_customer_id = int(_scalar(conn, "SELECT COALESCE(MAX(customer_id),0) FROM globalcart.dim_customer") or 0)
    geo_ids = _read_df(conn, "SELECT geo_id FROM globalcart.dim_geo")["geo_id"].astype(int).tolist()

    channels = ["ORGANIC", "PAID_SEARCH", "AFFILIATES", "EMAIL", "SOCIAL"]
    total_seconds = max(int((now_ts - since_ts).total_seconds()), 1)

    new_customers = []
    for i in range(dim_cfg.new_customers):
        cid = max_customer_id + 1 + i
        created_ts = since_ts + timedelta(seconds=rng.randrange(total_seconds))
        new_customers.append(
            {
                "customer_id": cid,
                "customer_created_ts": created_ts,
                "geo_id": int(geo_ids[rng.randrange(len(geo_ids))]),
                "acquisition_channel": channels[rng.randrange(len(channels))],
                "created_at": created_ts,
                "updated_at": now_ts,
            }
        )

    products = _read_df(
        conn,
        """
        SELECT product_id, sku, product_name, category_l1, category_l2, brand, unit_cost, list_price, created_at, updated_at
        FROM globalcart.dim_product
        ORDER BY RANDOM()
        LIMIT 500
        """,
    )
    if not products.empty:
        products = products.head(dim_cfg.update_products).copy()
        products["list_price"] = (products["list_price"].astype(float) * (1.0 + np.clip(np.random.normal(0.01, 0.02, len(products)), -0.03, 0.06))).round(2)
        products["updated_at"] = now_ts

    return pd.DataFrame(new_customers), products


def incremental_refresh(
    since_ts: datetime,
    delta_cfg: DeltaConfig,
    source_name: str,
    seed: int,
    dim_cfg: DimDeltaConfig,
) -> None:
    _ensure_incremental_objects()

    cfg = PostgresConfig()
    now_ts = datetime.utcnow().replace(microsecond=0)

    with get_conn(cfg) as conn:
        conn.execute("SET TIME ZONE 'UTC';", prepare=False)

        if since_ts is None:
            since_ts = _get_or_init_watermark(conn, source_name=source_name, default_ts=(now_ts - timedelta(minutes=30)))

        ids = _select_ids(conn)

        conn.execute(
            "TRUNCATE TABLE globalcart.stg_dim_customer, globalcart.stg_dim_product, "
            "globalcart.stg_fact_orders, globalcart.stg_fact_order_items, globalcart.stg_fact_payments, globalcart.stg_fact_funnel_events, globalcart.stg_fact_shipments, globalcart.stg_fact_returns;",
            prepare=False,
        )
        conn.commit()

        new_customers, product_updates = _generate_dim_deltas(
            conn=conn,
            dim_cfg=dim_cfg,
            since_ts=since_ts,
            now_ts=now_ts,
            seed=seed,
        )

        for df, table in [
            (new_customers, "globalcart.stg_dim_customer"),
            (product_updates, "globalcart.stg_dim_product"),
        ]:
            _copy_df(conn, table, df)

        conn.commit()

        def call_counts(fn: str) -> tuple[int, int]:
            with conn.cursor() as cur:
                cur.execute(f"SELECT inserted_count, updated_count FROM {fn}()")
                row = cur.fetchone()
                if row is None:
                    return 0, 0
                return int(row[0]), int(row[1])

        ins_dc, upd_dc = call_counts("globalcart.upsert_dim_customer_from_stg")
        ins_dp, upd_dp = call_counts("globalcart.upsert_dim_product_from_stg")

        new_orders, new_items, new_payments, new_shipments, new_funnel_events = _generate_new_orders(
            conn=conn,
            cfg=delta_cfg,
            since_ts=since_ts,
            now_ts=now_ts,
            ids=ids,
            seed=seed,
        )

        (order_updates, shipment_updates, late_returns, returned_order_updates), payment_updates = _generate_updates_and_late_events(
            conn=conn,
            cfg=delta_cfg,
            now_ts=now_ts,
            seed=seed,
        )

        order_updates_all = order_updates
        if returned_order_updates is not None and not returned_order_updates.empty:
            order_updates_all = pd.concat([order_updates_all, returned_order_updates], ignore_index=True) if not order_updates_all.empty else returned_order_updates

        fact_orders_delta = pd.concat([new_orders, order_updates_all], ignore_index=True) if not order_updates_all.empty else new_orders
        fact_shipments_delta = pd.concat([new_shipments, shipment_updates], ignore_index=True) if not shipment_updates.empty else new_shipments
        fact_payments_delta = pd.concat([new_payments, payment_updates], ignore_index=True) if not payment_updates.empty else new_payments

        new_customers = _dedupe_latest(new_customers, ["customer_id"])
        product_updates = _dedupe_latest(product_updates, ["product_id"])
        fact_orders_delta = _dedupe_latest(fact_orders_delta, ["order_id"])
        new_items = _dedupe_latest(new_items, ["order_item_id"])
        fact_payments_delta = _dedupe_latest(fact_payments_delta, ["payment_id"])
        fact_shipments_delta = _dedupe_latest(fact_shipments_delta, ["shipment_id"])
        late_returns = _dedupe_latest(late_returns, ["return_id"])

        for df, table in [
            (fact_orders_delta, "globalcart.stg_fact_orders"),
            (new_items, "globalcart.stg_fact_order_items"),
            (fact_payments_delta, "globalcart.stg_fact_payments"),
            (new_funnel_events, "globalcart.stg_fact_funnel_events"),
            (fact_shipments_delta, "globalcart.stg_fact_shipments"),
            (late_returns, "globalcart.stg_fact_returns"),
        ]:
            _copy_df(conn, table, df)

        conn.commit()

        ins_o, upd_o = call_counts("globalcart.upsert_fact_orders_from_stg")
        ins_i, upd_i = call_counts("globalcart.upsert_fact_order_items_from_stg")
        ins_p, upd_p = call_counts("globalcart.upsert_fact_payments_from_stg")
        ins_fe, upd_fe = call_counts("globalcart.upsert_fact_funnel_events_from_stg")
        ins_s, upd_s = call_counts("globalcart.upsert_fact_shipments_from_stg")
        ins_r, upd_r = call_counts("globalcart.upsert_fact_returns_from_stg")

        with conn.cursor() as cur:
            cur.execute("SELECT globalcart.set_watermark(%s, %s)", (source_name, now_ts))
        conn.commit()

    print("Incremental refresh completed")
    print(f"dim_customer: inserted={ins_dc}, updated={upd_dc}")
    print(f"dim_product: inserted={ins_dp}, updated={upd_dp}")
    print(f"fact_orders: inserted={ins_o}, updated={upd_o}")
    print(f"fact_order_items: inserted={ins_i}, updated={upd_i}")
    print(f"fact_payments: inserted={ins_p}, updated={upd_p}")
    print(f"fact_funnel_events: inserted={ins_fe}, updated={upd_fe}")
    print(f"fact_shipments: inserted={ins_s}, updated={upd_s}")
    print(f"fact_returns: inserted={ins_r}, updated={upd_r}")
    print(f"watermark({source_name})={now_ts.isoformat()}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--since_timestamp", default=None, help="ISO timestamp watermark (UTC). Example: 2025-12-19T12:00:00")
    parser.add_argument("--new_orders", type=int, default=1500)
    parser.add_argument("--update_orders", type=int, default=250)
    parser.add_argument("--update_shipments", type=int, default=200)
    parser.add_argument("--late_returns", type=int, default=120)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--source_name", default="globalcart_incremental")
    parser.add_argument("--new_customers", type=int, default=200)
    parser.add_argument("--update_products", type=int, default=40)
    args = parser.parse_args()

    since_ts = None if args.since_timestamp is None else _parse_since_ts(args.since_timestamp)
    delta_cfg = DeltaConfig(
        new_orders=args.new_orders,
        update_orders=args.update_orders,
        update_shipments=args.update_shipments,
        late_returns=args.late_returns,
    )

    incremental_refresh(
        since_ts=since_ts,
        delta_cfg=delta_cfg,
        source_name=args.source_name,
        seed=args.seed,
        dim_cfg=DimDeltaConfig(new_customers=args.new_customers, update_products=args.update_products),
    )


if __name__ == "__main__":
    main()
