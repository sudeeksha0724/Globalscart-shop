# Business Insights & Recommendations (GlobalCart 360)

This document is designed for senior stakeholder review. It summarizes the key findings and actions that follow directly from the KPI model.

## Executive Summary
- Growth is present, but profitability is diluted by **discounting**, **shipping cost overruns**, and **refund leakage**.
- **SLA breaches** are a meaningful operational driver of customer dissatisfaction and return likelihood.
- A small set of categories/SKUs drive most profit; several high-revenue items show margin erosion after discounting and refunds.

## Key Findings (What the analysis surfaces)

### 1) Discount-driven growth is reducing effective margin
- Discount % is elevated in promotion-heavy periods (e.g., Nov/Dec).
- Categories with higher discount % show lower gross margin % and higher volatility.

### 2) Profit leakage has 3 dominant contributors
- Discounts: margin erosion at acquisition/price point.
- Shipping: cost as % of revenue increases on lanes with frequent SLA breaches.
- Refunds: concentrated in specific categories and driven by a few reason codes.

### 3) Logistics performance influences returns
- Orders with `sla_breached_flag = true` show higher probability of return initiation.
- Carrier/FC combinations show measurable differences in breach rates and shipping cost.

### 4) Customer base is segmented (not all churn is equal)
- RFM segmentation typically reveals:
  - Champions: high frequency + low recency
  - At Risk Loyal: historically valuable but not recent
  - New Customers: recent but low frequency
  - Lost: high recency days + low frequency

## Recommendations (What leadership can do)

### Revenue Growth (without margin collapse)
- Implement **promo guardrails**: cap discount % on low-margin SKUs; move from blanket discounts to segment-targeted offers.
- Introduce **bundling** and threshold incentives to increase AOV (e.g., free shipping over a threshold).

### Cost Reduction / Margin Improvement
- Re-route shipments dynamically to reduce SLA breaches for high-LTV segments.
- Renegotiate carrier lane pricing where shipping cost % is persistently above baseline.
- Improve product content / QC for high-return categories (sizing charts, defect checks).

### Retention / CRM
- Win-back campaigns for **churned (90-day inactivity)** customers, prioritized by historical monetary value.
- Automate a weekly list of **At Risk Loyal** customers for CRM outreach.

## How this becomes a real operating cadence
- Daily: Ops dashboard (SLA breaches, refunds, payment failures)
- Weekly: Category profitability & leakage review
- Monthly: Cohort retention + churn analysis; forecast-based planning
