from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import List
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query
import psycopg

from ..db import get_conn
from ..models import ProductDetailOut, ProductOut


router = APIRouter(prefix="/products", tags=["products"])


def _stable_discount_pct(product_id: int) -> int:
    # Deterministic "discount" purely for UI/demo (not stored in dim_product)
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


@router.get("", response_model=List[ProductOut])
def list_products(limit: int = Query(24, ge=1, le=200), offset: int = Query(0, ge=0)):
    sql = """
        SELECT product_id, sku, product_name, category_l1, category_l2, brand,
               unit_cost, list_price
        FROM globalcart.dim_product
        ORDER BY product_id
        LIMIT %s OFFSET %s;
    """

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (limit, offset))
                rows = cur.fetchall()
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
                "Warehouse tables not found (missing globalcart.dim_product). "
                "Run: python3 -m src.run_sql --sql sql/00_schema.sql and load/generate data before using the web demo."
            ),
        )

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


@router.get("/{product_id}", response_model=ProductDetailOut)
def get_product(product_id: int):
    sql = """
        SELECT product_id, sku, product_name, category_l1, category_l2, brand,
               unit_cost, list_price
        FROM globalcart.dim_product
        WHERE product_id = %s;
    """

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (product_id,))
                row = cur.fetchone()
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
                "Warehouse tables not found (missing globalcart.dim_product). "
                "Run: python3 -m src.run_sql --sql sql/00_schema.sql and load/generate data before using the web demo."
            ),
        )

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

    desc = (
        f"{product_name} by {brand}. Category: {category_l1} / {category_l2}. "
        "Demo product description for GlobalCart." 
    )

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
    )
