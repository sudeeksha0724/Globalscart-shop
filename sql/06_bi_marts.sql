DROP MATERIALIZED VIEW IF EXISTS globalcart.mart_exec_daily_kpis;
DROP MATERIALIZED VIEW IF EXISTS globalcart.mart_finance_profitability;
DROP MATERIALIZED VIEW IF EXISTS globalcart.mart_funnel_conversion;
DROP MATERIALIZED VIEW IF EXISTS globalcart.mart_product_performance;
DROP MATERIALIZED VIEW IF EXISTS globalcart.mart_customer_segments;

CREATE MATERIALIZED VIEW globalcart.mart_exec_daily_kpis AS
WITH bounds AS (
  SELECT
    MIN(dt) AS min_dt,
    MAX(dt2) AS max_dt
  FROM (
    SELECT MIN(date(order_ts)) AS dt, MAX(date(order_ts)) AS dt2 FROM globalcart.fact_orders
    UNION ALL
    SELECT MIN(date(event_ts)) AS dt, MAX(date(event_ts)) AS dt2 FROM globalcart.fact_funnel_events
    UNION ALL
    SELECT MIN(date(return_ts)) AS dt, MAX(date(return_ts)) AS dt2 FROM globalcart.fact_returns
    UNION ALL
    SELECT MIN(date(COALESCE(shipped_ts, created_at))) AS dt, MAX(date(COALESCE(shipped_ts, created_at))) AS dt2 FROM globalcart.fact_shipments
  ) x
),
dates AS (
  SELECT d.date_id, d.date_value
  FROM globalcart.dim_date d
  CROSS JOIN bounds b
  WHERE d.date_value BETWEEN b.min_dt AND b.max_dt
),
sales AS (
  SELECT
    order_dt AS dt,
    COUNT(DISTINCT order_id) AS orders,
    COUNT(DISTINCT customer_id) AS active_customers,
    COALESCE(SUM(revenue_ex_tax), 0) AS revenue_ex_tax,
    COALESCE(SUM(cogs), 0) AS cogs,
    COALESCE(SUM(gross_profit_ex_tax), 0) AS gross_profit_ex_tax,
    COALESCE(SUM(net_profit_ex_tax), 0) AS net_profit_ex_tax,
    COALESCE(SUM(discount_amount), 0) AS discount_amount,
    COALESCE(SUM(shipping_cost), 0) AS shipping_cost_attrib,
    COALESCE(SUM(gateway_fee_amount), 0) AS gateway_fee_amount,
    COALESCE(SUM(refund_amount), 0) AS refund_amount_order_attrib
  FROM globalcart.vw_finance_order_pnl
  GROUP BY 1
),
refunds AS (
  SELECT
    date(return_ts) AS dt,
    COUNT(*) AS return_lines,
    COALESCE(SUM(refund_amount), 0) AS refund_amount_return_dt
  FROM globalcart.fact_returns
  GROUP BY 1
),
ship AS (
  SELECT
    date(COALESCE(shipped_ts, created_at)) AS dt,
    COUNT(*) AS shipments,
    COUNT(*) FILTER (WHERE sla_breached_flag) AS sla_breaches,
    COALESCE(SUM(shipping_cost), 0) AS shipping_cost_actual
  FROM globalcart.fact_shipments
  GROUP BY 1
),
funnel AS (
  SELECT
    event_dt AS dt,
    COALESCE(product_views, 0) AS product_views,
    COALESCE(add_to_cart, 0) AS add_to_cart,
    COALESCE(checkout_started, 0) AS checkout_started,
    COALESCE(payment_attempts, 0) AS payment_attempts,
    COALESCE(orders_placed, 0) AS orders_placed,
    COALESCE(conversion_rate, 0) AS conversion_rate,
    COALESCE(cart_abandonment_rate, 0) AS cart_abandonment_rate,
    COALESCE(payment_failure_rate, 0) AS payment_failure_rate
  FROM globalcart.vw_funnel_daily_metrics
)
SELECT
  md5(d.date_id::text) AS exec_daily_sk,
  d.date_id,
  d.date_value AS kpi_dt,
  COALESCE(s.orders, 0) AS orders,
  COALESCE(s.active_customers, 0) AS active_customers,
  COALESCE(s.revenue_ex_tax, 0) AS revenue_ex_tax,
  COALESCE(s.cogs, 0) AS cogs,
  COALESCE(s.gross_profit_ex_tax, 0) AS gross_profit_ex_tax,
  COALESCE(s.net_profit_ex_tax, 0) AS net_profit_ex_tax,
  CASE WHEN COALESCE(s.revenue_ex_tax, 0) > 0
    THEN ROUND(100.0 * COALESCE(s.gross_profit_ex_tax, 0) / NULLIF(COALESCE(s.revenue_ex_tax, 0), 0), 4)
    ELSE 0 END AS gross_margin_pct,
  CASE WHEN COALESCE(s.revenue_ex_tax, 0) > 0
    THEN ROUND(100.0 * COALESCE(s.net_profit_ex_tax, 0) / NULLIF(COALESCE(s.revenue_ex_tax, 0), 0), 4)
    ELSE 0 END AS net_margin_pct,
  CASE WHEN COALESCE(s.orders, 0) > 0
    THEN ROUND(1.0 * COALESCE(s.revenue_ex_tax, 0) / NULLIF(COALESCE(s.orders, 0), 0), 2)
    ELSE 0 END AS aov_ex_tax,
  COALESCE(s.discount_amount, 0) AS discount_amount,
  COALESCE(s.shipping_cost_attrib, 0) AS shipping_cost_attrib,
  COALESCE(s.gateway_fee_amount, 0) AS gateway_fee_amount,
  COALESCE(s.refund_amount_order_attrib, 0) AS refund_amount_order_attrib,
  COALESCE(r.return_lines, 0) AS return_lines,
  COALESCE(r.refund_amount_return_dt, 0) AS refund_amount_return_dt,
  COALESCE(sh.shipments, 0) AS shipments,
  CASE WHEN COALESCE(sh.shipments, 0) > 0
    THEN ROUND(100.0 * COALESCE(sh.sla_breaches, 0) / NULLIF(COALESCE(sh.shipments, 0), 0), 4)
    ELSE 0 END AS sla_breach_pct,
  COALESCE(f.product_views, 0) AS funnel_product_views,
  COALESCE(f.add_to_cart, 0) AS funnel_add_to_cart,
  COALESCE(f.checkout_started, 0) AS funnel_checkout_started,
  COALESCE(f.payment_attempts, 0) AS funnel_payment_attempts,
  COALESCE(f.orders_placed, 0) AS funnel_orders_placed,
  COALESCE(f.conversion_rate, 0) AS funnel_conversion_rate,
  COALESCE(f.cart_abandonment_rate, 0) AS funnel_cart_abandonment_rate,
  COALESCE(f.payment_failure_rate, 0) AS funnel_payment_failure_rate
