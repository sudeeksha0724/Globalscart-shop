from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List
from urllib.parse import quote

from fastapi import APIRouter, Header, HTTPException, Query
import psycopg

from ..db import get_conn
from ..models import (
    CancelOrderIn,
    CancelOrderOut,
    CreateOrderRequest,
    CustomerEmailOut,
    CustomerResolveIn,
    CustomerResolveOut,
    OrderDetailOut,
    OrderCreatedOut,
    OrderTimelineOut,
    OrderTimelineStageOut,
    OrdersByCustomerOut,
    ProductRatingSummaryOut,
    ProductReviewIn,
    ProductReviewOut,
    ProductDetailOut,
    ProductOut,
    PromoValidateOut,
    WishlistItemOut,
)


router = APIRouter(prefix="/api/customer", tags=["api_customer"])


def _reject_admin(admin_key: str | None) -> None:
    if admin_key is not None:
        raise HTTPException(status_code=403, detail="Admin access is not allowed on customer APIs")


def _utc_now() -> datetime:
    return datetime.utcnow().replace(microsecond=0)


def _ts(x) -> str | None:
    if x is None:
        return None
    if hasattr(x, "isoformat"):
        return x.isoformat()
    return str(x)


def _stable_discount_pct(product_id: int) -> int:
    return [5, 8, 10, 12, 15, 18, 20][product_id % 7]


