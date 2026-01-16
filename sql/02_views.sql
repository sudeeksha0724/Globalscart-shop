CREATE SCHEMA IF NOT EXISTS globalcart;

CREATE OR REPLACE VIEW globalcart.vw_orders_core AS
SELECT
  o.order_id,
  o.customer_id,
  o.geo_id,
  o.order_ts,
  date(o.order_ts) AS order_dt,
  o.order_status,
  o.channel,
  o.currency,
  o.gross_amount,
  o.discount_amount,
  o.tax_amount,
  o.net_amount
FROM globalcart.fact_orders o;

CREATE OR REPLACE VIEW globalcart.vw_orders_completed AS
SELECT *
FROM globalcart.vw_orders_core
WHERE order_status IN ('PLACED','DELIVERED','COMPLETED','RETURNED');

CREATE OR REPLACE VIEW globalcart.vw_item_profitability AS
SELECT
  i.order_item_id,
  i.order_id,
  i.product_id,
  p.category_l1,
  p.category_l2,
  p.brand,
  i.qty,
  i.unit_sell_price,
  i.unit_cost,
  i.line_discount,
  i.line_tax,
  i.line_net_revenue,
  (i.qty * i.unit_cost) AS line_cogs,
  (i.line_net_revenue - (i.qty * i.unit_cost)) AS line_gross_profit
FROM globalcart.fact_order_items i
JOIN globalcart.dim_product p ON p.product_id = i.product_id;

CREATE OR REPLACE VIEW globalcart.vw_sla AS
SELECT
  s.shipment_id,
  s.order_id,
  s.fc_id,
  fc.fc_name,
  s.carrier,
  s.shipped_ts,
  s.promised_delivery_dt,
  s.delivered_dt,
  s.shipping_cost,
  s.sla_breached_flag
FROM globalcart.fact_shipments s
JOIN globalcart.dim_fc fc ON fc.fc_id = s.fc_id;

CREATE OR REPLACE VIEW globalcart.vw_returns_enriched AS
SELECT
  r.return_id,
  r.order_id,
  r.order_item_id,
  r.product_id,
  p.category_l1,
  p.category_l2,
  r.return_ts,
  date(r.return_ts) AS return_dt,
  r.return_reason,
  r.refund_amount,
  r.return_status,
  r.restocked_flag
FROM globalcart.fact_returns r
JOIN globalcart.dim_product p ON p.product_id = r.product_id;

CREATE OR REPLACE VIEW globalcart.vw_payments_enriched AS
SELECT
  p.payment_id,
  p.order_id,
  p.payment_method,
  p.payment_status,
  p.payment_provider,
  p.amount,
  p.authorized_ts,
  p.captured_ts,
  p.failure_reason,
  p.refund_amount,
  p.chargeback_flag,
  p.gateway_fee_amount
FROM globalcart.fact_payments p;

CREATE OR REPLACE VIEW globalcart.vw_funnel_daily_metrics AS
WITH session_flags AS (
  SELECT
    date(event_ts) AS event_dt,
    session_id,
    BOOL_OR(stage = 'VIEW_PRODUCT') AS viewed,
    BOOL_OR(stage = 'ADD_TO_CART') AS added,
    BOOL_OR(stage = 'CHECKOUT_STARTED') AS checkout,
    BOOL_OR(stage = 'PAYMENT_ATTEMPTED') AS pay_attempt,
    BOOL_OR(stage = 'PAYMENT_FAILED') AS pay_failed,
    BOOL_OR(stage = 'ORDER_PLACED') AS ordered
  FROM globalcart.fact_funnel_events
  GROUP BY 1, 2
)
SELECT
  event_dt,
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
GROUP BY 1;

