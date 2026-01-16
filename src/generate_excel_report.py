from __future__ import annotations

import argparse
import os
from pathlib import Path

import pandas as pd

from .config import Paths, PostgresConfig
from .db import get_engine


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def build_excel_report(out_path: Path) -> None:
    cfg = PostgresConfig()
    engine = get_engine(cfg)

    kpi = pd.read_sql(
        """
        SELECT
          COUNT(DISTINCT order_id) AS orders,
          SUM(net_amount) AS net_revenue,
          ROUND(SUM(net_amount) / NULLIF(COUNT(DISTINCT order_id),0), 2) AS aov
        FROM globalcart.vw_orders_completed
        """,
        engine,
    )

    monthly = pd.read_sql(
        """
        SELECT date_trunc('month', order_ts) AS month,
               COUNT(DISTINCT order_id) AS orders,
               SUM(net_amount) AS net_revenue
        FROM globalcart.vw_orders_completed
        GROUP BY 1
        ORDER BY 1
        """,
        engine,
    )

    category_profit = pd.read_sql(
        """
        SELECT category_l1,
               SUM(line_net_revenue) AS revenue,
               SUM(line_cogs) AS cogs,
               SUM(line_gross_profit) AS gross_profit,
               ROUND(100.0 * SUM(line_gross_profit) / NULLIF(SUM(line_net_revenue),0), 2) AS gross_margin_pct
        FROM globalcart.vw_item_profitability
        GROUP BY 1
        ORDER BY gross_profit DESC
        """,
        engine,
    )

    returns = pd.read_sql(
        """
        SELECT category_l1,
               return_reason,
               COUNT(*) AS return_lines,
               SUM(refund_amount) AS refund_amount
        FROM globalcart.vw_returns_enriched
        GROUP BY 1,2
        ORDER BY refund_amount DESC
        """,
        engine,
    )

    sla = pd.read_sql(
        """
        SELECT carrier,
               COUNT(*) AS shipments,
               ROUND(100.0 * AVG(CASE WHEN sla_breached_flag THEN 1 ELSE 0 END), 2) AS sla_breach_pct,
               SUM(shipping_cost) AS shipping_cost
        FROM globalcart.vw_sla
        GROUP BY 1
        ORDER BY sla_breach_pct DESC
        """,
        engine,
    )

    out_path = out_path.resolve()
    _ensure_dir(out_path.parent)

    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        kpi.to_excel(writer, sheet_name="KPI_Summary", index=False)
        monthly.to_excel(writer, sheet_name="Monthly_Trend", index=False)
        category_profit.to_excel(writer, sheet_name="Category_Profit", index=False)
        returns.to_excel(writer, sheet_name="Returns", index=False)
        sla.to_excel(writer, sheet_name="SLA", index=False)


def main() -> None:
    parser = argparse.ArgumentParser()
    default_root = Path(__file__).resolve().parents[1]
    paths = Paths(project_root=str(default_root))

    parser.add_argument(
        "--out",
        default=os.path.join(paths.reports_dir, "globalcart_management_report.xlsx"),
    )
    args = parser.parse_args()

    build_excel_report(Path(args.out))


if __name__ == "__main__":
    main()
