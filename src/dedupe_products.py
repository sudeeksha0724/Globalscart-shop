from __future__ import annotations

import argparse

import psycopg
from psycopg import Connection

from .config import PostgresConfig
from .db import get_conn


def _stats(conn: Connection) -> tuple[int, int, int]:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM globalcart.dim_product")
        total = int(cur.fetchone()[0])

        cur.execute(
            """
            SELECT COUNT(*)
            FROM (
              SELECT product_name
              FROM globalcart.dim_product
              GROUP BY product_name
              HAVING COUNT(*) > 1
            ) s;
            """
        )
        dup_groups = int(cur.fetchone()[0])

        cur.execute(
            """
            SELECT COALESCE(SUM(cnt - 1), 0)
            FROM (
              SELECT COUNT(*) AS cnt
              FROM globalcart.dim_product
              GROUP BY product_name
              HAVING COUNT(*) > 1
            ) s;
            """
        )
        extra_dup_rows = int(cur.fetchone()[0])

    return total, dup_groups, extra_dup_rows


def dedupe_products(cfg: PostgresConfig) -> None:
    with get_conn(cfg) as conn:
        with conn.transaction():
            before_total, before_dup_groups, before_dup_rows = _stats(conn)
            print(
                f"Before: dim_product rows={before_total}, dup_groups={before_dup_groups}, extra_dup_rows={before_dup_rows}"
            )

            with conn.cursor() as cur:
                cur.execute("DROP TABLE IF EXISTS tmp_product_merge")
                cur.execute(
                    """
                    CREATE TEMP TABLE tmp_product_merge AS
                    WITH canonical AS (
                      SELECT product_name, MIN(product_id) AS canonical_id
                      FROM globalcart.dim_product
                      GROUP BY product_name
                    )
                    SELECT p.product_id AS old_id, c.canonical_id
                    FROM globalcart.dim_product p
                    JOIN canonical c
                      ON p.product_name IS NOT DISTINCT FROM c.product_name
                    WHERE p.product_id <> c.canonical_id;
                    """
                )
                cur.execute("CREATE INDEX tmp_product_merge_old_id_idx ON tmp_product_merge(old_id)")

                cur.execute("SELECT COUNT(*) FROM tmp_product_merge")
                merge_rows = int(cur.fetchone()[0])
                print(f"Merge map rows: {merge_rows}")

                cur.execute(
                    """
                    UPDATE globalcart.fact_order_items oi
                    SET product_id = m.canonical_id
                    FROM tmp_product_merge m
                    WHERE oi.product_id = m.old_id;
                    """
                )
                print(f"Updated fact_order_items rows: {cur.rowcount}")

                cur.execute(
                    """
                    UPDATE globalcart.fact_returns r
                    SET product_id = m.canonical_id
                    FROM tmp_product_merge m
                    WHERE r.product_id = m.old_id;
                    """
                )
                print(f"Updated fact_returns rows (via map): {cur.rowcount}")

                cur.execute(
                    """
                    UPDATE globalcart.fact_returns r
                    SET product_id = oi.product_id
                    FROM globalcart.fact_order_items oi
                    WHERE r.order_item_id = oi.order_item_id
                      AND r.product_id <> oi.product_id;
                    """
                )
                print(f"Updated fact_returns rows (align to order_item): {cur.rowcount}")

                cur.execute(
                    """
                    UPDATE globalcart.fact_funnel_events fe
                    SET product_id = m.canonical_id
                    FROM tmp_product_merge m
                    WHERE fe.product_id = m.old_id;
                    """
                )
                print(f"Updated fact_funnel_events rows: {cur.rowcount}")

                # Shop extension tables (may not exist depending on what SQL was run)
                try:
                    with conn.transaction():
                        cur.execute(
                            """
                            UPDATE globalcart.customer_wishlist w
                            SET product_id = m.canonical_id
                            FROM tmp_product_merge m
                            WHERE w.product_id = m.old_id;
                            """
                        )
                    print(f"Updated customer_wishlist rows: {cur.rowcount}")
                except (psycopg.errors.UndefinedTable, psycopg.errors.InvalidSchemaName):
                    print("Skipped customer_wishlist remap (table missing)")

                try:
                    with conn.transaction():
                        cur.execute(
                            """
                            UPDATE globalcart.product_reviews pr
                            SET product_id = m.canonical_id
                            FROM tmp_product_merge m
                            WHERE pr.product_id = m.old_id;
                            """
                        )
                    print(f"Updated product_reviews rows: {cur.rowcount}")
                except (psycopg.errors.UndefinedTable, psycopg.errors.InvalidSchemaName):
                    print("Skipped product_reviews remap (table missing)")

                cur.execute(
                    """
                    DELETE FROM globalcart.dim_product p
                    USING tmp_product_merge m
                    WHERE p.product_id = m.old_id;
                    """
                )
                print(f"Deleted duplicate dim_product rows: {cur.rowcount}")

            after_total, after_dup_groups, after_dup_rows = _stats(conn)
            print(
                f"After: dim_product rows={after_total}, dup_groups={after_dup_groups}, extra_dup_rows={after_dup_rows}"
            )


def main() -> None:
    _ = argparse.ArgumentParser()
    cfg = PostgresConfig()
    dedupe_products(cfg)


if __name__ == "__main__":
    main()