def _demo_catalog(
    limit: int,
    offset: int,
    category_l1: str | None,
    category_l2: str | None,
    sort_key: str,
) -> List[ProductOut]:
    brands = [
        "GlobalCart",
        "Nimbus",
        "Aurora",
        "Vertex",
        "Nova",
        "Atlas",
        "Pulse",
        "Zenith",
    ]
    cats = [
        ("Electronics", ["Headphones", "Smartwatches", "Speakers", "Accessories"]),
        ("Home", ["Kitchen", "Decor", "Lighting", "Storage"]),
        ("Fashion", ["Sneakers", "Jackets", "Bags", "Accessories"]),
        ("Grocery", ["Coffee", "Snacks", "Breakfast", "Beverages"]),
    ]

    items: List[ProductOut] = []
    max_pid = 240
    start = max(1, int(offset) + 1)
    end = min(max_pid, start + int(limit) - 1)
    for pid in range(start, end + 1):
        c1, l2s = cats[pid % len(cats)]
        c2 = l2s[(pid // len(cats)) % len(l2s)]
        if category_l1 and str(category_l1) != c1:
            continue
        if category_l2 and str(category_l2) != c2:
            continue

        brand = brands[(pid * 3) % len(brands)]
        sku = f"SKU-{pid:05d}"
        name = f"{brand} {c2} {pid}"
        list_price = float(299 + ((pid * 37) % 2200))
        disc = _stable_discount_pct(pid)
        sell_price = round(list_price * (1 - disc / 100.0), 2)

        items.append(
            ProductOut(
                product_id=int(pid),
                sku=sku,
                product_name=name,
                category_l1=c1,
                category_l2=c2,
                brand=brand,
                list_price=float(list_price),
                discount_pct=int(disc),
                sell_price=float(sell_price),
                image_url=_product_photo_url(
                    seed=f"{sku}:{pid}",
                    label=name,
                    category_l1=c1,
                    category_l2=c2,
                    product_id=int(pid),
                    sku=sku,
                ),
            )
        )

    if sort_key == "price_asc":
        items.sort(key=lambda p: (p.list_price, p.product_id))
    elif sort_key == "price_desc":
        items.sort(key=lambda p: (-p.list_price, p.product_id))
    elif sort_key == "best_sellers":
        items.sort(key=lambda p: (-(p.product_id * 17) % 97, p.product_id))
    else:
        items.sort(key=lambda p: p.product_id)

    return items[: int(limit)]


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


def _next_id(conn, table: str, pk: str) -> int:
    with conn.cursor() as cur:
        cur.execute(f"SELECT COALESCE(MAX({pk}), 0) + 1 FROM {table};")
        row = cur.fetchone()
        return int(row[0])


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


@router.get("/promos/validate", response_model=PromoValidateOut)
def validate_promo(
    code: str,
    amount: float = Query(..., ge=0),
    admin_key: str | None = Header(None, alias="X-Admin-Key"),
):
    _reject_admin(admin_key)

    c = (code or "").strip().upper()
    if not c:
        raise HTTPException(status_code=400, detail="Promo code is required")

    now_ts = _utc_now()
    try:
        with get_conn() as conn:
            conn.execute("SET TIME ZONE 'UTC';", prepare=False)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT discount_type, discount_value, max_discount, min_order_amount, active, expires_at
                    FROM globalcart.promo_codes
                    WHERE code = %s;
                    """,
                    (c,),
                )
                row = cur.fetchone()

        if row is None:
            return PromoValidateOut(code=c, valid=False, discount_amount=0.0, message="Invalid code")

        discount_type = str(row[0] or "").upper()
        discount_value = float(row[1] or 0)
        max_discount = float(row[2]) if row[2] is not None else None
        min_order_amount = float(row[3]) if row[3] is not None else None
        active = bool(row[4])
        expires_at = row[5]

        if not active:
            return PromoValidateOut(code=c, valid=False, discount_amount=0.0, message="Code not active")
        if expires_at is not None and expires_at <= now_ts:
            return PromoValidateOut(code=c, valid=False, discount_amount=0.0, message="Code expired")
        if min_order_amount is not None and float(amount) < min_order_amount:
            return PromoValidateOut(code=c, valid=False, discount_amount=0.0, message=f"Minimum order amount is {min_order_amount}")

        if discount_type == "PERCENT":
            disc = round((float(amount) * discount_value) / 100.0, 2)
        elif discount_type == "FLAT":
            disc = round(discount_value, 2)
        else:
            return PromoValidateOut(code=c, valid=False, discount_amount=0.0, message="Invalid configuration")

        if max_discount is not None:
            disc = min(disc, round(max_discount, 2))
        disc = min(disc, float(amount))
        disc = round(disc, 2)

        return PromoValidateOut(code=c, valid=True, discount_amount=disc, message="Applied")

    except psycopg.OperationalError:
        return PromoValidateOut(
            code=c,
            valid=False,
            discount_amount=0.0,
            message="Demo mode: database unavailable",
        )
    except (psycopg.errors.UndefinedTable, psycopg.errors.InvalidSchemaName):
        raise HTTPException(
            status_code=500,
            detail=(
                "Promo tables not found. Run: python3 -m src.run_sql --sql sql/10_shop_features.sql"
            ),
        )


@router.get("/wishlist", response_model=List[WishlistItemOut])
def wishlist_list(
    customer_id: int = Query(..., ge=1),
    admin_key: str | None = Header(None, alias="X-Admin-Key"),
):
    _reject_admin(admin_key)
    try:
        with get_conn() as conn:
            conn.execute("SET TIME ZONE 'UTC';", prepare=False)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT w.product_id, w.created_at,
                           p.sku, p.product_name, p.category_l1, p.category_l2, p.brand,
                           p.unit_cost, p.list_price
                    FROM globalcart.customer_wishlist w
                    JOIN globalcart.vw_customer_products p ON p.product_id = w.product_id
                    WHERE w.customer_id = %s
                    ORDER BY w.created_at DESC;
                    """,
                    (int(customer_id),),
                )
                rows = cur.fetchall()

        out: List[WishlistItemOut] = []
        for r in rows:
            pid = int(r[0])
            added_at = _ts(r[1]) or ""
            sku = str(r[2])
            name = str(r[3])
            c1 = str(r[4])
            c2 = str(r[5])
            brand = str(r[6])
            list_price = float(r[8])
            disc = _stable_discount_pct(pid)
            sell = round(list_price * (1 - disc / 100.0), 2)
            out.append(
                WishlistItemOut(
                    product_id=pid,
                    sku=sku,
                    product_name=name,
                    category_l1=c1,
                    category_l2=c2,
                    brand=brand,
                    list_price=float(list_price),
                    discount_pct=int(disc),
                    sell_price=float(sell),
                    image_url=_product_photo_url(
                        seed=f"{sku}:{pid}",
                        label=name,
                        category_l1=c1,
                        category_l2=c2,
                        product_id=pid,
                        sku=sku,
                    ),
                    added_at=added_at,
                )
            )
        return out

    except psycopg.OperationalError:
        return []
    except (psycopg.errors.UndefinedTable, psycopg.errors.InvalidSchemaName):
        raise HTTPException(
            status_code=500,
            detail=(
                "Wishlist tables not found. Run: python3 -m src.run_sql --sql sql/10_shop_features.sql"
            ),
        )


@router.post("/wishlist/{product_id}")
def wishlist_add(
    product_id: int,
    customer_id: int = Query(..., ge=1),
    admin_key: str | None = Header(None, alias="X-Admin-Key"),
):
    _reject_admin(admin_key)
    try:
        with get_conn() as conn:
            conn.execute("SET TIME ZONE 'UTC';", prepare=False)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO globalcart.customer_wishlist (customer_id, product_id)
                    VALUES (%s, %s)
                    ON CONFLICT (customer_id, product_id) DO NOTHING;
                    """,
                    (int(customer_id), int(product_id)),
                )
            conn.commit()
        return {"detail": "Added"}
    except psycopg.OperationalError:
        return {"detail": "Added"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to add wishlist item: {e}")


@router.delete("/wishlist/{product_id}")
def wishlist_remove(
    product_id: int,
    customer_id: int = Query(..., ge=1),
    admin_key: str | None = Header(None, alias="X-Admin-Key"),
):
    _reject_admin(admin_key)
    try:
        with get_conn() as conn:
            conn.execute("SET TIME ZONE 'UTC';", prepare=False)
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM globalcart.customer_wishlist WHERE customer_id = %s AND product_id = %s;",
                    (int(customer_id), int(product_id)),
                )
            conn.commit()
        return {"detail": "Removed"}
    except psycopg.OperationalError:
        return {"detail": "Removed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to remove wishlist item: {e}")


@router.get("/products/{product_id}/rating", response_model=ProductRatingSummaryOut)
def product_rating_summary(
    product_id: int,
    admin_key: str | None = Header(None, alias="X-Admin-Key"),
):
    _reject_admin(admin_key)
    try:
        with get_conn() as conn:
            conn.execute("SET TIME ZONE 'UTC';", prepare=False)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COALESCE(AVG(rating), 0)::float, COUNT(*)::int
                    FROM globalcart.product_reviews
                    WHERE product_id = %s;
                    """,
                    (int(product_id),),
                )
                row = cur.fetchone()
        avg = float(row[0] or 0.0)
        cnt = int(row[1] or 0)
        return ProductRatingSummaryOut(product_id=int(product_id), average_rating=round(avg, 2), rating_count=cnt)
    except psycopg.OperationalError:
        pid = int(product_id)
        avg = round(3.6 + ((pid % 7) * 0.2), 2)
        cnt = 15 + (pid % 180)
        return ProductRatingSummaryOut(product_id=pid, average_rating=float(avg), rating_count=int(cnt))
    except (psycopg.errors.UndefinedTable, psycopg.errors.InvalidSchemaName):
        raise HTTPException(
            status_code=500,
            detail=(
                "Review tables not found. Run: python3 -m src.run_sql --sql sql/10_shop_features.sql"
            ),
        )


