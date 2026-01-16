from __future__ import annotations

import argparse
import os
from pathlib import Path

import pandas as pd

from .config import PostgresConfig
from .db import get_engine


EXPORTS: dict[str, str] = {
    "monthly_revenue": """
      SELECT date_trunc('month', order_ts) AS month,
             COUNT(DISTINCT order_id) AS orders,
             SUM(net_amount) AS net_revenue
      FROM globalcart.vw_orders_completed
      GROUP BY 1
      ORDER BY 1
    """,
    "category_profit": """
      SELECT category_l1,
             SUM(line_net_revenue) AS revenue,
             SUM(line_cogs) AS cogs,
             SUM(line_gross_profit) AS gross_profit,
             ROUND(100.0 * SUM(line_gross_profit) / NULLIF(SUM(line_net_revenue),0), 2) AS gross_margin_pct
      FROM globalcart.vw_item_profitability
      GROUP BY 1
      ORDER BY gross_profit DESC
    """,
    "carrier_sla": """
      SELECT carrier,
             COUNT(*) AS shipments,
             ROUND(100.0 * AVG(CASE WHEN sla_breached_flag THEN 1 ELSE 0 END), 2) AS sla_breach_pct,
             SUM(shipping_cost) AS shipping_cost
      FROM globalcart.vw_sla
      GROUP BY 1
      ORDER BY sla_breach_pct DESC
    """,
    "returns_by_reason": """
      SELECT category_l1,
             return_reason,
             COUNT(*) AS return_lines,
             SUM(refund_amount) AS refund_amount
      FROM globalcart.vw_returns_enriched
      GROUP BY 1,2
      ORDER BY refund_amount DESC
    """,
    "payment_failures": """
      SELECT payment_method,
             COUNT(*) AS total_attempts,
             ROUND(100.0 * AVG(CASE WHEN payment_status IN ('FAILED','DECLINED') THEN 1 ELSE 0 END), 2) AS failure_pct
      FROM globalcart.vw_payments_enriched
      GROUP BY 1
      ORDER BY failure_pct DESC
    """,
}


def export_all(out_dir: Path) -> None:
    cfg = PostgresConfig()
    engine = get_engine(cfg)

    out_dir.mkdir(parents=True, exist_ok=True)

    for name, sql in EXPORTS.items():
        df = pd.read_sql(sql, engine)
        df.to_csv(out_dir / f"{name}.csv", index=False)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out-dir",
        default=str(Path(__file__).resolve().parents[1] / "reports" / "kpi_exports"),
    )
    args = parser.parse_args()

    export_all(Path(args.out_dir))


if __name__ == "__main__":
    main()
