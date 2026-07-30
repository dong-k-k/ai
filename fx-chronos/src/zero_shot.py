from __future__ import annotations

import pandas as pd
from pathlib import Path

from chronos import Chronos2Pipeline


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PROCESSED_DIR = DATA_DIR / "processed"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs" / "forecasts"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def load_preprocessed_series(csv_path: Path) -> pd.Series:
    df = pd.read_csv(csv_path, parse_dates=["date"])
    df = df.sort_values("date").reset_index(drop=True)
    df = df.set_index("date")
    return df["value"].astype(float)


def run_zero_shot_forecast(series: pd.Series, horizon: int = 20) -> None:
    pipeline = Chronos2Pipeline.from_pretrained("amazon/chronos-2")

    values = series.to_numpy(dtype=float)
    values = values.reshape(1, 1, -1)
    prediction = pipeline.predict(values, prediction_length=horizon)

    forecast = prediction[0]
    if hasattr(forecast, "detach"):
        forecast = forecast.detach().cpu().numpy()
    forecast = forecast.reshape(-1)
    out_path = OUTPUT_DIR / f"usd_krw_forecast_h{horizon}.csv"
    pd.DataFrame({"forecast": forecast}).to_csv(out_path, index=False)
    print(f"Saved forecast to {out_path}")
    print(f"Forecast preview: {forecast[:5]}")


def main() -> None:
    input_path = PROCESSED_DIR / "usd_krw_preprocessed.csv"
    series = load_preprocessed_series(input_path)
    run_zero_shot_forecast(series, horizon=20)


if __name__ == "__main__":
    main()
