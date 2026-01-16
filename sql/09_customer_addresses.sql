-- Create customer addresses table
-- Run once: python3 -m src.run_sql --sql sql/09_customer_addresses.sql

CREATE TABLE IF NOT EXISTS globalcart.customer_addresses (
  address_id BIGINT PRIMARY KEY,
  customer_id BIGINT NOT NULL REFERENCES globalcart.dim_customer(customer_id),
  recipient_name VARCHAR(200) NOT NULL,
  phone VARCHAR(30),
  address_line1 VARCHAR(300) NOT NULL,
  address_line2 VARCHAR(300),
  city VARCHAR(100) NOT NULL,
  state VARCHAR(100) NOT NULL,
  postal_code VARCHAR(20) NOT NULL,
  country VARCHAR(60) NOT NULL,
  is_default BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Ensure only one default address per customer
CREATE UNIQUE INDEX IF NOT EXISTS idx_customer_default_address 
ON globalcart.customer_addresses (customer_id) 
WHERE is_default = TRUE;