@router.get("/products/{product_id}/reviews/eligibility")
def product_review_eligibility(
    product_id: int,
    customer_id: int = Query(..., ge=1),
    admin_key: str | None = Header(None, alias="X-Admin-Key"),
):
    _reject_admin(admin_key)
    try:
        with get_conn() as conn:
            conn.execute("SET TIME ZONE 'UTC';", prepare=False)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT 1
                    FROM globalcart.fact_orders o
                    JOIN globalcart.fact_order_items i ON i.order_id = o.order_id
                    WHERE o.customer_id = %s
                      AND i.product_id = %s
                      AND UPPER(COALESCE(o.order_status, '')) NOT IN ('CANCELLED', 'PAYMENT_FAILED')
                    LIMIT 1;
                    """,
                    (int(customer_id), int(product_id)),
                )
                purchased = cur.fetchone() is not None

                cur.execute(
                    """
                    SELECT 1
                    FROM globalcart.fact_orders o
                    JOIN globalcart.fact_order_items i ON i.order_id = o.order_id
                    JOIN globalcart.fact_shipments s ON s.order_id = o.order_id
                    WHERE o.customer_id = %s
                      AND i.product_id = %s
                      AND s.delivered_dt IS NOT NULL
                      AND s.delivered_dt <= CURRENT_DATE
                      AND UPPER(COALESCE(o.order_status, '')) NOT IN ('CANCELLED', 'PAYMENT_FAILED')
                    LIMIT 1;
                    """,
                    (int(customer_id), int(product_id)),
                )
                delivered = cur.fetchone() is not None

        if delivered:
            return {"eligible": True, "reason": None}
        if purchased:
            return {"eligible": False, "reason": "NOT_DELIVERED"}
        return {"eligible": False, "reason": "NOT_PURCHASED"}
    except psycopg.OperationalError:
        return {"eligible": False, "reason": "DB_UNAVAILABLE"}
    except (psycopg.errors.UndefinedTable, psycopg.errors.InvalidSchemaName):
        raise HTTPException(
            status_code=500,
            detail=(
                "Required order/shipment tables not found. Run: python3 -m src.run_sql --sql sql/00_schema.sql"
            ),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to check eligibility: {e}")


@router.get("/products/{product_id}/reviews", response_model=List[ProductReviewOut])
def list_product_reviews(
    product_id: int,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    admin_key: str | None = Header(None, alias="X-Admin-Key"),
):
    _reject_admin(admin_key)
    try:
        with get_conn() as conn:
            conn.execute("SET TIME ZONE 'UTC';", prepare=False)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT review_id, product_id, customer_id, rating, title, body, created_at, updated_at
                    FROM globalcart.product_reviews
                    WHERE product_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s;
                    """,
                    (int(product_id), int(limit), int(offset)),
                )
                rows = cur.fetchall()

        out: List[ProductReviewOut] = []
        for r in rows:
            out.append(
                ProductReviewOut(
                    review_id=int(r[0]),
                    product_id=int(r[1]),
                    customer_id=int(r[2]),
                    rating=int(r[3]),
                    title=r[4],
                    body=r[5],
                    created_at=_ts(r[6]) or "",
                    updated_at=_ts(r[7]) or "",
                )
            )
        return out
    except psycopg.OperationalError:
        return []
    except (psycopg.errors.UndefinedTable, psycopg.errors.InvalidSchemaName):
        raise HTTPException(
            status_code=500,
            detail=(
                "Review tables not found. Run: python3 -m src.run_sql --sql sql/10_shop_features.sql"
            ),
        )


@router.post("/products/{product_id}/reviews", response_model=ProductReviewOut)
def upsert_product_review(
    product_id: int,
    payload: ProductReviewIn,
    customer_id: int = Query(..., ge=1),
    admin_key: str | None = Header(None, alias="X-Admin-Key"),
):
    _reject_admin(admin_key)
    now_ts = _utc_now()
    try:
        with get_conn() as conn:
            conn.execute("SET TIME ZONE 'UTC';", prepare=False)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT 1
                    FROM globalcart.fact_orders o
                    JOIN globalcart.fact_order_items i ON i.order_id = o.order_id
                    JOIN globalcart.fact_shipments s ON s.order_id = o.order_id
                    WHERE o.customer_id = %s
                      AND i.product_id = %s
                      AND s.delivered_dt IS NOT NULL
                      AND s.delivered_dt <= CURRENT_DATE
                      AND UPPER(COALESCE(o.order_status, '')) NOT IN ('CANCELLED', 'PAYMENT_FAILED')
                    LIMIT 1;
                    """,
                    (int(customer_id), int(product_id)),
                )
                if cur.fetchone() is None:
                    raise HTTPException(
                        status_code=403,
                        detail="Only customers with a delivered order for this product can review it.",
                    )

                cur.execute(
                    """
                    INSERT INTO globalcart.product_reviews (product_id, customer_id, rating, title, body, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (product_id, customer_id) DO UPDATE SET
                      rating = EXCLUDED.rating,
                      title = EXCLUDED.title,
                      body = EXCLUDED.body,
                      updated_at = EXCLUDED.updated_at
                    RETURNING review_id;
                    """,
                    (
                        int(product_id),
                        int(customer_id),
                        int(payload.rating),
                        payload.title,
                        payload.body,
                        now_ts,
                        now_ts,
                    ),
                )
                rid = cur.fetchone()[0]

            conn.commit()

        return ProductReviewOut(
            review_id=int(rid),
            product_id=int(product_id),
            customer_id=int(customer_id),
            rating=int(payload.rating),
            title=payload.title,
            body=payload.body,
            created_at=_ts(now_ts) or "",
            updated_at=_ts(now_ts) or "",
        )

    except psycopg.OperationalError:
        demo_id = int((int(product_id) * 100000) + (int(customer_id) % 100000))
        return ProductReviewOut(
            review_id=demo_id,
            product_id=int(product_id),
            customer_id=int(customer_id),
            rating=int(payload.rating),
            title=payload.title,
            body=payload.body,
            created_at=_ts(now_ts) or "",
            updated_at=_ts(now_ts) or "",
        )
    except (psycopg.errors.UndefinedTable, psycopg.errors.InvalidSchemaName):
        raise HTTPException(
            status_code=500,
            detail=(
                "Review tables not found. Run: python3 -m src.run_sql --sql sql/10_shop_features.sql"
            ),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save review: {e}")


@router.get("/emails", response_model=List[CustomerEmailOut])
def list_customer_emails(
    customer_id: int = Query(..., ge=1),
    limit: int = Query(50, ge=1, le=200),
    admin_key: str | None = Header(None, alias="X-Admin-Key"),
):
    _reject_admin(admin_key)
    try:
        with get_conn() as conn:
            conn.execute("SET TIME ZONE 'UTC';", prepare=False)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT email_id, to_email, subject, body, kind, order_id, status, created_at, sent_at
                    FROM globalcart.app_email_outbox
                    WHERE customer_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s;
                    """,
                    (int(customer_id), int(limit)),
                )
                rows = cur.fetchall()

        out: List[CustomerEmailOut] = []
        for r in rows:
            out.append(
                CustomerEmailOut(
                    email_id=int(r[0]),
                    to_email=str(r[1]),
                    subject=str(r[2]),
                    body=str(r[3]),
                    kind=str(r[4]),
                    order_id=int(r[5]) if r[5] is not None else None,
                    status=str(r[6]),
                    created_at=_ts(r[7]) or "",
                    sent_at=_ts(r[8]),
                )
            )
        return out
    except psycopg.OperationalError:
        now = _utc_now()
        cid = int(customer_id)
        to_email = f"customer{cid}@example.com"
        demo: List[CustomerEmailOut] = [
            CustomerEmailOut(
                email_id=1000 + cid,
                to_email=to_email,
                subject="Welcome to GlobalCart",
                body="This is demo inbox data (PostgreSQL is unavailable).",
                kind="WELCOME",
                order_id=None,
                status="SENT",
                created_at=_ts(now) or "",
                sent_at=_ts(now),
            ),
            CustomerEmailOut(
                email_id=1100 + cid,
                to_email=to_email,
                subject="Order confirmed",
                body="Your order has been confirmed (demo).",
                kind="ORDER_CONFIRMED",
                order_id=12000 + (cid % 500),
                status="SENT",
                created_at=_ts(now - timedelta(minutes=20)) or "",
                sent_at=_ts(now - timedelta(minutes=19)),
            ),
        ]
        return demo[: int(limit)]
    except (psycopg.errors.UndefinedTable, psycopg.errors.InvalidSchemaName):
        raise HTTPException(
            status_code=500,
            detail=(
                "Email outbox tables not found. Run: python3 -m src.run_sql --sql sql/10_shop_features.sql"
            ),
        )


