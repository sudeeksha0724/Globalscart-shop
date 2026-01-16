-- GlobalCart 360 KPI / Interview-level query pack

-- 1) Monthly net revenue + orders
SELECT date_trunc('month', order_ts) AS month,
       COUNT(DISTINCT order_id) AS orders,
       SUM(net_amount) AS net_revenue
FROM globalcart.vw_orders_completed
GROUP BY 1
ORDER BY 1;

-- 2) MoM growth % (window)
WITH m AS (
  SELECT date_trunc('month', order_ts) AS month,
         SUM(net_amount) AS net_revenue
  FROM globalcart.vw_orders_completed
  GROUP BY 1
)
SELECT month,
       net_revenue,
       ROUND(100.0 * (net_revenue - LAG(net_revenue) OVER (ORDER BY month))
             / NULLIF(LAG(net_revenue) OVER (ORDER BY month),0), 2) AS mom_growth_pct
FROM m
ORDER BY month;

-- 3) Rolling 7-day revenue
WITH d AS (
  SELECT order_dt AS dt, SUM(net_amount) AS rev
  FROM globalcart.vw_orders_completed
  GROUP BY 1
)
SELECT dt,
       rev,
       SUM(rev) OVER (ORDER BY dt ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) AS rolling_7d_rev
FROM d
ORDER BY dt;

-- 4) Top 10 products by revenue
SELECT p.product_id, p.product_name,
       SUM(i.line_net_revenue) AS revenue
FROM globalcart.fact_order_items i
JOIN globalcart.dim_product p ON p.product_id = i.product_id
GROUP BY 1,2
ORDER BY revenue DESC
LIMIT 10;

-- 5) Bottom 10 products by revenue
SELECT p.product_id, p.product_name,
       SUM(i.line_net_revenue) AS revenue
FROM globalcart.fact_order_items i
JOIN globalcart.dim_product p ON p.product_id = i.product_id
GROUP BY 1,2
ORDER BY revenue ASC
LIMIT 10;

-- 6) Gross margin by category
SELECT category_l1,
       SUM(line_net_revenue) AS revenue,
       SUM(line_cogs) AS cogs,
       SUM(line_gross_profit) AS gross_profit,
       ROUND(100.0 * SUM(line_gross_profit) / NULLIF(SUM(line_net_revenue),0), 2) AS gross_margin_pct
FROM globalcart.vw_item_profitability
GROUP BY 1
ORDER BY gross_profit DESC;

-- 7) Discount % by category
SELECT category_l1,
       SUM(line_discount) AS total_discount,
       SUM(line_net_revenue + line_discount) AS gross_sales_before_discount,
       ROUND(100.0 * SUM(line_discount) / NULLIF(SUM(line_net_revenue + line_discount),0), 2) AS discount_pct
FROM globalcart.vw_item_profitability
GROUP BY 1
ORDER BY discount_pct DESC;

-- 8) Active customers per month
SELECT date_trunc('month', order_ts) AS month,
       COUNT(DISTINCT customer_id) AS active_customers
FROM globalcart.vw_orders_completed
GROUP BY 1
ORDER BY 1;

-- 9) Repeat customer % (>=2 orders)
WITH c AS (
  SELECT customer_id, COUNT(*) AS orders_cnt
  FROM globalcart.vw_orders_completed
  GROUP BY 1
)
SELECT ROUND(100.0 * SUM(CASE WHEN orders_cnt >= 2 THEN 1 ELSE 0 END) / COUNT(*), 2) AS repeat_customer_pct
FROM c;

-- 10) Churned customers (no purchase in last 90 days)
WITH last_order AS (
  SELECT customer_id, MAX(order_ts) AS last_order_ts
  FROM globalcart.vw_orders_completed
  GROUP BY 1
)
SELECT COUNT(*) AS churned_customers
FROM last_order
WHERE last_order_ts < (CURRENT_DATE - INTERVAL '90 days');

