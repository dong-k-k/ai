from __future__ import annotations

import pandas as pd
from pathlib import Path


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PROCESSED_DIR = DATA_DIR / "processed"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs" / "metrics"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def build_summary() -> None:
    series = pd.read_csv(PROCESSED_DIR / "usd_krw_preprocessed.csv", parse_dates=["date"])
    forecast = pd.read_csv(Path(__file__).resolve().parent.parent / "outputs" / "forecasts" / "usd_krw_forecast_h20.csv")

    summary = pd.DataFrame(
        {
            "series_rows": [len(series)],
            "forecast_rows": [len(forecast)],
            "forecast_mean": [forecast["forecast"].mean()],
            "forecast_std": [forecast["forecast"].std()],
            "forecast_min": [forecast["forecast"].min()],
            "forecast_max": [forecast["forecast"].max()],
        }
    )
    summary_path = OUTPUT_DIR / "usd_krw_forecast_summary.csv"
    summary.to_csv(summary_path, index=False)
    print(f"Saved summary to {summary_path}")


def main() -> None:
    build_summary()


if __name__ == "__main__":
    main()
