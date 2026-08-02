from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from src.evaluation.evaluate import save_without_overwrite


PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = PROJECT_DIR / "configs" / "ensemble.json"
INPUT_PATH = (
    PROJECT_DIR
    / "outputs"
    / "forecasts"
    / "core"
    / "usd_krw_zero_shot_h20_ctx756_validation_2018_2021.csv"
)
OUTPUT_STEM = "usd_krw_shrunk_ensemble_h20_ctx756_validation_2018_2021"
FORECAST_PATH = PROJECT_DIR / "outputs" / "forecasts" / "ensemble" / f"{OUTPUT_STEM}.csv"
METRICS_DIR = PROJECT_DIR / "outputs" / "metrics" / "ensemble"
SUMMARY_PATH = METRICS_DIR / f"{OUTPUT_STEM}_summary.csv"
BY_ORIGIN_PATH = METRICS_DIR / f"{OUTPUT_STEM}_by_origin.csv"
BY_LEAD_PATH = METRICS_DIR / f"{OUTPUT_STEM}_by_lead.csv"
SELECTION_PATH = METRICS_DIR / f"{OUTPUT_STEM}_selection.json"
EXPECTED_ORIGINS = 48
EXPECTED_ROWS_PER_ORIGIN = 20
TOLERANCE = 1e-12


def load_config(config_path: Path) -> dict[str, object]:
    """결과 확인 전에 고정한 앙상블 후보와 선택 규칙을 읽는다."""
    config = json.loads(config_path.read_text(encoding="utf-8"))
    alphas = [float(alpha) for alpha in config["alpha_candidates"]]
    if alphas != [0.0, 0.1, 0.2, 0.3, 0.5]:
        raise RuntimeError(f"α 후보가 사전 정의와 다릅니다: {alphas}")
    if len(alphas) != len(set(alphas)) or any(alpha < 0 or alpha > 1 for alpha in alphas):
        raise RuntimeError("α 후보는 중복 없이 0과 1 사이여야 합니다.")
    if int(config["prediction_length"]) != EXPECTED_ROWS_PER_ORIGIN:
        raise RuntimeError("앙상블 예측 길이가 20이 아닙니다.")
    return config


def load_validation_forecast(input_path: Path) -> pd.DataFrame:
    """선택된 Zero-shot Validation 원시 예측만 검증해 읽는다."""
    forecast = pd.read_csv(
        input_path,
        parse_dates=["forecast_origin_date", "target_date"],
    )
    required_columns = {
        "requested_origin",
        "forecast_origin_date",
        "forecast_origin_value",
        "forecast_step",
        "target_date",
        "actual_value",
        "chronos_q0.5_median",
        "random_walk_forecast",
        "context_length",
    }
    missing_columns = required_columns - set(forecast.columns)
    if missing_columns:
        raise RuntimeError(f"앙상블 입력에 필수 열이 없습니다: {sorted(missing_columns)}")
    if forecast[list(required_columns)].isna().any().any():
        raise RuntimeError("앙상블 입력에 결측값이 있습니다.")
    if set(forecast["context_length"].astype(int).unique()) != {756}:
        raise RuntimeError("앙상블 입력이 선택된 context 756 예측이 아닙니다.")
    if len(forecast) != EXPECTED_ORIGINS * EXPECTED_ROWS_PER_ORIGIN:
        raise RuntimeError(f"앙상블 입력 행 수가 예상과 다릅니다: {len(forecast)}")
    counts = forecast.groupby("requested_origin")["forecast_step"].agg(["size", "nunique"])
    if (
        (counts["size"] != EXPECTED_ROWS_PER_ORIGIN)
        | (counts["nunique"] != EXPECTED_ROWS_PER_ORIGIN)
    ).any():
        raise RuntimeError("기준일별 행 또는 forecast_step이 20개가 아닙니다.")
    if forecast.duplicated(["requested_origin", "forecast_step", "target_date"]).any():
        raise RuntimeError("앙상블 입력에 중복 예측 행이 있습니다.")
    if not np.allclose(
        forecast["random_walk_forecast"].astype(float),
        forecast["forecast_origin_value"].astype(float),
        rtol=0,
        atol=TOLERANCE,
    ):
        raise RuntimeError("Random Walk가 forecast origin의 마지막 관측값과 다릅니다.")
    return forecast.sort_values(
        ["forecast_origin_date", "forecast_step"]
    ).reset_index(drop=True)


