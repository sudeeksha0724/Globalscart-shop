CREATE SCHEMA IF NOT EXISTS globalcart;

CREATE TABLE IF NOT EXISTS globalcart.app_users (
  email VARCHAR(320) PRIMARY KEY,
  customer_id BIGINT NOT NULL REFERENCES globalcart.dim_customer(customer_id),
  geo_id BIGINT NOT NULL REFERENCES globalcart.dim_geo(geo_id),
  verified_at TIMESTAMP NOT NULL DEFAULT NOW(),
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_app_users_customer_id ON globalcart.app_users(customer_id);

CREATE TABLE IF NOT EXISTS globalcart.app_email_otps (
  otp_id BIGSERIAL PRIMARY KEY,
  email VARCHAR(320) NOT NULL,
  otp_hash VARCHAR(128) NOT NULL,
  expires_at TIMESTAMP NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  last_attempt_at TIMESTAMP NULL,
  consumed_at TIMESTAMP NULL
);

CREATE INDEX IF NOT EXISTS idx_app_email_otps_email_created ON globalcart.app_email_otps(email, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_app_email_otps_expires_at ON globalcart.app_email_otps(expires_at);

ALTER TABLE IF EXISTS globalcart.app_users
  ADD COLUMN IF NOT EXISTS display_name VARCHAR(120),
  ADD COLUMN IF NOT EXISTS password_hash TEXT,
  ADD COLUMN IF NOT EXISTS role VARCHAR(20) NOT NULL DEFAULT 'customer';

ALTER TABLE IF EXISTS globalcart.app_email_otps
  ADD COLUMN IF NOT EXISTS purpose VARCHAR(32) NOT NULL DEFAULT 'SIGNUP',
  ADD COLUMN IF NOT EXISTS display_name VARCHAR(120),
  ADD COLUMN IF NOT EXISTS password_hash TEXT;

CREATE INDEX IF NOT EXISTS idx_app_email_otps_email_purpose_created ON globalcart.app_email_otps(email, purpose, created_at DESC);
