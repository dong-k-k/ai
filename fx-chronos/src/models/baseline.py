from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
PROCESSED_DIR = DATA_DIR / "processed"
OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "outputs" / "forecasts" / "core"


def load_model_series(csv_path: Path) -> pd.Series:
    """Load the weekday-only USD/KRW series used by all forecast models."""
    df = pd.read_csv(csv_path, parse_dates=["date"])
    if df.empty:
        raise RuntimeError("기준 모델에 사용할 시계열이 비어 있습니다.")
    if df["date"].isna().any() or df["value"].isna().any():
        raise RuntimeError("기준 모델 입력에 빈 날짜 또는 환율 값이 있습니다.")
    if df["date"].duplicated().any():
        raise RuntimeError("기준 모델 입력에 중복 날짜가 있습니다.")

    df = df.sort_values("date").reset_index(drop=True)
    if (df["date"].dt.weekday >= 5).any():
        raise RuntimeError("기준 모델 입력에 주말 관측이 포함되어 있습니다.")
    return df.set_index("date")["value"].astype(float)


def build_random_walk_forecast(series: pd.Series, horizon: int) -> pd.DataFrame:
    """Forecast every future step using the last value available at the origin."""
    if series.empty:
        raise RuntimeError("기준 모델에 사용할 시계열이 비어 있습니다.")
    if horizon <= 0:
        raise ValueError("horizon은 1 이상이어야 합니다.")

    forecast_origin = pd.Timestamp(series.index[-1])
    origin_value = float(series.iloc[-1])
    weekday_dates = pd.bdate_range(
        start=forecast_origin + pd.offsets.BDay(1),
        periods=horizon,
    )
    return pd.DataFrame(
        {
            "forecast_step": np.arange(1, horizon + 1),
            "weekday_date": weekday_dates,
            "random_walk_forecast": origin_value,
            "forecast_origin_date": forecast_origin.date().isoformat(),
            "forecast_origin_value": origin_value,
            "model_id": "random_walk_last_observation",
            "history_rows": len(series),
        }
    )


def save_random_walk_forecast(forecast: pd.DataFrame, out_path: Path) -> None:
    """Save a baseline forecast without overwriting an existing result."""
    if out_path.exists():
        raise FileExistsError(f"기존 기준 모델 예측을 덮어쓰지 않습니다: {out_path}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    forecast.to_csv(out_path, index=False)


def main() -> None:
    input_path = PROCESSED_DIR / "usd_krw_model_weekdays_19640504_20260730.csv"
    series = load_model_series(input_path)

    for horizon in (5, 20, 30):
        forecast = build_random_walk_forecast(series, horizon)
        out_path = OUTPUT_DIR / f"usd_krw_random_walk_h{horizon}.csv"
        save_random_walk_forecast(forecast, out_path)
        print(f"Saved Random Walk forecast to {out_path}")
        print(f"Horizon: {horizon}, origin: {series.index[-1].date()}, value: {series.iloc[-1]}")


if __name__ == "__main__":
    main()
