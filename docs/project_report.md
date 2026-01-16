# GlobalCart 360 — Project Report (Interview Ready)

## 1) 10-minute project explanation (talk track)

### 0:00 – 1:00 | What this project is
GlobalCart 360 is an end-to-end e-commerce analytics + demo storefront project.
It combines a PostgreSQL star-schema “single source of truth”, near real-time KPIs, retention analytics (RFM/cohorts/churn), profitability & leakage analytics, demand/forecasting notebooks, and a working customer-facing shop UI with funnel tracking.
It also includes an Admin dashboard that reads from the same metrics/views so the demo feels production-like.

### 1:00 – 2:30 | What problem it solves
In many e-commerce setups, operational data exists but:
- business KPIs are inconsistent across dashboards,
- profitability is unclear because shipping/refunds/payment failures leak revenue,
- retention/churn signals are not operationalized,
- product demand decisions are made without clean historical trends.

This project addresses those gaps by:
- standardizing KPI definitions in SQL views,
- building an analytics-ready warehouse schema,
- simulating incremental refresh (production-like ingestion),
- exposing both customer and admin UIs that use the same backend APIs.

### 2:30 – 4:00 | End-to-end architecture (high level)
The architecture is split into 4 layers:
1) **Data + Warehouse (PostgreSQL)**
   - Star schema in `globalcart` schema.
   - Views for KPIs, orders summary, funnel metrics.

2) **Data generation + pipelines (Python in `src/`)**
   - Synthetic data generation with realistic relationships.
   - Loaders into Postgres.
   - SQL runner for schema/views.
   - Optional incremental refresh simulation.

3) **Backend APIs (FastAPI in `backend/`)**
   - Customer APIs: authentication, products, cart/checkout/orders.
   - Admin APIs: KPIs, orders monitor, audit log, funnel analytics, product analytics.
   - Serves static frontend pages for Shop and Admin.

4) **Frontends (HTML/CSS/JS in `frontend/`)**
   - Shop storefront `/shop/`.
   - Admin dashboard `/admin/`.
   - Both call backend APIs.

### 4:00 – 6:00 | What happens during a user journey (Shop)
A typical flow is:
- Customer opens `/shop/`.
- The frontend JS calls backend APIs (products, auth, cart, orders).
- When checkout happens, an order is created in the database.
- Funnel events can be tracked (sessions, add-to-cart, checkout started, payment attempted/failed, order placed).

This is useful because the admin dashboard can later show:
- total orders, revenue,
- funnel conversion and leakage,
- top products performance,
- order monitoring.

### 6:00 – 7:30 | Admin view and business insights
Admin dashboard (`/admin/`) uses protected admin endpoints.
It supports:
- KPIs snapshot visualization,
- Orders monitor (order status, net amount, customer identifiers like email),
- Funnel and revenue leakage summary,
- Audit log and journey replay.

### 7:30 – 9:00 | Analytics & modeling outputs
On top of the warehouse:
- EDA and outlier analysis
- RFM segmentation for retention strategy
- cohort/churn tracking
- forecasting notebooks/scripts

These outputs are designed to be consistent with the same KPI definitions used by the dashboards.

### 9:00 – 10:00 | Deployment/demo and what I would do next
For demo/public access, the FastAPI server can be exposed using **Cloudflare Tunnel (Quick Tunnel)**, generating a temporary `trycloudflare.com` public URL.

If extending further:
- Use a custom domain + named tunnel for stable URL.
- Add role-based auth, pagination/filtering for admin order management.
- Add proper CI, unit tests for critical KPI queries.

---

## 2) Tech, languages, tools, and skills used

### Languages
- Python
- SQL
- JavaScript
- HTML/CSS

### Frameworks / Libraries
- **FastAPI** (backend API server)
- **Uvicorn** (ASGI server)
- **PostgreSQL** (warehouse + analytics DB)
- **Bootstrap** (frontend styling)
- Data/analytics stack: pandas, numpy, matplotlib/seaborn, scikit-learn, statsmodels (see `requirements.txt`)

### Tooling
- Docker + Docker Compose (local Postgres)
- Cloudflare Tunnel (`cloudflared`) for public demo URL
- Git (typical repo workflow)