@router.get("/orders/{order_id}", response_model=OrderDetailOut)
def order_detail(
    order_id: int,
    customer_id: int = Query(..., ge=1),
    admin_key: str | None = Header(None, alias="X-Admin-Key"),
):
    _reject_admin(admin_key)
    try:
        with get_conn() as conn:
            conn.execute("SET TIME ZONE 'UTC';", prepare=False)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT o.order_id, o.customer_id, o.order_ts, o.order_status,
                           o.gross_amount, o.discount_amount, o.tax_amount, o.net_amount,
                           p.payment_status,
                           op.promo_code, op.discount_amount
                    FROM globalcart.fact_orders o
                    LEFT JOIN globalcart.fact_payments p ON p.order_id = o.order_id
                    LEFT JOIN globalcart.order_promotions op ON op.order_id = o.order_id
                    WHERE o.order_id = %s;
                    """,
                    (int(order_id),),
                )
                row = cur.fetchone()
                if row is None:
                    raise HTTPException(status_code=404, detail="Order not found")

                if int(row[1]) != int(customer_id):
                    raise HTTPException(status_code=403, detail="Order does not belong to this customer")

                cur.execute(
                    """
                    SELECT oi.product_id, p.product_name, oi.qty
                    FROM globalcart.fact_order_items oi
                    JOIN globalcart.dim_product p ON p.product_id = oi.product_id
                    WHERE oi.order_id = %s
                    ORDER BY oi.order_item_id;
                    """,
                    (int(order_id),),
                )
                items = [
                    {
                        "product_id": int(r[0]),
                        "product_name": str(r[1]),
                        "qty": int(r[2]),
                    }
                    for r in cur.fetchall()
                ]

        return OrderDetailOut(
            order_id=int(row[0]),
            customer_id=int(row[1]),
            order_ts=_ts(row[2]) or "",
            order_status=str(row[3]),
            gross_amount=float(row[4]),
            discount_amount=float(row[5]),
            tax_amount=float(row[6]),
            net_amount=float(row[7]),
            payment_status=str(row[8]) if row[8] is not None else None,
            promo_code=str(row[9]) if row[9] is not None else None,
            promo_discount_amount=float(row[10]) if row[10] is not None else None,
            items=items,
        )
    except psycopg.OperationalError:
        now = _utc_now()
        oid = int(order_id)
        cid = int(customer_id)
        status = ["PLACED", "SHIPPED", "DELIVERED", "CANCELLED"][oid % 4]
        items = [
            {"product_id": 1001 + (oid % 50), "product_name": f"Demo Product {1001 + (oid % 50)}", "qty": 1 + (oid % 2)},
            {"product_id": 1101 + (oid % 50), "product_name": f"Demo Product {1101 + (oid % 50)}", "qty": 1},
        ]
        net = float(499 + (oid % 9000))
        disc = float((oid % 7) * 19)
        tax = float(round(net * 0.05, 2))
        gross = float(round(net + tax + 40 - disc, 2))
        return OrderDetailOut(
            order_id=oid,
            customer_id=cid,
            order_ts=_ts(now - timedelta(hours=(oid % 36))) or "",
            order_status=status,
            payment_status=None if status == "CANCELLED" else "CAPTURED",
            net_amount=net,
            gross_amount=gross,
            discount_amount=disc,
            tax_amount=tax,
            promo_code=None,
            promo_discount_amount=None,
            items=items,
        )
    except (psycopg.errors.UndefinedTable, psycopg.errors.InvalidSchemaName):
        raise HTTPException(
            status_code=500,
            detail=(
                "Required tables not found. Run: python3 -m src.run_sql --sql sql/00_schema.sql and python3 -m src.run_sql --sql sql/10_shop_features.sql"
            ),
        )


@router.get("/orders/{order_id}/timeline", response_model=OrderTimelineOut)
def order_timeline(
    order_id: int,
    customer_id: int = Query(..., ge=1),
    admin_key: str | None = Header(None, alias="X-Admin-Key"),
):
    _reject_admin(admin_key)

    try:
        with get_conn() as conn:
            conn.execute("SET TIME ZONE 'UTC';", prepare=False)

            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT customer_id, order_ts, order_status
                    FROM globalcart.vw_customer_orders
                    WHERE order_id = %s;
                    """,
                    (int(order_id),),
                )
                row = cur.fetchone()

                if row is None:
                    raise HTTPException(status_code=404, detail="Order not found")

                owner_customer_id = int(row[0])
                order_ts = row[1]
                order_status = str(row[2] or "").upper()

                if owner_customer_id != int(customer_id):
                    raise HTTPException(status_code=403, detail="Order does not belong to this customer")

                cur.execute(
                    """
                    SELECT MAX(shipped_ts) AS shipped_ts, MAX(delivered_dt) AS delivered_dt
                    FROM globalcart.vw_customer_shipments_timeline
                    WHERE order_id = %s
                    """,
                    (int(order_id),),
                )
                ship = cur.fetchone()
                shipped_ts = ship[0] if ship else None
                delivered_dt = ship[1] if ship else None

                cancel_ts = None
                cancel_reason = None
                cur.execute("SELECT to_regclass('globalcart.vw_customer_order_cancellations');")
                has_cancel = cur.fetchone()[0] is not None
                if has_cancel:
                    cur.execute(
                        """
                        SELECT created_at, reason
                        FROM globalcart.vw_customer_order_cancellations
                        WHERE order_id = %s AND customer_id = %s
                        ORDER BY created_at DESC
                        LIMIT 1;
                        """,
                        (int(order_id), int(customer_id)),
                    )
                    c = cur.fetchone()
                    if c is not None:
                        cancel_ts = c[0]
                        cancel_reason = str(c[1])

        now = _utc_now()
        shipped_done = shipped_ts is not None and shipped_ts <= now
        delivered_done = delivered_dt is not None and delivered_dt <= now.date()

        if order_status == "CANCELLED":
            current = "CANCELLED"
        elif delivered_done:
            current = "DELIVERED"
        elif shipped_done:
            current = "SHIPPED"
        else:
            current = "PLACED"

        stages = [
            OrderTimelineStageOut(stage="PLACED", timestamp=_ts(order_ts)),
            OrderTimelineStageOut(stage="SHIPPED", timestamp=None if (current == "CANCELLED" or not shipped_done) else _ts(shipped_ts)),
            OrderTimelineStageOut(stage="DELIVERED", timestamp=None if (current != "DELIVERED" or not delivered_done) else _ts(delivered_dt)),
            OrderTimelineStageOut(stage="CANCELLED", timestamp=_ts(cancel_ts) if current == "CANCELLED" else None),
        ]

        return OrderTimelineOut(
            order_id=int(order_id),
            current_status=current,
            stages=stages,
            cancellation_reason=cancel_reason if current == "CANCELLED" else None,
        )

    except psycopg.OperationalError:
        now = _utc_now()
        oid = int(order_id)
        current = ["PLACED", "SHIPPED", "DELIVERED", "CANCELLED"][oid % 4]
        placed_ts = _ts(now - timedelta(hours=12))
        shipped_ts = None if current in ("PLACED", "CANCELLED") else _ts(now - timedelta(hours=6))
        delivered_ts = None if current != "DELIVERED" else _ts(now - timedelta(hours=1))
        cancel_ts = None if current != "CANCELLED" else _ts(now - timedelta(hours=2))
        stages = [
            OrderTimelineStageOut(stage="PLACED", timestamp=placed_ts),
            OrderTimelineStageOut(stage="SHIPPED", timestamp=shipped_ts),
            OrderTimelineStageOut(stage="DELIVERED", timestamp=delivered_ts),
            OrderTimelineStageOut(stage="CANCELLED", timestamp=cancel_ts),
        ]
        return OrderTimelineOut(
            order_id=oid,
            current_status=current,
            stages=stages,
            cancellation_reason="Demo cancellation" if current == "CANCELLED" else None,
        )
    except (psycopg.errors.UndefinedTable, psycopg.errors.InvalidSchemaName):
        raise HTTPException(
            status_code=500,
            detail=(
                "Required views not found (missing globalcart.vw_customer_orders / globalcart.vw_customer_shipments_timeline). "
                "Run: python3 -m src.run_sql --sql sql/02_views.sql"
            ),
        )


