from __future__ import annotations

import os

import pandas as pd

from .common import get_paths, read_sql_df


def run() -> None:
    paths = get_paths()
    os.makedirs(paths.data_processed_dir, exist_ok=True)

    churned = read_sql_df(
        """
        WITH last_order AS (
          SELECT customer_id, MAX(order_ts) AS last_order_ts
          FROM globalcart.vw_orders_completed
          GROUP BY 1
        )
        SELECT customer_id, last_order_ts
        FROM last_order
        WHERE last_order_ts < (CURRENT_DATE - INTERVAL '90 days')
        """
    )
    churned.to_csv(os.path.join(paths.data_processed_dir, "churned_customers_90d.csv"), index=False)

    cohort = read_sql_df(
        """
        WITH first_purchase AS (
          SELECT customer_id, date_trunc('month', MIN(order_ts)) AS cohort_month
          FROM globalcart.vw_orders_completed
          GROUP BY 1
        ),
        activity AS (
          SELECT o.customer_id,
                 fp.cohort_month,
                 date_trunc('month', o.order_ts) AS activity_month
          FROM globalcart.vw_orders_completed o
          JOIN first_purchase fp ON fp.customer_id = o.customer_id
        )
        SELECT cohort_month,
               ((EXTRACT(YEAR FROM activity_month) - EXTRACT(YEAR FROM cohort_month)) * 12
                + (EXTRACT(MONTH FROM activity_month) - EXTRACT(MONTH FROM cohort_month))) AS months_since_cohort,
               COUNT(DISTINCT customer_id) AS customers
        FROM activity
        GROUP BY 1,2
        ORDER BY 1,2
        """
    )

    cohort.to_csv(os.path.join(paths.data_processed_dir, "cohort_retention_long.csv"), index=False)

    cohort_pivot = cohort.pivot_table(
        index="cohort_month",
        columns="months_since_cohort",
        values="customers",
        aggfunc="sum",
        fill_value=0,
    )
    cohort_pivot.to_csv(os.path.join(paths.data_processed_dir, "cohort_retention_matrix.csv"))


def main() -> None:
    run()


if __name__ == "__main__":
    main()
