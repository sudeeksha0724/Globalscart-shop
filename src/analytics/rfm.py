from __future__ import annotations

import os
from datetime import timedelta

import pandas as pd

from .common import get_paths, read_sql_df


def run() -> pd.DataFrame:
    paths = get_paths()
    os.makedirs(paths.data_processed_dir, exist_ok=True)

    orders = read_sql_df(
        """
        SELECT customer_id, order_id, order_ts, net_amount
        FROM globalcart.vw_orders_completed
        """
    )

    orders["order_ts"] = pd.to_datetime(orders["order_ts"], utc=True, errors="coerce")
    as_of = orders["order_ts"].max() + timedelta(days=1)

    rfm = (
        orders.groupby("customer_id")
        .agg(
            recency_days=("order_ts", lambda s: int((as_of - s.max()).days)),
            frequency=("order_id", "nunique"),
            monetary=("net_amount", "sum"),
        )
        .reset_index()
    )

    rfm["r_score"] = pd.qcut(rfm["recency_days"], 5, labels=[5, 4, 3, 2, 1]).astype(int)
    rfm["f_score"] = pd.qcut(rfm["frequency"].rank(method="first"), 5, labels=[1, 2, 3, 4, 5]).astype(int)
    rfm["m_score"] = pd.qcut(rfm["monetary"], 5, labels=[1, 2, 3, 4, 5]).astype(int)

    def segment(row: pd.Series) -> str:
        if row["r_score"] >= 4 and row["f_score"] >= 4:
            return "Champions"
        if row["r_score"] >= 4 and row["f_score"] <= 2:
            return "New Customers"
        if row["r_score"] <= 2 and row["f_score"] >= 4:
            return "At Risk Loyal"
        if row["r_score"] <= 2 and row["f_score"] <= 2:
            return "Lost"
        return "Potential Loyalist"

    rfm["segment"] = rfm.apply(segment, axis=1)
    rfm["rfm_score"] = rfm["r_score"] * 100 + rfm["f_score"] * 10 + rfm["m_score"]

    out = os.path.join(paths.data_processed_dir, "rfm_segments.csv")
    rfm.to_csv(out, index=False)
    return rfm


def main() -> None:
    run()


if __name__ == "__main__":
    main()
