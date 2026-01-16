# Revenue & Growth Intelligence (Power BI Page)

## Goal
Executive-grade view of revenue health, growth, and early warning signals.

## Primary tables (recommended)
- `globalcart.mart_exec_daily_kpis` (daily KPIs)
- `globalcart.mart_finance_profitability` (order-level finance)
- `globalcart.dim_date`
- `globalcart.dim_geo`
- `globalcart.dim_product`

## KPI cards (top row)
- Net Revenue
- Orders
- AOV
- Gross Profit
- Net Profit
- Gross Margin %
- Growth % vs last period (month or week)

## Visuals
1) Revenue trend (time series)
- Line: Daily Net Revenue by `dim_date[date_value]`
- Add analytics:
  - Forecast (next 30–60 days) from Analytics pane
  - Anomaly detection (Analytics pane) OR show anomaly flags

2) Orders vs Returns comparison
- Combo chart:
  - Column: Orders (daily)
  - Line: Refund Amount (daily) or Return Lines

3) Revenue by category (contribution)
- Waterfall:
  - Start: Net Revenue
  - Subtract: Discounts, Shipping Cost, Refund Amount, Gateway Fees
  - End: Net Revenue After Leakage (proxy)

4) Category contribution (share)
- Stacked bar or treemap:
  - Value: Net Revenue
  - Group: `dim_product[category_l1]` / `category_l2`

## Slicers
- Date (dim_date)
- Channel (from marts)
- Region/Country (dim_geo)
- Category L1/L2 (dim_product)

## “Advanced insights” implementation notes
- Growth drivers:
  - Decomposition Tree: Net Revenue → Category → Channel → Country
- Seasonality impact:
  - Add a line for a moving average (7/30 day) and compare WoW/MoM measures
- Revenue anomalies:
  - Either use Analytics pane anomalies or a Z-score measure