### Skills demonstrated
- Data modeling (star schema)
- KPI standardization and governance via SQL views
- Backend API design (FastAPI routing, auth patterns)
- Frontend integration with APIs
- Incremental refresh simulation (production-like ingestion mindset)
- Analytics: retention (RFM/cohorts/churn), profitability analysis, forecasting
- Debugging + UX fixes (intro animation + redirect correctness)

---

## 3) How components connect (backend ↔ frontend ↔ database)

### Database layer (PostgreSQL)
- Schema and base objects are created via SQL scripts in `sql/`.
- Views (like `vw_admin_order_summary`, KPI views) are created/updated via `sql/02_views.sql`.

### Pipeline layer (`src/`)
- `src/generate_data.py` creates realistic synthetic datasets.
- `src/load_to_postgres.py` loads generated data into Postgres.
- `src/run_sql.py` applies SQL files (schema/views/refresh logic).
- `src/pipeline.py` is a one-command orchestrator.
- `src/incremental_refresh.py` simulates near real-time incremental ingestion.

### Backend layer (`backend/`)
- FastAPI app entry point: `backend/main.py`.
- DB connectivity: `backend/db.py`.
- Request/response models: `backend/models.py` (Pydantic models).
- API routes are grouped in `backend/routes/`.

### Frontend layer (`frontend/`)
- Shop UI (customer-facing): `frontend/shop/`.
- Admin UI: `frontend/admin/`.
- Frontends are static HTML pages that call backend APIs using fetch.

### Data flow summary
1) User opens `/shop/` or `/admin/`.
2) Browser loads static HTML/CSS/JS.
3) JavaScript calls backend endpoints (e.g., `/api/...`).
4) Backend reads/writes Postgres (warehouse tables + views).
5) Backend returns JSON, frontend renders UI.

---

## 4) Hosting / public access (what we used)

### Local hosting
- FastAPI is started with Uvicorn on port `8000`.
- The app serves:
  - Shop: `/shop/`
  - Admin: `/admin/`

### Public demo URL
- Used **Cloudflare Quick Tunnel**:

```bash
cloudflared tunnel --url http://127.0.0.1:8000
```

- This produces a public URL like:
  - `https://<random>.trycloudflare.com`

Important note:
- This URL **changes when `cloudflared` restarts**.

### Optional stable hosting approach (next step)
- Buy/own a domain and set up Cloudflare DNS.
- Create a **named tunnel** and map a stable subdomain like `shop.yourdomain.com`.

---

## 5) File-by-file overview (what each key file contains)

### Repo root
- `README.md`
  - Step-by-step run guide for local + public demo.
- `docker-compose.yml`
  - Runs Postgres locally via Docker.
- `requirements.txt`
  - Python dependencies.

### `sql/` (database schema, views, marts)
- `sql/00_schema.sql`
  - Base schema/tables for warehouse.
- `sql/02_views.sql`
  - Core KPI and admin/customer views.
- `sql/03_kpi_queries.sql`
  - KPI query definitions.
- `sql/04_incremental_refresh.sql`
  - Objects/functions to simulate incremental refresh.
- `sql/06_bi_marts.sql`
  - BI marts for Power BI-style consumption.
- `sql/07_app_auth.sql`
  - App auth tables (`app_users`, OTP tables, etc.).
- `sql/08_add_order_address.sql`
  - Adds order address fields like recipient name to orders.
- `sql/09_customer_addresses.sql`
  - Customer addresses table.
- `sql/10_shop_features.sql`
  - Additional shop-related tables/indexes.

### `src/` (data generation + pipeline)
- `src/generate_data.py`
  - Generates synthetic e-commerce data with realistic patterns.
- `src/load_to_postgres.py`
  - Loads generated data to Postgres.
- `src/run_sql.py`
  - Applies SQL scripts to Postgres.
- `src/pipeline.py`
  - Orchestrates generation + loading + views + analytics.
- `src/incremental_refresh.py`
  - Simulates near real-time refresh (new events, late arrivals, upserts).
- `src/export_kpis.py`
  - Exports KPI datasets for BI.
- `src/generate_excel_report.py`
  - Produces an Excel management report extract.