def point_metrics(group: pd.DataFrame) -> dict[str, float | int]:
    """앙상블과 두 기준 모델의 점 예측 지표를 계산한다."""
    actual = group["actual_value"].astype(float)
    ensemble = group["ensemble_forecast"].astype(float)
    chronos = group["chronos_q0.5_median"].astype(float)
    random_walk = group["random_walk_forecast"].astype(float)
    origin = group["forecast_origin_value"].astype(float)

    ensemble_error = ensemble - actual
    chronos_error = chronos - actual
    random_walk_error = random_walk - actual
    ensemble_mae = float(ensemble_error.abs().mean())
    chronos_mae = float(chronos_error.abs().mean())
    random_walk_mae = float(random_walk_error.abs().mean())
    ensemble_rmse = float(math.sqrt((ensemble_error**2).mean()))
    chronos_rmse = float(math.sqrt((chronos_error**2).mean()))
    random_walk_rmse = float(math.sqrt((random_walk_error**2).mean()))

    actual_direction = np.sign(actual.to_numpy() - origin.to_numpy())
    ensemble_direction = np.sign(ensemble.to_numpy() - origin.to_numpy())
    chronos_direction = np.sign(chronos.to_numpy() - origin.to_numpy())
    random_walk_direction = np.sign(random_walk.to_numpy() - origin.to_numpy())

    return {
        "rows": len(group),
        "ensemble_mae": ensemble_mae,
        "chronos_mae": chronos_mae,
        "random_walk_mae": random_walk_mae,
        "ensemble_rmse": ensemble_rmse,
        "chronos_rmse": chronos_rmse,
        "random_walk_rmse": random_walk_rmse,
        "ensemble_direction_accuracy": float(
            np.mean(ensemble_direction == actual_direction)
        ),
        "chronos_direction_accuracy": float(
            np.mean(chronos_direction == actual_direction)
        ),
        "random_walk_direction_accuracy": float(
            np.mean(random_walk_direction == actual_direction)
        ),
        "mae_improvement_vs_random_walk_percent": float(
            100 * (random_walk_mae - ensemble_mae) / random_walk_mae
        ),
        "rmse_improvement_vs_random_walk_percent": float(
            100 * (random_walk_rmse - ensemble_rmse) / random_walk_rmse
        ),
        "mae_improvement_vs_chronos_percent": float(
            100 * (chronos_mae - ensemble_mae) / chronos_mae
        ),
        "rmse_improvement_vs_chronos_percent": float(
            100 * (chronos_rmse - ensemble_rmse) / chronos_rmse
        ),
    }


