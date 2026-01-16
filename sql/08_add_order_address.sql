-- Add address columns to fact_orders
-- Run once: python3 -m src.run_sql --sql sql/08_add_order_address.sql

ALTER TABLE globalcart.fact_orders
ADD COLUMN IF NOT EXISTS recipient_name VARCHAR(200),
ADD COLUMN IF NOT EXISTS address_line1 VARCHAR(300),
ADD COLUMN IF NOT EXISTS address_line2 VARCHAR(300),
ADD COLUMN IF NOT EXISTS city VARCHAR(100),
ADD COLUMN IF NOT EXISTS state VARCHAR(100),
ADD COLUMN IF NOT EXISTS postal_code VARCHAR(20),
ADD COLUMN IF NOT EXISTS country VARCHAR(60),
ADD COLUMN IF NOT EXISTS phone VARCHAR(30);