-- 11) Cohort retention (customers active by months since first purchase)
WITH first_purchase AS (
  SELECT customer_id, date_trunc('month', MIN(order_ts)) AS cohort_month
  FROM globalcart.vw_orders_completed
  GROUP BY 1
),
activity AS (
  SELECT o.customer_id,
         fp.cohort_month,
         date_trunc('month', o.order_ts) AS activity_month
  FROM globalcart.vw_orders_completed o
  JOIN first_purchase fp ON fp.customer_id = o.customer_id
)
SELECT cohort_month,
       ((EXTRACT(YEAR FROM activity_month) - EXTRACT(YEAR FROM cohort_month)) * 12
        + (EXTRACT(MONTH FROM activity_month) - EXTRACT(MONTH FROM cohort_month))) AS months_since_cohort,
       COUNT(DISTINCT customer_id) AS customers
FROM activity
GROUP BY 1,2
ORDER BY 1,2;

-- 12) SLA breach % by carrier
SELECT carrier,
       COUNT(*) AS shipments,
       ROUND(100.0 * AVG(CASE WHEN sla_breached_flag THEN 1 ELSE 0 END), 2) AS sla_breach_pct
FROM globalcart.vw_sla
GROUP BY 1
ORDER BY sla_breach_pct DESC;

-- 13) Shipping cost % of net revenue
SELECT ROUND(100.0 * SUM(s.shipping_cost) / NULLIF(SUM(o.net_amount),0), 2) AS shipping_cost_pct_of_revenue
FROM globalcart.fact_shipments s
JOIN globalcart.vw_orders_completed o ON o.order_id = s.order_id;

-- 14) Return rate proxy by category (return lines / sold qty)
WITH sold AS (
  SELECT category_l1, SUM(qty) AS sold_qty
  FROM globalcart.vw_item_profitability
  GROUP BY 1
),
ret AS (
  SELECT category_l1, COUNT(*) AS return_lines
  FROM globalcart.vw_returns_enriched
  GROUP BY 1
)
SELECT s.category_l1,
       s.sold_qty,
       COALESCE(r.return_lines,0) AS return_lines,
       ROUND(100.0 * COALESCE(r.return_lines,0) / NULLIF(s.sold_qty,0), 2) AS return_rate_proxy_pct
FROM sold s
LEFT JOIN ret r ON r.category_l1 = s.category_l1
ORDER BY return_rate_proxy_pct DESC;

-- 15) Top return reasons
SELECT return_reason, COUNT(*) AS returns
FROM globalcart.vw_returns_enriched
GROUP BY 1
ORDER BY returns DESC
LIMIT 10;

-- 16) Monthly refunds trend
SELECT date_trunc('month', return_ts) AS month,
       SUM(refund_amount) AS total_refunds
FROM globalcart.vw_returns_enriched
GROUP BY 1
ORDER BY 1;

-- 17) Payment failure % by method
SELECT payment_method,
       COUNT(*) AS total_attempts,
       ROUND(100.0 * AVG(CASE WHEN payment_status IN ('FAILED','DECLINED') THEN 1 ELSE 0 END), 2) AS failure_pct
FROM globalcart.vw_payments_enriched
GROUP BY 1
ORDER BY failure_pct DESC;

-- 18) Chargeback rate
SELECT ROUND(100.0 * AVG(CASE WHEN chargeback_flag THEN 1 ELSE 0 END), 3) AS chargeback_pct
FROM globalcart.vw_payments_enriched;

-- 19) Top 3 products per category by revenue (dense_rank)
WITH x AS (
  SELECT p.category_l1, p.product_id, p.product_name,
         SUM(i.line_net_revenue) AS revenue
  FROM globalcart.fact_order_items i
  JOIN globalcart.dim_product p ON p.product_id = i.product_id
  GROUP BY 1,2,3
)
SELECT *
FROM (
  SELECT x.*,
         DENSE_RANK() OVER (PARTITION BY category_l1 ORDER BY revenue DESC) AS rnk
  FROM x
) t
WHERE rnk <= 3
ORDER BY category_l1, revenue DESC;

-- 20) Profit leakage breakdown: discounts + shipping + refunds
WITH revenue AS (
  SELECT SUM(net_amount) AS net_rev,
         SUM(discount_amount) AS discounts
  FROM globalcart.vw_orders_completed
),
ship AS (
  SELECT SUM(shipping_cost) AS shipping_cost
  FROM globalcart.fact_shipments
),
refunds AS (
  SELECT SUM(refund_amount) AS refunds
  FROM globalcart.fact_returns
)
SELECT net_rev,
       discounts,
       shipping_cost,
       refunds,
       (discounts + shipping_cost + refunds) AS leakage_total
FROM revenue, ship, refunds;
