from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pandas as pd
import psycopg
from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import FileResponse

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import seaborn as sns

from ..db import get_conn


router = APIRouter(prefix="/api/admin/analytics", tags=["admin_analytics"])


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_STATIC_DIR = _PROJECT_ROOT / "static"
_OUT_DIR = _STATIC_DIR / "analytics"


def _require_admin(admin_key: str | None) -> None:
    expected = os.getenv("ADMIN_KEY", "admin")
    if admin_key != expected:
        raise HTTPException(status_code=403, detail="Admin access required")


def _read_df(sql: str, params: tuple | None = None) -> pd.DataFrame:
    with get_conn() as conn:
        conn.execute("SET TIME ZONE 'UTC';", prepare=False)
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            rows = cur.fetchall()
            cols = [c.name for c in (cur.description or [])]
    return pd.DataFrame(rows, columns=cols)


def _save_png(fig, filename: str) -> Path:
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = _OUT_DIR / filename
    with tempfile.NamedTemporaryFile(dir=str(_OUT_DIR), suffix=".png", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    fig.tight_layout()
    fig.savefig(tmp_path, dpi=180, bbox_inches="tight", pad_inches=0.05)
    os.replace(tmp_path, out_path)
    return out_path


def _png_response(path: Path) -> FileResponse:
    return FileResponse(path=path, media_type="image/png", filename=path.name)


def _placeholder_chart(filename: str, title: str) -> FileResponse:
    sns.set_theme(style="whitegrid")
    fig, ax = plt.subplots(figsize=(10, 5.0))
    ax.text(
        0.5,
        0.55,
        title,
        ha="center",
        va="center",
        fontsize=14,
    )
    ax.text(
        0.5,
        0.40,
        "Demo mode: PostgreSQL unavailable",
        ha="center",
        va="center",
        fontsize=11,
        color="#6b7280",
    )
    ax.axis("off")
    path = _save_png(fig, filename)
    plt.close(fig)
    return _png_response(path)


def _build_refund_leakage_chart(window_days: int) -> Path:
    sql = """
        SELECT
          order_dt::date AS dt,
          COALESCE(SUM(revenue_ex_tax),0) AS revenue_ex_tax,
          COALESCE(SUM(refund_amount),0) AS refund_amount,
          COALESCE(SUM(net_profit_ex_tax),0) AS net_profit_ex_tax
        FROM globalcart.mart_finance_profitability
        WHERE order_dt >= (CURRENT_DATE - (%s::int * INTERVAL '1 day'))
        GROUP BY 1
        ORDER BY 1;
    """
    df = _read_df(sql, (int(window_days),))
    if df.empty:
        raise HTTPException(status_code=404, detail="No data in mart_finance_profitability")

    sns.set_theme(style="whitegrid")
    fig, ax1 = plt.subplots(figsize=(12, 5.6))

    sns.lineplot(data=df, x="dt", y="refund_amount", ax=ax1, color="#dc2626", label="Refunds")
    ax1.set_ylabel("Refunds", color="#dc2626")
    ax1.tick_params(axis="y", labelcolor="#dc2626")

    ax2 = ax1.twinx()
    sns.lineplot(data=df, x="dt", y="net_profit_ex_tax", ax=ax2, color="#16a34a", label="Net profit (ex tax)")
    ax2.set_ylabel("Net profit (ex tax)", color="#16a34a")
    ax2.tick_params(axis="y", labelcolor="#16a34a")

    ax1.set_title("Refund / Leakage Trend")
    ax1.set_xlabel("")
    ax1.tick_params(axis="x", rotation=30)

    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, loc="upper left")

    path = _save_png(fig, "refund_leakage.png")
    plt.close(fig)
    return path


