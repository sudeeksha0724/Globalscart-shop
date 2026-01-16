# Milestone 4: Power BI Business Intelligence Integration (GlobalCart 360)

## 1) BI-ready Data Exposure (Postgres marts)

### Create marts
Run:

- `python3 -m src.run_sql --sql sql/06_bi_marts.sql`

This creates 5 **materialized views** in schema `globalcart`:

- `globalcart.mart_exec_daily_kpis`
- `globalcart.mart_finance_profitability`
- `globalcart.mart_funnel_conversion`
- `globalcart.mart_product_performance`
- `globalcart.mart_customer_segments`

### Refresh marts
After new data arrives, refresh materialized views:

- SQL: `SELECT globalcart.refresh_bi_marts();`

(You can schedule this via cron / Airflow / db job, or run manually.)

### Key design rules
- **Clean date grain**: marts use `date_id` (YYYYMMDD) and `date_value` from `globalcart.dim_date`.
- **Surrogate keys**: marts include a stable SK (e.g. `*_sk`) computed as `md5(...)` of their natural key(s).
- **Power BI friendly**:
  - One row per grain (e.g. per day, per order, per day-channel-device)
  - Explicit `date_id` and/or `*_date_id` columns for relationships to `dim_date`

## 2) Recommended Power BI Semantic Model (Star)

### Suggested tables to import
- **Dimensions**:
  - `globalcart.dim_date`
  - `globalcart.dim_geo`
  - `globalcart.dim_product`
  - `globalcart.dim_customer`

- **Facts / Marts**:
  - `globalcart.mart_exec_daily_kpis` (daily executive KPIs)
  - `globalcart.mart_finance_profitability` (order-level profitability)
  - `globalcart.mart_funnel_conversion` (daily funnel by channel/device)
  - `globalcart.mart_product_performance` (daily product perf + leakage)
  - `globalcart.mart_customer_segments` (customer segments + value quartiles)

### Relationships (recommended)
- `dim_date[date_id]` 1—* `mart_exec_daily_kpis[date_id]`
- `dim_date[date_id]` 1—* `mart_finance_profitability[date_id]`
- `dim_date[date_id]` 1—* `mart_funnel_conversion[date_id]`
- `dim_date[date_id]` 1—* `mart_product_performance[date_id]`

- `dim_customer[customer_id]` 1—* `mart_finance_profitability[customer_id]`
- `dim_geo[geo_id]` 1—* `mart_finance_profitability[geo_id]`
- `dim_product[product_id]` 1—* `mart_product_performance[product_id]`

- `dim_geo[geo_id]` 1—* `mart_customer_segments[geo_id]`
- `dim_customer[customer_id]` 1—1 `mart_customer_segments[customer_id]`

## 3) Power BI Connectivity (PostgreSQL Connector)

### Connection details
Use the **PostgreSQL database** connector:

- **Host**: `PGHOST` (default `localhost`)
- **Port**: `PGPORT` (default `5432`)
- **Database**: `PGDATABASE` (default `globalcart`)
- **Schema**: `globalcart`
- **Username**: `PGUSER` (default `globalcart`)
- **Password**: `PGPASSWORD` (default `globalcart`)

These values are read from `globalcart-360/.env`.

### Import vs DirectQuery
- **Import**: recommended for fastest visuals and easiest modeling.
- **DirectQuery**: use if you require near real-time analytics (you may need indexing and careful DAX).

## 4) Optional CSV Exports (API)

Admin-only CSV export endpoint:

- `GET /api/admin/bi/marts/{mart_name}.csv?limit=50000`

Allowed `{mart_name}`:
- `mart_exec_daily_kpis`
- `mart_finance_profitability`
- `mart_funnel_conversion`
- `mart_product_performance`
- `mart_customer_segments`

Auth:
- `X-Admin-Key: <ADMIN_KEY>`

## 5) Dashboard Deliverables (Recommended)