CREATE OR REPLACE VIEW globalcart.vw_revenue_leakage AS
WITH realized AS (
  SELECT COALESCE(SUM(net_amount - tax_amount), 0) AS net_revenue_ex_tax
  FROM globalcart.vw_orders_completed
),
refunds AS (
  SELECT COALESCE(SUM(refund_amount), 0) AS refunds_leakage
  FROM globalcart.fact_returns
),
failed_orders AS (
  SELECT DISTINCT order_id
  FROM globalcart.fact_funnel_events
  WHERE stage = 'PAYMENT_FAILED' AND order_id IS NOT NULL
),
rev_failures AS (
  SELECT COALESCE(SUM(i.qty * i.unit_sell_price), 0) AS revenue_lost_payment_failures
  FROM globalcart.fact_order_items i
  JOIN failed_orders fo ON fo.order_id = i.order_id
),
sell_ratio AS (
  SELECT COALESCE(AVG(unit_sell_price / NULLIF(unit_list_price,0)), 0.88) AS ratio
  FROM globalcart.fact_order_items
),
abandoned_sessions AS (
  SELECT session_id
  FROM globalcart.fact_funnel_events
  GROUP BY session_id
  HAVING BOOL_OR(stage = 'ADD_TO_CART') AND NOT BOOL_OR(stage = 'ORDER_PLACED')
),
abandoned_products AS (
  SELECT DISTINCT e.session_id, e.product_id
  FROM globalcart.fact_funnel_events e
  JOIN abandoned_sessions s ON s.session_id = e.session_id
  WHERE e.stage = 'ADD_TO_CART' AND e.product_id IS NOT NULL
),
rev_abandon AS (
  SELECT COALESCE(SUM(dp.list_price * sr.ratio), 0) AS revenue_lost_cart_abandonment
  FROM abandoned_products ap
  JOIN globalcart.dim_product dp ON dp.product_id = ap.product_id
  CROSS JOIN sell_ratio sr
)
SELECT
  ra.net_revenue_ex_tax,
  rva.revenue_lost_cart_abandonment,
  rvf.revenue_lost_payment_failures,
  rf.refunds_leakage,
  (
    ra.net_revenue_ex_tax
    - COALESCE(rf.refunds_leakage, 0)
    - COALESCE(rva.revenue_lost_cart_abandonment, 0)
    - COALESCE(rvf.revenue_lost_payment_failures, 0)
  ) AS net_revenue_after_leakage
FROM realized ra
CROSS JOIN rev_abandon rva
CROSS JOIN rev_failures rvf
CROSS JOIN refunds rf;

CREATE OR REPLACE VIEW globalcart.vw_funnel_product_leakage AS
WITH per_session_product AS (
  SELECT
    product_id,
    session_id,
    BOOL_OR(stage = 'VIEW_PRODUCT') AS viewed,
    BOOL_OR(stage = 'ADD_TO_CART') AS added
  FROM globalcart.fact_funnel_events
  WHERE product_id IS NOT NULL
  GROUP BY 1, 2
),
session_outcome AS (
  SELECT
    session_id,
    BOOL_OR(stage = 'ORDER_PLACED') AS ordered
  FROM globalcart.fact_funnel_events
  GROUP BY 1
),
sell_ratio AS (
  SELECT COALESCE(AVG(unit_sell_price / NULLIF(unit_list_price,0)), 0.88) AS ratio
  FROM globalcart.fact_order_items
),
abandonment AS (
  SELECT
    psp.product_id,
    COUNT(*) FILTER (WHERE psp.viewed) AS product_views,
    COUNT(*) FILTER (WHERE psp.added) AS add_to_cart,
    COUNT(*) FILTER (WHERE psp.added AND NOT so.ordered) AS abandoned_adds,
    COALESCE(SUM(CASE WHEN psp.added AND NOT so.ordered THEN dp.list_price * sr.ratio ELSE 0 END), 0) AS revenue_lost_cart_abandonment
  FROM per_session_product psp
  JOIN session_outcome so ON so.session_id = psp.session_id
  JOIN globalcart.dim_product dp ON dp.product_id = psp.product_id
  CROSS JOIN sell_ratio sr
  GROUP BY 1
),
failed_orders AS (
  SELECT DISTINCT order_id
  FROM globalcart.fact_funnel_events
  WHERE stage = 'PAYMENT_FAILED' AND order_id IS NOT NULL
),
failed_order_items AS (
  SELECT
    i.product_id,
    COUNT(DISTINCT i.order_id) AS failed_orders,
    COALESCE(SUM(i.qty * i.unit_sell_price), 0) AS revenue_lost_payment_failures
  FROM globalcart.fact_order_items i
  JOIN failed_orders fo ON fo.order_id = i.order_id
  GROUP BY 1
)
SELECT
  a.product_id,
  dp.product_name,
  a.product_views,
  a.add_to_cart,
  a.abandoned_adds,
  ROUND(a.revenue_lost_cart_abandonment, 2) AS revenue_lost_cart_abandonment,
  COALESCE(foi.failed_orders, 0) AS failed_orders,
  COALESCE(foi.revenue_lost_payment_failures, 0) AS revenue_lost_payment_failures