- `src/analytics/*`
  - EDA, RFM, churn/cohort, forecasting modules.

### `backend/` (FastAPI server)
- `backend/main.py`
  - FastAPI app, middleware, mounting static frontend paths.
- `backend/db.py`
  - Connection handling helpers.
- `backend/models.py`
  - Pydantic models for API requests/responses.
- `backend/routes/*`
  - Modular API routes (customer + admin + auth + orders + analytics).

### `frontend/` (web UI)
- `frontend/shop/`
  - Customer storefront pages and scripts.
  - Main JS orchestration: `frontend/shop/shop.js`.
- `frontend/admin/`
  - Admin dashboard pages.
  - Main JS orchestration: `frontend/admin/app.js`.

### `docs/`
- `docs/architecture.md`
  - High-level architecture notes.
- `docs/kpi_definitions.md`
  - KPI definition documentation.
- `docs/data_dictionary.md`
  - Data dictionary.
- `docs/interview_ready.md`
  - Existing interview notes.

---

## 6) How to run (reference)

### Local
1) Start Postgres:

```bash
docker compose up -d
```

2) Create venv and install deps:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

3) Generate + load data + build views:

```bash
python -m src.generate_data --scale small
python -m src.load_to_postgres
python -m src.run_sql --sql sql/02_views.sql
```

4) Start backend:

