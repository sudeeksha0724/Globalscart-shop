# KPI Definitions (GlobalCart 360)

All tools (SQL, Python, Excel, Power BI/Tableau) must use the same KPI definitions.

## Scope Filter
- **Completed Orders**: `order_status IN ('DELIVERED','COMPLETED','RETURNED')`
- Currency handling: KPIs are computed in the order currency; for multi-currency consolidation, introduce FX conversion (out of scope for synthetic demo).

## Commercial KPIs
- **Gross Amount**: total before discounts and taxes
- **Discount Amount**: total discount applied at order level
- **Tax Amount**: tax amount
- **Net Revenue (ex tax)**: `net_amount - tax_amount` (used for profitability + finance KPIs)
- **AOV (Average Order Value)**: `Net Revenue / Distinct Orders`

## Profitability KPIs (Item-based)
- **COGS**: `qty * unit_cost`
- **Gross Profit**: `line_net_revenue - COGS`
- **Gross Margin %**: `Gross Profit / line_net_revenue`

## Retention KPIs
- **Active Customers**: distinct customers with >=1 completed order in period
- **Repeat Customer %**: customers with lifetime completed orders >= 2 / all customers with >=1 completed order
- **Churned Customer**: last completed order timestamp older than `CURRENT_DATE - 90 days`

## Operations KPIs
- **SLA Breach %**: breached shipments / total shipments
- **Shipping Cost % of Revenue**: total shipping_cost / total net revenue (completed orders)

## Returns & Payments
- **Return Rate Proxy**: return lines / sold quantity (demo metric; can be refined to item-level denominator)
- **Refund Amount**: sum of refund_amount
- **Payment Failure %**: failed or declined payment attempts / total payment attempts
- **Chargeback %**: chargeback_flag true / total payments

## Funnel & Conversion KPIs (Milestone 2)
These are computed from session-level events in `globalcart.fact_funnel_events`.

- **Product Views (Sessions)**: distinct `session_id` with at least one `stage='VIEW_PRODUCT'`
- **Add To Cart (Sessions)**: distinct `session_id` with at least one `stage='ADD_TO_CART'`
- **Checkout Started (Sessions)**: distinct `session_id` with at least one `stage='CHECKOUT_STARTED'`
- **Payment Attempts (Sessions)**: distinct `session_id` with at least one `stage='PAYMENT_ATTEMPTED'`
- **Orders Placed (Sessions)**: distinct `session_id` with at least one `stage='ORDER_PLACED'`

- **Conversion Rate**: `orders_placed_sessions / product_view_sessions`
- **Cart Abandonment Rate**: `(add_to_cart_sessions - checkout_started_sessions) / add_to_cart_sessions`
- **Payment Failure Rate**: `payment_failed_sessions / payment_attempt_sessions`

## Revenue Leakage KPIs (Milestone 2)
Leakage is split into:
- **Refund leakage**: realized revenue lost post-purchase (from `fact_returns.refund_amount`)
- **Cart abandonment revenue loss (estimated)**: monetization proxy using product list price and average sell/list ratio
- **Payment failures revenue loss (estimated)**: sum of attempted basket sell price (from `fact_order_items` of failed orders)

The semantic layer is exposed via:
- `globalcart.vw_funnel_daily_metrics`
- `globalcart.vw_revenue_leakage`