FROM abandonment a
JOIN globalcart.dim_product dp ON dp.product_id = a.product_id
LEFT JOIN failed_order_items foi ON foi.product_id = a.product_id;

CREATE OR REPLACE VIEW globalcart.vw_funnel_payment_failures AS
SELECT
  date(COALESCE(p.authorized_ts, p.created_at)) AS event_dt,
  p.payment_method,
  p.payment_provider,
  p.failure_reason,
  COUNT(*) AS failed_payments,
  COALESCE(SUM(p.amount), 0) AS amount_attempted,
  COALESCE(SUM(i.qty * i.unit_sell_price), 0) AS revenue_at_risk_ex_tax
FROM globalcart.fact_payments p
LEFT JOIN globalcart.fact_order_items i ON i.order_id = p.order_id
WHERE p.payment_status IN ('FAILED','DECLINED')
GROUP BY 1,2,3,4;

CREATE OR REPLACE VIEW globalcart.vw_finance_order_pnl AS
WITH order_items AS (
  SELECT
    i.order_id,
    SUM(i.qty * i.unit_sell_price) AS item_revenue_ex_tax,
    SUM(i.qty * i.unit_cost) AS item_cogs,
    SUM(i.line_discount) AS discount_amount,
    SUM(i.line_tax) AS tax_amount
  FROM globalcart.fact_order_items i
  GROUP BY 1
),
ship AS (
  SELECT order_id, SUM(shipping_cost) AS shipping_cost
  FROM globalcart.fact_shipments
  GROUP BY 1
),
pay AS (
  SELECT
    order_id,
    SUM(CASE WHEN payment_status NOT IN ('FAILED','DECLINED') THEN gateway_fee_amount ELSE 0 END) AS gateway_fee_amount,
    SUM(CASE WHEN payment_status IN ('FAILED','DECLINED') THEN 1 ELSE 0 END) AS payment_failures
  FROM globalcart.fact_payments
  GROUP BY 1
),
ret AS (
  SELECT order_id, SUM(refund_amount) AS refund_amount
  FROM globalcart.fact_returns
  GROUP BY 1
),
sla AS (
  SELECT order_id, BOOL_OR(sla_breached_flag) AS sla_breached_flag
  FROM globalcart.fact_shipments
  GROUP BY 1
)
SELECT
  o.order_id,
  o.customer_id,
  o.geo_id,
  o.order_ts,
  date(o.order_ts) AS order_dt,
  o.order_status,
  o.channel,
  o.currency,
  COALESCE(oi.item_revenue_ex_tax, 0) AS revenue_ex_tax,
  COALESCE(oi.discount_amount, 0) AS discount_amount,
  COALESCE(oi.tax_amount, 0) AS tax_amount,
  COALESCE(oi.item_cogs, 0) AS cogs,
  COALESCE(s.shipping_cost, 0) AS shipping_cost,
  COALESCE(p.gateway_fee_amount, 0) AS gateway_fee_amount,
  COALESCE(r.refund_amount, 0) AS refund_amount,
  (COALESCE(oi.item_revenue_ex_tax, 0) - COALESCE(oi.item_cogs, 0)) AS gross_profit_ex_tax,
  (
    (COALESCE(oi.item_revenue_ex_tax, 0) - COALESCE(oi.item_cogs, 0))
    - COALESCE(s.shipping_cost, 0)
    - COALESCE(p.gateway_fee_amount, 0)
    - COALESCE(r.refund_amount, 0)
  ) AS net_profit_ex_tax,
  CASE WHEN COALESCE(oi.item_revenue_ex_tax, 0) > 0
    THEN ROUND(100.0 * (COALESCE(oi.item_revenue_ex_tax, 0) - COALESCE(oi.item_cogs, 0)) / NULLIF(COALESCE(oi.item_revenue_ex_tax, 0), 0), 4)
    ELSE 0 END AS gross_margin_pct,
  CASE WHEN COALESCE(oi.item_revenue_ex_tax, 0) > 0
    THEN ROUND(100.0 * (
      (COALESCE(oi.item_revenue_ex_tax, 0) - COALESCE(oi.item_cogs, 0))
      - COALESCE(s.shipping_cost, 0)
      - COALESCE(p.gateway_fee_amount, 0)
      - COALESCE(r.refund_amount, 0)
    ) / NULLIF(COALESCE(oi.item_revenue_ex_tax, 0), 0), 4)
    ELSE 0 END AS net_margin_pct,
  COALESCE(sl.sla_breached_flag, FALSE) AS sla_breached_flag,
  CASE WHEN COALESCE(r.refund_amount, 0) > 0 THEN TRUE ELSE FALSE END AS has_return_flag,
  CASE WHEN COALESCE(oi.item_revenue_ex_tax, 0) > 0 AND (COALESCE(oi.discount_amount, 0) / NULLIF(COALESCE(oi.item_revenue_ex_tax, 0) + COALESCE(oi.discount_amount, 0), 0)) > 0.30
    THEN TRUE ELSE FALSE END AS discount_heavy_flag,
  CASE WHEN (
    (COALESCE(oi.item_revenue_ex_tax, 0) - COALESCE(oi.item_cogs, 0))
    - COALESCE(s.shipping_cost, 0)
    - COALESCE(p.gateway_fee_amount, 0)
    - COALESCE(r.refund_amount, 0)
  ) < 0 THEN TRUE ELSE FALSE END AS loss_order_flag