```bash
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

5) Open:
- http://localhost:8000/shop/
- http://localhost:8000/admin/

### Public demo
Run quick tunnel:

```bash
cloudflared tunnel --url http://127.0.0.1:8000
```

Then open the printed `trycloudflare.com` URL + `/shop/` or `/admin/`.

---

## 7) Suggested interview Q&A (quick answers)

### “What makes this project strong?”
- It’s end-to-end: warehouse + KPIs + analytics + backend APIs + UI.
- KPI definitions are centralized and reused (reduces dashboard mismatch).
- Shows production thinking via incremental refresh simulation.

### “What were the hardest issues?”
- Preventing stale frontend caching and fixing redirect bugs.
- Ensuring consistent assets across pages.
- Providing a shareable public demo URL via Cloudflare Tunnel.

### “What would you improve next?”
- Stable custom domain deployment.
- More automated tests around KPI queries and critical endpoints.
- Better admin order search/filter/export.

---

# Appendix A — Detailed Architecture (deep dive)

## A1) Layered system view

### A1.1) Data / Warehouse layer (PostgreSQL)
This is the “single source of truth” for:
- Orders, order items, payments, shipments, returns
- Customer and product dimensions
- Funnel events (session-based user behavior)

The key principle is **analytics-ready modeling**:
- Facts contain measurable events/transactions (orders, payments, shipments, returns, funnel events).
- Dimensions contain descriptive context (customer, product, geo, fulfillment center).

### A1.2) ELT / Pipeline layer (`src/`)
This layer:
- Generates synthetic data (for demo purposes)
- Loads it into Postgres tables
- Builds semantic views for consistent KPI computation
- Optionally simulates incremental refresh (late arriving data, status changes, etc.)

The goal is to demonstrate production-style thinking:
- repeatable runs
- idempotent updates
- incremental refresh design

### A1.3) Backend service layer (`backend/`)
FastAPI exposes:
- Shop APIs (products, auth, cart/checkout/orders)
- Admin APIs (KPIs, orders monitor, audit log, funnel, analytics charts)

Backend is responsible for:
- reading/writing Postgres
- enforcing admin/customer access patterns
- shaping responses for the UI (Pydantic models)
- serving the Shop/Admin static frontends

### A1.4) Presentation layer (`frontend/`)
Two UIs:
- **Shop UI** (`/shop/`): customer browsing, cart, checkout, orders
- **Admin UI** (`/admin/`): monitoring and analytics

Both are static HTML/CSS/JS and call APIs using `fetch`.

## A2) End-to-end request lifecycle

### A2.1) Shop page load
1) Browser requests `GET /shop/`.
2) FastAPI serves static `index.html` from `frontend/shop/`.
3) `shop.js` loads and calls APIs like:
   - `GET /api/customer/products`
   - `GET /api/customer/cart?...`
4) API reads Postgres and returns JSON.
5) UI renders catalog/cart.

### A2.2) Checkout
1) Shop frontend sends a checkout/order create request to backend.
2) Backend validates request + writes:
   - order record in `fact_orders`
   - item records in `fact_order_items`
   - (optional) payment attempt records in `fact_payments`
3) Backend returns order id + status.
4) Frontend navigates to confirmation/order details.

### A2.3) Admin monitoring
1) Admin opens `GET /admin/`.
2) Admin UI JS fetches:
   - `GET /api/admin/kpis/latest`
   - `GET /api/admin/orders`
   - `GET /api/admin/funnel/summary`
3) Backend queries views like `vw_admin_order_summary`, `vw_admin_kpis`, funnel views.
4) Admin UI renders tables and summary panels.

---

# Appendix B — Database Design (star schema explanation)

This section is designed for interviews. You can explain the warehouse in a structured way: **dimensions**, **facts**, then **semantic views**.

## B1) Dimensions (who/what/where)

### B1.1) `globalcart.dim_geo`
Purpose:
- Geographic and currency context for customers/orders.

Typical fields:
- `country`, `region`, `city`, `currency`

Why it matters:
- Enables geo-level breakdowns (country, city) and currency segmentation.

### B1.2) `globalcart.dim_fc`
Purpose:
- Fulfillment center (warehouse) where shipments originate.

Key fields:
- `fc_name`, `geo_id`, `timezone`

Why it matters:
- SLA breach analysis and shipping cost differences per fulfillment center.

### B1.3) `globalcart.dim_customer`
Purpose:
- Customer master dimension for analytics.

Key fields:
- `geo_id` (where the customer belongs)
- `acquisition_channel` (marketing channel attribution)
- `customer_created_ts`

Why it matters:
- Cohort analysis, RFM segmentation, churn calculations.

### B1.4) `globalcart.dim_product`
Purpose:
- Product master dimension.

Key fields:
- `sku`, `product_name`, `category_l1`, `category_l2`, `brand`
- `unit_cost`, `list_price`

Why it matters:
- Profitability (margin) depends on cost vs sell price.
- Category contribution and top-products analyses require consistent product attributes.

### B1.5) `globalcart.dim_date`
Purpose:
- Standard date dimension for time intelligence.

Why it matters:
- Enables consistent time-based aggregations (month, quarter, week, weekday).

## B2) Facts (measurable events)

### B2.1) `globalcart.fact_orders`
Grain:
- 1 row per order.

Key fields:
- `order_ts`, `order_status`, `channel`, `currency`
- `gross_amount`, `discount_amount`, `tax_amount`, `net_amount`

Common interview explanation:
- Orders represent the primary revenue event.
- By storing gross/discount/tax/net, we can compute revenue metrics without recomputing item-level rollups.

### B2.2) `globalcart.fact_order_items`
Grain:
- 1 row per product line item per order.

Key fields:
- `qty`, `unit_list_price`, `unit_sell_price`, `unit_cost`
- `line_discount`, `line_tax`, `line_net_revenue`

Why it matters:
- Profitability is most accurate at item-level.
- Lets you compute category/brand contribution and margin.

### B2.3) `globalcart.fact_payments`
Grain:
- 1 row per payment attempt/transaction.

Key fields:
- `payment_method`, `payment_provider`, `payment_status`
- `gateway_fee_amount`, `refund_amount`, `chargeback_flag`
- timestamps for authorized/captured

Why it matters:
- Payment failures create conversion leakage.
- Gateway fees and chargebacks affect finance P&L.

### B2.4) `globalcart.fact_shipments`
Grain:
- 1 row per shipment.

Key fields:
- `fc_id`, `carrier`
- `promised_delivery_dt`, `delivered_dt`
- `shipping_cost`, `sla_breached_flag`

Why it matters:
- SLA breaches correlate with returns/refunds and churn.
- Shipping cost is a major component of profit leakage.

### B2.5) `globalcart.fact_returns`
Grain:
- 1 row per return event per item.

Key fields:
- `return_reason`, `refund_amount`, `return_status`, `restocked_flag`

Why it matters:
- Returns are realized revenue leakage.
- Enables return rate proxy and refund totals.

### B2.6) `globalcart.fact_funnel_events`
Grain:
- 1 row per funnel event.

Key fields:
- `session_id`, `event_ts`, `stage`
- optional `customer_id`, `product_id`, `order_id`
- `channel`, `device`, optional `failure_reason`

Interview framing:
- Funnel analytics is evaluated at session level (not raw event counts).
- This avoids over-counting repeated events and matches how product analytics teams measure conversion.

## B3) Semantic views (KPI governance)

### B3.1) Why views?
In analytics, mismatched KPI definitions cause “dashboard wars”.
This project centralizes KPI logic inside Postgres views so:
- Admin UI, Python analytics, and BI tools reuse the same calculations.

### B3.2) Examples of semantic views
- `vw_orders_core` and `vw_orders_completed`
- `vw_item_profitability`
- `vw_funnel_daily_metrics`
- `vw_revenue_leakage`

---

# Appendix C — KPI Logic (how KPIs are computed)

This section explains the logic in words so you can speak confidently in interviews.

## C1) Order revenue metrics
- **Gross Amount**: before discounts and taxes.
- **Discount Amount**: order-level discount.
- **Tax Amount**: order tax.
- **Net Amount**: after discounts, includes tax.
- **Net Revenue (ex tax)**: `net_amount - tax_amount`.

## C2) Profitability
Profitability is item-based:
- `line_cogs = qty * unit_cost`
- `line_gross_profit = line_net_revenue - line_cogs`

Then aggregated by:
- day, category, brand, customer segment, etc.

## C3) Operations
- SLA breach rate is computed from shipments:
  - `breached_shipments / total_shipments`
- Shipping cost leakage:
  - `sum(shipping_cost) / sum(net_revenue_ex_tax)`

## C4) Returns & refunds
- Refund leakage is realized loss:
  - `sum(refund_amount)` from `fact_returns`

## C5) Funnel conversion
Conversion is **session-based**:
- Sessions with `VIEW_PRODUCT` are the top-of-funnel.
- Sessions with `ORDER_PLACED` are the converted sessions.

Rates:
- `conversion_rate = ordered_sessions / viewed_sessions`
- `cart_abandonment_rate = (added_sessions - checkout_sessions) / added_sessions`
- `payment_failure_rate = failed_sessions / payment_attempt_sessions`

## C6) Revenue leakage (pre-purchase + post-purchase)
Project splits leakage into:
- **Refund leakage** (post-purchase, realized)
- **Cart abandonment loss** (pre-purchase, estimated)
- **Payment failure loss** (pre-purchase, estimated)

The SQL view `vw_revenue_leakage` combines them into:
- `net_revenue_after_leakage`

---

# Appendix D — Backend API Design (deep dive)

This section is written so you can explain the backend like a production service.

## D1) FastAPI entrypoint and routing
Entry point: `backend/main.py`

Key responsibilities:
- loads environment variables (`.env`)
- mounts routers
- mounts static files for `/shop`, `/admin`, `/assets`, `/static`
- sets middleware for request ID logging and cache-control behavior

Key routers:
- `api_customer` (shop APIs)
- `api_auth` (login/signup)
- `api_admin` (admin monitoring)
- `api_events` (funnel tracking)

## D2) Admin auth approach
Admin endpoints require header:
- `X-Admin-Key`

Server checks it against `ADMIN_KEY` env.

This is intentionally lightweight for a demo; in a real system you’d use:
- JWTs
- OAuth / SSO
- role-based permissions

## D3) Admin endpoints (examples)

### D3.1) Orders Monitor
Endpoint:
- `GET /api/admin/orders?limit=...&offset=...`

Purpose:
- show latest orders with status and customer identifiers.

Data sources:
- `vw_admin_order_summary`
- `app_users` for email

### D3.2) KPIs latest
Endpoint:
- `GET /api/admin/kpis/latest`

Purpose:
- fetch latest KPI snapshot.

### D3.3) Funnel summary
Endpoint family:
- `GET /api/admin/funnel/summary`
- `GET /api/admin/funnel/product-leakage`
- `GET /api/admin/funnel/payment-failures`

Purpose:
- conversion and leakage reporting.

## D4) Customer endpoints (examples)

### D4.1) Auth
Endpoints:
- `POST /api/auth/login`
- OTP flows (optional)

### D4.2) Products
Endpoints:
- list products
- product details

### D4.3) Orders
Endpoints:
- create order
- list orders per customer
- order detail

---

# Appendix E — Frontend Design (deep dive)

## E1) Why static HTML + JS?
The goal is to keep it demo-friendly and easy to run:
- no complex build tooling required
- FastAPI can directly serve static assets
- focus is on architecture, analytics, and integration

## E2) Shop UI (`frontend/shop/`)

### E2.1) Main script: `shop.js`
Responsibilities:
- API client wrapper (`fetch` helpers)
- customer auth state management
- navigation and redirect rules
- cart logic
- checkout logic
- order history and order details

### E2.2) UX detail: intro animation
The shop supports an intro animation overlay.
Important UX point:
- prevent content flash before animation by applying a class early in `<head>`.

### E2.3) Redirect correctness
Login redirects can cause wrong paths if `next` is malformed.
Fix was implemented using a normalization function to prevent `/shop/shop` errors.

## E3) Admin UI (`frontend/admin/`)

### E3.1) Main script: `frontend/admin/app.js`
Responsibilities:
- admin login UI
- store admin key in local storage
- call admin endpoints
- render KPI cards and tables

### E3.2) Orders monitor
Admin UI calls `GET /api/admin/orders`.
It renders:
- order id
- customer id
- customer email
- timestamps and amounts

---

# Appendix F — Deployment / Public Demo (deep dive)

## F1) Why Cloudflare Tunnel?
Problem:
- local demo server is not reachable from outside.

Cloudflare Tunnel provides:
- public HTTPS URL
- no router configuration
- works for quick demos

## F2) Quick Tunnel vs Named Tunnel

### Quick Tunnel
- command: `cloudflared tunnel --url http://127.0.0.1:8000`
- output: temporary `https://<random>.trycloudflare.com`
- limitation: URL changes on restart