For detailed page-by-page build specs (full-length dashboard), use:
- `dashboards/powerbi/revenue_growth_intelligence_spec.md`
- `dashboards/powerbi/funnel_revenue_leakage_spec.md`
- `dashboards/powerbi/customer_analytics_rfm_retention_spec.md`
- `dashboards/powerbi/product_intelligence_spec.md`
- `dashboards/powerbi/operational_efficiency_spec.md`

### Executive KPI Overview
- Cards: Revenue, Orders, AOV, Gross Profit, Net Profit, Gross Margin %, Net Margin %, Active Customers
- Trend: Revenue + Orders by day
- Waterfall: Profit leakage proxy (Discounts + Shipping + Refunds + Gateway fees)

### Revenue & Profitability
- Order profitability distribution
- Net margin by Channel / Region
- Top loss-making orders (filters)

### Product & Category Performance
- Revenue / Units / Gross Profit by Category L1/L2
- Discount-heavy products
- Returns + refund by product/category

### Funnel & Conversion
- Daily funnel conversion (views → add_to_cart → checkout → payment → order)
- Split by channel/device

### Payment Failure & Leakage
- Payment failure rate (by method/provider if imported)
- Revenue at risk
- Cart abandonment revenue proxy

### Customer Segments / Repeat Behavior
- Segment counts (Prospect / One-time / Repeat)
- Revenue / profit by acquisition channel
- Value quartiles

## 6) DAX Measures (Recommended)

Assuming measures are built on marts:

- Full measures list: `dashboards/powerbi/dax_measures.md`

- `Net Revenue = SUM(mart_finance_profitability[revenue_ex_tax])`
- `Orders = DISTINCTCOUNT(mart_finance_profitability[order_id])`
- `AOV = DIVIDE([Net Revenue], [Orders])`

- `Gross Profit = SUM(mart_finance_profitability[gross_profit_ex_tax])`
- `Net Profit = SUM(mart_finance_profitability[net_profit_ex_tax])`
- `Gross Margin % = DIVIDE([Gross Profit], [Net Revenue])`
- `Net Margin % = DIVIDE([Net Profit], [Net Revenue])`

- `Repeat Customers = CALCULATE(DISTINCTCOUNT(mart_customer_segments[customer_id]), mart_customer_segments[repeat_customer_flag] = TRUE())`
- `Customers = DISTINCTCOUNT(mart_customer_segments[customer_id])`
- `Repeat Purchase Rate = DIVIDE([Repeat Customers], [Customers])`

- `Contribution Profit = [Net Profit]`  
  (already includes shipping, refunds, gateway fees in `mart_finance_profitability`)

### LTV estimate (simple)
A pragmatic estimate (demo-friendly):

- `LTV Estimate = AVERAGE(mart_customer_segments[revenue_ex_tax])`

Better (requires assumptions):
- `LTV Estimate = [AOV] * (1 + [Repeat Purchase Rate])`  
  (or multiply by an assumed horizon)

## 7) Sample PBIX model structure (how to build)

In Power BI Desktop:

1. Get Data → PostgreSQL database
2. Select schema `globalcart`
3. Import:
   - `dim_date`, `dim_geo`, `dim_product`, `dim_customer`
   - `mart_exec_daily_kpis`, `mart_finance_profitability`, `mart_funnel_conversion`, `mart_product_performance`, `mart_customer_segments`
4. Create relationships as listed above
5. Create measures from Section 6
6. Build pages:
   - Exec Overview
   - Finance
   - Product
   - Funnel
   - Payment/Leakage
   - Customer Segments

## 8) Refresh instructions

### Manual refresh
- Home → Refresh

### Scheduled refresh (Power BI Service)
- Publish PBIX
- Configure data source credentials for PostgreSQL
- Set a refresh schedule
- If you refresh marts via `refresh_bi_marts()`, schedule that job before the dataset refresh.
