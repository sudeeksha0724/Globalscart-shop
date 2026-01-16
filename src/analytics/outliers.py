from __future__ import annotations

import os

import numpy as np
import pandas as pd

from .common import get_paths, read_sql_df


def _iqr_bounds(s: pd.Series) -> tuple[float, float]:
    q1 = s.quantile(0.25)
    q3 = s.quantile(0.75)
    iqr = q3 - q1
    lo = q1 - 1.5 * iqr
    hi = q3 + 1.5 * iqr
    return float(lo), float(hi)


def run() -> pd.DataFrame:
    paths = get_paths()
    os.makedirs(paths.data_processed_dir, exist_ok=True)

    items = read_sql_df(
        """
        SELECT o.customer_id,
               i.order_id,
               SUM(i.line_discount) AS discount_amount,
               SUM(i.line_net_revenue + i.line_discount) AS gross_before_discount,
               SUM(i.line_net_revenue) AS net_revenue
        FROM globalcart.fact_order_items i
        JOIN globalcart.vw_orders_completed o ON o.order_id = i.order_id
        GROUP BY 1,2
        """
    )

    items["discount_pct"] = np.where(
        items["gross_before_discount"] == 0,
        0.0,
        100.0 * items["discount_amount"] / items["gross_before_discount"],
    )

    returns = read_sql_df(
        """
        SELECT o.customer_id,
               COUNT(*) AS return_lines,
               SUM(r.refund_amount) AS refund_amount
        FROM globalcart.fact_returns r
        JOIN globalcart.fact_orders o ON o.order_id = r.order_id
        GROUP BY 1
        """
    )

    cust = (
        items.groupby("customer_id")
        .agg(
            orders=("order_id", "nunique"),
            avg_discount_pct=("discount_pct", "mean"),
            p95_discount_pct=("discount_pct", lambda s: float(s.quantile(0.95))),
            net_revenue=("net_revenue", "sum"),
        )
        .reset_index()
    )

    cust = cust.merge(returns, on="customer_id", how="left")
    cust[["return_lines", "refund_amount"]] = cust[["return_lines", "refund_amount"]].fillna(0)

    lo_d, hi_d = _iqr_bounds(cust["avg_discount_pct"])
    lo_r, hi_r = _iqr_bounds(cust["refund_amount"])

    cust["flag_discount_abuse"] = cust["avg_discount_pct"] > hi_d
    cust["flag_refund_abuse"] = cust["refund_amount"] > hi_r
    cust["flag_any"] = cust["flag_discount_abuse"] | cust["flag_refund_abuse"]

    out_path = os.path.join(paths.data_processed_dir, "outlier_customers.csv")
    cust.sort_values(["flag_any", "refund_amount"], ascending=[False, False]).to_csv(out_path, index=False)
    return cust


def main() -> None:
    run()


if __name__ == "__main__":
    main()
