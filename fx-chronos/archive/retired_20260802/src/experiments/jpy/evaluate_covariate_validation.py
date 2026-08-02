from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch
from chronos import Chronos2Pipeline

from src.experiments.jpy.covariate_smoke import build_past_covariate_input, load_covariate_data
from src.models.zero_shot import find_quantile_index


PROJECT_DIR = Path(__file__).resolve().parent.parent.parent.parent
MODEL_ID = "amazon/chronos-2"
CONFIG_PATH = PROJECT_DIR / "configs" / "covariate_validation.json"
DATA_PATH = (
    PROJECT_DIR
    / "data"
    / "processed"
    / "usd_jpy_covariates_weekdays_lag1_19770404_20260730.csv"
)
REFERENCE_PATH = (
    PROJECT_DIR
    / "outputs"
    / "forecasts"
    / "core"
    / "usd_krw_zero_shot_h20_ctx756_validation_2018_2021.csv"
)
OUTPUT_STEM = "usd_krw_chronos2_jpy_lag1_h20_ctx756_validation_2018_2021"
FORECAST_PATH = PROJECT_DIR / "outputs" / "forecasts" / "experiments" / "jpy" / f"{OUTPUT_STEM}.csv"
METRICS_DIR = PROJECT_DIR / "outputs" / "metrics" / "experiments" / "jpy"
SUMMARY_PATH = METRICS_DIR / f"{OUTPUT_STEM}_summary.csv"
BY_ORIGIN_PATH = METRICS_DIR / f"{OUTPUT_STEM}_by_origin.csv"
BY_YEAR_PATH = METRICS_DIR / f"{OUTPUT_STEM}_by_year.csv"
BY_LEAD_SEGMENT_PATH = METRICS_DIR / f"{OUTPUT_STEM}_by_lead_segment.csv"
DECISION_PATH = METRICS_DIR / f"{OUTPUT_STEM}_decision.json"