@router.get("/sales_trend")
def sales_trend(
    window_days: int = Query(90, ge=7, le=365),
    admin_key: str | None = Header(None, alias="X-Admin-Key"),
) -> FileResponse:
    try:
        _require_admin(admin_key)

        sql = """
            SELECT
              kpi_dt::date AS dt,
              orders,
              revenue_ex_tax,
              net_profit_ex_tax,
              refund_amount_return_dt
            FROM globalcart.mart_exec_daily_kpis
            WHERE kpi_dt >= (CURRENT_DATE - (%s::int * INTERVAL '1 day'))
            ORDER BY kpi_dt;
        """
        df = _read_df(sql, (int(window_days),))
        if df.empty:
            raise HTTPException(status_code=404, detail="No data in mart_exec_daily_kpis")

        sns.set_theme(style="whitegrid")
        fig, ax = plt.subplots(figsize=(12, 5.6))
        sns.lineplot(data=df, x="dt", y="revenue_ex_tax", ax=ax, label="Revenue (ex tax)")
        sns.lineplot(data=df, x="dt", y="refund_amount_return_dt", ax=ax, label="Refunds")
        ax.set_title("Daily Revenue Trend")
        ax.set_xlabel("")
        ax.set_ylabel("Amount")
        ax.tick_params(axis="x", rotation=30)

        path = _save_png(fig, "sales_trend.png")
        plt.close(fig)

        try:
            _build_refund_leakage_chart(int(window_days))
        except HTTPException:
            pass

        return _png_response(path)

    except psycopg.OperationalError:
        return _placeholder_chart("sales_trend.png", "Daily Revenue Trend")
    except (psycopg.errors.UndefinedTable, psycopg.errors.InvalidSchemaName):
        raise HTTPException(
            status_code=500,
            detail="Mart tables not found. Run: python3 -m src.run_sql --sql sql/06_bi_marts.sql",
        )
    except Exception as e:
        import traceback, sys
        print("ERROR in sales_trend:", e, file=sys.stderr)
        print(traceback.format_exc(), file=sys.stderr)
        raise HTTPException(status_code=500, detail="Failed to generate sales_trend chart")


@router.get("/orders_vs_revenue")
def orders_vs_revenue(
    window_days: int = Query(90, ge=7, le=3650),
    admin_key: str | None = Header(None, alias="X-Admin-Key"),
) -> FileResponse:
    try:
        _require_admin(admin_key)

        sql = """
            SELECT
              kpi_dt::date AS dt,
              orders,
              revenue_ex_tax
            FROM globalcart.mart_exec_daily_kpis
            WHERE kpi_dt >= (CURRENT_DATE - (%s::int * INTERVAL '1 day'))
            ORDER BY kpi_dt;
        """
        df = _read_df(sql, (int(window_days),))
        if df.empty:
            raise HTTPException(status_code=404, detail="No data in mart_exec_daily_kpis")

        sns.set_theme(style="whitegrid")
        fig, ax1 = plt.subplots(figsize=(12, 5.6))

        sns.lineplot(data=df, x="dt", y="orders", ax=ax1, color="#2563eb", label="Orders")
        ax1.set_ylabel("Orders", color="#2563eb")
        ax1.tick_params(axis="y", labelcolor="#2563eb")

        ax2 = ax1.twinx()
        sns.lineplot(data=df, x="dt", y="revenue_ex_tax", ax=ax2, color="#16a34a", label="Revenue (ex tax)")
        ax2.set_ylabel("Revenue (ex tax)", color="#16a34a")
        ax2.tick_params(axis="y", labelcolor="#16a34a")

        ax1.set_title("Orders vs Revenue")
        ax1.set_xlabel("")
        ax1.tick_params(axis="x", rotation=30)

        h1, l1 = ax1.get_legend_handles_labels()
        h2, l2 = ax2.get_legend_handles_labels()
        ax1.legend(h1 + h2, l1 + l2, loc="upper left")

        path = _save_png(fig, "orders_vs_revenue.png")
        plt.close(fig)

        return _png_response(path)

    except psycopg.OperationalError:
        return _placeholder_chart("orders_vs_revenue.png", "Orders vs Revenue")
    except (psycopg.errors.UndefinedTable, psycopg.errors.InvalidSchemaName):
        raise HTTPException(
            status_code=500,
            detail="Mart tables not found. Run: python3 -m src.run_sql --sql sql/06_bi_marts.sql",
        )
    except Exception as e:
        import traceback, sys
        print("ERROR in orders_vs_revenue:", e, file=sys.stderr)
        print(traceback.format_exc(), file=sys.stderr)
        raise HTTPException(status_code=500, detail="Failed to generate orders_vs_revenue chart")


