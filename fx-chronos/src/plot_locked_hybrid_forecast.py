from __future__ import annotations

from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.ticker import FuncFormatter


PROJECT_DIR = Path(__file__).resolve().parent.parent
MODEL_DATA_PATH = (
    PROJECT_DIR
    / "data"
    / "processed"
    / "usd_krw_model_weekdays_19640504_20260730.csv"
)
FORECAST_PATH = (
    PROJECT_DIR
    / "outputs"
    / "forecasts"
    / "usd_krw_shrunk_ensemble_h20_ctx756_alpha0.5_2026_locked.csv"
)
OUTPUT_PATH = (
    PROJECT_DIR
    / "outputs"
    / "figures"
    / "usd_krw_locked_hybrid_20260701.png"
)
REQUESTED_ORIGIN = "2026-07-01"
HISTORY_ROWS = 60


def load_plot_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.Timestamp]:
    history = pd.read_csv(MODEL_DATA_PATH, parse_dates=["date"])
    forecast = pd.read_csv(
        FORECAST_PATH,
        parse_dates=["requested_origin", "forecast_origin_date", "target_date"],
    )
    selected = forecast[
        forecast["requested_origin"].eq(pd.Timestamp(REQUESTED_ORIGIN))
    ].copy()
    if len(selected) != 20 or selected["forecast_step"].nunique() != 20:
        raise RuntimeError(f"2026-07-01 예측 행 또는 step이 20개가 아닙니다: {len(selected)}")
    if selected.isna().any().any():
        raise RuntimeError("그래프 예측 입력에 결측값이 있습니다.")
    selected = selected.sort_values("forecast_step").reset_index(drop=True)
    forecast_origins = selected["forecast_origin_date"].unique()
    if len(forecast_origins) != 1:
        raise RuntimeError("선택한 예측에 forecast origin이 여러 개입니다.")
    forecast_origin = pd.Timestamp(forecast_origins[0])

    history = history[history["date"] <= forecast_origin].sort_values("date").tail(HISTORY_ROWS)
    if len(history) != HISTORY_ROWS:
        raise RuntimeError(f"그래프 이력 행 수가 예상과 다릅니다: {len(history)}")
    if history["date"].duplicated().any() or selected["target_date"].duplicated().any():
        raise RuntimeError("그래프 입력 날짜에 중복이 있습니다.")
    return history, selected, forecast_origin


def plot_locked_hybrid_forecast(
    history: pd.DataFrame,
    forecast: pd.DataFrame,
    forecast_origin: pd.Timestamp,
    output_path: Path,
) -> None:
    if output_path.exists():
        raise FileExistsError(f"기존 그래프를 덮어쓰지 않습니다: {output_path}")

    figure, axis = plt.subplots(figsize=(14, 8))
    axis.plot(
        history["date"],
        history["value"],
        color="#334155",
        linewidth=1.8,
        label="Observed history",
    )
    axis.plot(
        forecast["target_date"],
        forecast["actual_value"],
        color="#111827",
        linewidth=2.4,
        marker="o",
        markersize=4,
        label="Actual after origin",
        zorder=6,
    )
    axis.plot(
        forecast["target_date"],
        forecast["random_walk_forecast"],
        color="#64748b",
        linewidth=1.8,
        linestyle="--",
        label="Random Walk baseline",
    )
    axis.plot(
        forecast["target_date"],
        forecast["chronos_q0.5_median"],
        color="#f59e0b",
        linewidth=1.8,
        linestyle=":",
        label="Chronos-2 median",
    )
    axis.plot(
        forecast["target_date"],
        forecast["ensemble_forecast"],
        color="#2563eb",
        linewidth=2.6,
        label="Shrunk ensemble (alpha=0.5)",
        zorder=5,
    )
    axis.fill_between(
        forecast["target_date"],
        forecast["chronos_q0.1_lower"],
        forecast["chronos_q0.9_upper"],
        color="#f59e0b",
        alpha=0.16,
        label="Chronos q0.1-q0.9 reference scenario",
    )
    axis.axvline(
        forecast_origin,
        color="#dc2626",
        linewidth=1.4,
        linestyle="--",
        alpha=0.85,
        label=f"Forecast origin ({forecast_origin.date()})",
    )

    axis.set_title(
        "USD/KRW 20-Observation Locked Hybrid Forecast\n"
        "2026-07 origin | Research candidate, not a production-final model",
        fontsize=15,
        pad=14,
    )
    axis.set_xlabel("Observation date")
    axis.set_ylabel("KRW per USD (ECOS basic exchange rate)")
    axis.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:,.0f}"))
    axis.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
    axis.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    axis.grid(alpha=0.22)
    axis.legend(loc="upper left", frameon=True, framealpha=0.95, fontsize=9)
    axis.tick_params(axis="x", rotation=35)

    note = (
        "Point candidate: Random Walk + 0.5 x Chronos change | "
        "2026 locked evaluation: MAE +3.35%, RMSE +1.99% vs Random Walk (7 origins)\n"
        "Shaded band is an uncalibrated Chronos reference quantile scenario; "
        "historical coverage was below the nominal 80%."
    )
    figure.text(0.5, 0.015, note, ha="center", va="bottom", fontsize=9, color="#475569")
    figure.tight_layout(rect=(0, 0.07, 1, 1))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(figure)


def main() -> None:
    history, forecast, forecast_origin = load_plot_data()
    plot_locked_hybrid_forecast(history, forecast, forecast_origin, OUTPUT_PATH)
    print(f"requested_origin: {REQUESTED_ORIGIN}")
    print(f"forecast_origin: {forecast_origin.date()}")
    print(f"history_rows: {len(history)}")
    print(f"forecast_rows: {len(forecast)}")
    print(f"target_start: {forecast['target_date'].min().date()}")
    print(f"target_end: {forecast['target_date'].max().date()}")
    print(f"saved: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
