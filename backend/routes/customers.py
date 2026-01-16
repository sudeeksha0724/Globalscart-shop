from __future__ import annotations

import hashlib

from fastapi import APIRouter, HTTPException
import psycopg

from ..db import get_conn
from ..models import CustomerResolveIn, CustomerResolveOut


router = APIRouter(prefix="/customers", tags=["customers"])


@router.post("/resolve", response_model=CustomerResolveOut)
def resolve_customer(req: CustomerResolveIn):
    email = (req.email or "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="email is required")

    h = int(hashlib.md5(email.encode("utf-8")).hexdigest(), 16)

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM globalcart.dim_customer")
                n = int(cur.fetchone()[0])
                if n <= 0:
                    raise HTTPException(status_code=400, detail="No customers found. Load demo data first.")

                offset = int(h % n)
                cur.execute(
                    "SELECT customer_id, geo_id FROM globalcart.dim_customer ORDER BY customer_id OFFSET %s LIMIT 1",
                    (offset,),
                )
                row = cur.fetchone()

        if row is None:
            raise HTTPException(status_code=400, detail="No customers found. Load demo data first.")

        return CustomerResolveOut(email=email, customer_id=int(row[0]), geo_id=int(row[1]))

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
                "Warehouse tables not found (missing globalcart.dim_customer). "
                "Run: python3 -m src.load_to_postgres (or make reset-db) first."
            ),
        )
