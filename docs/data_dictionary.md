# Data Dictionary (GlobalCart 360)

## Dimensions

### dim_geo
- `geo_id` (PK)
- `country`
- `region`
- `city`
- `currency`

### dim_fc
- `fc_id` (PK)
- `fc_name`
- `geo_id` (FK to dim_geo)
- `timezone`

### dim_customer
- `customer_id` (PK)
- `customer_created_ts`
- `geo_id` (FK)
- `acquisition_channel` (e.g., Organic, Paid Search, Affiliates, Email)

### dim_product
- `product_id` (PK)
- `sku`
- `product_name`
- `category_l1`, `category_l2`
- `brand`
- `unit_cost`
- `list_price`

### dim_date
- `date_id` (PK, yyyymmdd)
- `date_value`
- `year`, `quarter`, `month`, `month_name`
- `week_of_year`
- `day_of_month`, `day_of_week`, `day_name`
- `is_weekend`

## Facts

### fact_orders
- `order_id` (PK)
- `customer_id` (FK)
- `geo_id` (FK)
- `order_ts`, `order_status`
- `channel` (Web/App)
- `currency`
- `gross_amount`, `discount_amount`, `tax_amount`, `net_amount`

### fact_order_items
- `order_item_id` (PK)
- `order_id` (FK)
- `product_id` (FK)
- `qty`
- `unit_list_price`, `unit_sell_price`, `unit_cost`
- `line_discount`, `line_tax`, `line_net_revenue`

### fact_payments
- `payment_id` (PK)
- `order_id` (FK)
- `payment_method` (Card/UPI/Wallet/COD)
- `payment_status` (CAPTURED/FAILED/DECLINED/REFUNDED)
- `payment_provider`
- `amount`, `authorized_ts`, `captured_ts`
- `failure_reason`
- `refund_amount`, `chargeback_flag`

### fact_shipments
- `shipment_id` (PK)
- `order_id` (FK)
- `fc_id` (FK)
- `carrier`
- `shipped_ts`, `promised_delivery_dt`, `delivered_dt`
- `shipping_cost`, `sla_breached_flag`

### fact_returns
- `return_id` (PK)
- `order_id` (FK)
- `order_item_id` (FK)
- `product_id` (FK)
- `return_ts`, `return_reason`, `return_status`
- `refund_amount`, `restocked_flag`

### fact_funnel_events
- `event_id` (PK)
- `event_ts`
- `session_id` (session-level journey id)
- `customer_id` (nullable; guest sessions)
- `product_id` (nullable; cart/checkout/payment stages may not be product-specific)
- `order_id` (nullable; may exist once checkout/payment is started)
- `stage` (ENUM):
  - `VIEW_PRODUCT`
  - `ADD_TO_CART`
  - `VIEW_CART`
  - `CHECKOUT_STARTED`
  - `PAYMENT_ATTEMPTED`
  - `PAYMENT_FAILED`
  - `ORDER_PLACED`
- `channel` (WEB/APP)
- `device` (MOBILE/DESKTOP)
- `failure_reason` (nullable; populated for `PAYMENT_FAILED`)
