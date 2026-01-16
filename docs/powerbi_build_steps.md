# Power BI Build Steps (GlobalCart 360)

This project is designed to work best with the **BI marts** created in `sql/06_bi_marts.sql`.

## 1) Connect to PostgreSQL
- Get Data → PostgreSQL database
- Server: `localhost:5432`
- Database: `globalcart`

### Recommended: create/refresh BI marts first
Run these once (or whenever schema changes):
- `python3 -m src.run_sql --sql sql/02_views.sql`
- `python3 -m src.run_sql --sql sql/06_bi_marts.sql`

After new data loads, refresh:
- SQL: `SELECT globalcart.refresh_bi_marts();`

### Import tables (recommended)
- Dimensions:
  - `globalcart.dim_date`
  - `globalcart.dim_geo`
  - `globalcart.dim_product`
  - `globalcart.dim_customer`
- Marts:
  - `globalcart.mart_exec_daily_kpis`
  - `globalcart.mart_finance_profitability`
  - `globalcart.mart_funnel_conversion`
  - `globalcart.mart_product_performance`
  - `globalcart.mart_customer_segments`

### Optional imports (for operational drilldowns)
- `globalcart.vw_sla`
- `globalcart.vw_returns_enriched`
- `globalcart.vw_payments_enriched`

## 2) Model relationships (Star Schema)
- `dim_date[date_id]` → `mart_exec_daily_kpis[date_id]`
- `dim_date[date_id]` → `mart_finance_profitability[date_id]`
- `dim_date[date_id]` → `mart_funnel_conversion[date_id]`
- `dim_date[date_id]` → `mart_product_performance[date_id]`

- `dim_customer[customer_id]` → `mart_finance_profitability[customer_id]`
- `dim_customer[customer_id]` → `mart_customer_segments[customer_id]`

- `dim_geo[geo_id]` → `mart_finance_profitability[geo_id]`
- `dim_geo[geo_id]` → `mart_customer_segments[geo_id]`

- `dim_product[product_id]` → `mart_product_performance[product_id]`

## 3) Measures
Use `dashboards/powerbi/dax_measures.md`.

## 4) Pages
- Revenue & Growth Intelligence: `dashboards/powerbi/revenue_growth_intelligence_spec.md`
- Funnel & Revenue Leakage: `dashboards/powerbi/funnel_revenue_leakage_spec.md`
- Customer Analytics (RFM + Retention): `dashboards/powerbi/customer_analytics_rfm_retention_spec.md`
- Product Intelligence: `dashboards/powerbi/product_intelligence_spec.md`
- Operational Efficiency: `dashboards/powerbi/operational_efficiency_spec.md`

Optional (legacy/simple pages still available):
- Executive (compact): `dashboards/powerbi/executive_dashboard_spec.md`
- Operational (compact): `dashboards/powerbi/operational_dashboard_spec.md`

## 5) Refresh
For a near real-time demo:
- Refresh every 30 minutes (Power BI Service) or manual refresh locally after rerunning the pipeline.

## Incremental Refresh Mapping (How this would work in Power BI)

### Option A: Power BI Incremental Refresh (recommended)
- Partition by `order_dt` (derived date) for historical backfill.
- Use `updated_at` (or a fact-level last updated timestamp) as the change detection column.
- Configure incremental refresh policy:
  - Store last: e.g., 2 years
  - Refresh last: e.g., 7 days

### Option B: Scheduled refresh + warehouse incrementals
- Keep Power BI refresh scheduled (e.g., every 30 minutes).
- Run `src/incremental_refresh.py` (or production ELT) on a tighter cadence.
- BI always reads the latest current-state tables.

### Option C: Streaming (executive tiles)
- For a true streaming experience, push aggregated KPIs to a streaming dataset.
- In production this would be fed by Kafka/Kinesis consumers writing to a metrics store.