FROM dates d
LEFT JOIN sales s ON s.dt = d.date_value
LEFT JOIN refunds r ON r.dt = d.date_value
LEFT JOIN ship sh ON sh.dt = d.date_value
LEFT JOIN funnel f ON f.dt = d.date_value;

CREATE UNIQUE INDEX IF NOT EXISTS ux_mart_exec_daily_kpis_date_id ON globalcart.mart_exec_daily_kpis(date_id);

CREATE MATERIALIZED VIEW globalcart.mart_finance_profitability AS
SELECT
  md5(o.order_id::text) AS finance_order_sk,
  dd.date_id,
  o.order_dt,
  o.order_id,
  o.customer_id,
  o.geo_id,
  o.channel,
  o.currency,
  o.revenue_ex_tax,
  o.discount_amount,
  o.tax_amount,
  o.cogs,
  o.shipping_cost,
  o.gateway_fee_amount,
  o.refund_amount,
  o.gross_profit_ex_tax,
  o.net_profit_ex_tax,
  o.gross_margin_pct,
  o.net_margin_pct,
  o.sla_breached_flag,
  o.has_return_flag,
  o.discount_heavy_flag,
  o.loss_order_flag
FROM globalcart.vw_finance_order_pnl o
JOIN globalcart.dim_date dd ON dd.date_value = o.order_dt;

CREATE UNIQUE INDEX IF NOT EXISTS ux_mart_finance_profitability_order_id ON globalcart.mart_finance_profitability(order_id);
CREATE INDEX IF NOT EXISTS ix_mart_finance_profitability_date_id ON globalcart.mart_finance_profitability(date_id);
CREATE INDEX IF NOT EXISTS ix_mart_finance_profitability_customer_id ON globalcart.mart_finance_profitability(customer_id);