FROM globalcart.vw_orders_completed o
LEFT JOIN order_items oi ON oi.order_id = o.order_id
LEFT JOIN ship s ON s.order_id = o.order_id
LEFT JOIN pay p ON p.order_id = o.order_id
LEFT JOIN ret r ON r.order_id = o.order_id
LEFT JOIN sla sl ON sl.order_id = o.order_id;

CREATE OR REPLACE VIEW globalcart.vw_finance_item_pnl AS
WITH order_totals AS (
  SELECT
    i.order_id,
    SUM(i.qty * i.unit_sell_price) AS order_revenue_ex_tax
  FROM globalcart.fact_order_items i
  GROUP BY 1
),
order_costs AS (
  SELECT
    o.order_id,
    COALESCE(SUM(s.shipping_cost), 0) AS shipping_cost,
    COALESCE(SUM(CASE WHEN p.payment_status NOT IN ('FAILED','DECLINED') THEN p.gateway_fee_amount ELSE 0 END), 0) AS gateway_fee_amount,
    COALESCE(SUM(r.refund_amount), 0) AS refund_amount
  FROM globalcart.vw_orders_completed o
  LEFT JOIN globalcart.fact_shipments s ON s.order_id = o.order_id
  LEFT JOIN globalcart.fact_payments p ON p.order_id = o.order_id
  LEFT JOIN globalcart.fact_returns r ON r.order_id = o.order_id
  GROUP BY 1
)
SELECT
  i.order_item_id,
  i.order_id,
  i.product_id,
  p.category_l1,
  p.category_l2,
  p.brand,
  i.qty,
  i.unit_list_price,
  i.unit_sell_price,
  i.unit_cost,
  i.line_discount,
  i.line_tax,
  (i.qty * i.unit_sell_price) AS line_revenue_ex_tax,
  (i.qty * i.unit_cost) AS line_cogs,
  ((i.qty * i.unit_sell_price) - (i.qty * i.unit_cost)) AS line_gross_profit_ex_tax,
  COALESCE(r.refund_amount, 0) AS line_refund_amount,
  CASE WHEN COALESCE(ot.order_revenue_ex_tax, 0) > 0
    THEN ROUND(COALESCE(oc.shipping_cost, 0) * ((i.qty * i.unit_sell_price) / NULLIF(ot.order_revenue_ex_tax, 0)), 2)
    ELSE 0 END AS alloc_shipping_cost,
  CASE WHEN COALESCE(ot.order_revenue_ex_tax, 0) > 0
    THEN ROUND(COALESCE(oc.gateway_fee_amount, 0) * ((i.qty * i.unit_sell_price) / NULLIF(ot.order_revenue_ex_tax, 0)), 2)
    ELSE 0 END AS alloc_gateway_fee,
  (
    ((i.qty * i.unit_sell_price) - (i.qty * i.unit_cost))
    - (CASE WHEN COALESCE(ot.order_revenue_ex_tax, 0) > 0
        THEN COALESCE(oc.shipping_cost, 0) * ((i.qty * i.unit_sell_price) / NULLIF(ot.order_revenue_ex_tax, 0))
        ELSE 0 END)
    - (CASE WHEN COALESCE(ot.order_revenue_ex_tax, 0) > 0
        THEN COALESCE(oc.gateway_fee_amount, 0) * ((i.qty * i.unit_sell_price) / NULLIF(ot.order_revenue_ex_tax, 0))
        ELSE 0 END)
    - COALESCE(r.refund_amount, 0)
  ) AS line_net_profit_ex_tax,
  CASE WHEN COALESCE(r.refund_amount, 0) > 0 THEN TRUE ELSE FALSE END AS return_leakage_flag,
  CASE WHEN (i.qty * i.unit_sell_price) > 0 AND (i.line_discount / NULLIF((i.qty * i.unit_sell_price) + i.line_discount, 0)) > 0.30
    THEN TRUE ELSE FALSE END AS discount_heavy_flag