def _product_map(conn, product_ids: List[int]) -> Dict[int, dict]:
    if not product_ids:
        return {}

    placeholders = ",".join(["%s"] * len(product_ids))
    sql = f"""
        SELECT product_id, sku, product_name, category_l1, category_l2, brand, unit_cost, list_price
        FROM globalcart.vw_customer_products
        WHERE product_id IN ({placeholders});
    """

    with conn.cursor() as cur:
        cur.execute(sql, tuple(product_ids))
        rows = cur.fetchall()

    out: Dict[int, dict] = {}
    for r in rows:
        out[int(r[0])] = {
            "sku": str(r[1]),
            "product_name": str(r[2]),
            "category_l1": str(r[3]),
            "category_l2": str(r[4]),
            "brand": str(r[5]),
            "unit_cost": float(r[6]),
            "list_price": float(r[7]),
        }
    return out


@router.post("/customers/resolve", response_model=CustomerResolveOut)
def resolve_customer(req: CustomerResolveIn, admin_key: str | None = Header(None, alias="X-Admin-Key")):
    _reject_admin(admin_key)

    email = (req.email or "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="email is required")

    h = int(hashlib.md5(email.encode("utf-8")).hexdigest(), 16)

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM globalcart.vw_customer_customers")
                n = int(cur.fetchone()[0])
                if n <= 0:
                    raise HTTPException(status_code=400, detail="No customers found. Load demo data first.")

                offset = int(h % n)
                cur.execute(
                    "SELECT customer_id, geo_id FROM globalcart.vw_customer_customers ORDER BY customer_id OFFSET %s LIMIT 1",
                    (offset,),
                )
                row = cur.fetchone()

        if row is None:
            raise HTTPException(status_code=400, detail="No customers found. Load demo data first.")

        return CustomerResolveOut(email=email, customer_id=int(row[0]), geo_id=int(row[1]))

    except psycopg.OperationalError:
        cid = int((h % 5000) + 1)
        geo_id = int((h % 250) + 1)
        return CustomerResolveOut(email=email, customer_id=cid, geo_id=geo_id)
    except (psycopg.errors.UndefinedTable, psycopg.errors.InvalidSchemaName):
        raise HTTPException(
            status_code=500,
            detail=(
                "Warehouse tables not found (missing globalcart.dim_customer). "
                "Run: python3 -m src.load_to_postgres (or make reset-db) first."
            ),
        )


@router.get("/products", response_model=List[ProductOut])
def list_products(
    limit: int = Query(24, ge=1, le=200),
    offset: int = Query(0, ge=0),
    category_l1: str | None = Query(None),
    category_l2: str | None = Query(None),
    sort: str = Query("default"),
    admin_key: str | None = Header(None, alias="X-Admin-Key"),
):
    _reject_admin(admin_key)

    sort_key = (sort or "default").strip().lower()
    allowed = {"default", "price_asc", "price_desc", "best_sellers"}
    if sort_key not in allowed:
        raise HTTPException(status_code=400, detail=f"Invalid sort: {sort}. Allowed: {sorted(list(allowed))}")

    where = []
    params: List[object] = []
    if category_l1:
        where.append("p.category_l1 = %s")
        params.append(str(category_l1))
    if category_l2:
        where.append("p.category_l2 = %s")
        params.append(str(category_l2))

    join_best = ""
    order_by = "p.product_id"
    if sort_key == "price_asc":
        order_by = "p.list_price ASC, p.product_id"
    elif sort_key == "price_desc":
        order_by = "p.list_price DESC, p.product_id"
    elif sort_key == "best_sellers":
        join_best = """
            LEFT JOIN (
              SELECT i.product_id, COALESCE(SUM(i.qty), 0) AS units_sold
              FROM globalcart.fact_order_items i
              JOIN globalcart.vw_orders_completed o ON o.order_id = i.order_id
              GROUP BY 1
            ) bs ON bs.product_id = p.product_id
        """
        order_by = "COALESCE(bs.units_sold, 0) DESC, p.product_id"

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    sql = f"""
        SELECT p.product_id, p.sku, p.product_name, p.category_l1, p.category_l2, p.brand, p.unit_cost, p.list_price
        FROM globalcart.vw_customer_products p
        {join_best}
        {where_sql}
        ORDER BY {order_by}
        LIMIT %s OFFSET %s;
    """

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                params2 = list(params) + [int(limit), int(offset)]
                cur.execute(sql, tuple(params2))
                rows = cur.fetchall()

        products: List[ProductOut] = []
        for r in rows:
            pid = int(r[0])
            sku = str(r[1])
            product_name = str(r[2])
            category_l1 = str(r[3])
            category_l2 = str(r[4])
            brand = str(r[5])
            list_price = float(r[7])
            disc = _stable_discount_pct(pid)
            sell_price = round(list_price * (1 - disc / 100.0), 2)

            products.append(
                ProductOut(
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
                )
            )

        return products

    except psycopg.OperationalError:
        return _demo_catalog(
            limit=int(limit),
            offset=int(offset),
            category_l1=category_l1,
            category_l2=category_l2,
            sort_key=sort_key,
        )
    except (psycopg.errors.UndefinedTable, psycopg.errors.InvalidSchemaName):
        raise HTTPException(
            status_code=500,
            detail=(
                "Warehouse tables not found (missing globalcart.dim_product). "
                "Run: python3 -m src.run_sql --sql sql/00_schema.sql and load/generate data before using the web demo."
            ),
        )


@router.get("/products/{product_id}", response_model=ProductDetailOut)
def get_product(product_id: int, admin_key: str | None = Header(None, alias="X-Admin-Key")):
    _reject_admin(admin_key)

    sql = """
        SELECT product_id, sku, product_name, category_l1, category_l2, brand, unit_cost, list_price
        FROM globalcart.vw_customer_products
        WHERE product_id = %s;
    """

    try:
        with get_conn() as conn:
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


@router.post("/orders", response_model=OrderCreatedOut)
def create_order(req: CreateOrderRequest, admin_key: str | None = Header(None, alias="X-Admin-Key")):
    _reject_admin(admin_key)

    if not req.items:
        raise HTTPException(status_code=400, detail="Cart is empty")

    if req.customer_id is None:
        raise HTTPException(status_code=401, detail="Sign in required to place an order")

    now_ts = _utc_now()

    simulate_fail = bool(getattr(req, "simulate_payment_failure", False))
    payment_method = str(getattr(req, "payment_method", "UPI") or "UPI")
    failure_reason = getattr(req, "failure_reason", None)
    if failure_reason is not None:
        failure_reason = str(failure_reason).strip() or None
    promo_code = getattr(req, "promo_code", None)
    if promo_code is not None:
        promo_code = str(promo_code).strip() or None

    try:
        with get_conn() as conn:
            conn.execute("SET TIME ZONE 'UTC';", prepare=False)

            if req.customer_id is not None:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT geo_id FROM globalcart.vw_customer_customers WHERE customer_id = %s",
                        (int(req.customer_id),),
                    )
                    row = cur.fetchone()
                if row is None:
                    raise HTTPException(status_code=400, detail="Invalid customer_id")
                customer_id = int(req.customer_id)
                geo_id = int(row[0])
            else:
                customer_id = _pick_any(conn, "globalcart.vw_customer_customers", "customer_id")
                geo_id = _pick_any(conn, "globalcart.vw_customer_geo", "geo_id")
            fc_id = _pick_any(conn, "globalcart.vw_customer_fc", "fc_id")

            order_id = _next_id(conn, "globalcart.vw_customer_orders", "order_id")
            payment_id = _next_id(conn, "globalcart.vw_customer_payments", "payment_id")
            shipment_id = _next_id(conn, "globalcart.vw_customer_shipments", "shipment_id")
            next_item_id = _next_id(conn, "globalcart.vw_customer_order_items_core", "order_item_id")

            product_ids = [i.product_id for i in req.items]
            prod = _product_map(conn, product_ids)

            missing = [pid for pid in product_ids if pid not in prod]
            if missing:
                raise HTTPException(status_code=400, detail=f"Invalid product_ids: {missing}")

            gross_amount = 0.0
            discount_amount = 0.0
            tax_amount = 0.0
            net_amount = 0.0
            promo_discount_amount = 0.0

            order_items_rows: List[tuple] = []

            for item in req.items:
                pid = int(item.product_id)
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

            if promo_code:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT discount_type, discount_value, max_discount, min_order_amount, active, expires_at
                        FROM globalcart.promo_codes
                        WHERE code = %s;
                        """,
                        (promo_code,),
                    )
                    pr = cur.fetchone()

                if pr is None:
                    raise HTTPException(status_code=400, detail="Invalid promo code")

                discount_type = str(pr[0] or "").upper()
                discount_value = float(pr[1] or 0)
                max_discount = float(pr[2]) if pr[2] is not None else None
                min_order_amount = float(pr[3]) if pr[3] is not None else None
                active = bool(pr[4])
                expires_at = pr[5]

                if not active:
                    raise HTTPException(status_code=400, detail="Promo code is not active")
                if expires_at is not None and expires_at <= now_ts:
                    raise HTTPException(status_code=400, detail="Promo code has expired")
                if min_order_amount is not None and net_amount < min_order_amount:
                    raise HTTPException(status_code=400, detail=f"Minimum order amount is {min_order_amount}")

                if discount_type == "PERCENT":
                    promo_discount_amount = round((net_amount * discount_value) / 100.0, 2)
                elif discount_type == "FLAT":
                    promo_discount_amount = round(discount_value, 2)
                else:
                    raise HTTPException(status_code=400, detail="Invalid promo configuration")

                if max_discount is not None:
                    promo_discount_amount = min(promo_discount_amount, round(max_discount, 2))
                promo_discount_amount = min(promo_discount_amount, net_amount)
                promo_discount_amount = round(promo_discount_amount, 2)

                discount_amount = round(discount_amount + promo_discount_amount, 2)
                net_amount = round(max(0.0, net_amount - promo_discount_amount), 2)

            order_sql = """
                INSERT INTO globalcart.fact_orders (
                    order_id, customer_id, geo_id, order_ts, order_status, channel, currency,
                    gross_amount, discount_amount, tax_amount, net_amount, created_at, updated_at
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s);
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
                cur.execute(
                    order_sql,
                    (
                        order_id,
                        customer_id,
                        geo_id,
                        now_ts,
                        "PAYMENT_FAILED" if simulate_fail else "PLACED",
                        req.channel,
                        req.currency or "INR",
                        gross_amount,
                        discount_amount,
                        tax_amount,
                        net_amount,
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
                        payment_method,
                        "FAILED" if simulate_fail else "CAPTURED",
                        "DEMO",
                        net_amount,
                        now_ts,
                        None if simulate_fail else (now_ts + timedelta(minutes=1)),
                        failure_reason if simulate_fail else None,
                        0.0,
                        False,
                        now_ts,
                        now_ts,
                    ),
                )

                if promo_code and promo_discount_amount > 0 and not simulate_fail:
                    cur.execute(
                        """
                        INSERT INTO globalcart.order_promotions (order_id, promo_code, discount_amount)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (order_id) DO UPDATE SET promo_code = EXCLUDED.promo_code, discount_amount = EXCLUDED.discount_amount;
                        """,
                        (int(order_id), promo_code, promo_discount_amount),
                    )

                try:
                    cur.execute("SELECT to_regclass('globalcart.app_users');")
                    has_users = cur.fetchone()[0] is not None
                    cur.execute("SELECT to_regclass('globalcart.app_email_outbox');")
                    has_outbox = cur.fetchone()[0] is not None

                    to_email = None
                    if has_users and customer_id is not None:
                        cur.execute(
                            """
                            SELECT email
                            FROM globalcart.app_users
                            WHERE customer_id = %s
                            ORDER BY updated_at DESC
                            LIMIT 1;
                            """,
                            (int(customer_id),),
                        )
                        er = cur.fetchone()
                        if er is not None:
                            to_email = str(er[0])

                    if has_outbox and to_email:
                        if simulate_fail:
                            subject = f"Payment failed for order #{order_id}"
                            body = f"Your payment failed for order #{order_id}. Please retry."
                            kind = "PAYMENT_FAILED"
                        else:
                            subject = f"Order confirmed #{order_id}"
                            body = f"Your order #{order_id} has been confirmed. Total: {net_amount}."
                            if promo_code and promo_discount_amount > 0:
                                body += f" Promo applied: {promo_code} (-{promo_discount_amount})."
                            kind = "ORDER_CONFIRMED"

                        cur.execute(
                            """
                            INSERT INTO globalcart.app_email_outbox (customer_id, to_email, subject, body, kind, order_id)
                            VALUES (%s, %s, %s, %s, %s, %s);
                            """,
                            (int(customer_id), to_email, subject, body, kind, int(order_id)),
                        )
                except Exception:
                    pass

                if not simulate_fail:
                    cur.execute(
                        shipment_sql,
                        (
                            shipment_id,
                            order_id,
                            fc_id,
                            "Delhivery",
                            (now_ts + timedelta(minutes=1)),
                            (now_ts + timedelta(days=3)).date(),
                            (now_ts + timedelta(days=3)).date(),
                            49.0,
                            False,
                            now_ts,
                            now_ts,
                        ),
                    )

            conn.commit()
            return OrderCreatedOut(
                order_id=order_id,
                net_amount=net_amount,
                order_status="PAYMENT_FAILED" if simulate_fail else "PLACED",
                payment_status="FAILED" if simulate_fail else "CAPTURED",
                promo_code=promo_code,
                promo_discount_amount=promo_discount_amount if promo_discount_amount > 0 else None,
            )

    except psycopg.OperationalError:
        net_amount = 0.0
        for item in req.items:
            pid = int(item.product_id)
            qty = int(item.qty)
            list_price = float(199 + (pid % 200) * 10)
            disc = _stable_discount_pct(pid)
            unit_sell = round(list_price * (1 - disc / 100.0), 2)
            line_tax = round(0.07 * (unit_sell * qty), 2)
            line_net = round((unit_sell * qty) + line_tax, 2)
            net_amount += line_net
        net_amount = round(net_amount, 2)
        demo_order_id = int(900000 + (int(now_ts.timestamp()) % 100000))
        promo_discount_amount = None
        return OrderCreatedOut(
            order_id=demo_order_id,
            net_amount=float(net_amount),
            order_status="PAYMENT_FAILED" if simulate_fail else "PLACED",
            payment_status="FAILED" if simulate_fail else "CAPTURED",
            promo_code=promo_code,
            promo_discount_amount=promo_discount_amount,
        )
    except (psycopg.errors.UndefinedTable, psycopg.errors.InvalidSchemaName):
        raise HTTPException(
            status_code=500,
            detail=(
                "Warehouse tables not found (missing globalcart schema/tables). "
                "Run: python3 -m src.run_sql --sql sql/00_schema.sql and load/generate data before placing orders."
            ),
        )
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logger = logging.getLogger("api_customer")
        logger.exception("Unexpected error in create_order")
        raise HTTPException(status_code=500, detail=f"Unexpected error while creating order: {e}")


