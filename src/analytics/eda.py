from __future__ import annotations

import os

import matplotlib.pyplot as plt
import seaborn as sns

from .common import get_paths, read_sql_df


def run() -> None:
    paths = get_paths()
    os.makedirs(paths.reports_dir, exist_ok=True)

    monthly = read_sql_df(
        """
        SELECT date_trunc('month', order_ts) AS month,
               SUM(net_amount) AS net_revenue,
               COUNT(DISTINCT order_id) AS orders
        FROM globalcart.vw_orders_completed
        GROUP BY 1
        ORDER BY 1
        """
    )

    sns.set_theme(style="whitegrid")

    plt.figure(figsize=(10, 4))
    sns.lineplot(data=monthly, x="month", y="net_revenue")
    plt.title("Monthly Net Revenue")
    plt.tight_layout()
    plt.savefig(os.path.join(paths.reports_dir, "monthly_net_revenue.png"), dpi=160)
    plt.close()

    cat = read_sql_df(
        """
        SELECT category_l1,
               SUM(line_net_revenue) AS revenue,
               SUM(line_gross_profit) AS gross_profit,
               ROUND(100.0 * SUM(line_gross_profit) / NULLIF(SUM(line_net_revenue),0), 2) AS gross_margin_pct
        FROM globalcart.vw_item_profitability
        GROUP BY 1
        ORDER BY gross_profit DESC
        """
    )

    plt.figure(figsize=(10, 4))
    sns.barplot(data=cat, x="category_l1", y="gross_profit")
    plt.title("Gross Profit by Category")
    plt.xticks(rotation=25, ha="right")
    plt.tight_layout()
    plt.savefig(os.path.join(paths.reports_dir, "gross_profit_by_category.png"), dpi=160)
    plt.close()


def main() -> None:
    run()


if __name__ == "__main__":
    main()