FROM globalcart.fact_order_items i
JOIN globalcart.vw_orders_completed o ON o.order_id = i.order_id
JOIN globalcart.dim_product p ON p.product_id = i.product_id
LEFT JOIN globalcart.fact_returns r ON r.order_item_id = i.order_item_id
LEFT JOIN order_totals ot ON ot.order_id = i.order_id
LEFT JOIN order_costs oc ON oc.order_id = i.order_id;

CREATE OR REPLACE VIEW globalcart.vw_finance_product_pnl AS
SELECT
  product_id,
  category_l1,
  category_l2,
  brand,
  SUM(line_revenue_ex_tax) AS revenue_ex_tax,
  SUM(line_cogs) AS cogs,
  SUM(line_gross_profit_ex_tax) AS gross_profit_ex_tax,
  SUM(alloc_shipping_cost) AS shipping_cost,
  SUM(alloc_gateway_fee) AS gateway_fee_amount,
  SUM(line_refund_amount) AS refund_amount,
  SUM(line_net_profit_ex_tax) AS net_profit_ex_tax,
  CASE WHEN SUM(line_revenue_ex_tax) > 0
    THEN ROUND(100.0 * SUM(line_net_profit_ex_tax) / NULLIF(SUM(line_revenue_ex_tax), 0), 4)
    ELSE 0 END AS net_margin_pct,
  CASE WHEN SUM(line_net_profit_ex_tax) < 0 THEN TRUE ELSE FALSE END AS loss_product_flag
FROM globalcart.vw_finance_item_pnl
GROUP BY 1,2,3,4;

