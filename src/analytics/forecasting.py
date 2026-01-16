from __future__ import annotations

import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from statsmodels.tsa.arima.model import ARIMA

from .common import get_paths, read_sql_df


def run(horizon_days: int = 30) -> None:
    paths = get_paths()
    os.makedirs(paths.data_processed_dir, exist_ok=True)
    os.makedirs(paths.reports_dir, exist_ok=True)

    daily = read_sql_df(
        """
        SELECT date(order_ts) AS dt, SUM(net_amount) AS net_revenue
        FROM globalcart.vw_orders_completed
        GROUP BY 1
        ORDER BY 1
        """
    )

    daily["dt"] = pd.to_datetime(daily["dt"])
    daily = daily.set_index("dt").asfreq("D", fill_value=0.0)

    y = daily["net_revenue"].values
    X = np.arange(len(y)).reshape(-1, 1)

    lr = LinearRegression().fit(X, y)
    X_f = np.arange(len(y), len(y) + horizon_days).reshape(-1, 1)
    lr_fc = lr.predict(X_f)

    arima = ARIMA(daily["net_revenue"], order=(1, 1, 1)).fit()
    arima_fc = arima.forecast(steps=horizon_days)

    future_idx = pd.date_range(daily.index.max() + pd.Timedelta(days=1), periods=horizon_days, freq="D")
    out = pd.DataFrame(
        {
            "dt": future_idx,
            "forecast_lr": lr_fc,
            "forecast_arima": arima_fc.values,
        }
    )

    out_path = os.path.join(paths.data_processed_dir, "revenue_forecast.csv")
    out.to_csv(out_path, index=False)

    plt.figure(figsize=(10, 4))
    plt.plot(daily.index, daily["net_revenue"], label="actual")
    plt.plot(out["dt"], out["forecast_lr"], label="lr")
    plt.plot(out["dt"], out["forecast_arima"], label="arima")
    plt.title("Daily Net Revenue Forecast")
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(paths.reports_dir, "revenue_forecast.png"), dpi=160)
    plt.close()


def main() -> None:
    run()


if __name__ == "__main__":
    main()