CREATE MATERIALIZED VIEW globalcart.mart_funnel_conversion AS
WITH session_flags AS (
  SELECT
    date(event_ts) AS event_dt,
    COALESCE(channel, 'WEB') AS channel,
    COALESCE(device, 'DESKTOP') AS device,
    session_id,
    BOOL_OR(stage = 'VIEW_PRODUCT') AS viewed,
    BOOL_OR(stage = 'ADD_TO_CART') AS added,
    BOOL_OR(stage = 'CHECKOUT_STARTED') AS checkout,
    BOOL_OR(stage = 'PAYMENT_ATTEMPTED') AS pay_attempt,
    BOOL_OR(stage = 'PAYMENT_FAILED') AS pay_failed,
    BOOL_OR(stage = 'ORDER_PLACED') AS ordered
  FROM globalcart.fact_funnel_events
  GROUP BY 1,2,3,4
),
agg AS (
  SELECT
    event_dt,
    channel,
    device,
    COUNT(*) FILTER (WHERE viewed) AS product_views,
    COUNT(*) FILTER (WHERE added) AS add_to_cart,
    COUNT(*) FILTER (WHERE checkout) AS checkout_started,
    COUNT(*) FILTER (WHERE pay_attempt) AS payment_attempts,
    COUNT(*) FILTER (WHERE ordered) AS orders_placed,
    CASE WHEN COUNT(*) FILTER (WHERE viewed) > 0
      THEN ROUND(1.0 * COUNT(*) FILTER (WHERE ordered) / NULLIF(COUNT(*) FILTER (WHERE viewed), 0), 4)
      ELSE 0 END AS conversion_rate,
    CASE WHEN COUNT(*) FILTER (WHERE added) > 0
      THEN ROUND(1.0 * (COUNT(*) FILTER (WHERE added) - COUNT(*) FILTER (WHERE checkout)) / NULLIF(COUNT(*) FILTER (WHERE added), 0), 4)
      ELSE 0 END AS cart_abandonment_rate,
    CASE WHEN COUNT(*) FILTER (WHERE pay_attempt) > 0
      THEN ROUND(1.0 * COUNT(*) FILTER (WHERE pay_failed) / NULLIF(COUNT(*) FILTER (WHERE pay_attempt), 0), 4)
      ELSE 0 END AS payment_failure_rate
  FROM session_flags
  GROUP BY 1,2,3
)
SELECT
  md5(concat_ws('|', dd.date_id::text, a.channel, a.device)) AS funnel_conv_sk,
  dd.date_id,
  a.event_dt,
  a.channel,
  a.device,
  a.product_views,
  a.add_to_cart,
  a.checkout_started,
  a.payment_attempts,
  a.orders_placed,
  a.conversion_rate,
  a.cart_abandonment_rate,
  a.payment_failure_rate
FROM agg a
JOIN globalcart.dim_date dd ON dd.date_value = a.event_dt;

CREATE UNIQUE INDEX IF NOT EXISTS ux_mart_funnel_conversion_key ON globalcart.mart_funnel_conversion(date_id, channel, device);
CREATE INDEX IF NOT EXISTS ix_mart_funnel_conversion_date_id ON globalcart.mart_funnel_conversion(date_id);

