# Power BI DAX Measures (GlobalCart 360)

Assume model tables use the BI marts (`globalcart.mart_*`) and core dimensions.

Assumptions:
- `dim_date[date_value]` is the primary date column used in visuals/slicers.
- Relationships exist from `dim_date[date_id]` to each mart’s `date_id`.
- For product breakdowns, use `dim_product` related to `mart_product_performance`.

## Core
- `Net Revenue = SUM(mart_finance_profitability[revenue_ex_tax])`
- `Orders = DISTINCTCOUNT(mart_finance_profitability[order_id])`
- `AOV = DIVIDE([Net Revenue], [Orders])`

## Profitability (requires item table)
- `COGS = SUM(mart_finance_profitability[cogs])`
- `Gross Profit = SUM(mart_finance_profitability[gross_profit_ex_tax])`
- `Net Profit = SUM(mart_finance_profitability[net_profit_ex_tax])`
- `Gross Margin % = DIVIDE([Gross Profit], [Net Revenue])`
- `Net Margin % = DIVIDE([Net Profit], [Net Revenue])`
- `Contribution Profit = [Net Profit]`

## Returns / Refunds
- `Refund Amount = SUM(mart_exec_daily_kpis[refund_amount_return_dt])`
- `Return Lines = SUM(mart_exec_daily_kpis[return_lines])`

## Operations
- `Shipping Cost = SUM(mart_exec_daily_kpis[shipping_cost_attrib])`
- `SLA Breach % = AVERAGE(mart_exec_daily_kpis[sla_breach_pct])`
- `Shipping Cost % of Revenue = DIVIDE([Shipping Cost], [Net Revenue])`

## Retention (basic, computed in Power BI)
- `Customers = DISTINCTCOUNT(mart_customer_segments[customer_id])`
- `Active Customers (Daily) = SUM(mart_exec_daily_kpis[active_customers])`
- `Repeat Customers = CALCULATE(DISTINCTCOUNT(mart_customer_segments[customer_id]), mart_customer_segments[repeat_customer_flag] = TRUE())`
- `Repeat Purchase Rate = DIVIDE([Repeat Customers], [Customers])`
- `LTV Estimate = AVERAGE(mart_customer_segments[revenue_ex_tax])`

## Profit Leakage (executive waterfall)
- `Discount Amount = SUM(mart_exec_daily_kpis[discount_amount])`
- `Gateway Fees = SUM(mart_exec_daily_kpis[gateway_fee_amount])`
- `Leakage Total = [Discount Amount] + [Shipping Cost] + [Refund Amount] + [Gateway Fees]`

## Revenue & Growth Intelligence
- `Net Revenue MTD = TOTALMTD([Net Revenue], dim_date[date_value])`
- `Net Revenue QTD = TOTALQTD([Net Revenue], dim_date[date_value])`
- `Net Revenue YTD = TOTALYTD([Net Revenue], dim_date[date_value])`

- `Net Revenue (Prev Month) = CALCULATE([Net Revenue], DATEADD(dim_date[date_value], -1, MONTH))`
- `Growth % MoM = DIVIDE([Net Revenue] - [Net Revenue (Prev Month)], [Net Revenue (Prev Month)])`

- `Net Revenue (Prev Week) = CALCULATE([Net Revenue], DATEADD(dim_date[date_value], -7, DAY))`
- `Growth % WoW = DIVIDE([Net Revenue] - [Net Revenue (Prev Week)], [Net Revenue (Prev Week)])`

### Anomaly flag (simple Z-score)
- `Net Revenue Z = VAR mu = AVERAGEX(ALLSELECTED(dim_date[date_value]), [Net Revenue])
  VAR sd = STDEVX.P(ALLSELECTED(dim_date[date_value]), [Net Revenue])
  RETURN DIVIDE([Net Revenue] - mu, sd)`
- `Revenue Anomaly Flag = IF(ABS([Net Revenue Z]) >= 2, 1, 0)`

## Funnel & Conversion
- `Product Views = SUM(mart_funnel_conversion[product_views])`
- `Add To Cart = SUM(mart_funnel_conversion[add_to_cart])`
- `Checkout Started = SUM(mart_funnel_conversion[checkout_started])`
- `Payment Attempts = SUM(mart_funnel_conversion[payment_attempts])`
- `Orders Placed (Funnel) = SUM(mart_funnel_conversion[orders_placed])`
- `Conversion Rate = DIVIDE([Orders Placed (Funnel)], [Product Views])`
- `Cart Abandonment Rate = AVERAGE(mart_funnel_conversion[cart_abandonment_rate])`
- `Payment Failure Rate = AVERAGE(mart_funnel_conversion[payment_failure_rate])`

## Funnel & Revenue Leakage (advanced)
- `Revenue Lost (Cart Abandonment) = SUM(mart_product_performance[revenue_lost_cart_abandonment])`
- `Revenue At Risk (Payment Failures) = SUM(mart_product_performance[revenue_at_risk_ex_tax])`
- `Net Revenue After Leakage (Proxy) = [Net Revenue] - [Leakage Total] - [Revenue Lost (Cart Abandonment)] - [Revenue At Risk (Payment Failures)]`

## Customer Analytics (RFM + Retention)
### RFM measures (use at customer grain)
- `Recency Days = VAR last_dt = MAX(mart_customer_segments[last_order_dt])
  RETURN IF(ISBLANK(last_dt), BLANK(), DATEDIFF(last_dt, TODAY(), DAY))`
- `Frequency (Orders) = SUM(mart_customer_segments[orders])`
- `Monetary (Revenue) = SUM(mart_customer_segments[revenue_ex_tax])`

### Churn-risk (rule-based)
- `Churn-risk Customers = COUNTROWS(
    FILTER(
      VALUES(mart_customer_segments[customer_id]),
      [Frequency (Orders)] >= 2 && [Recency Days] > 60
    )
  )`

## Product Intelligence
### Product KPIs
- `Product Revenue = SUM(mart_product_performance[revenue_ex_tax])`
- `Product Units Sold = SUM(mart_product_performance[units_sold])`
- `Product Gross Profit = SUM(mart_product_performance[gross_profit_ex_tax])`

### Return rate (proxy)
- `Return Rate (Proxy) = DIVIDE(SUM(mart_product_performance[return_lines]), SUM(mart_product_performance[units_sold]))`

### Pareto / ABC (measure patterns)
These are easiest when used in visuals that are already grouped by product.

- `Product Revenue Rank = RANKX(ALLSELECTED(dim_product[product_id]), [Product Revenue], , DESC, Dense)`
- `Product Revenue Cumulative = VAR r = [Product Revenue Rank]
  RETURN CALCULATE([Product Revenue], FILTER(ALLSELECTED(dim_product[product_id]), [Product Revenue Rank] <= r))`
- `Product Revenue Cumulative % = DIVIDE([Product Revenue Cumulative], CALCULATE([Product Revenue], ALLSELECTED(dim_product[product_id])))`

- `ABC Class = VAR p = [Product Revenue Cumulative %]
  RETURN SWITCH(TRUE(), p <= 0.8, "A", p <= 0.95, "B", "C")`

## Operational Efficiency
- `Refund % of Revenue = DIVIDE([Refund Amount], [Net Revenue])`

### Risk index (demo-friendly composite)
- `Risk Index = 100 * (
    0.40 * COALESCE([SLA Breach %], 0)
    + 0.30 * COALESCE([Refund % of Revenue], 0)
    + 0.30 * COALESCE([Payment Failure Rate], 0)
  )`
