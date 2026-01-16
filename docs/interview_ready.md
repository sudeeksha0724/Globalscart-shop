# Interview-ready explanation (GlobalCart 360)

## How to explain the project (90 seconds)
- Built a single source of truth for revenue, margin, returns, shipping SLAs and payments using a PostgreSQL star schema.
- Standardized KPI definitions through warehouse views so SQL, Python, Excel and Power BI metrics stayed consistent.
- Delivered executive and operational dashboards with near real-time refresh assumptions.
- Performed retention analytics (RFM, churn, cohorts), quantified profit leakage drivers, and produced a revenue forecast to support inventory and marketing planning.

## STAR (example)
- Situation: Growth slowed while discounting increased; leadership lacked unified visibility across commercial and ops metrics.
- Task: Create scalable KPIs + dashboards and identify leakage + churn drivers.
- Action: Designed star schema, built KPI SQL, implemented Python segmentation + forecasting, and delivered dashboard specs.
- Result: Identified top leakage categories and SLA drivers; enabled prioritization of promo strategy and carrier/FC improvements.

## Questions you should be ready for
- Churn definition and why 90 days
- How you ensured KPI consistency across tools
- Why ARIMA vs a baseline regression
- How you would productionize near real-time refresh (watermarks, idempotent loads, partitioning)

## Near real-time interview talking points (incremental refresh)

### How did you handle near real-time data?
- Used an `updated_at` watermark strategy and incremental ELT.
- Landed deltas into staging tables and upserted into the star schema.
- Demonstrated KPI changes before/after refresh using KPI snapshots.

### How did you avoid full reloads?
- Idempotent upserts (`ON CONFLICT DO UPDATE`) with a safety condition: only update when incoming `updated_at` is newer.
- Staging tables are truncated per run (cheap) while warehouse facts are not.

### How did you handle late-arriving data?
- Returns/refunds arrive after the order; model supports late events via separate fact tables and incremental upserts.
- Status transitions (delayed shipments, returns) are handled as updates with auditing.

### How would this scale in production?
- CDC/streaming ingestion into bronze, then incremental transforms into curated star schema.
- Partition big facts by date, maintain aggregates, and use BI incremental refresh.