@router.get("/funnel_conversion")
def funnel_conversion(
    window_days: int = Query(30, ge=7, le=3650),
    admin_key: str | None = Header(None, alias="X-Admin-Key"),
):
    try:
        _require_admin(admin_key)

        sql = """
            SELECT
              COALESCE(SUM(product_views),0) AS product_views,
              COALESCE(SUM(add_to_cart),0) AS add_to_cart,
              COALESCE(SUM(checkout_started),0) AS checkout_started,
              COALESCE(SUM(payment_attempts),0) AS payment_attempts,
              COALESCE(SUM(orders_placed),0) AS orders_placed
            FROM globalcart.mart_funnel_conversion
            WHERE event_dt >= (CURRENT_DATE - (%s::int * INTERVAL '1 day'));
        """
        df = _read_df(sql, (int(window_days),))
        if df.empty:
            raise HTTPException(status_code=404, detail="No data in mart_funnel_conversion")

        row = df.iloc[0].to_dict()
        stages = [
            ("Product Views", float(row.get("product_views") or 0)),
            ("Add To Cart", float(row.get("add_to_cart") or 0)),
            ("Checkout Started", float(row.get("checkout_started") or 0)),
            ("Payment Attempts", float(row.get("payment_attempts") or 0)),
            ("Orders Placed", float(row.get("orders_placed") or 0)),
        ]
        plot_df = pd.DataFrame(stages, columns=["stage", "count"])

        sns.set_theme(style="whitegrid")
        fig, ax = plt.subplots(figsize=(10, 4.5))
        sns.barplot(data=plot_df, x="stage", y="count", ax=ax, palette="Blues")
        ax.set_title(f"Funnel Conversion (Last {int(window_days)} days)")
        ax.set_xlabel("")
        ax.set_ylabel("Count")
        ax.tick_params(axis="x", rotation=20)

        path = _save_png(fig, "funnel_conversion.png")
        plt.close(fig)
        return _png_response(path)

    except psycopg.OperationalError:
        return _placeholder_chart("funnel_conversion.png", "Funnel Conversion")
    except (psycopg.errors.UndefinedTable, psycopg.errors.InvalidSchemaName):
        raise HTTPException(
            status_code=500,
            detail="Mart tables not found. Run: python3 -m src.run_sql --sql sql/06_bi_marts.sql",
        )
    except Exception as e:
        import traceback, sys
        print("ERROR in funnel_conversion:", e, file=sys.stderr)
        print(traceback.format_exc(), file=sys.stderr)
        raise HTTPException(status_code=500, detail="Failed to generate funnel_conversion chart")


@router.get("/top_products")
def top_products(
    window_days: int = Query(30, ge=7, le=3650),
    top_n: int = Query(10, ge=5, le=50),
    admin_key: str | None = Header(None, alias="X-Admin-Key"),
) -> FileResponse:
    try:
        _require_admin(admin_key)

        sql = """
            SELECT
              p.product_id,
              dp.product_name,
              COALESCE(SUM(p.revenue_ex_tax),0) AS revenue_ex_tax
            FROM globalcart.mart_product_performance p
            JOIN globalcart.dim_product dp ON dp.product_id = p.product_id
            WHERE p.dt >= (CURRENT_DATE - (%s::int * INTERVAL '1 day'))
            GROUP BY 1,2
            ORDER BY revenue_ex_tax DESC
            LIMIT %s;
        """
        df = _read_df(sql, (int(window_days), int(top_n)))
        if df.empty:
            raise HTTPException(status_code=404, detail="No data in mart_product_performance")

        df = df.sort_values("revenue_ex_tax", ascending=True)

        sns.set_theme(style="whitegrid")
        fig, ax = plt.subplots(figsize=(10, 5.5))
        sns.barplot(data=df, x="revenue_ex_tax", y="product_name", ax=ax, palette="Greens")
        ax.set_title(f"Top {int(top_n)} Products by Revenue (Last {int(window_days)} days)")
        ax.set_xlabel("Revenue (ex tax)")
        ax.set_ylabel("")

        path = _save_png(fig, "top_products.png")
        plt.close(fig)
        return _png_response(path)

    except psycopg.OperationalError:
        return _placeholder_chart("top_products.png", "Top Products")
    except (psycopg.errors.UndefinedTable, psycopg.errors.InvalidSchemaName):
        raise HTTPException(
            status_code=500,
            detail="Mart tables not found. Run: python3 -m src.run_sql --sql sql/06_bi_marts.sql",
        )
    except Exception as e:
        import traceback, sys
        print("ERROR in top_products:", e, file=sys.stderr)
        print(traceback.format_exc(), file=sys.stderr)
        raise HTTPException(status_code=500, detail="Failed to generate top_products chart")


