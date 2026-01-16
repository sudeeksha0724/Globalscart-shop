# Architecture (GlobalCart 360)

## Target Operating Model (Real Company)

### Data Sources (Operational)
- Orders service (order created/updated)
- Payments service (auth/capture/refund/chargeback)
- Shipping service (fulfillment events, carrier SLAs)
- Returns service (return initiated/approved/refunded)
- Web/App event stream (product views, cart actions, checkout, payment attempts)

### Near Real-Time Assumption
- Events arrive continuously; KPI dashboards refresh every **15–30 minutes**.
- Facts are updated incrementally using a watermark (e.g., `updated_at`) and idempotent upserts.

## Incremental Refresh (Implemented in this repo)

### Key design decisions
- **Watermark**: `updated_at` on all facts and key dimensions; stored per-source in `globalcart.etl_watermarks`.
- **Staging**: `globalcart.stg_*` tables to land deltas.
- **Idempotency**: upserts only apply when incoming `updated_at` is newer than target.
- **Historical accuracy**: updated fact rows are captured in `globalcart.audit_fact_*` before overwrite.

### Incremental flow
1. Source events (order/payment/shipping/return) arrive.
2. ELT job reads only events where `updated_at > last_processed_ts`.
3. Load into staging tables.
4. Execute upsert functions to merge into facts/dimensions.
5. Advance the watermark.
6. BI refresh reads current-state tables/views.

### Demo scripts
- `sql/04_incremental_refresh.sql` (staging + upsert functions + KPI snapshots)
- `src/incremental_refresh.py` (generates deltas + loads staging + runs upserts + logs insert/update counts)

### Warehouse (PostgreSQL)
- Star schema in schema `globalcart`.
- KPI definitions standardized via SQL views (`sql/02_views.sql`).

### Funnel Tracking (Milestone 2)
- Funnel events are stored in `globalcart.fact_funnel_events` and keyed by `session_id`.
- Events can be anonymous (guest checkout), hence `customer_id` is nullable.
- This is analogous to how Amazon/Flipkart teams track the customer journey:
  - event collection at the edge (web/app)
  - sessionization and enrichment (customer/device/channel)
  - funnel metrics computed as session-level flags per stage
  - revenue leakage estimated from drop-offs and failures, and tied back to Finance P&L.

#### How conversion is calculated
- The funnel is evaluated at the **session** granularity (not raw event counts).
- Each stage is a boolean flag per session (e.g., a session can have many `VIEW_PRODUCT` events, but it counts as 1 “viewed session”).
- Core rates:
  - `conversion_rate = sessions_with_ORDER_PLACED / sessions_with_VIEW_PRODUCT`
  - `cart_abandonment_rate = (sessions_with_ADD_TO_CART - sessions_with_CHECKOUT_STARTED) / sessions_with_ADD_TO_CART`
  - `payment_failure_rate = sessions_with_PAYMENT_FAILED / sessions_with_PAYMENT_ATTEMPTED`

#### How leakage ties back to Finance (Milestone 1)
- Finance P&L explains realized profit erosion (refunds, shipping cost, gateway fees, COGS).
- Funnel leakage explains **pre-purchase loss** (sessions that expressed intent but did not convert).
- In real marketplaces, both are monitored together:
  - Funnel drop-offs are owned by product/UX/payment reliability teams.
  - P&L leakage is owned by operations/quality/CS teams.

### Analytics Layer
- Python pulls from warehouse for EDA, segmentation, and forecasting.
- Outputs stored as reproducible artifacts:
  - `data/processed/` (segments, forecasts)
  - `reports/` (plots, Excel management report)

### BI Layer (Power BI/Tableau)
- Executive Dashboard: business health + profit leakage
- Operational Dashboard: SLA/returns/payments drilldowns

## Scaling Notes (100M+ orders/year)
- Partition large facts by date (monthly) and maintain summary tables for speed.
- Use indexes on `order_ts`, `customer_id`, `product_id` and event timestamps.
- Consider a streaming layer (Kafka/Kinesis) + incremental ELT in production.