CREATE MATERIALIZED VIEW globalcart.mart_product_performance AS
WITH sell_ratio AS (
  SELECT COALESCE(AVG(unit_sell_price / NULLIF(unit_list_price, 0)), 0.88) AS ratio
  FROM globalcart.fact_order_items
),
sales AS (
  SELECT
    o.order_dt AS dt,
    i.product_id,
    COALESCE(SUM(i.qty), 0) AS units_sold,
    COALESCE(SUM(i.qty * i.unit_sell_price), 0) AS revenue_ex_tax,
    COALESCE(SUM(i.qty * i.unit_cost), 0) AS cogs,
    COALESCE(SUM(i.line_discount), 0) AS discount_amount,
    COALESCE(SUM((i.qty * i.unit_sell_price) - (i.qty * i.unit_cost)), 0) AS gross_profit_ex_tax
  FROM globalcart.fact_order_items i
  JOIN globalcart.vw_orders_completed o ON o.order_id = i.order_id
  GROUP BY 1,2
),
returns AS (
  SELECT
    date(r.return_ts) AS dt,
    r.product_id,
    COUNT(*) AS return_lines,
    COALESCE(SUM(r.refund_amount), 0) AS refund_amount
  FROM globalcart.fact_returns r
  GROUP BY 1,2
),
per_session_product_add AS (
  SELECT
    session_id,
    product_id,
    MIN(date(event_ts)) AS dt
  FROM globalcart.fact_funnel_events
  WHERE stage = 'ADD_TO_CART' AND product_id IS NOT NULL
  GROUP BY 1,2
),
session_outcome AS (
  SELECT
    session_id,
    BOOL_OR(stage = 'ORDER_PLACED') AS ordered
  FROM globalcart.fact_funnel_events
  GROUP BY 1
),
abandon AS (
  SELECT
    a.dt,
    a.product_id,
    COUNT(*) AS add_sessions,
    COUNT(*) FILTER (WHERE NOT COALESCE(o.ordered, FALSE)) AS abandoned_add_sessions,
    COALESCE(SUM(CASE WHEN NOT COALESCE(o.ordered, FALSE) THEN dp.list_price * sr.ratio ELSE 0 END), 0) AS revenue_lost_cart_abandonment
  FROM per_session_product_add a
  JOIN session_outcome o ON o.session_id = a.session_id
  JOIN globalcart.dim_product dp ON dp.product_id = a.product_id
  CROSS JOIN sell_ratio sr
  GROUP BY 1,2
),
failed_orders AS (
  SELECT
    order_id,
    MIN(date(event_ts)) AS dt
  FROM globalcart.fact_funnel_events
  WHERE stage = 'PAYMENT_FAILED' AND order_id IS NOT NULL
  GROUP BY 1
),
pay_fail AS (
  SELECT
    fo.dt,
    i.product_id,
    COUNT(DISTINCT i.order_id) AS failed_orders,
    COALESCE(SUM(i.qty * i.unit_sell_price), 0) AS revenue_at_risk_ex_tax
  FROM failed_orders fo
  JOIN globalcart.fact_order_items i ON i.order_id = fo.order_id
  GROUP BY 1,2
),
keys AS (
  SELECT dt, product_id FROM sales
  UNION
  SELECT dt, product_id FROM returns
  UNION
  SELECT dt, product_id FROM abandon
  UNION
  SELECT dt, product_id FROM pay_fail
)
SELECT
  md5(concat_ws('|', dd.date_id::text, k.product_id::text)) AS product_perf_sk,
  dd.date_id,
  k.dt,
  k.product_id,
  dp.category_l1,
  dp.category_l2,
  dp.brand,
  COALESCE(s.units_sold, 0) AS units_sold,
  COALESCE(s.revenue_ex_tax, 0) AS revenue_ex_tax,
  COALESCE(s.cogs, 0) AS cogs,
  COALESCE(s.gross_profit_ex_tax, 0) AS gross_profit_ex_tax,
  COALESCE(s.discount_amount, 0) AS discount_amount,
  COALESCE(r.return_lines, 0) AS return_lines,
  COALESCE(r.refund_amount, 0) AS refund_amount,
  COALESCE(a.add_sessions, 0) AS add_sessions,
  COALESCE(a.abandoned_add_sessions, 0) AS abandoned_add_sessions,
  COALESCE(a.revenue_lost_cart_abandonment, 0) AS revenue_lost_cart_abandonment,
  COALESCE(pf.failed_orders, 0) AS failed_orders,
  COALESCE(pf.revenue_at_risk_ex_tax, 0) AS revenue_at_risk_ex_tax
FROM keys k
JOIN globalcart.dim_date dd ON dd.date_value = k.dt
JOIN globalcart.dim_product dp ON dp.product_id = k.product_id
LEFT JOIN sales s ON s.dt = k.dt AND s.product_id = k.product_id
LEFT JOIN returns r ON r.dt = k.dt AND r.product_id = k.product_id
LEFT JOIN abandon a ON a.dt = k.dt AND a.product_id = k.product_id
LEFT JOIN pay_fail pf ON pf.dt = k.dt AND pf.product_id = k.product_id;

CREATE UNIQUE INDEX IF NOT EXISTS ux_mart_product_performance_key ON globalcart.mart_product_performance(date_id, product_id);
CREATE INDEX IF NOT EXISTS ix_mart_product_performance_date_id ON globalcart.mart_product_performance(date_id);
CREATE INDEX IF NOT EXISTS ix_mart_product_performance_category ON globalcart.mart_product_performance(category_l1, category_l2);