@router.get("/category_contribution")
def category_contribution(
    window_days: int = Query(30, ge=7, le=3650),
    level: str = Query("category_l1"),
    top_n: int = Query(10, ge=3, le=50),
    admin_key: str | None = Header(None, alias="X-Admin-Key"),
) -> FileResponse:
    try:
        _require_admin(admin_key)

        lvl = (level or "").strip().lower()
        if lvl not in {"category_l1", "category_l2"}:
            raise HTTPException(status_code=400, detail="level must be category_l1 or category_l2")

        sql = f"""
            SELECT
              {lvl} AS category,
              COALESCE(SUM(revenue_ex_tax),0) AS revenue_ex_tax
            FROM globalcart.mart_product_performance
            WHERE dt >= (CURRENT_DATE - (%s::int * INTERVAL '1 day'))
              AND {lvl} IS NOT NULL
            GROUP BY 1
            ORDER BY revenue_ex_tax DESC
            LIMIT %s;
        """
        df = _read_df(sql, (int(window_days), int(top_n)))
        if df.empty:
            raise Exception("No data in mart_product_performance for window")

        total = float(df["revenue_ex_tax"].sum() or 0)
        if total <= 0:
            raise Exception("Zero revenue in mart_product_performance for window")

        df["share_pct"] = (df["revenue_ex_tax"] / total) * 100.0
        df = df.sort_values("share_pct", ascending=True)

        sns.set_theme(style="whitegrid")
        fig, ax = plt.subplots(figsize=(10, 5.0))
        sns.barplot(data=df, x="share_pct", y="category", ax=ax, palette="Purples")
        ax.set_title(f"Category Revenue Share ({lvl}) - Last {int(window_days)} days")
        ax.set_xlabel("Revenue share (%)")
        ax.set_ylabel("")

        path = _save_png(fig, "category_contribution.png")
        plt.close(fig)
        return _png_response(path)

    except Exception as e:
        import traceback, sys
        print("ERROR in category_contribution:", e, file=sys.stderr)
        print(traceback.format_exc(), file=sys.stderr)
        # Fallback: generate a placeholder chart
        try:
            sns.set_theme(style="whitegrid")
            fig, ax = plt.subplots(figsize=(10, 5.0))
            ax.text(0.5, 0.5, "Category Revenue Share\n(No data available)", ha="center", va="center", fontsize=14)
            ax.set_title("Category Revenue Share (Last 30 days)")
            ax.axis("off")
            path = _save_png(fig, "category_contribution.png")
            plt.close(fig)
            return _png_response(path)
        except Exception as fallback_e:
            print("Fallback also failed:", fallback_e, file=sys.stderr)
            raise HTTPException(status_code=500, detail="Failed to generate category_contribution chart")


@router.get("/refund_leakage")
def refund_leakage(
    window_days: int = Query(90, ge=7, le=3650),
    admin_key: str | None = Header(None, alias="X-Admin-Key"),
) -> FileResponse:
    try:
        _require_admin(admin_key)

        path = _build_refund_leakage_chart(int(window_days))
        return _png_response(path)

    except psycopg.OperationalError:
        return _placeholder_chart("refund_leakage.png", "Refund / Leakage Trend")
    except (psycopg.errors.UndefinedTable, psycopg.errors.InvalidSchemaName):
        raise HTTPException(
            status_code=500,
            detail="Mart tables not found. Run: python3 -m src.run_sql --sql sql/06_bi_marts.sql",
        )
    except Exception as e:
        import traceback, sys
        print("ERROR in refund_leakage:", e, file=sys.stderr)
        print(traceback.format_exc(), file=sys.stderr)
        raise HTTPException(status_code=500, detail="Failed to generate refund_leakage chart")
