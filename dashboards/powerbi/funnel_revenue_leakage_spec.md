# Funnel & Revenue Leakage (Power BI Page)

## Goal
Understand conversion drop-offs, quantify leakage, and identify where revenue is lost.

## Primary tables (recommended)
- `globalcart.mart_funnel_conversion` (daily funnel by channel/device)
- `globalcart.mart_product_performance` (cart abandonment + payment risk by product)
- `globalcart.mart_exec_daily_kpis` (daily orders + revenue)
- `globalcart.dim_date`
- `globalcart.dim_product`

## Funnel stages (required)
- Product Views
- Add to Cart
- Checkout Started
- Payment Attempted
- Order Completed (Orders Placed)

## KPIs
- Conversion Rate
- Cart Abandonment Rate
- Payment Failure Rate
- Revenue Lost (Cart Abandonment proxy)
- Revenue at Risk (Payment failures proxy)
- Net Revenue After Leakage (proxy)

## Visuals
1) Funnel chart
- Use mart_funnel_conversion sums:
  - product_views → add_to_cart → checkout_started → payment_attempts → orders_placed

2) Trend: Conversion + abandonment + failure
- Line chart by date, with 2–3 lines:
  - Conversion Rate
  - Cart Abandonment Rate
  - Payment Failure Rate

3) Leakage waterfall
- Waterfall:
  - Start: Net Revenue
  - Subtract: Revenue Lost (Cart Abandonment)
  - Subtract: Revenue at Risk (Payment Failures)
  - Subtract: Refund Amount (optional)

4) Breakdown visuals (optional but recommended)
- By Device: small multiple line charts (desktop vs mobile)
- By Channel: clustered bar of conversion rate
- By Category: matrix of revenue lost / payment risk

## Slicers
- Date
- Channel
- Device
- Category

## Notes
- `mart_funnel_conversion` already provides daily funnel rates by channel/device.
- `mart_product_performance` provides product-level leakage proxies:
  - `revenue_lost_cart_abandonment`
  - `revenue_at_risk_ex_tax`