CREATE MATERIALIZED VIEW globalcart.mart_customer_segments AS
WITH cust_orders AS (
  SELECT
    customer_id,
    MIN(order_dt) AS first_order_dt,
    MAX(order_dt) AS last_order_dt,
    COUNT(DISTINCT order_id) AS orders,
    COALESCE(SUM(revenue_ex_tax), 0) AS revenue_ex_tax,
    COALESCE(SUM(gross_profit_ex_tax), 0) AS gross_profit_ex_tax,
    COALESCE(SUM(net_profit_ex_tax), 0) AS net_profit_ex_tax,
    COALESCE(SUM(refund_amount), 0) AS refund_amount,
    COALESCE(SUM(shipping_cost), 0) AS shipping_cost,
    COALESCE(SUM(gateway_fee_amount), 0) AS gateway_fee_amount
  FROM globalcart.vw_finance_order_pnl
  GROUP BY 1
),
ranked AS (
  SELECT
    c.customer_id,
    c.geo_id,
    c.acquisition_channel,
    date(c.customer_created_ts) AS customer_created_dt,
    co.first_order_dt,
    co.last_order_dt,
    COALESCE(co.orders, 0) AS orders,
    COALESCE(co.revenue_ex_tax, 0) AS revenue_ex_tax,
    COALESCE(co.gross_profit_ex_tax, 0) AS gross_profit_ex_tax,
    COALESCE(co.net_profit_ex_tax, 0) AS net_profit_ex_tax,
    COALESCE(co.refund_amount, 0) AS refund_amount,
    COALESCE(co.shipping_cost, 0) AS shipping_cost,
    COALESCE(co.gateway_fee_amount, 0) AS gateway_fee_amount,
    CASE WHEN COALESCE(co.orders, 0) >= 2 THEN TRUE ELSE FALSE END AS repeat_customer_flag,
    CASE WHEN COALESCE(co.orders, 0) > 0 THEN ROUND(1.0 * COALESCE(co.revenue_ex_tax, 0) / NULLIF(COALESCE(co.orders, 0), 0), 2) ELSE 0 END AS aov_ex_tax,
    NTILE(4) OVER (ORDER BY COALESCE(co.revenue_ex_tax, 0) DESC) AS value_quartile
  FROM globalcart.dim_customer c
  LEFT JOIN cust_orders co ON co.customer_id = c.customer_id
)
SELECT
  md5(r.customer_id::text) AS customer_segment_sk,
  r.customer_id,
  r.geo_id,
  g.region,
  g.country,
  g.city,
  r.acquisition_channel,
  d_created.date_id AS customer_created_date_id,
  r.customer_created_dt,
  d_first.date_id AS first_order_date_id,
  r.first_order_dt,
  d_last.date_id AS last_order_date_id,
  r.last_order_dt,
  r.orders,
  r.revenue_ex_tax,
  r.gross_profit_ex_tax,
  r.net_profit_ex_tax,
  r.refund_amount,
  r.shipping_cost,
  r.gateway_fee_amount,
  r.aov_ex_tax,
  r.repeat_customer_flag,
  r.value_quartile,
  CASE
    WHEN r.orders = 0 THEN 'PROSPECT'
    WHEN r.orders = 1 THEN 'ONE_TIME'
    WHEN r.orders >= 2 THEN 'REPEAT'
    ELSE 'UNKNOWN' END AS lifecycle_segment
FROM ranked r
JOIN globalcart.dim_geo g ON g.geo_id = r.geo_id
LEFT JOIN globalcart.dim_date d_created ON d_created.date_value = r.customer_created_dt
LEFT JOIN globalcart.dim_date d_first ON d_first.date_value = r.first_order_dt
LEFT JOIN globalcart.dim_date d_last ON d_last.date_value = r.last_order_dt;

CREATE UNIQUE INDEX IF NOT EXISTS ux_mart_customer_segments_customer_id ON globalcart.mart_customer_segments(customer_id);
CREATE INDEX IF NOT EXISTS ix_mart_customer_segments_geo_id ON globalcart.mart_customer_segments(geo_id);

CREATE OR REPLACE FUNCTION globalcart.refresh_bi_marts() RETURNS void AS $$
BEGIN
  REFRESH MATERIALIZED VIEW globalcart.mart_exec_daily_kpis;
  REFRESH MATERIALIZED VIEW globalcart.mart_finance_profitability;
  REFRESH MATERIALIZED VIEW globalcart.mart_funnel_conversion;
  REFRESH MATERIALIZED VIEW globalcart.mart_product_performance;
  REFRESH MATERIALIZED VIEW globalcart.mart_customer_segments;
END;
$$ LANGUAGE plpgsql;