def build_grouped_metrics(
    forecast: pd.DataFrame, group_column: str
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for (alpha, group_value), group in forecast.groupby(
        ["alpha", group_column], sort=True
    ):
        row: dict[str, object] = {"alpha": alpha, group_column: group_value}
        row.update(point_metrics(group))
        rows.append(row)
    return pd.DataFrame(rows)


def build_summary(forecast: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for alpha, group in forecast.groupby("alpha", sort=True):
        metrics = point_metrics(group)
        metrics["selection_score"] = 0.5 * (
            metrics["ensemble_mae"] / metrics["random_walk_mae"]
        ) + 0.5 * (metrics["ensemble_rmse"] / metrics["random_walk_rmse"])
        metrics["eligible"] = bool(
            metrics["ensemble_mae"] <= metrics["random_walk_mae"] + TOLERANCE
            and metrics["ensemble_rmse"] <= metrics["random_walk_rmse"] + TOLERANCE
        )
        rows.append(
            {
                "split": "validation_2018_2021",
                "horizon": EXPECTED_ROWS_PER_ORIGIN,
                "origins": EXPECTED_ORIGINS,
                "alpha": alpha,
                **metrics,
            }
        )
    summary = pd.DataFrame(rows).sort_values("alpha").reset_index(drop=True)
    return summary


def select_alpha(summary: pd.DataFrame) -> tuple[float, str]:
    eligible = summary[summary["eligible"]].copy()
    if eligible.empty:
        return 0.0, "fallback_no_candidate_improves_both_mae_and_rmse"
    selected = eligible.sort_values(
        ["selection_score", "alpha"], ascending=[True, True]
    ).iloc[0]
    return float(selected["alpha"]), "lowest_balanced_relative_error_score"


def main() -> None:
    output_paths = (
        FORECAST_PATH,
        SUMMARY_PATH,
        BY_ORIGIN_PATH,
        BY_LEAD_PATH,
        SELECTION_PATH,
    )
    existing_paths = [path for path in output_paths if path.exists()]
    if existing_paths:
        raise FileExistsError(f"기존 앙상블 결과를 덮어쓰지 않습니다: {existing_paths}")

    config = load_config(CONFIG_PATH)
    base = load_validation_forecast(INPUT_PATH)
    forecast_parts: list[pd.DataFrame] = []
    for alpha_value in config["alpha_candidates"]:
        alpha = float(alpha_value)
        candidate = base.copy()
        candidate["alpha"] = alpha
        candidate["ensemble_forecast"] = candidate["forecast_origin_value"] + alpha * (
            candidate["chronos_q0.5_median"] - candidate["forecast_origin_value"]
        )
        forecast_parts.append(candidate)
    forecast = pd.concat(forecast_parts, ignore_index=True)

    summary = build_summary(forecast)
    by_origin = build_grouped_metrics(forecast, "requested_origin")
    by_lead = build_grouped_metrics(forecast, "forecast_step")
    origin_win_rates = (
        by_origin.assign(
            origin_mae_win=by_origin["ensemble_mae"] < by_origin["random_walk_mae"],
            origin_rmse_win=by_origin["ensemble_rmse"] < by_origin["random_walk_rmse"],
        )
        .groupby("alpha")[["origin_mae_win", "origin_rmse_win"]]
        .mean()
        .rename(
            columns={
                "origin_mae_win": "origin_mae_win_rate_vs_random_walk",
                "origin_rmse_win": "origin_rmse_win_rate_vs_random_walk",
            }
        )
        .reset_index()
    )
    summary = summary.merge(origin_win_rates, on="alpha", validate="one_to_one")
    selected_alpha, selection_reason = select_alpha(summary)
    summary["selected"] = summary["alpha"].eq(selected_alpha)

    selection = {
        "selection_split": config["selection_split"],
        "alpha_candidates": config["alpha_candidates"],
        "selected_alpha": selected_alpha,
        "selection_reason": selection_reason,
        "selection_rule": config["selection_rule"],
        "final_test_used_for_selection": False,
        "input_path": str(INPUT_PATH.relative_to(PROJECT_DIR)),
    }

    save_without_overwrite(forecast, FORECAST_PATH)
    save_without_overwrite(summary, SUMMARY_PATH)
    save_without_overwrite(by_origin, BY_ORIGIN_PATH)
    save_without_overwrite(by_lead, BY_LEAD_PATH)
    SELECTION_PATH.parent.mkdir(parents=True, exist_ok=True)
    SELECTION_PATH.write_text(
        json.dumps(selection, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(summary.to_string(index=False))
    print(f"selected_alpha: {selected_alpha}")
    print(f"selection_reason: {selection_reason}")
    print(f"final_test_used_for_selection: {selection['final_test_used_for_selection']}")
    print(f"saved_forecast: {FORECAST_PATH}")
    print(f"saved_summary: {SUMMARY_PATH}")
    print(f"saved_selection: {SELECTION_PATH}")


if __name__ == "__main__":
    main()
