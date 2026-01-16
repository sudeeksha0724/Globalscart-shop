-- KPI before/after comparison helper
-- Usage:
-- 1) SELECT globalcart.snapshot_kpis('before');
-- 2) run incremental refresh
-- 3) SELECT globalcart.snapshot_kpis('after');
-- 4) run this query to compare latest before vs after

WITH snaps AS (
  SELECT label, snapshot_ts,
         MAX(CASE WHEN metric_name = 'net_revenue_total' THEN metric_value END) AS net_revenue_total,
         MAX(CASE WHEN metric_name = 'orders_total' THEN metric_value END) AS orders_total,
         MAX(CASE WHEN metric_name = 'refund_amount_total' THEN metric_value END) AS refund_amount_total,
         MAX(CASE WHEN metric_name = 'shipping_cost_total' THEN metric_value END) AS shipping_cost_total
  FROM globalcart.kpi_snapshots
  GROUP BY 1,2
),
latest AS (
  SELECT * FROM snaps
  WHERE label IN ('before','after')
),
picked AS (
  SELECT
    (SELECT snapshot_ts FROM latest WHERE label='before' ORDER BY snapshot_ts DESC LIMIT 1) AS before_ts,
    (SELECT snapshot_ts FROM latest WHERE label='after' ORDER BY snapshot_ts DESC LIMIT 1) AS after_ts
)
SELECT
  b.snapshot_ts AS before_snapshot_ts,
  a.snapshot_ts AS after_snapshot_ts,
  b.net_revenue_total AS before_net_revenue_total,
  a.net_revenue_total AS after_net_revenue_total,
  (a.net_revenue_total - b.net_revenue_total) AS delta_net_revenue,
  b.orders_total AS before_orders_total,
  a.orders_total AS after_orders_total,
  (a.orders_total - b.orders_total) AS delta_orders,
  b.refund_amount_total AS before_refunds_total,
  a.refund_amount_total AS after_refunds_total,
  (a.refund_amount_total - b.refund_amount_total) AS delta_refunds,
  b.shipping_cost_total AS before_shipping_cost_total,
  a.shipping_cost_total AS after_shipping_cost_total,
  (a.shipping_cost_total - b.shipping_cost_total) AS delta_shipping_cost
FROM picked p
JOIN latest b ON b.label='before' AND b.snapshot_ts = p.before_ts
JOIN latest a ON a.label='after' AND a.snapshot_ts = p.after_ts;
