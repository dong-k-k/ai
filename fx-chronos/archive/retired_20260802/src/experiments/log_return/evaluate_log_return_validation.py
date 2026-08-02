from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch
from chronos import Chronos2Pipeline

from src.evaluation.backtest import load_model_data
from src.experiments.jpy.evaluate_covariate_validation import load_reference, save_dataframe_without_overwrite
from src.experiments.log_return.log_return_smoke import build_log_return_input, reconstruct_levels
from src.models.zero_shot import find_quantile_index


PROJECT_DIR = Path(__file__).resolve().parent.parent.parent.parent
MODEL_ID = "amazon/chronos-2"
CONFIG_PATH = PROJECT_DIR / "configs" / "log_return_validation.json"
DATA_PATH = (
    PROJECT_DIR / "data" / "processed" / "usd_krw_model_weekdays_19640504_20260730.csv"
)
REFERENCE_PATH = (
    PROJECT_DIR
    / "outputs"
    / "forecasts"
    / "core"
    / "usd_krw_zero_shot_h20_ctx756_validation_2018_2021.csv"
)
OUTPUT_STEM = "usd_krw_chronos2_log_return_h20_ctx756_validation_2018_2021"
FORECAST_PATH = PROJECT_DIR / "outputs" / "forecasts" / "experiments" / "log_return" / f"{OUTPUT_STEM}.csv"
METRICS_DIR = PROJECT_DIR / "outputs" / "metrics" / "experiments" / "log_return"
SUMMARY_PATH = METRICS_DIR / f"{OUTPUT_STEM}_summary.csv"
BY_ORIGIN_PATH = METRICS_DIR / f"{OUTPUT_STEM}_by_origin.csv"
BY_YEAR_PATH = METRICS_DIR / f"{OUTPUT_STEM}_by_year.csv"
BY_LEAD_SEGMENT_PATH = METRICS_DIR / f"{OUTPUT_STEM}_by_lead_segment.csv"
DECISION_PATH = METRICS_DIR / f"{OUTPUT_STEM}_decision.json"


def load_settings(config_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    validation = config["validation"]
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
            raise RuntimeError(f"로그수익률 Validation 고정 설정이 예상과 다릅니다: {key}")
    return validation, config["candidate_entry_criteria"]


def build_validation_inputs(
    data: pd.DataFrame,
    reference: pd.DataFrame,
    context_length: int,
    prediction_length: int,
) -> tuple[list[np.ndarray], list[pd.DataFrame], list[float]]:
    inputs: list[np.ndarray] = []
    groups: list[pd.DataFrame] = []
    origin_values: list[float] = []
    for requested_origin, rows in reference.groupby("requested_origin", sort=False):
        rows = rows.sort_values("forecast_step").reset_index(drop=True)
        model_input, origin_index = build_log_return_input(
            data,
            str(requested_origin),
            context_length,
            prediction_length,
        )
        actual_origin = pd.Timestamp(data.loc[origin_index, "date"])
        expected_origin = pd.Timestamp(rows["forecast_origin_date"].iloc[0])
        if actual_origin != expected_origin:
            raise RuntimeError(
                f"로그수익률과 기존 Validation의 실제 기준일이 다릅니다: {requested_origin}"
            )
        inputs.append(model_input)
        groups.append(rows)
        origin_values.append(float(data.loc[origin_index, "value"]))
    return inputs, groups, origin_values


def forecasts_to_dataframe(
    predictions: list[Any],
    groups: list[pd.DataFrame],
    origin_values: list[float],
    quantiles: list[float],
    context_length: int,
    prediction_length: int,
) -> pd.DataFrame:
    if not (len(predictions) == len(groups) == len(origin_values)):
        raise RuntimeError("로그수익률 예측, 기준일 그룹, 기준값 수가 다릅니다.")
    q50_index = find_quantile_index(quantiles, 0.5)
    outputs: list[pd.DataFrame] = []
    for prediction, reference_rows, origin_value in zip(
        predictions, groups, origin_values, strict=True
    ):
        if hasattr(prediction, "detach"):
            prediction = prediction.detach().cpu().numpy()
        prediction = np.asarray(prediction)
        expected_shape = (1, len(quantiles), prediction_length)
        if prediction.shape != expected_shape:
            raise RuntimeError(
                f"로그수익률 예측 shape가 예상과 다릅니다: {prediction.shape} != {expected_shape}"
            )
        q50_returns = prediction[0, q50_index, :]
        output = reference_rows.copy().rename(
            columns={"chronos_q0.5_median": "level_chronos_q0.5_median"}
        )
        output["predicted_log_return_q0.5"] = q50_returns
        output["log_return_reconstructed_q0.5"] = reconstruct_levels(
            origin_value, q50_returns
        )
        output["log_return_context_length"] = context_length
        outputs.append(output)
    forecast = pd.concat(outputs, ignore_index=True)
    if forecast[["predicted_log_return_q0.5", "log_return_reconstructed_q0.5"]].isna().any().any():
        raise RuntimeError("로그수익률 Validation 결과에 결측값이 있습니다.")
    if not np.isfinite(
        forecast[["predicted_log_return_q0.5", "log_return_reconstructed_q0.5"]]
    ).all().all():
        raise RuntimeError("로그수익률 Validation 결과에 유한하지 않은 값이 있습니다.")
    return forecast


def metric_row(data: pd.DataFrame) -> dict[str, float | int]:
    actual = data["actual_value"].to_numpy(dtype=float)
    transformed = data["log_return_reconstructed_q0.5"].to_numpy(dtype=float)
    level = data["level_chronos_q0.5_median"].to_numpy(dtype=float)
    random_walk = data["random_walk_forecast"].to_numpy(dtype=float)
    origin = data["forecast_origin_value"].to_numpy(dtype=float)

    def mae(values: np.ndarray) -> float:
        return float(np.mean(np.abs(actual - values)))

    def rmse(values: np.ndarray) -> float:
        return float(np.sqrt(np.mean((actual - values) ** 2)))

    def direction(values: np.ndarray) -> float:
        return float(np.mean(np.sign(values - origin) == np.sign(actual - origin)))

    return {
        "rows": len(data),
        "log_return_mae": mae(transformed),
        "level_chronos_mae": mae(level),
        "random_walk_mae": mae(random_walk),
        "log_return_rmse": rmse(transformed),
        "level_chronos_rmse": rmse(level),
        "random_walk_rmse": rmse(random_walk),
        "log_return_direction_accuracy": direction(transformed),
        "level_chronos_direction_accuracy": direction(level),
        "random_walk_direction_accuracy": direction(random_walk),
    }


def grouped_metrics(forecast: pd.DataFrame, group_column: str) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {group_column: value, **metric_row(group)}
            for value, group in forecast.groupby(group_column, sort=True, observed=True)
        ]
    )


