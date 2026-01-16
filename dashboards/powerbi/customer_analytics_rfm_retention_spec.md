# Customer Analytics (RFM + Retention) (Power BI Page)

## Goal
Segment customers, track retention, and identify high-value and churn-risk customers.

## Primary tables (recommended)
- `globalcart.mart_customer_segments`
- `globalcart.mart_finance_profitability` (for customer revenue/profit breakdowns)
- `globalcart.dim_customer`
- `globalcart.dim_geo`
- `globalcart.dim_date`

## KPIs
- Customers
- Active Customers
- Repeat Purchase Rate
- Average Revenue per Customer (proxy LTV)
- Churn-risk Customers (rule-based)

## Core segmentation
Use existing `mart_customer_segments[lifecycle_segment]`:
- PROSPECT
- ONE_TIME
- REPEAT

Add RFM-style segmentation (Power BI calculated columns or measures)
- Recency: days since last order
- Frequency: number of orders
- Monetary: total revenue

Suggested segment labels (rule-based)
- New: orders = 1 and recency <= 30
- Returning: orders >= 2 and recency <= 60
- Loyal: orders >= 3 and value_quartile = 1
- Churn-risk: orders >= 2 and recency > 60
- High-value: value_quartile = 1 and revenue_ex_tax high

## Visuals
1) Customer segment distribution
- Donut / bar: count of customers by lifecycle_segment / custom segment

2) RFM scatter
- Scatter:
  - X = Recency Days (lower is better)
  - Y = Monetary (revenue)
  - Size = Frequency (orders)

3) Retention proxy
- Line chart:
  - Repeat Purchase Rate over time (if you model cohorts) OR
  - Active Customers trend (daily) from mart_exec_daily_kpis

4) Geo breakdown
- Map: customers or revenue by country/region

## Slicers
- Date range
- Region/Country
- Acquisition channel
- Lifecycle segment