CREATE OR REPLACE VIEW globalcart.vw_finance_customer_pnl AS
WITH by_order AS (
  SELECT
    customer_id,
    COUNT(DISTINCT order_id) AS orders,
    SUM(revenue_ex_tax) AS revenue_ex_tax,
    SUM(cogs) AS cogs,
    SUM(shipping_cost) AS shipping_cost,
    SUM(gateway_fee_amount) AS gateway_fee_amount,
    SUM(refund_amount) AS refund_amount,
    SUM(gross_profit_ex_tax) AS gross_profit_ex_tax,
    SUM(net_profit_ex_tax) AS net_profit_ex_tax
  FROM globalcart.vw_finance_order_pnl
  GROUP BY 1
)
SELECT
  b.customer_id,
  c.acquisition_channel,
  g.region,
  g.country,
  b.orders,
  b.revenue_ex_tax,
  b.cogs,
  b.shipping_cost,
  b.gateway_fee_amount,
  b.refund_amount,
  b.gross_profit_ex_tax,
  b.net_profit_ex_tax,
  CASE WHEN b.revenue_ex_tax > 0
    THEN ROUND(100.0 * b.net_profit_ex_tax / NULLIF(b.revenue_ex_tax, 0), 4)
    ELSE 0 END AS net_margin_pct,
  CASE WHEN b.net_profit_ex_tax < 0 THEN TRUE ELSE FALSE END AS loss_customer_flag
FROM by_order b
JOIN globalcart.dim_customer c ON c.customer_id = b.customer_id
JOIN globalcart.dim_geo g ON g.geo_id = c.geo_id;

CREATE OR REPLACE VIEW globalcart.vw_customer_products AS
SELECT
  product_id,
  sku,
  product_name,
  category_l1,
  category_l2,
  brand,
  unit_cost,
  list_price
FROM globalcart.dim_product;

CREATE OR REPLACE VIEW globalcart.vw_customer_customers AS
SELECT
  customer_id,
  geo_id
FROM globalcart.dim_customer;

CREATE OR REPLACE VIEW globalcart.vw_customer_geo AS
SELECT geo_id
FROM globalcart.dim_geo;

CREATE OR REPLACE VIEW globalcart.vw_customer_fc AS
SELECT fc_id
FROM globalcart.dim_fc;

CREATE OR REPLACE VIEW globalcart.vw_customer_orders AS
SELECT
  order_id,
  customer_id,
  order_ts,
  order_status,
  net_amount
FROM globalcart.fact_orders;

CREATE OR REPLACE VIEW globalcart.vw_customer_order_items AS
SELECT
  oi.order_id,
  oi.product_id,
  p.product_name,
  oi.qty
FROM globalcart.fact_order_items oi
JOIN globalcart.dim_product p ON p.product_id = oi.product_id;

CREATE OR REPLACE VIEW globalcart.vw_customer_order_items_core AS
SELECT
  order_item_id,
  order_id
FROM globalcart.fact_order_items;

CREATE OR REPLACE VIEW globalcart.vw_customer_payments AS
SELECT payment_id
FROM globalcart.fact_payments;

CREATE OR REPLACE VIEW globalcart.vw_customer_shipments AS
SELECT shipment_id
FROM globalcart.fact_shipments;

CREATE OR REPLACE VIEW globalcart.vw_customer_shipments_timeline AS
SELECT
  order_id,
  shipped_ts,
  delivered_dt
FROM globalcart.fact_shipments;

CREATE OR REPLACE VIEW globalcart.vw_customer_order_cancellations AS
SELECT
  order_id,
  customer_id,
  reason,
  created_at
FROM globalcart.order_cancellations;

CREATE OR REPLACE VIEW globalcart.vw_admin_order_summary AS
SELECT
  order_id,
  customer_id,
  order_ts,
  order_status,
  net_amount,
  channel
FROM globalcart.fact_orders;

CREATE OR REPLACE VIEW globalcart.vw_admin_kpis AS
SELECT
  snapshot_ts,
  label,
  metric_name,
  metric_value
FROM globalcart.kpi_snapshots;

CREATE OR REPLACE VIEW globalcart.vw_admin_shipments AS
SELECT
  order_id,
  shipped_ts,
  delivered_dt
FROM globalcart.fact_shipments;

CREATE OR REPLACE VIEW globalcart.vw_admin_order_cancellations AS
SELECT
  order_id,
  customer_id,
  reason,
  created_at
FROM globalcart.order_cancellations;
