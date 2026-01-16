# Operational Efficiency Dashboard (Power BI Page)

## Goal
Track operational KPIs: refunds, delivery performance, SLA breaches, payment failures, and execution risk.

## Primary tables (recommended)
- `globalcart.mart_exec_daily_kpis` (daily SLA breach %, shipping cost, refunds)
- `globalcart.vw_sla` (carrier + FC + SLA flags)
- `globalcart.vw_returns_enriched` (return reasons)
- `globalcart.vw_payments_enriched` (failure reasons)
- `globalcart.dim_date`
- `globalcart.dim_fc`
- `globalcart.dim_geo`

## KPIs
- Refund Amount
- SLA Breach %
- Shipping Cost % of Revenue
- Payment Failure Rate
- Risk Index (simple)

## Suggested visuals
1) Delivery / SLA trends
- Line: SLA Breach % over time
- Bar: SLA breach % by carrier
- Bar: SLA breach % by FC

2) Refund leakage
- Line: refund amount trend
- Bar: returns by reason

3) Payment failures
- Bar: failures by method/provider
- Bar: failures by reason

4) Operational “risk index”
- Gauge or card:
  - Combine breach %, refunds %, payment failure % into a single score

## Alert thresholds (demo-friendly)
- SLA breach % > 8%
- Return rate proxy > 6%
- Payment failure % > 4%
