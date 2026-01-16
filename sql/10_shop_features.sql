CREATE SCHEMA IF NOT EXISTS globalcart;

CREATE TABLE IF NOT EXISTS globalcart.customer_wishlist (
  customer_id BIGINT NOT NULL REFERENCES globalcart.dim_customer(customer_id),
  product_id BIGINT NOT NULL REFERENCES globalcart.dim_product(product_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (customer_id, product_id)
);

CREATE TABLE IF NOT EXISTS globalcart.promo_codes (
  code VARCHAR(40) PRIMARY KEY,
  discount_type VARCHAR(20) NOT NULL,
  discount_value NUMERIC(14,2) NOT NULL,
  max_discount NUMERIC(14,2) NULL,
  min_order_amount NUMERIC(14,2) NULL,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  expires_at TIMESTAMPTZ NULL
);

INSERT INTO globalcart.promo_codes (code, discount_type, discount_value, max_discount, min_order_amount)
VALUES ('WELCOME10','PERCENT',10,250,0)
ON CONFLICT (code) DO NOTHING;

INSERT INTO globalcart.promo_codes (code, discount_type, discount_value, max_discount, min_order_amount)
VALUES ('FLAT100','FLAT',100,NULL,499)
ON CONFLICT (code) DO NOTHING;

CREATE TABLE IF NOT EXISTS globalcart.order_promotions (
  order_id BIGINT PRIMARY KEY REFERENCES globalcart.fact_orders(order_id) ON DELETE CASCADE,
  promo_code VARCHAR(40) NOT NULL REFERENCES globalcart.promo_codes(code),
  discount_amount NUMERIC(14,2) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS globalcart.product_reviews (
  review_id BIGSERIAL PRIMARY KEY,
  product_id BIGINT NOT NULL REFERENCES globalcart.dim_product(product_id),
  customer_id BIGINT NOT NULL REFERENCES globalcart.dim_customer(customer_id),
  rating SMALLINT NOT NULL CHECK (rating >= 1 AND rating <= 5),
  title VARCHAR(120) NULL,
  body TEXT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_product_reviews_product_created
ON globalcart.product_reviews (product_id, created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_product_reviews_unique
ON globalcart.product_reviews (product_id, customer_id);

CREATE TABLE IF NOT EXISTS globalcart.app_email_outbox (
  email_id BIGSERIAL PRIMARY KEY,
  customer_id BIGINT NULL REFERENCES globalcart.dim_customer(customer_id),
  to_email VARCHAR(320) NOT NULL,
  subject VARCHAR(200) NOT NULL,
  body TEXT NOT NULL,
  kind VARCHAR(40) NOT NULL,
  order_id BIGINT NULL REFERENCES globalcart.fact_orders(order_id),
  status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
  provider VARCHAR(40) NULL,
  error TEXT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  sent_at TIMESTAMPTZ NULL
);

CREATE INDEX IF NOT EXISTS idx_app_email_outbox_customer_created
ON globalcart.app_email_outbox (customer_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_app_email_outbox_order_created
ON globalcart.app_email_outbox (order_id, created_at DESC);

ALTER TABLE IF EXISTS globalcart.customer_addresses
  ADD COLUMN IF NOT EXISTS label VARCHAR(40);