def evaluate_forecast(
    forecast: pd.DataFrame,
    criteria: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    overall = metric_row(forecast)
    summary = pd.DataFrame([{"split": "validation_2018_2021", "origins": 48, **overall}])
    by_origin = grouped_metrics(forecast, "requested_origin")
    by_year = grouped_metrics(forecast.assign(year=forecast["target_date"].dt.year), "year")
    by_segment = grouped_metrics(
        forecast.assign(
            lead_segment=pd.cut(
                forecast["forecast_step"],
                bins=[0, 5, 10, 20],
                labels=["D+1~D+5", "D+6~D+10", "D+11~D+20"],
            )
        ),
        "lead_segment",
    )
    mae_wins = int((by_origin["log_return_mae"] < by_origin["level_chronos_mae"]).sum())
    rmse_wins = int((by_origin["log_return_rmse"] < by_origin["level_chronos_rmse"]).sum())
    checks = {
        "lower_mae_than_level_chronos": overall["log_return_mae"] < overall["level_chronos_mae"],
        "lower_rmse_than_level_chronos": overall["log_return_rmse"] < overall["level_chronos_rmse"],
        "lower_mae_than_random_walk": overall["log_return_mae"] < overall["random_walk_mae"],
        "lower_rmse_than_random_walk": overall["log_return_rmse"] < overall["random_walk_rmse"],
        "minimum_origin_mae_wins_vs_level_chronos": mae_wins
        >= int(criteria["minimum_origin_mae_wins_vs_level_chronos"]),
        "minimum_origin_rmse_wins_vs_level_chronos": rmse_wins
        >= int(criteria["minimum_origin_rmse_wins_vs_level_chronos"]),
        "all_forecast_origins_must_match_reference": True,
    }
    passed = all(checks.values())
    decision = {
        "experiment": "usd_krw_log_return_target",
        "selection_split": "validation_2018_2021",
        "final_test_2022_2025_used": False,
        "intervals_evaluated": False,
        "origin_mae_wins_vs_level_chronos": mae_wins,
        "origin_rmse_wins_vs_level_chronos": rmse_wins,
        "criteria_checks": checks,
        "passed_candidate_entry_criteria": passed,
        "next_action": (
            "eligible_for_additional_validation" if passed else "drop_log_return_target_candidate"
        ),
    }
    return summary, by_origin, by_year, by_segment, decision


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
        raise FileExistsError(f"기존 로그수익률 Validation 결과를 덮어쓰지 않습니다: {existing}")

    settings, criteria = load_settings(CONFIG_PATH)
    if not torch.backends.mps.is_available():
        raise RuntimeError("현재 실행 환경에서 MPS를 사용할 수 없습니다.")
    data = load_model_data(DATA_PATH)
    reference = load_reference(
        REFERENCE_PATH,
        int(settings["expected_rows"]),
        int(settings["expected_origins"]),
    )
    inputs, groups, origin_values = build_validation_inputs(
        data,
        reference,
        int(settings["context_length"]),
        int(settings["prediction_length"]),
    )

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
        origin_values,
        [float(level) for level in pipeline.quantiles],
        int(settings["context_length"]),
        int(settings["prediction_length"]),
    )
    summary, by_origin, by_year, by_segment, decision = evaluate_forecast(
        forecast, criteria
    )

    save_dataframe_without_overwrite(forecast, FORECAST_PATH)
    save_dataframe_without_overwrite(summary, SUMMARY_PATH)
    save_dataframe_without_overwrite(by_origin, BY_ORIGIN_PATH)
    save_dataframe_without_overwrite(by_year, BY_YEAR_PATH)
    save_dataframe_without_overwrite(by_segment, BY_LEAD_SEGMENT_PATH)
    DECISION_PATH.parent.mkdir(parents=True, exist_ok=True)
    DECISION_PATH.write_text(
        json.dumps(decision, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(summary.to_string(index=False))
    print(json.dumps(decision, ensure_ascii=False, indent=2))
    print(f"device: {pipeline.model.device}")
    print(f"saved_forecast: {FORECAST_PATH}")
    print(f"saved_decision: {DECISION_PATH}")


if __name__ == "__main__":
    main()
