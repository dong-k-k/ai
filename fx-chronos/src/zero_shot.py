from __future__ import annotations

import numpy as np
import pandas as pd
from pathlib import Path

from chronos import Chronos2Pipeline


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PROCESSED_DIR = DATA_DIR / "processed"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs" / "forecasts"
FIGURE_DIR = Path(__file__).resolve().parent.parent / "outputs" / "figures"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def load_preprocessed_series(csv_path: Path) -> pd.Series:
    df = pd.read_csv(csv_path, parse_dates=["date"])
    df = df.sort_values("date").reset_index(drop=True)
    if df.empty:
        raise RuntimeError("예측에 사용할 시계열이 비어 있습니다.")
    if df["date"].isna().any() or df["value"].isna().any():
        raise RuntimeError("예측 입력에 빈 날짜 또는 환율 값이 있습니다.")
    if df["date"].duplicated().any():
        raise RuntimeError("예측 입력에 중복 날짜가 있습니다.")
    if (df["date"].dt.weekday >= 5).any():
        raise RuntimeError("예측 입력에 주말 관측이 포함되어 있습니다.")
    df = df.set_index("date")
    return df["value"].astype(float)


def find_quantile_index(quantile_levels: list[float], target: float) -> int:
    """Find a model quantile by value instead of assuming a fixed output position."""
    for index, level in enumerate(quantile_levels):
        if abs(float(level) - target) < 1e-8:
            return index
    raise RuntimeError(f"모델 출력에 필요한 분위수 {target}이 없습니다: {quantile_levels}")


def run_zero_shot_forecast(
    pipeline: Chronos2Pipeline,
    series: pd.Series,
    horizon: int,
    context_length: int = 8192,
) -> Path:
    """Generate and save one univariate USD/KRW quantile forecast."""
    if horizon <= 0:
        raise ValueError("horizon은 1 이상이어야 합니다.")

    values = series.to_numpy(dtype=np.float32)
    values = values.reshape(1, 1, -1)
    predictions = pipeline.predict(
        values,
        prediction_length=horizon,
        context_length=context_length,
    )
    if len(predictions) != 1:
        raise RuntimeError(f"예측 결과 목록의 길이가 1이 아닙니다: {len(predictions)}")

    forecast = predictions[0]
    if hasattr(forecast, "detach"):
        forecast = forecast.detach().cpu().numpy()

    quantile_levels = [float(level) for level in pipeline.quantiles]
    expected_shape = (1, len(quantile_levels), horizon)
    if forecast.shape != expected_shape:
        raise RuntimeError(f"예상하지 못한 예측 shape: 실제={forecast.shape}, 예상={expected_shape}")

    q10 = forecast[0, find_quantile_index(quantile_levels, 0.1), :]
    q50 = forecast[0, find_quantile_index(quantile_levels, 0.5), :]
    q90 = forecast[0, find_quantile_index(quantile_levels, 0.9), :]
    if not np.all((q10 <= q50) & (q50 <= q90)):
        raise RuntimeError("예측 분위수 순서가 q0.1 <= q0.5 <= q0.9를 만족하지 않습니다.")

    last_observation_date = pd.Timestamp(series.index[-1])
    weekday_dates = pd.bdate_range(
        start=last_observation_date + pd.offsets.BDay(1),
        periods=horizon,
    )
    result = pd.DataFrame(
        {
            "forecast_step": np.arange(1, horizon + 1),
            "weekday_date": weekday_dates,
            "q0.1_lower": q10,
            "q0.5_median": q50,
            "q0.9_upper": q90,
            "last_observation_date": last_observation_date.date().isoformat(),
            "model_id": "amazon/chronos-2",
            "history_rows": len(series),
            "context_length": min(context_length, len(series)),
        }
    )

    out_path = OUTPUT_DIR / f"usd_krw_zero_shot_h{horizon}.csv"
    if out_path.exists():
        raise FileExistsError(f"기존 예측 파일을 덮어쓰지 않습니다: {out_path}")
    result.to_csv(out_path, index=False)
    print(f"Saved forecast to {out_path}")
    print(f"Horizon: {horizon}")
    print(f"Input rows: {len(series)}, context length: {min(context_length, len(series))}")
    print(f"Model quantiles: {quantile_levels}")
    print(f"Forecast shape: {forecast.shape}")
    print(result.head())
    return out_path


def plot_zero_shot_forecast(
    series: pd.Series,
    forecast_path: Path,
    out_path: Path,
    history_points: int = 252,
) -> None:
    """Plot recent observations with the median and 0.1–0.9 forecast interval."""
    import matplotlib.pyplot as plt

    if out_path.exists():
        raise FileExistsError(f"기존 그래프를 덮어쓰지 않습니다: {out_path}")
    if history_points <= 0:
        raise ValueError("history_points는 1 이상이어야 합니다.")

    forecast = pd.read_csv(forecast_path, parse_dates=["weekday_date", "last_observation_date"])
    required_columns = {"weekday_date", "q0.1_lower", "q0.5_median", "q0.9_upper"}
    missing_columns = required_columns - set(forecast.columns)
    if missing_columns:
        raise RuntimeError(f"예측 파일에 필수 열이 없습니다: {sorted(missing_columns)}")
    if forecast.empty or forecast[list(required_columns)].isna().any().any():
        raise RuntimeError("예측 그래프 입력이 비어 있거나 결측값이 있습니다.")
    if not (
        (forecast["q0.1_lower"] <= forecast["q0.5_median"])
        & (forecast["q0.5_median"] <= forecast["q0.9_upper"])
    ).all():
        raise RuntimeError("예측 분위수 순서가 올바르지 않습니다.")

    history = series.tail(history_points)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    figure, axis = plt.subplots(figsize=(14, 6))
    axis.plot(history.index, history.values, label="Observed USD/KRW", color="#1f77b4", linewidth=1.3)
    axis.plot(
        forecast["weekday_date"],
        forecast["q0.5_median"],
        label="Chronos-2 median (q0.5)",
        color="#d62728",
        linewidth=1.8,
    )
    axis.fill_between(
        forecast["weekday_date"],
        forecast["q0.1_lower"],
        forecast["q0.9_upper"],
        label="q0.1–q0.9 interval",
        color="#ff9896",
        alpha=0.35,
    )
    axis.axvline(history.index[-1], color="#555555", linestyle="--", linewidth=1, label="Forecast origin")
    axis.set_title("USD/KRW Chronos-2 Zero-shot Forecast (20 Observation Steps)")
    axis.set_xlabel("Observation Date / Provisional Weekday Date")
    axis.set_ylabel("KRW per USD")
    axis.grid(alpha=0.25)
    axis.legend()
    axis.text(
        0.01,
        0.02,
        "Future dates are provisional weekdays; forecast_step denotes the next actual ECOS observation.",
        transform=axis.transAxes,
        fontsize=9,
    )
    figure.tight_layout()
    figure.savefig(out_path, dpi=150)
    plt.close(figure)


def main() -> None:
    input_path = PROCESSED_DIR / "usd_krw_model_weekdays_19640504_20260730.csv"
    series = load_preprocessed_series(input_path)
    pipeline = Chronos2Pipeline.from_pretrained("amazon/chronos-2")
    for horizon in (5, 20, 30):
        run_zero_shot_forecast(pipeline, series, horizon=horizon)


if __name__ == "__main__":
    main()
