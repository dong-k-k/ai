from __future__ import annotations

import json
import math

import numpy as np
import pandas as pd
from pathlib import Path


OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "outputs" / "metrics" / "core"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "configs" / "evaluation.json"


def pinball_loss(actual: pd.Series, forecast: pd.Series, quantile: float) -> float:
    """Calculate mean quantile loss using actual minus forecast as the error."""
    error = actual.to_numpy(dtype=float) - forecast.to_numpy(dtype=float)
    loss = np.maximum(quantile * error, (quantile - 1.0) * error)
    return float(np.mean(loss))


def calculate_metrics(group: pd.DataFrame) -> dict[str, float | int]:
    """Calculate point, direction, probabilistic, and scaled metrics."""
    actual = group["actual_value"].astype(float)
    chronos = group["chronos_q0.5_median"].astype(float)
    baseline = group["random_walk_forecast"].astype(float)
    origin = group["forecast_origin_value"].astype(float)
    scale = group["mase_scale_training_only"].astype(float)

    chronos_error = chronos - actual
    baseline_error = baseline - actual
    chronos_mae = float(chronos_error.abs().mean())
    baseline_mae = float(baseline_error.abs().mean())
    chronos_rmse = float(math.sqrt((chronos_error**2).mean()))
    baseline_rmse = float(math.sqrt((baseline_error**2).mean()))

    actual_direction = np.sign(actual.to_numpy() - origin.to_numpy())
    chronos_direction = np.sign(chronos.to_numpy() - origin.to_numpy())
    baseline_direction = np.sign(baseline.to_numpy() - origin.to_numpy())
    interval_covered = (
        (actual >= group["chronos_q0.1_lower"])
        & (actual <= group["chronos_q0.9_upper"])
    )
    pinball_q01 = pinball_loss(actual, group["chronos_q0.1_lower"], 0.1)
    pinball_q05 = pinball_loss(actual, group["chronos_q0.5_median"], 0.5)
    pinball_q09 = pinball_loss(actual, group["chronos_q0.9_upper"], 0.9)

    return {
        "rows": len(group),
        "chronos_mae": chronos_mae,
        "random_walk_mae": baseline_mae,
        "chronos_rmse": chronos_rmse,
        "random_walk_rmse": baseline_rmse,
        "chronos_mase": float((chronos_error.abs() / scale).mean()),
        "random_walk_mase": float((baseline_error.abs() / scale).mean()),
        "chronos_direction_accuracy": float(np.mean(chronos_direction == actual_direction)),
        "random_walk_direction_accuracy": float(np.mean(baseline_direction == actual_direction)),
        "pinball_q0.1": pinball_q01,
        "pinball_q0.5": pinball_q05,
        "pinball_q0.9": pinball_q09,
        "mean_pinball_loss": float(np.mean([pinball_q01, pinball_q05, pinball_q09])),
        "interval_80_coverage": float(interval_covered.mean()),
        "interval_mean_width": float(
            (group["chronos_q0.9_upper"] - group["chronos_q0.1_lower"]).mean()
        ),
        "mae_improvement_vs_random_walk_percent": (
            float(100.0 * (baseline_mae - chronos_mae) / baseline_mae)
            if baseline_mae > 0
            else float("nan")
        ),
        "rmse_improvement_vs_random_walk_percent": (
            float(100.0 * (baseline_rmse - chronos_rmse) / baseline_rmse)
            if baseline_rmse > 0
            else float("nan")
        ),
    }


def build_grouped_metrics(df: pd.DataFrame, group_column: str) -> pd.DataFrame:
    """Calculate the same metrics independently for each origin or lead step."""
    rows: list[dict[str, object]] = []
    for group_value, group in df.groupby(group_column, sort=True):
        row: dict[str, object] = {group_column: group_value}
        row.update(calculate_metrics(group))
        rows.append(row)
    return pd.DataFrame(rows)


def save_without_overwrite(df: pd.DataFrame, out_path: Path) -> None:
    if out_path.exists():
        raise FileExistsError(f"기존 평가 결과를 덮어쓰지 않습니다: {out_path}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)


def evaluate_backtest(backtest_path: Path, output_stem: str, horizon: int) -> pd.DataFrame:
    """Evaluate one backtest file and save overall, origin, and lead-step metrics."""
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if config["forecast"]["quantile_levels"] != [0.1, 0.5, 0.9]:
        raise RuntimeError("지원하지 않는 평가 분위수 설정입니다.")

    backtest = pd.read_csv(
        backtest_path,
        parse_dates=["forecast_origin_date", "target_date"],
    )
    required_columns = {
        "forecast_origin_date",
        "forecast_origin_value",
        "forecast_step",
        "actual_value",
        "chronos_q0.1_lower",
        "chronos_q0.5_median",
        "chronos_q0.9_upper",
        "random_walk_forecast",
        "mase_scale_training_only",
    }
    missing_columns = required_columns - set(backtest.columns)
    if missing_columns:
        raise RuntimeError(f"백테스트 결과에 필수 열이 없습니다: {sorted(missing_columns)}")
    if backtest[list(required_columns)].isna().any().any():
        raise RuntimeError("백테스트 평가 입력에 결측값이 있습니다.")

    origin_count = int(backtest["forecast_origin_date"].nunique())
    summary = pd.DataFrame(
        [{"horizon": horizon, "origins": origin_count, **calculate_metrics(backtest)}]
    )
    by_origin = build_grouped_metrics(backtest, "forecast_origin_date")
    by_lead = build_grouped_metrics(backtest, "forecast_step")

    summary_path = OUTPUT_DIR / f"{output_stem}_summary.csv"
    by_origin_path = OUTPUT_DIR / f"{output_stem}_by_origin.csv"
    by_lead_path = OUTPUT_DIR / f"{output_stem}_by_lead.csv"
    for path in (summary_path, by_origin_path, by_lead_path):
        if path.exists():
            raise FileExistsError(f"기존 평가 결과를 덮어쓰지 않습니다: {path}")

    save_without_overwrite(summary, summary_path)
    save_without_overwrite(by_origin, by_origin_path)
    save_without_overwrite(by_lead, by_lead_path)
    print(f"Saved summary metrics to {summary_path}")
    print(f"Saved origin metrics to {by_origin_path}")
    print(f"Saved lead-step metrics to {by_lead_path}")
    print(summary.to_string(index=False))
    return summary


def main() -> None:
    forecast_dir = Path(__file__).resolve().parent.parent.parent / "outputs" / "forecasts" / "core"
    monthly_h20_stem = "usd_krw_walk_forward_h20_monthly_1997_2025"
    evaluate_backtest(
        forecast_dir / f"{monthly_h20_stem}.csv",
        monthly_h20_stem,
        horizon=20,
    )


if __name__ == "__main__":
    main()