@router.get("/orders/by-customer/{customer_id}", response_model=OrdersByCustomerOut)
def orders_by_customer(
    customer_id: int,
    limit: int = Query(20, ge=1, le=100),
    admin_key: str | None = Header(None, alias="X-Admin-Key"),
):
    _reject_admin(admin_key)

    try:
        with get_conn() as conn:
            conn.execute("SET TIME ZONE 'UTC';", prepare=False)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT order_id, order_ts, order_status, net_amount
                    FROM globalcart.vw_customer_orders
                    WHERE customer_id = %s
                    ORDER BY order_ts DESC
                    LIMIT %s;
                    """,
                    (int(customer_id), int(limit)),
                )
                rows = cur.fetchall()

                ship_by_order: Dict[int, tuple] = {}

                order_ids = [int(r[0]) for r in rows]
                items_by_order: Dict[int, List[dict]] = {oid: [] for oid in order_ids}

                if order_ids:
                    placeholders = ",".join(["%s"] * len(order_ids))
                    cur.execute(
                        f"""
                        SELECT order_id, product_id, product_name, qty
                        FROM globalcart.vw_customer_order_items
                        WHERE order_id IN ({placeholders})
                        ORDER BY order_id, product_id;
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

                    placeholders = ",".join(["%s"] * len(order_ids))
                    cur.execute(
                        f"""
                        SELECT order_id, MAX(shipped_ts) AS shipped_ts, MAX(delivered_dt) AS delivered_dt
                        FROM globalcart.vw_customer_shipments_timeline
                        WHERE order_id IN ({placeholders})
                        GROUP BY order_id
                        ORDER BY order_id;
                        """,
                        tuple(order_ids),
                    )
                    ship_rows = cur.fetchall()
                    for sr in ship_rows:
                        oid = int(sr[0])
                        if oid not in ship_by_order:
                            ship_by_order[oid] = (sr[1], sr[2])

        now = _utc_now()
        orders = []
        for r in rows:
            oid = int(r[0])
            ts = r[1].isoformat() if hasattr(r[1], "isoformat") else str(r[1])

            status_raw = str(r[2] or "").upper()
            status = status_raw
            if status_raw != "CANCELLED":
                shipped_ts, delivered_dt = ship_by_order.get(oid, (None, None))
                delivered_done = delivered_dt is not None and delivered_dt <= now.date()
                shipped_done = shipped_ts is not None and shipped_ts <= now
                if delivered_done:
                    status = "DELIVERED"
                elif shipped_done:
                    status = "SHIPPED"
                else:
                    status = "PLACED"

            orders.append(
                {
                    "order_id": oid,
                    "order_ts": ts,
                    "order_status": status,
                    "net_amount": float(r[3]),
                    "items": items_by_order.get(oid, []),
                }
            )

        return {"customer_id": int(customer_id), "orders": orders}

    except psycopg.OperationalError:
        now = _utc_now()
        cid = int(customer_id)
        n = int(min(max(limit, 1), 20))
        base = 12000 + (cid % 500)
        statuses = ["PLACED", "SHIPPED", "DELIVERED", "CANCELLED"]
        demo_orders: List[dict] = []
        for i in range(n):
            oid = base + i
            demo_orders.append(
                {
                    "order_id": int(oid),
                    "order_ts": _ts(now - timedelta(days=i, hours=(i * 3) % 12)) or "",
                    "order_status": statuses[oid % len(statuses)],
                    "net_amount": float(399 + (oid % 9000)),
                    "items": [
                        {
                            "product_id": 1001 + (oid % 50),
                            "product_name": f"Demo Product {1001 + (oid % 50)}",
                            "qty": 1 + (oid % 2),
                        },
                        {
                            "product_id": 1101 + (oid % 50),
                            "product_name": f"Demo Product {1101 + (oid % 50)}",
                            "qty": 1,
                        },
                    ],
                }
            )
        return {"customer_id": cid, "orders": demo_orders}
    except (psycopg.errors.UndefinedTable, psycopg.errors.InvalidSchemaName):
        raise HTTPException(
            status_code=500,
            detail=(
                "Required views not found (missing globalcart.vw_customer_orders / vw_customer_order_items). "
                "Run: python3 -m src.run_sql --sql sql/02_views.sql"
            ),
        )


