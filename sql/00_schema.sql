CREATE SCHEMA IF NOT EXISTS globalcart;

CREATE TABLE IF NOT EXISTS globalcart.dim_geo (
  geo_id BIGINT PRIMARY KEY,
  country VARCHAR(60) NOT NULL,
  region VARCHAR(60) NOT NULL,
  city VARCHAR(80) NOT NULL,
  currency VARCHAR(10) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS globalcart.dim_fc (
  fc_id BIGINT PRIMARY KEY,
  fc_name VARCHAR(80) NOT NULL,
  geo_id BIGINT NOT NULL REFERENCES globalcart.dim_geo(geo_id),
  timezone VARCHAR(40) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS globalcart.dim_customer (
  customer_id BIGINT PRIMARY KEY,
  customer_created_ts TIMESTAMP NOT NULL,
  geo_id BIGINT NOT NULL REFERENCES globalcart.dim_geo(geo_id),
  acquisition_channel VARCHAR(50) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS globalcart.dim_product (
  product_id BIGINT PRIMARY KEY,
  sku VARCHAR(50) NOT NULL,
  product_name VARCHAR(200) NOT NULL,
  category_l1 VARCHAR(50) NOT NULL,
  category_l2 VARCHAR(50) NOT NULL,
  brand VARCHAR(80) NOT NULL,
  unit_cost NUMERIC(12,2) NOT NULL,
  list_price NUMERIC(12,2) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS globalcart.dim_date (
  date_id INTEGER PRIMARY KEY,
  date_value DATE NOT NULL UNIQUE,
  year INTEGER NOT NULL,
  quarter INTEGER NOT NULL,
  month INTEGER NOT NULL,
  month_name VARCHAR(15) NOT NULL,
  week_of_year INTEGER NOT NULL,
  day_of_month INTEGER NOT NULL,
  day_of_week INTEGER NOT NULL,
  day_name VARCHAR(15) NOT NULL,
  is_weekend BOOLEAN NOT NULL
);

CREATE TABLE IF NOT EXISTS globalcart.fact_orders (
  order_id BIGINT PRIMARY KEY,
  customer_id BIGINT NOT NULL REFERENCES globalcart.dim_customer(customer_id),
  geo_id BIGINT NOT NULL REFERENCES globalcart.dim_geo(geo_id),
  order_ts TIMESTAMP NOT NULL,
  order_status VARCHAR(30) NOT NULL,
  channel VARCHAR(30) NOT NULL,
  currency VARCHAR(10) NOT NULL,
  gross_amount NUMERIC(14,2) NOT NULL,
  discount_amount NUMERIC(14,2) NOT NULL,
  tax_amount NUMERIC(14,2) NOT NULL,
  net_amount NUMERIC(14,2) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS globalcart.fact_order_items (
  order_item_id BIGINT PRIMARY KEY,
  order_id BIGINT NOT NULL REFERENCES globalcart.fact_orders(order_id),
  product_id BIGINT NOT NULL REFERENCES globalcart.dim_product(product_id),
  qty INTEGER NOT NULL,
  unit_list_price NUMERIC(12,2) NOT NULL,
  unit_sell_price NUMERIC(12,2) NOT NULL,
  unit_cost NUMERIC(12,2) NOT NULL,
  line_discount NUMERIC(14,2) NOT NULL,
  line_tax NUMERIC(14,2) NOT NULL,
  line_net_revenue NUMERIC(14,2) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS globalcart.fact_payments (
  payment_id BIGINT PRIMARY KEY,
  order_id BIGINT NOT NULL REFERENCES globalcart.fact_orders(order_id),
  payment_method VARCHAR(30) NOT NULL,
  payment_status VARCHAR(30) NOT NULL,
  payment_provider VARCHAR(30) NOT NULL,
  amount NUMERIC(14,2) NOT NULL,
  gateway_fee_amount NUMERIC(14,2) NOT NULL DEFAULT 0,
  authorized_ts TIMESTAMP,
  captured_ts TIMESTAMP,
  failure_reason VARCHAR(80),
  refund_amount NUMERIC(14,2) NOT NULL,
  chargeback_flag BOOLEAN NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS globalcart.fact_shipments (
  shipment_id BIGINT PRIMARY KEY,
  order_id BIGINT NOT NULL REFERENCES globalcart.fact_orders(order_id),
  fc_id BIGINT NOT NULL REFERENCES globalcart.dim_fc(fc_id),
  carrier VARCHAR(50) NOT NULL,
  shipped_ts TIMESTAMP,
  promised_delivery_dt DATE NOT NULL,
  delivered_dt DATE,
  shipping_cost NUMERIC(14,2) NOT NULL,
  sla_breached_flag BOOLEAN NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS globalcart.fact_returns (
  return_id BIGINT PRIMARY KEY,
  order_id BIGINT NOT NULL REFERENCES globalcart.fact_orders(order_id),
  order_item_id BIGINT NOT NULL REFERENCES globalcart.fact_order_items(order_item_id),
  product_id BIGINT NOT NULL REFERENCES globalcart.dim_product(product_id),
  return_ts TIMESTAMP NOT NULL,
  return_reason VARCHAR(80) NOT NULL,
  refund_amount NUMERIC(14,2) NOT NULL,
  return_status VARCHAR(30) NOT NULL,
  restocked_flag BOOLEAN NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

DO $$
BEGIN
  CREATE TYPE globalcart.funnel_stage AS ENUM (
    'VIEW_PRODUCT',
    'ADD_TO_CART',
    'VIEW_CART',
    'CHECKOUT_STARTED',
    'PAYMENT_ATTEMPTED',
    'PAYMENT_FAILED',
    'ORDER_PLACED'
  );
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS globalcart.fact_funnel_events (
  event_id BIGINT PRIMARY KEY,
  event_ts TIMESTAMP NOT NULL,
  session_id VARCHAR(64) NOT NULL,
  customer_id BIGINT REFERENCES globalcart.dim_customer(customer_id),
  product_id BIGINT REFERENCES globalcart.dim_product(product_id),
  order_id BIGINT REFERENCES globalcart.fact_orders(order_id),
  stage globalcart.funnel_stage NOT NULL,
  channel VARCHAR(10) NOT NULL,
  device VARCHAR(10) NOT NULL,
  failure_reason VARCHAR(80)
);

CREATE TABLE IF NOT EXISTS globalcart.order_cancellations (
  cancellation_id BIGSERIAL PRIMARY KEY,
  order_id BIGINT NOT NULL,
  customer_id BIGINT NOT NULL,
  reason TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_fact_orders_order_ts ON globalcart.fact_orders(order_ts);
CREATE INDEX IF NOT EXISTS idx_fact_orders_customer_id ON globalcart.fact_orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_fact_order_items_order_id ON globalcart.fact_order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_fact_order_items_product_id ON globalcart.fact_order_items(product_id);
CREATE INDEX IF NOT EXISTS idx_fact_returns_order_id ON globalcart.fact_returns(order_id);
CREATE INDEX IF NOT EXISTS idx_fact_shipments_order_id ON globalcart.fact_shipments(order_id);
CREATE INDEX IF NOT EXISTS idx_fact_payments_order_id ON globalcart.fact_payments(order_id);

CREATE INDEX IF NOT EXISTS idx_fact_funnel_events_event_ts ON globalcart.fact_funnel_events(event_ts);
CREATE INDEX IF NOT EXISTS idx_fact_funnel_events_session_id ON globalcart.fact_funnel_events(session_id);
CREATE INDEX IF NOT EXISTS idx_fact_funnel_events_customer_id ON globalcart.fact_funnel_events(customer_id);
CREATE INDEX IF NOT EXISTS idx_fact_funnel_events_product_id ON globalcart.fact_funnel_events(product_id);
CREATE INDEX IF NOT EXISTS idx_fact_funnel_events_order_id ON globalcart.fact_funnel_events(order_id);
CREATE INDEX IF NOT EXISTS idx_fact_funnel_events_stage ON globalcart.fact_funnel_events(stage);

CREATE INDEX IF NOT EXISTS idx_order_cancellations_order_id ON globalcart.order_cancellations(order_id);
CREATE INDEX IF NOT EXISTS idx_order_cancellations_customer_id ON globalcart.order_cancellations(customer_id);

CREATE INDEX IF NOT EXISTS idx_dim_customer_updated_at ON globalcart.dim_customer(updated_at);
CREATE INDEX IF NOT EXISTS idx_dim_product_updated_at ON globalcart.dim_product(updated_at);
CREATE INDEX IF NOT EXISTS idx_fact_order_items_updated_at ON globalcart.fact_order_items(updated_at);
CREATE INDEX IF NOT EXISTS idx_fact_payments_updated_at ON globalcart.fact_payments(updated_at);
CREATE INDEX IF NOT EXISTS idx_fact_shipments_updated_at ON globalcart.fact_shipments(updated_at);
CREATE INDEX IF NOT EXISTS idx_fact_returns_updated_at ON globalcart.fact_returns(updated_at);

ALTER TABLE globalcart.dim_geo ADD COLUMN IF NOT EXISTS created_at TIMESTAMP NOT NULL DEFAULT NOW();
ALTER TABLE globalcart.dim_geo ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT NOW();

ALTER TABLE globalcart.dim_fc ADD COLUMN IF NOT EXISTS created_at TIMESTAMP NOT NULL DEFAULT NOW();
ALTER TABLE globalcart.dim_fc ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT NOW();

ALTER TABLE globalcart.dim_customer ADD COLUMN IF NOT EXISTS created_at TIMESTAMP NOT NULL DEFAULT NOW();
ALTER TABLE globalcart.dim_customer ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT NOW();

ALTER TABLE globalcart.dim_product ADD COLUMN IF NOT EXISTS created_at TIMESTAMP NOT NULL DEFAULT NOW();
ALTER TABLE globalcart.dim_product ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT NOW();

ALTER TABLE globalcart.fact_order_items ADD COLUMN IF NOT EXISTS created_at TIMESTAMP NOT NULL DEFAULT NOW();
ALTER TABLE globalcart.fact_order_items ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT NOW();

ALTER TABLE globalcart.fact_payments ADD COLUMN IF NOT EXISTS created_at TIMESTAMP NOT NULL DEFAULT NOW();
ALTER TABLE globalcart.fact_payments ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT NOW();

ALTER TABLE globalcart.fact_payments ADD COLUMN IF NOT EXISTS gateway_fee_amount NUMERIC(14,2) NOT NULL DEFAULT 0;

ALTER TABLE globalcart.fact_shipments ADD COLUMN IF NOT EXISTS created_at TIMESTAMP NOT NULL DEFAULT NOW();
ALTER TABLE globalcart.fact_shipments ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT NOW();

ALTER TABLE globalcart.fact_returns ADD COLUMN IF NOT EXISTS created_at TIMESTAMP NOT NULL DEFAULT NOW();
ALTER TABLE globalcart.fact_returns ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT NOW();

ALTER TABLE globalcart.fact_funnel_events ADD COLUMN IF NOT EXISTS failure_reason VARCHAR(80);
