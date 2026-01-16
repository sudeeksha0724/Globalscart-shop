# Operational Dashboard Spec (SLA, Returns, Payments)

## Goal
Operational drilldowns for daily execution: logistics SLAs, returns, refunds, and payment failures.

## Visuals
- SLA breach % by Carrier (bar)
- SLA breach % by FC (bar)
- Shipping cost by FC and lane (matrix)
- Returns by Reason (bar)
- Return rate proxy by Category (bar)
- Refund trend (line)
- Payment failure % by Method (bar)

## Slicers
- Date
- Carrier
- FC
- Category
- Region
- Payment method

## Alert thresholds (recommended)
- SLA breach % > 8% (carrier/FC)
- Return rate proxy > 6% (category)
- Payment failure % > 4% (method)