### Named Tunnel (stable)
- requires Cloudflare account + a domain
- map stable hostname like `shop.globalscart.in` to your tunnel

---

# Appendix G — Troubleshooting & Debugging Stories (what I fixed)

Use this section during interviews when asked: “Tell me a bug you solved.”

## G1) Browser caching causing stale HTML/JS
Symptom:
- users saw old behavior even after code changes.

Root cause:
- browser caching (ETag / 304 Not Modified) returned stale HTML.

Fix:
- backend middleware sets `Cache-Control: no-store` for Shop/Admin HTML routes.

## G2) Intro animation content flash
Symptom:
- page content appears briefly before intro overlay.

Root cause:
- overlay was added after initial paint.

Fix:
- add early CSS/JS in `<head>` so the overlay is visible before first paint.

## G3) Bad redirect path (`/shop/shop`)
Symptom:
- login redirect produced `/shop/shop?intro=1` 404.

Root cause:
- `next=shop` was being treated as a relative file path incorrectly.

Fix:
- normalize `next` into `index.html` for `shop` / `/shop` / `/shop/`.

---

# Appendix H — Extended Interview Q&A (long form)

## H1) “How did you ensure KPI consistency?”
I centralized KPI definitions into SQL semantic views (and referenced them in documentation).
This prevents divergence between Python/BI/dashboards.

## H2) “How would you scale this to production?”
- Partition big fact tables by date.
- Add CDC/stream ingestion.
- Materialize heavy aggregations.
- Add role-based auth and observability.

## H3) “How do you handle late-arriving data?”
The incremental refresh design uses:
- staging tables
- idempotent upserts based on `updated_at`
- watermarks to only process new changes

## H4) “How do you estimate funnel leakage?”
I compute:
- session-based drop-offs
- estimate abandonment revenue loss using product list prices and observed sell/list ratio
- estimate payment failure loss using failed order items

## H5) “Why do you store both order-level and item-level revenue?”
- Order-level values simplify top-line reporting.
- Item-level values support accurate margin and category profitability.

## H6) “What tradeoffs did you make in this project?”
- Used static frontend (simpler demo) instead of React build.
- Used simple admin header key instead of full auth.
- Used Cloudflare quick tunnel for demo rather than full deployment.