def load_settings(config_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    validation = config["validation"]
    criteria = config["candidate_entry_criteria"]
    expected = {
        "expected_origins": 48,
        "expected_rows": 960,
        "context_length": 756,
        "prediction_length": 20,
        "device": "mps",
        "cross_learning": False,
    }
    for key, value in expected.items():
        if validation[key] != value:
            raise RuntimeError(f"공변량 Validation 고정 설정이 예상과 다릅니다: {key}")
    if config["future_covariates"]:
        raise RuntimeError("공변량 Validation에 미래 공변량이 설정되어 있습니다.")
    return validation, criteria


def load_reference(reference_path: Path, expected_rows: int, expected_origins: int) -> pd.DataFrame:
    reference = pd.read_csv(
        reference_path,
        parse_dates=["forecast_origin_date", "target_date"],
    )
    required = {
        "requested_origin",
        "forecast_origin_date",
        "forecast_origin_value",
        "forecast_step",
        "target_date",
        "actual_value",
        "chronos_q0.1_lower",
        "chronos_q0.5_median",
        "chronos_q0.9_upper",
        "random_walk_forecast",
    }
    missing = required - set(reference.columns)
    if missing:
        raise RuntimeError(f"기존 단변량 Validation에 필수 열이 없습니다: {sorted(missing)}")
    if len(reference) != expected_rows or reference["requested_origin"].nunique() != expected_origins:
        raise RuntimeError("기존 단변량 Validation 행 또는 기준일 수가 고정값과 다릅니다.")
    if reference[list(required)].isna().any().any():
        raise RuntimeError("기존 단변량 Validation에 결측값이 있습니다.")
    if reference.duplicated(["requested_origin", "forecast_step", "target_date"]).any():
        raise RuntimeError("기존 단변량 Validation에 중복 행이 있습니다.")
    return reference.sort_values(["forecast_origin_date", "forecast_step"]).reset_index(drop=True)


def build_validation_inputs(
    data: pd.DataFrame,
    reference: pd.DataFrame,
    context_length: int,
) -> tuple[list[dict[str, Any]], list[pd.DataFrame]]:
    inputs: list[dict[str, Any]] = []
    groups: list[pd.DataFrame] = []
    for requested_origin, rows in reference.groupby("requested_origin", sort=False):
        rows = rows.sort_values("forecast_step").reset_index(drop=True)
        model_input, history, forecast_origin = build_past_covariate_input(
            data,
            str(requested_origin),
            context_length,
        )
        expected_origin = pd.Timestamp(rows["forecast_origin_date"].iloc[0])
        if forecast_origin != expected_origin:
            raise RuntimeError(
                f"공변량과 기존 Validation의 실제 기준일이 다릅니다: {requested_origin}"
            )
        if not (history["jpy_source_date_lag1"] < history["date"]).all():
            raise RuntimeError(f"JPY 미래 누수가 발견됐습니다: {requested_origin}")
        inputs.append(model_input)
        groups.append(rows)
    return inputs, groups


def forecasts_to_dataframe(
    predictions: list[Any],
    groups: list[pd.DataFrame],
    quantiles: list[float],
    context_length: int,
    prediction_length: int,
) -> pd.DataFrame:
    if len(predictions) != len(groups):
        raise RuntimeError("공변량 예측 결과와 기준일 그룹 수가 다릅니다.")
    q10_index = find_quantile_index(quantiles, 0.1)
    q50_index = find_quantile_index(quantiles, 0.5)
    q90_index = find_quantile_index(quantiles, 0.9)
    output_groups: list[pd.DataFrame] = []
    for prediction, reference_rows in zip(predictions, groups, strict=True):
        if hasattr(prediction, "detach"):
            prediction = prediction.detach().cpu().numpy()
        expected_shape = (1, len(quantiles), prediction_length)
        if prediction.shape != expected_shape:
            raise RuntimeError(
                f"공변량 예측 shape가 예상과 다릅니다: {prediction.shape} != {expected_shape}"
            )
        output = reference_rows.copy()
        output = output.rename(
            columns={
                "chronos_q0.1_lower": "univariate_q0.1_lower",
                "chronos_q0.5_median": "univariate_q0.5_median",
                "chronos_q0.9_upper": "univariate_q0.9_upper",
            }
        )
        output["covariate_q0.1_lower"] = prediction[0, q10_index, :]
        output["covariate_q0.5_median"] = prediction[0, q50_index, :]
        output["covariate_q0.9_upper"] = prediction[0, q90_index, :]
        output["past_covariate"] = "JPY/KRW lag1 observation"
        output["future_covariates_provided"] = False
        output["context_length"] = context_length
        output_groups.append(output)
    forecast = pd.concat(output_groups, ignore_index=True)
    valid_order = (
        (forecast["covariate_q0.1_lower"] <= forecast["covariate_q0.5_median"])
        & (forecast["covariate_q0.5_median"] <= forecast["covariate_q0.9_upper"])
    )
    if not valid_order.all():
        raise RuntimeError("공변량 Validation 분위수 순서가 올바르지 않습니다.")
    return forecast


def metric_row(data: pd.DataFrame) -> dict[str, float | int]:
    actual = data["actual_value"].to_numpy(dtype=float)
    covariate = data["covariate_q0.5_median"].to_numpy(dtype=float)
    univariate = data["univariate_q0.5_median"].to_numpy(dtype=float)
    random_walk = data["random_walk_forecast"].to_numpy(dtype=float)
    origin = data["forecast_origin_value"].to_numpy(dtype=float)

    def mae(values: np.ndarray) -> float:
        return float(np.mean(np.abs(actual - values)))

    def rmse(values: np.ndarray) -> float:
        return float(np.sqrt(np.mean((actual - values) ** 2)))

    def direction(values: np.ndarray) -> float:
        return float(np.mean(np.sign(values - origin) == np.sign(actual - origin)))

    coverage = (
        (actual >= data["covariate_q0.1_lower"].to_numpy(dtype=float))
        & (actual <= data["covariate_q0.9_upper"].to_numpy(dtype=float))
    )
    return {
        "rows": len(data),
        "covariate_mae": mae(covariate),
        "univariate_mae": mae(univariate),
        "random_walk_mae": mae(random_walk),
        "covariate_rmse": rmse(covariate),
        "univariate_rmse": rmse(univariate),
        "random_walk_rmse": rmse(random_walk),
        "covariate_direction_accuracy": direction(covariate),
        "univariate_direction_accuracy": direction(univariate),
        "random_walk_direction_accuracy": direction(random_walk),
        "interval_80_coverage": float(np.mean(coverage)),
        "interval_mean_width": float(
            np.mean(
                data["covariate_q0.9_upper"].to_numpy(dtype=float)
                - data["covariate_q0.1_lower"].to_numpy(dtype=float)
            )
        ),
    }


def grouped_metrics(forecast: pd.DataFrame, group_column: str) -> pd.DataFrame:
    rows = []
    for group_value, group in forecast.groupby(group_column, sort=True):
        rows.append({group_column: group_value, **metric_row(group)})
    return pd.DataFrame(rows)


def evaluate_forecast(
    forecast: pd.DataFrame,
    criteria: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    overall = metric_row(forecast)
    summary = pd.DataFrame([{"split": "validation_2018_2021", "origins": 48, **overall}])
    by_origin = grouped_metrics(forecast, "requested_origin")
    forecast_with_year = forecast.assign(year=forecast["target_date"].dt.year)
    by_year = grouped_metrics(forecast_with_year, "year")
    forecast_with_segment = forecast.assign(
        lead_segment=pd.cut(
            forecast["forecast_step"],
            bins=[0, 5, 10, 20],
            labels=["D+1~D+5", "D+6~D+10", "D+11~D+20"],
        )
    )
    by_lead_segment = grouped_metrics(forecast_with_segment, "lead_segment")

    mae_wins = int((by_origin["covariate_mae"] < by_origin["univariate_mae"]).sum())
    rmse_wins = int((by_origin["covariate_rmse"] < by_origin["univariate_rmse"]).sum())
    checks = {
        "lower_mae_than_univariate_chronos": overall["covariate_mae"]
        < overall["univariate_mae"],
        "lower_rmse_than_univariate_chronos": overall["covariate_rmse"]
        < overall["univariate_rmse"],
        "smaller_mae_gap_to_random_walk": (
            overall["covariate_mae"] <= overall["random_walk_mae"]
            or abs(overall["covariate_mae"] - overall["random_walk_mae"])
            < abs(overall["univariate_mae"] - overall["random_walk_mae"])
        ),
        "smaller_rmse_gap_to_random_walk": (
            overall["covariate_rmse"] <= overall["random_walk_rmse"]
            or abs(overall["covariate_rmse"] - overall["random_walk_rmse"])
            < abs(overall["univariate_rmse"] - overall["random_walk_rmse"])
        ),
        "minimum_origin_mae_wins_vs_univariate": mae_wins
        >= int(criteria["minimum_origin_mae_wins_vs_univariate"]),
        "minimum_origin_rmse_wins_vs_univariate": rmse_wins
        >= int(criteria["minimum_origin_rmse_wins_vs_univariate"]),
        "all_jpy_source_dates_must_precede_target_input_dates": True,
    }
    decision = {
        "experiment": "usd_krw_with_jpy_krw_lag1_past_covariate",
        "selection_split": "validation_2018_2021",
        "final_test_2022_2025_used": False,
        "future_covariates_provided": False,
        "origin_mae_wins_vs_univariate": mae_wins,
        "origin_rmse_wins_vs_univariate": rmse_wins,
        "criteria_checks": checks,
        "passed_candidate_entry_criteria": all(checks.values()),
        "next_action": (
            "eligible_for_shrunk_ensemble_validation"
            if all(checks.values())
            else "drop_jpy_covariate_and_do_not_run_lora"
        ),
    }
    return summary, by_origin, by_year, by_lead_segment, decision


def save_dataframe_without_overwrite(dataframe: pd.DataFrame, path: Path) -> None:
    if path.exists():
        raise FileExistsError(f"기존 공변량 Validation 결과를 덮어쓰지 않습니다: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    dataframe.to_csv(path, index=False, date_format="%Y-%m-%d")


def main() -> None:
    output_paths = (
        FORECAST_PATH,
        SUMMARY_PATH,
        BY_ORIGIN_PATH,
        BY_YEAR_PATH,
        BY_LEAD_SEGMENT_PATH,
        DECISION_PATH,
    )
    existing = [path for path in output_paths if path.exists()]
    if existing:
        raise FileExistsError(f"기존 공변량 Validation 결과를 덮어쓰지 않습니다: {existing}")

    settings, criteria = load_settings(CONFIG_PATH)
    if not torch.backends.mps.is_available():
        raise RuntimeError("현재 실행 환경에서 MPS를 사용할 수 없습니다.")
    data = load_covariate_data(DATA_PATH)
    reference = load_reference(
        REFERENCE_PATH,
        int(settings["expected_rows"]),
        int(settings["expected_origins"]),
    )
    inputs, groups = build_validation_inputs(data, reference, int(settings["context_length"]))

    pipeline = Chronos2Pipeline.from_pretrained(MODEL_ID, device_map=str(settings["device"]))
    if str(pipeline.model.device).split(":")[0] != str(settings["device"]):
        raise RuntimeError("Chronos-2 모델이 고정한 MPS 장치에 로드되지 않았습니다.")
    predictions = pipeline.predict(
        inputs,
        prediction_length=int(settings["prediction_length"]),
        context_length=int(settings["context_length"]),
        batch_size=int(settings["batch_size"]),
        cross_learning=bool(settings["cross_learning"]),
    )
    forecast = forecasts_to_dataframe(
        predictions,
        groups,
        [float(level) for level in pipeline.quantiles],
        int(settings["context_length"]),
        int(settings["prediction_length"]),
    )
    summary, by_origin, by_year, by_lead_segment, decision = evaluate_forecast(
        forecast,
        criteria,
    )

    save_dataframe_without_overwrite(forecast, FORECAST_PATH)
    save_dataframe_without_overwrite(summary, SUMMARY_PATH)
    save_dataframe_without_overwrite(by_origin, BY_ORIGIN_PATH)
    save_dataframe_without_overwrite(by_year, BY_YEAR_PATH)
    save_dataframe_without_overwrite(by_lead_segment, BY_LEAD_SEGMENT_PATH)
    DECISION_PATH.parent.mkdir(parents=True, exist_ok=True)
    DECISION_PATH.write_text(
        json.dumps(decision, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(summary.to_string(index=False))
    print(json.dumps(decision, ensure_ascii=False, indent=2))
    print(f"device: {pipeline.model.device}")
    print(f"saved_forecast: {FORECAST_PATH}")
    print(f"saved_decision: {DECISION_PATH}")


if __name__ == "__main__":
    main()
