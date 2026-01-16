CREATE SCHEMA IF NOT EXISTS globalcart;

CREATE TABLE IF NOT EXISTS globalcart.etl_watermarks (
  source_name VARCHAR(80) PRIMARY KEY,
  last_processed_ts TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS globalcart.kpi_snapshots (
  snapshot_id BIGSERIAL PRIMARY KEY,
  snapshot_ts TIMESTAMP NOT NULL,
  label VARCHAR(40) NOT NULL,
  metric_name VARCHAR(80) NOT NULL,
  metric_value NUMERIC(20,4) NOT NULL
);

CREATE TABLE IF NOT EXISTS globalcart.stg_fact_orders (LIKE globalcart.fact_orders INCLUDING DEFAULTS);
CREATE TABLE IF NOT EXISTS globalcart.stg_fact_order_items (LIKE globalcart.fact_order_items INCLUDING DEFAULTS);
CREATE TABLE IF NOT EXISTS globalcart.stg_fact_payments (LIKE globalcart.fact_payments INCLUDING DEFAULTS);
CREATE TABLE IF NOT EXISTS globalcart.stg_fact_shipments (LIKE globalcart.fact_shipments INCLUDING DEFAULTS);
CREATE TABLE IF NOT EXISTS globalcart.stg_fact_returns (LIKE globalcart.fact_returns INCLUDING DEFAULTS);
CREATE TABLE IF NOT EXISTS globalcart.stg_fact_funnel_events (LIKE globalcart.fact_funnel_events INCLUDING DEFAULTS);

CREATE TABLE IF NOT EXISTS globalcart.stg_dim_customer (LIKE globalcart.dim_customer INCLUDING DEFAULTS);
CREATE TABLE IF NOT EXISTS globalcart.stg_dim_product (LIKE globalcart.dim_product INCLUDING DEFAULTS);

ALTER TABLE globalcart.stg_fact_orders DROP CONSTRAINT IF EXISTS fact_orders_pkey;
ALTER TABLE globalcart.stg_fact_order_items DROP CONSTRAINT IF EXISTS fact_order_items_pkey;
ALTER TABLE globalcart.stg_fact_payments DROP CONSTRAINT IF EXISTS fact_payments_pkey;
ALTER TABLE globalcart.stg_fact_shipments DROP CONSTRAINT IF EXISTS fact_shipments_pkey;
ALTER TABLE globalcart.stg_fact_returns DROP CONSTRAINT IF EXISTS fact_returns_pkey;
ALTER TABLE globalcart.stg_fact_funnel_events DROP CONSTRAINT IF EXISTS fact_funnel_events_pkey;
ALTER TABLE globalcart.stg_dim_customer DROP CONSTRAINT IF EXISTS dim_customer_pkey;
ALTER TABLE globalcart.stg_dim_product DROP CONSTRAINT IF EXISTS dim_product_pkey;

CREATE TABLE IF NOT EXISTS globalcart.audit_fact_orders (
  audit_id BIGSERIAL PRIMARY KEY,
  audit_ts TIMESTAMP NOT NULL,
  audit_action VARCHAR(20) NOT NULL,
  LIKE globalcart.fact_orders INCLUDING DEFAULTS
);

CREATE TABLE IF NOT EXISTS globalcart.audit_fact_payments (
  audit_id BIGSERIAL PRIMARY KEY,
  audit_ts TIMESTAMP NOT NULL,
  audit_action VARCHAR(20) NOT NULL,
  LIKE globalcart.fact_payments INCLUDING DEFAULTS
);

ALTER TABLE globalcart.stg_fact_payments ADD COLUMN IF NOT EXISTS gateway_fee_amount NUMERIC(14,2) NOT NULL DEFAULT 0;
ALTER TABLE globalcart.audit_fact_payments ADD COLUMN IF NOT EXISTS gateway_fee_amount NUMERIC(14,2) NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS globalcart.audit_fact_shipments (
  audit_id BIGSERIAL PRIMARY KEY,
  audit_ts TIMESTAMP NOT NULL,
  audit_action VARCHAR(20) NOT NULL,
  LIKE globalcart.fact_shipments INCLUDING DEFAULTS
);

CREATE TABLE IF NOT EXISTS globalcart.audit_fact_returns (
  audit_id BIGSERIAL PRIMARY KEY,
  audit_ts TIMESTAMP NOT NULL,
  audit_action VARCHAR(20) NOT NULL,
  LIKE globalcart.fact_returns INCLUDING DEFAULTS
);

CREATE OR REPLACE FUNCTION globalcart.set_watermark(p_source_name VARCHAR, p_ts TIMESTAMP)
RETURNS VOID
LANGUAGE sql
AS $$
INSERT INTO globalcart.etl_watermarks(source_name, last_processed_ts)
VALUES (p_source_name, p_ts)
ON CONFLICT (source_name) DO UPDATE
SET last_processed_ts = EXCLUDED.last_processed_ts;
$$;

CREATE OR REPLACE FUNCTION globalcart.get_watermark(p_source_name VARCHAR)
RETURNS TIMESTAMP
LANGUAGE sql
AS $$
SELECT last_processed_ts
FROM globalcart.etl_watermarks
WHERE source_name = p_source_name;
$$;

CREATE OR REPLACE FUNCTION globalcart.snapshot_kpis(p_label VARCHAR)
RETURNS VOID
LANGUAGE plpgsql
AS $$
DECLARE
  snap_ts TIMESTAMP := NOW();
  v_net_rev NUMERIC(20,4);
  v_orders NUMERIC(20,4);
  v_refunds NUMERIC(20,4);
  v_shipping NUMERIC(20,4);
  v_cogs NUMERIC(20,4);
  v_gateway NUMERIC(20,4);
  v_gross_profit NUMERIC(20,4);
  v_net_profit NUMERIC(20,4);
  v_gross_margin_pct NUMERIC(20,4);
  v_net_margin_pct NUMERIC(20,4);
  v_loss_orders NUMERIC(20,4);

  v_sessions_view NUMERIC(20,4);
  v_sessions_add NUMERIC(20,4);
  v_sessions_checkout NUMERIC(20,4);
  v_sessions_pay_attempt NUMERIC(20,4);
  v_sessions_pay_failed NUMERIC(20,4);
  v_sessions_order NUMERIC(20,4);
  v_conversion_rate NUMERIC(20,4);
  v_cart_abandon_rate NUMERIC(20,4);
  v_payment_failure_rate NUMERIC(20,4);
  v_rev_lost_failures NUMERIC(20,4);
  v_rev_lost_abandon NUMERIC(20,4);
BEGIN
  SELECT COALESCE(SUM(net_amount - tax_amount),0), COALESCE(COUNT(DISTINCT order_id),0)
  INTO v_net_rev, v_orders
  FROM globalcart.vw_orders_completed;

  SELECT COALESCE(SUM(refund_amount),0)
  INTO v_refunds
  FROM globalcart.fact_returns;

  SELECT COALESCE(SUM(shipping_cost),0)
  INTO v_shipping
  FROM globalcart.fact_shipments;

  SELECT COALESCE(SUM(i.qty * i.unit_cost), 0)
  INTO v_cogs
  FROM globalcart.fact_order_items i
  JOIN globalcart.vw_orders_completed o ON o.order_id = i.order_id;

  SELECT COALESCE(SUM(p.gateway_fee_amount), 0)
  INTO v_gateway
  FROM globalcart.fact_payments p
  JOIN globalcart.vw_orders_completed o ON o.order_id = p.order_id
  WHERE p.payment_status NOT IN ('FAILED','DECLINED');

  v_gross_profit := COALESCE(v_net_rev,0) - COALESCE(v_cogs,0);
  v_net_profit := COALESCE(v_gross_profit,0) - COALESCE(v_shipping,0) - COALESCE(v_gateway,0) - COALESCE(v_refunds,0);
  v_gross_margin_pct := ROUND(100.0 * COALESCE(v_gross_profit,0) / NULLIF(COALESCE(v_net_rev,0),0), 4);
  v_net_margin_pct := ROUND(100.0 * COALESCE(v_net_profit,0) / NULLIF(COALESCE(v_net_rev,0),0), 4);

  SELECT COALESCE(COUNT(*),0)
  INTO v_loss_orders
  FROM globalcart.vw_finance_order_pnl
  WHERE net_profit_ex_tax < 0;

  v_sessions_view := 0;
  v_sessions_add := 0;
  v_sessions_checkout := 0;
  v_sessions_pay_attempt := 0;
  v_sessions_pay_failed := 0;
  v_sessions_order := 0;
  v_conversion_rate := 0;
  v_cart_abandon_rate := 0;
  v_payment_failure_rate := 0;
  v_rev_lost_failures := 0;
  v_rev_lost_abandon := 0;

  IF to_regclass('globalcart.fact_funnel_events') IS NOT NULL THEN
    SELECT
      COALESCE(COUNT(DISTINCT session_id) FILTER (WHERE stage = 'VIEW_PRODUCT'), 0),
      COALESCE(COUNT(DISTINCT session_id) FILTER (WHERE stage = 'ADD_TO_CART'), 0),
      COALESCE(COUNT(DISTINCT session_id) FILTER (WHERE stage = 'CHECKOUT_STARTED'), 0),
      COALESCE(COUNT(DISTINCT session_id) FILTER (WHERE stage = 'PAYMENT_ATTEMPTED'), 0),
      COALESCE(COUNT(DISTINCT session_id) FILTER (WHERE stage = 'PAYMENT_FAILED'), 0),
      COALESCE(COUNT(DISTINCT session_id) FILTER (WHERE stage = 'ORDER_PLACED'), 0)
    INTO v_sessions_view, v_sessions_add, v_sessions_checkout, v_sessions_pay_attempt, v_sessions_pay_failed, v_sessions_order
    FROM globalcart.fact_funnel_events;

    v_conversion_rate := ROUND(COALESCE(v_sessions_order,0) / NULLIF(COALESCE(v_sessions_view,0),0), 4);
    v_cart_abandon_rate := ROUND((COALESCE(v_sessions_add,0) - COALESCE(v_sessions_checkout,0)) / NULLIF(COALESCE(v_sessions_add,0),0), 4);
    v_payment_failure_rate := ROUND(COALESCE(v_sessions_pay_failed,0) / NULLIF(COALESCE(v_sessions_pay_attempt,0),0), 4);

    WITH failed_orders AS (
      SELECT DISTINCT order_id
      FROM globalcart.fact_funnel_events
      WHERE stage = 'PAYMENT_FAILED' AND order_id IS NOT NULL
    )
    SELECT COALESCE(SUM(i.qty * i.unit_sell_price), 0)
    INTO v_rev_lost_failures
    FROM globalcart.fact_order_items i
    JOIN failed_orders fo ON fo.order_id = i.order_id;

    WITH sell_ratio AS (
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
    )
    SELECT COALESCE(SUM(dp.list_price * sr.ratio), 0)
    INTO v_rev_lost_abandon
    FROM abandoned_products ap
    JOIN globalcart.dim_product dp ON dp.product_id = ap.product_id
    CROSS JOIN sell_ratio sr;
  END IF;

  INSERT INTO globalcart.kpi_snapshots(snapshot_ts, label, metric_name, metric_value)
  VALUES
    (snap_ts, p_label, 'net_revenue_total', v_net_rev),
    (snap_ts, p_label, 'orders_total', v_orders),
    (snap_ts, p_label, 'refund_amount_total', v_refunds),
    (snap_ts, p_label, 'shipping_cost_total', v_shipping),
    (snap_ts, p_label, 'cogs_total', v_cogs),
    (snap_ts, p_label, 'gateway_fee_total', v_gateway),
    (snap_ts, p_label, 'gross_profit_total', v_gross_profit),
    (snap_ts, p_label, 'net_profit_total', v_net_profit),
    (snap_ts, p_label, 'gross_margin_pct', v_gross_margin_pct),
    (snap_ts, p_label, 'net_margin_pct', v_net_margin_pct),
    (snap_ts, p_label, 'loss_orders_total', v_loss_orders),
    (snap_ts, p_label, 'conversion_rate', v_conversion_rate),
    (snap_ts, p_label, 'cart_abandonment_rate', v_cart_abandon_rate),
    (snap_ts, p_label, 'payment_failure_rate', v_payment_failure_rate),
    (snap_ts, p_label, 'revenue_lost_due_to_failures', v_rev_lost_failures),
    (snap_ts, p_label, 'revenue_lost_due_to_abandonment', v_rev_lost_abandon);
END $$;

CREATE OR REPLACE FUNCTION globalcart.upsert_dim_customer_from_stg()
RETURNS TABLE(inserted_count INT, updated_count INT)
LANGUAGE plpgsql
AS $$
BEGIN
  WITH upserted AS (
    INSERT INTO globalcart.dim_customer (customer_id, customer_created_ts, geo_id, acquisition_channel, created_at, updated_at)
    SELECT customer_id, customer_created_ts, geo_id, acquisition_channel, created_at, updated_at
    FROM globalcart.stg_dim_customer
    ON CONFLICT (customer_id) DO UPDATE
      SET geo_id = EXCLUDED.geo_id,
          acquisition_channel = EXCLUDED.acquisition_channel,
          updated_at = EXCLUDED.updated_at
      WHERE EXCLUDED.updated_at > globalcart.dim_customer.updated_at
    RETURNING (xmax = 0) AS inserted
  )
  SELECT
    COUNT(*) FILTER (WHERE inserted),
    COUNT(*) FILTER (WHERE NOT inserted)
  INTO inserted_count, updated_count
  FROM upserted;

  TRUNCATE TABLE globalcart.stg_dim_customer;
  RETURN QUERY SELECT inserted_count, updated_count;
END $$;

CREATE OR REPLACE FUNCTION globalcart.upsert_dim_product_from_stg()
RETURNS TABLE(inserted_count INT, updated_count INT)
LANGUAGE plpgsql
AS $$
BEGIN
  WITH upserted AS (
    INSERT INTO globalcart.dim_product (product_id, sku, product_name, category_l1, category_l2, brand, unit_cost, list_price, created_at, updated_at)
    SELECT product_id, sku, product_name, category_l1, category_l2, brand, unit_cost, list_price, created_at, updated_at
    FROM globalcart.stg_dim_product
    ON CONFLICT (product_id) DO UPDATE
      SET product_name = EXCLUDED.product_name,
          category_l1 = EXCLUDED.category_l1,
          category_l2 = EXCLUDED.category_l2,
          brand = EXCLUDED.brand,
          unit_cost = EXCLUDED.unit_cost,
          list_price = EXCLUDED.list_price,
          updated_at = EXCLUDED.updated_at
      WHERE EXCLUDED.updated_at > globalcart.dim_product.updated_at
    RETURNING (xmax = 0) AS inserted
  )
  SELECT
    COUNT(*) FILTER (WHERE inserted),
    COUNT(*) FILTER (WHERE NOT inserted)
  INTO inserted_count, updated_count
  FROM upserted;

  TRUNCATE TABLE globalcart.stg_dim_product;
  RETURN QUERY SELECT inserted_count, updated_count;
END $$;

CREATE OR REPLACE FUNCTION globalcart.upsert_fact_orders_from_stg()
RETURNS TABLE(inserted_count INT, updated_count INT)
LANGUAGE plpgsql
AS $$
BEGIN
  INSERT INTO globalcart.audit_fact_orders
  SELECT
    nextval('globalcart.audit_fact_orders_audit_id_seq') AS audit_id,
    NOW() AS audit_ts,
    'UPDATE' AS audit_action,
    fo.*
  FROM globalcart.fact_orders fo
  JOIN globalcart.stg_fact_orders s ON s.order_id = fo.order_id
  WHERE s.updated_at > fo.updated_at;

  WITH upserted AS (
    INSERT INTO globalcart.fact_orders (order_id, customer_id, geo_id, order_ts, order_status, channel, currency, gross_amount, discount_amount, tax_amount, net_amount, created_at, updated_at)
    SELECT order_id, customer_id, geo_id, order_ts, order_status, channel, currency, gross_amount, discount_amount, tax_amount, net_amount, created_at, updated_at
    FROM globalcart.stg_fact_orders
    ON CONFLICT (order_id) DO UPDATE
      SET order_status = EXCLUDED.order_status,
          gross_amount = EXCLUDED.gross_amount,
          discount_amount = EXCLUDED.discount_amount,
          tax_amount = EXCLUDED.tax_amount,
          net_amount = EXCLUDED.net_amount,
          updated_at = EXCLUDED.updated_at
      WHERE EXCLUDED.updated_at > globalcart.fact_orders.updated_at
    RETURNING (xmax = 0) AS inserted
  )
  SELECT
    COUNT(*) FILTER (WHERE inserted),
    COUNT(*) FILTER (WHERE NOT inserted)
  INTO inserted_count, updated_count
  FROM upserted;

  TRUNCATE TABLE globalcart.stg_fact_orders;
  RETURN QUERY SELECT inserted_count, updated_count;
END $$;

CREATE OR REPLACE FUNCTION globalcart.upsert_fact_order_items_from_stg()
RETURNS TABLE(inserted_count INT, updated_count INT)
LANGUAGE plpgsql
AS $$
BEGIN
  WITH upserted AS (
    INSERT INTO globalcart.fact_order_items (order_item_id, order_id, product_id, qty, unit_list_price, unit_sell_price, unit_cost, line_discount, line_tax, line_net_revenue, created_at, updated_at)
    SELECT order_item_id, order_id, product_id, qty, unit_list_price, unit_sell_price, unit_cost, line_discount, line_tax, line_net_revenue, created_at, updated_at
    FROM globalcart.stg_fact_order_items
    ON CONFLICT (order_item_id) DO UPDATE
      SET qty = EXCLUDED.qty,
          unit_sell_price = EXCLUDED.unit_sell_price,
          line_discount = EXCLUDED.line_discount,
          line_tax = EXCLUDED.line_tax,
          line_net_revenue = EXCLUDED.line_net_revenue,
          updated_at = EXCLUDED.updated_at
      WHERE EXCLUDED.updated_at > globalcart.fact_order_items.updated_at
    RETURNING (xmax = 0) AS inserted
  )
  SELECT
    COUNT(*) FILTER (WHERE inserted),
    COUNT(*) FILTER (WHERE NOT inserted)
  INTO inserted_count, updated_count
  FROM upserted;

  TRUNCATE TABLE globalcart.stg_fact_order_items;
  RETURN QUERY SELECT inserted_count, updated_count;
END $$;

CREATE OR REPLACE FUNCTION globalcart.upsert_fact_funnel_events_from_stg()
RETURNS TABLE(inserted_count INT, updated_count INT)
LANGUAGE plpgsql
AS $$
BEGIN
  WITH ins AS (
    INSERT INTO globalcart.fact_funnel_events (event_id, event_ts, session_id, customer_id, product_id, order_id, stage, channel, device, failure_reason)
    SELECT event_id, event_ts, session_id, customer_id, product_id, order_id, stage, channel, device, failure_reason
    FROM globalcart.stg_fact_funnel_events
    ON CONFLICT (event_id) DO NOTHING
    RETURNING 1
  )
  SELECT COALESCE(COUNT(*),0), 0
  INTO inserted_count, updated_count
  FROM ins;

  TRUNCATE TABLE globalcart.stg_fact_funnel_events;
  RETURN QUERY SELECT inserted_count, updated_count;
END $$;

CREATE OR REPLACE FUNCTION globalcart.upsert_fact_payments_from_stg()
RETURNS TABLE(inserted_count INT, updated_count INT)
LANGUAGE plpgsql
AS $$
BEGIN
  INSERT INTO globalcart.audit_fact_payments
  SELECT
    nextval('globalcart.audit_fact_payments_audit_id_seq') AS audit_id,
    NOW() AS audit_ts,
    'UPDATE' AS audit_action,
    p.*
  FROM globalcart.fact_payments p
  JOIN globalcart.stg_fact_payments s ON s.payment_id = p.payment_id
  WHERE s.updated_at > p.updated_at;

  WITH upserted AS (
    INSERT INTO globalcart.fact_payments (payment_id, order_id, payment_method, payment_status, payment_provider, amount, gateway_fee_amount, authorized_ts, captured_ts, failure_reason, refund_amount, chargeback_flag, created_at, updated_at)
    SELECT payment_id, order_id, payment_method, payment_status, payment_provider, amount, gateway_fee_amount, authorized_ts, captured_ts, failure_reason, refund_amount, chargeback_flag, created_at, updated_at
    FROM globalcart.stg_fact_payments
    ON CONFLICT (payment_id) DO UPDATE
      SET payment_status = EXCLUDED.payment_status,
          captured_ts = EXCLUDED.captured_ts,
          failure_reason = EXCLUDED.failure_reason,
          refund_amount = EXCLUDED.refund_amount,
          chargeback_flag = EXCLUDED.chargeback_flag,
          gateway_fee_amount = EXCLUDED.gateway_fee_amount,
          updated_at = EXCLUDED.updated_at
      WHERE EXCLUDED.updated_at > globalcart.fact_payments.updated_at
    RETURNING (xmax = 0) AS inserted
  )
  SELECT
    COUNT(*) FILTER (WHERE inserted),
    COUNT(*) FILTER (WHERE NOT inserted)
  INTO inserted_count, updated_count
  FROM upserted;

  TRUNCATE TABLE globalcart.stg_fact_payments;
  RETURN QUERY SELECT inserted_count, updated_count;
END $$;

CREATE OR REPLACE FUNCTION globalcart.upsert_fact_shipments_from_stg()
RETURNS TABLE(inserted_count INT, updated_count INT)
LANGUAGE plpgsql
AS $$
BEGIN
  INSERT INTO globalcart.audit_fact_shipments
  SELECT
    nextval('globalcart.audit_fact_shipments_audit_id_seq') AS audit_id,
    NOW() AS audit_ts,
    'UPDATE' AS audit_action,
    s0.*
  FROM globalcart.fact_shipments s0
  JOIN globalcart.stg_fact_shipments s ON s.shipment_id = s0.shipment_id
  WHERE s.updated_at > s0.updated_at;

  WITH upserted AS (
    INSERT INTO globalcart.fact_shipments (shipment_id, order_id, fc_id, carrier, shipped_ts, promised_delivery_dt, delivered_dt, shipping_cost, sla_breached_flag, created_at, updated_at)
    SELECT shipment_id, order_id, fc_id, carrier, shipped_ts, promised_delivery_dt, delivered_dt, shipping_cost, sla_breached_flag, created_at, updated_at
    FROM globalcart.stg_fact_shipments
    ON CONFLICT (shipment_id) DO UPDATE
      SET delivered_dt = EXCLUDED.delivered_dt,
          shipping_cost = EXCLUDED.shipping_cost,
          sla_breached_flag = EXCLUDED.sla_breached_flag,
          updated_at = EXCLUDED.updated_at
      WHERE EXCLUDED.updated_at > globalcart.fact_shipments.updated_at
    RETURNING (xmax = 0) AS inserted
  )
  SELECT
    COUNT(*) FILTER (WHERE inserted),
    COUNT(*) FILTER (WHERE NOT inserted)
  INTO inserted_count, updated_count
  FROM upserted;

  TRUNCATE TABLE globalcart.stg_fact_shipments;
  RETURN QUERY SELECT inserted_count, updated_count;
END $$;

CREATE OR REPLACE FUNCTION globalcart.upsert_fact_returns_from_stg()
RETURNS TABLE(inserted_count INT, updated_count INT)
LANGUAGE plpgsql
AS $$
BEGIN
  INSERT INTO globalcart.audit_fact_returns
  SELECT
    nextval('globalcart.audit_fact_returns_audit_id_seq') AS audit_id,
    NOW() AS audit_ts,
    'UPDATE' AS audit_action,
    r0.*
  FROM globalcart.fact_returns r0
  JOIN globalcart.stg_fact_returns s ON s.return_id = r0.return_id
  WHERE s.updated_at > r0.updated_at;

  WITH upserted AS (
    INSERT INTO globalcart.fact_returns (return_id, order_id, order_item_id, product_id, return_ts, return_reason, refund_amount, return_status, restocked_flag, created_at, updated_at)
    SELECT return_id, order_id, order_item_id, product_id, return_ts, return_reason, refund_amount, return_status, restocked_flag, created_at, updated_at
    FROM globalcart.stg_fact_returns
    ON CONFLICT (return_id) DO UPDATE
      SET return_status = EXCLUDED.return_status,
          refund_amount = EXCLUDED.refund_amount,
          restocked_flag = EXCLUDED.restocked_flag,
          updated_at = EXCLUDED.updated_at
      WHERE EXCLUDED.updated_at > globalcart.fact_returns.updated_at
    RETURNING (xmax = 0) AS inserted
  )
  SELECT
    COUNT(*) FILTER (WHERE inserted),
    COUNT(*) FILTER (WHERE NOT inserted)
  INTO inserted_count, updated_count
  FROM upserted;

  TRUNCATE TABLE globalcart.stg_fact_returns;
  RETURN QUERY SELECT inserted_count, updated_count;
END $$;
