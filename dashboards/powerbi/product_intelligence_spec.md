# Product Intelligence (Power BI Page)

## Goal
Identify top products, low sellers (dead stock proxy), high return-rate items, and profit contribution.

## Primary tables (recommended)
- `globalcart.mart_product_performance`
- `globalcart.dim_product`
- `globalcart.dim_date`

## KPIs
- Units Sold
- Net Revenue
- Gross Profit
- Return Lines
- Return Rate (proxy)

## Visuals
1) Top products
- Bar: Top N products by Net Revenue / Units Sold

2) Pareto (80/20)
- Line + bar:
  - Bars: Net Revenue by product (sorted desc)
  - Line: Cumulative Revenue %

3) Heatmap
- Matrix/heatmap:
  - Rows: Category L1
  - Columns: Category L2
  - Values: Net Revenue / Gross Profit

4) ABC classification
- Table:
  - Product, revenue, cumulative %, ABC class

5) High return-rate products
- Bar:
  - Return Rate proxy by product/category

## Slicers
- Date
- Category L1/L2
- Brand

## Notes
- `mart_product_performance` includes leakage proxies:
  - abandoned add-to-cart sessions
  - revenue_lost_cart_abandonment
  - failed_orders + revenue_at_risk_ex_tax
