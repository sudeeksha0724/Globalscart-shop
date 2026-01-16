# Excel Management Report (GlobalCart 360)

## Goal
Provide a management-ready Excel file with consistent KPIs aligned to the warehouse definitions.

## Source of Truth
- KPIs are computed from `globalcart.vw_orders_completed` and profitability from `globalcart.vw_item_profitability`.
- The Python generator `src/generate_excel_report.py` exports raw KPI-ready tables to Excel.

## Workbook Structure (recommended)
- `KPI_Summary` (topline cards)
- `Monthly_Trend` (trend pivots)
- `Category_Profit` (profitability)
- `Returns` (returns + refunds)
- `SLA` (carrier performance)

## Pivot Tables to Build (interview-ready)
### 1) Executive Summary Pivot
- Rows: Month
- Values: Net Revenue, Orders
- Calculated: AOV (Net Revenue / Orders)

### 2) Category Profitability Pivot
- Rows: Category L1
- Values: Revenue, Gross Profit
- Calculated: Gross Margin %

### 3) Returns Drilldown
- Rows: Category L1 → Return Reason
- Values: Return Lines, Refund Amount

### 4) Ops Pivot
- Rows: Carrier
- Values: Shipments, SLA Breach %, Shipping Cost

## Slicers (if you extend extract)
If you extend the Excel export to include region/channel, add slicers:
- Date
- Region
- Category
- Channel
- Carrier
