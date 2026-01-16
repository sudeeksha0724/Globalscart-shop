# Near Real-Time Incremental Refresh (GlobalCart 360)

This extension simulates how an MNC analytics platform handles near real-time event ingestion **without full reloads**.

## What is simulated
- **New events**: new orders, order items, payments, shipments, funnel events (session journey)
- **Late-arriving events**: returns/refunds arriving days after the original order
- **Status changes**:
  - order: `DELIVERED → COMPLETED`
  - shipment: delivered date changes and `sla_breached_flag` becomes true (delivered → delayed)
  - order: `DELIVERED/COMPLETED → RETURNED` (driven by late returns)

## Watermark strategy
- Every record carries an `updated_at` timestamp.
- The pipeline tracks a per-source watermark in `globalcart.etl_watermarks`.
- On each run, the refresh processes **only records newer than the watermark** (simulated by generating events between `since_ts` and `now_ts`).

## Idempotent upserts (no full reload)
- Incoming deltas are loaded into **staging** tables (`globalcart.stg_*`).
- Warehouse tables are updated via `INSERT ... ON CONFLICT DO UPDATE` with a safety condition:
  - only apply updates when `EXCLUDED.updated_at > target.updated_at`
- This prevents older events from overwriting newer truth.

For funnel events (`globalcart.fact_funnel_events`), inserts are idempotent and use `ON CONFLICT DO NOTHING` (event stream append-only).

## Historical accuracy
Production systems often keep:
- **Current-state tables** (fast dashboards)
- **History / audit tables** (CDC replay and investigations)

In this project:
- Facts are stored as current-state rows in `globalcart.fact_*`.
- Updates are captured in `globalcart.audit_fact_*` tables *before* the upsert overwrites the row.

## How to demo KPI change after refresh
1) Snapshot KPIs before:
```sql
SELECT globalcart.snapshot_kpis('before');
```

2) Run incremental refresh:
```bash
python -m src.incremental_refresh
```

3) Snapshot KPIs after and compare:
```sql
SELECT globalcart.snapshot_kpis('after');
\i sql/05_before_after_kpis.sql
```

KPI snapshots also include funnel + leakage metrics if `fact_funnel_events` exists:
- `conversion_rate`
- `cart_abandonment_rate`
- `payment_failure_rate`
- `revenue_lost_due_to_failures`
- `revenue_lost_due_to_abandonment`

## Production scaling notes
- Partition large facts by date (monthly) + keep summary tables for BI performance.
- Use CDC from OLTP (Debezium) or streaming (Kafka/Kinesis) into a bronze layer.
- Use incremental ELT jobs (Airflow/DBT) with watermarks.
- Power BI incremental refresh (range partitioning) over `updated_at` / `order_dt`.
