from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch
from chronos import Chronos2Pipeline

from src.experiments.broad_usd.broad_usd_covariate_smoke import (
    build_broad_usd_input,
    load_broad_usd_covariate_data,
)
from src.experiments.jpy.evaluate_covariate_validation import (
    grouped_metrics,
    load_reference,
    metric_row,
    save_dataframe_without_overwrite,
)
from src.models.zero_shot import find_quantile_index


PROJECT_DIR = Path(__file__).resolve().parent.parent.parent.parent
MODEL_ID = "amazon/chronos-2"
CONFIG_PATH = PROJECT_DIR / "configs" / "broad_usd_validation.json"
DATA_PATH = (
    PROJECT_DIR
    / "data"
    / "processed"
    / "usd_broad_usd_covariates_weekdays_asof_20090114_20260730.csv"
)
REFERENCE_PATH = (
    PROJECT_DIR
    / "outputs"
    / "forecasts"
    / "core"
    / "usd_krw_zero_shot_h20_ctx756_validation_2018_2021.csv"
)
OUTPUT_STEM = "usd_krw_chronos2_broad_usd_asof_h20_ctx756_validation_2018_2021"
FORECAST_PATH = PROJECT_DIR / "outputs" / "forecasts" / "experiments" / "broad_usd" / f"{OUTPUT_STEM}.csv"
METRICS_DIR = PROJECT_DIR / "outputs" / "metrics" / "experiments" / "broad_usd"
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
            raise RuntimeError(f"Broad Dollar Validation 고정 설정이 예상과 다릅니다: {key}")
    if config["future_covariates"]:
        raise RuntimeError("Broad Dollar Validation에 미래 공변량이 설정되어 있습니다.")
    return validation, config["candidate_entry_criteria"]


def build_validation_inputs(
    data: pd.DataFrame,
    reference: pd.DataFrame,
    context_length: int,
) -> tuple[list[dict[str, Any]], list[pd.DataFrame]]:
    inputs: list[dict[str, Any]] = []
    groups: list[pd.DataFrame] = []
    for requested_origin, rows in reference.groupby("requested_origin", sort=False):
        rows = rows.sort_values("forecast_step").reset_index(drop=True)
        model_input, history, forecast_origin = build_broad_usd_input(
            data, str(requested_origin), context_length
        )
        expected_origin = pd.Timestamp(rows["forecast_origin_date"].iloc[0])
        if forecast_origin != expected_origin:
            raise RuntimeError(
                f"Broad Dollar와 기존 Validation 기준일이 다릅니다: {requested_origin}"
            )
        if not (history["broad_usd_safe_from_krw_date"] <= history["date"]).all():
            raise RuntimeError(f"Broad Dollar 공개시점 누수가 발견됐습니다: {requested_origin}")
        if not (history["broad_usd_observation_date"] < history["date"]).all():
            raise RuntimeError(f"Broad Dollar 관측시점 누수가 발견됐습니다: {requested_origin}")
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
        raise RuntimeError("Broad Dollar 예측 결과와 기준일 그룹 수가 다릅니다.")
    q10_index = find_quantile_index(quantiles, 0.1)
    q50_index = find_quantile_index(quantiles, 0.5)
    q90_index = find_quantile_index(quantiles, 0.9)
    outputs: list[pd.DataFrame] = []
    for prediction, reference_rows in zip(predictions, groups, strict=True):
        if hasattr(prediction, "detach"):
            prediction = prediction.detach().cpu().numpy()
        prediction = np.asarray(prediction)
        expected_shape = (1, len(quantiles), prediction_length)
        if prediction.shape != expected_shape:
            raise RuntimeError(
                f"Broad Dollar 예측 shape가 예상과 다릅니다: {prediction.shape} != {expected_shape}"
            )
        output = reference_rows.copy().rename(
            columns={
                "chronos_q0.1_lower": "univariate_q0.1_lower",
                "chronos_q0.5_median": "univariate_q0.5_median",
                "chronos_q0.9_upper": "univariate_q0.9_upper",
            }
        )
        output["covariate_q0.1_lower"] = prediction[0, q10_index, :]
        output["covariate_q0.5_median"] = prediction[0, q50_index, :]
        output["covariate_q0.9_upper"] = prediction[0, q90_index, :]
        output["past_covariate"] = "DTWEXBGS broad_usd_index point-in-time as-of"
        output["future_covariates_provided"] = False
        output["context_length"] = context_length
        outputs.append(output)
    forecast = pd.concat(outputs, ignore_index=True)
    valid_order = (
        (forecast["covariate_q0.1_lower"] <= forecast["covariate_q0.5_median"])
        & (forecast["covariate_q0.5_median"] <= forecast["covariate_q0.9_upper"])
    )
    if not valid_order.all():
        raise RuntimeError("Broad Dollar Validation 분위수 순서가 올바르지 않습니다.")
    return forecast


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
    mae_wins = int((by_origin["covariate_mae"] < by_origin["univariate_mae"]).sum())
    rmse_wins = int((by_origin["covariate_rmse"] < by_origin["univariate_rmse"]).sum())
    checks = {
        "lower_mae_than_univariate_chronos": overall["covariate_mae"] < overall["univariate_mae"],
        "lower_rmse_than_univariate_chronos": overall["covariate_rmse"] < overall["univariate_rmse"],
        "lower_mae_than_random_walk": overall["covariate_mae"] < overall["random_walk_mae"],
        "lower_rmse_than_random_walk": overall["covariate_rmse"] < overall["random_walk_rmse"],
        "minimum_origin_mae_wins_vs_univariate": mae_wins
        >= int(criteria["minimum_origin_mae_wins_vs_univariate"]),
        "minimum_origin_rmse_wins_vs_univariate": rmse_wins
        >= int(criteria["minimum_origin_rmse_wins_vs_univariate"]),
        "all_source_observations_and_safe_dates_must_precede_or_equal_input_dates": True,
    }
    passed = all(checks.values())
    decision = {
        "experiment": "usd_krw_with_broad_usd_index_asof_past_covariate",
        "selection_split": "validation_2018_2021",
        "final_test_2022_2025_used": False,
        "future_covariates_provided": False,
        "origin_mae_wins_vs_univariate": mae_wins,
        "origin_rmse_wins_vs_univariate": rmse_wins,
        "criteria_checks": checks,
        "passed_candidate_entry_criteria": passed,
        "next_action": (
            "eligible_for_additional_validation"
            if passed
            else "drop_broad_usd_covariate_candidate"
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
        raise FileExistsError(f"기존 Broad Dollar Validation 결과를 덮어쓰지 않습니다: {existing}")
    settings, criteria = load_settings(CONFIG_PATH)
    if not torch.backends.mps.is_available():
        raise RuntimeError("현재 실행 환경에서 MPS를 사용할 수 없습니다.")
    data = load_broad_usd_covariate_data(DATA_PATH)
    reference = load_reference(
        REFERENCE_PATH,
        int(settings["expected_rows"]),
        int(settings["expected_origins"]),
    )
    inputs, groups = build_validation_inputs(
        data, reference, int(settings["context_length"])
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
