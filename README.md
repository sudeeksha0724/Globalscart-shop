# GlobalCart 360: Real-Time E-Commerce Profitability, Retention & Demand Forecasting

GlobalCart 360 is an end-to-end, MNC-level analytics project for a global e-commerce business. It delivers a **single source of truth** (PostgreSQL star schema), **near real-time KPIs**, **customer retention analytics** (RFM + churn + cohorts), **profit leakage analysis**, **revenue/demand forecasting**, a **demo-ready customer storefront with funnel tracking**, and an **admin dashboard**.

## Tech Stack
- SQL: PostgreSQL
- Python: FastAPI, pandas, numpy, seaborn/matplotlib, scikit-learn, statsmodels
- Frontend: HTML/CSS/JavaScript with Bootstrap, voice search
- Excel: KPI + pivot-based management report (generated/extracted from the same KPI definitions)
- Power BI / Tableau: dashboard specs + DAX measures (ready to implement in BI)

## Repository Structure
- `sql/`: star schema DDL, views, KPI queries, BI marts
- `src/`: data generator, loaders, extractors, analytics pipeline
- `backend/`: FastAPI server for admin/customer APIs and web UIs
- `frontend/`: customer storefront (/shop) and admin UI assets
- `notebooks/`: EDA, RFM segmentation, forecasting (notebook-friendly)
- `docs/`: data dictionary, KPI definitions, architecture
- `dashboards/`: Power BI/Tableau specs + DAX measures
- `data/`: generated raw and processed extracts (created at runtime)

## Step-by-step (Local + Public URL)

### 0) Prerequisites
- Python 3
- Docker + Docker Compose
- `cloudflared` installed (for public URL)

### 1) Start PostgreSQL (Docker)
From the repo root:

```bash
docker compose up -d
```

### 2) Create venv + install Python deps
From the `globalcart-360` folder:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3) Generate synthetic (realistic) data

```bash
python -m src.generate_data --scale small
```

### 4) Load into PostgreSQL + build views

```bash
python -m src.load_to_postgres
python -m src.run_sql --sql sql/02_views.sql
```

### 5) (Optional) Enable OTP Sign-in tables
Only needed if you want OTP-based auth endpoints:

```bash
python3 -m src.run_sql --sql sql/07_app_auth.sql
```

### 6) Start the FastAPI backend (serves Shop + Admin)

```bash
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

### 7) Open the local URLs
- Shop: http://localhost:8000/shop/
- Admin: http://localhost:8000/admin/

### 8) Admin login
- Default Admin Username: `admin`
- Default Admin Password: `admin`

### 9) Make it public (Cloudflare Quick Tunnel)
In a new terminal (keep backend still running):

```bash
cloudflared tunnel --url http://127.0.0.1:8000
```

### 10) Open the public URLs
Current public URL:
- https://accessed-taken-grande-houston.trycloudflare.com

Then open:
- Shop: https://accessed-taken-grande-houston.trycloudflare.com/shop/
- Admin: https://accessed-taken-grande-houston.trycloudflare.com/admin/

Note: this `trycloudflare.com` URL **changes whenever you restart** `cloudflared`.

### 11) Want the same URL always?
Use a custom domain + Cloudflare **named tunnel** (stable URL).

### Troubleshooting
- If UI pages are not loading, confirm the backend is running on `http://127.0.0.1:8000`.
- If the public URL stops working, restart the quick tunnel command and use the new printed `trycloudflare.com` URL.

## One-command pipeline
After PostgreSQL is running:
```bash
python -m src.pipeline --scale small --truncate
```

## Near real-time incremental refresh (simulation)
This simulates a production-style incremental load with:
- new orders/payments/shipments
- late-arriving returns/refunds
- status updates (delivered → delayed, delivered → completed)
- `updated_at` watermark and idempotent upserts

### 1) Ensure incremental objects exist (staging + upsert functions)
```bash
python -m src.run_sql --sql sql/04_incremental_refresh.sql --stop-on-error
```

### (Optional) Enable OTP Sign-in (Amazon-like)
Create auth tables used by `/api/auth/request-otp` and `/api/auth/verify-otp`:

```bash
python3 -m src.run_sql --sql sql/07_app_auth.sql
```

### 2) Snapshot KPIs (before)
Run in psql / any SQL client:
```sql
SELECT globalcart.snapshot_kpis('before');
```

### 3) Run incremental refresh
```bash
python -m src.incremental_refresh --since_timestamp "2025-12-19T12:00:00"
```

### 4) Snapshot KPIs (after) and compare
```sql
SELECT globalcart.snapshot_kpis('after');
\i sql/05_before_after_kpis.sql
```

## Power BI Integration (BI Marts)
### 1) Create BI materialized marts for Power BI
```bash
python -m src.run_sql --sql sql/06_bi_marts.sql
```

### 2) Refresh BI marts after new data
```sql
SELECT globalcart.refresh_bi_marts();
```

### 3) Power BI connection
- Use PostgreSQL connector with `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD` from `.env`
- Import tables: `mart_exec_daily_kpis`, `mart_finance_profitability`, `mart_funnel_conversion`, `mart_product_performance`, `mart_customer_segments`
- See `dashboards/powerbi/powerbi_bi_integration.md` for detailed setup and DAX measures.

## KPI Consistency
KPI definitions are centralized in:
- `docs/kpi_definitions.md`
- SQL views in `sql/02_views.sql`

Dashboards and Python reuse the same definitions.

## Notes
- Default `--scale small` generates a sample sized dataset for laptops.
- The schema and scripts are designed to scale conceptually to 100M+ orders/year with incremental/streaming ingestion patterns documented in `docs/architecture.md`.