@router.post("/orders/{order_id}/cancel", response_model=CancelOrderOut)
def cancel_order(
    order_id: int,
    req: CancelOrderIn,
    admin_key: str | None = Header(None, alias="X-Admin-Key"),
):
    _reject_admin(admin_key)

    try:
        reason = str(req.reason or "").strip()
        if not reason:
            raise HTTPException(status_code=400, detail="Cancellation reason is required")

        with get_conn() as conn:
            conn.execute("SET TIME ZONE 'UTC';", prepare=False)
            with conn.cursor() as cur:
                cur.execute("SELECT to_regclass('globalcart.order_cancellations');")
                if cur.fetchone()[0] is None:
                    raise HTTPException(
                        status_code=500,
                        detail=(
                            "Warehouse tables not found (missing globalcart.order_cancellations). "
                            "Run: python3 -m src.run_sql --sql sql/00_schema.sql"
                        ),
                    )

                cur.execute(
                    """
                    SELECT customer_id, order_status
                    FROM globalcart.vw_customer_orders
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

                cur.execute(
                    """
                    SELECT MAX(shipped_ts) AS shipped_ts, MAX(delivered_dt) AS delivered_dt
                    FROM globalcart.vw_customer_shipments_timeline
                    WHERE order_id = %s
                    """,
                    (int(order_id),),
                )
                ship = cur.fetchone()
                shipped_ts = ship[0] if ship else None
                delivered_dt = ship[1] if ship else None

                now = _utc_now()
                delivered_done = delivered_dt is not None and delivered_dt <= now.date()
                shipped_done = shipped_ts is not None and shipped_ts <= now
                if status.upper() != "PLACED" or delivered_done or shipped_done:
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
        return CancelOrderOut(order_id=int(order_id), order_status="CANCELLED")
    except (psycopg.errors.UndefinedTable, psycopg.errors.InvalidSchemaName):
        raise HTTPException(
            status_code=500,
            detail=(
                "Required objects not found. "
                "Run: python3 -m src.run_sql --sql sql/00_schema.sql and python3 -m src.run_sql --sql sql/02_views.sql"
            ),
        )
