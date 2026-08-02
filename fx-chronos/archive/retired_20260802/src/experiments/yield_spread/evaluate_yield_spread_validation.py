from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch
from chronos import Chronos2Pipeline

from src.experiments.jpy.evaluate_covariate_validation import (
    grouped_metrics,
    load_reference,
    metric_row,
    save_dataframe_without_overwrite,
)
from src.experiments.yield_spread.yield_spread_covariate_smoke import (
    build_yield_spread_input,
    load_yield_spread_data,
)
from src.models.zero_shot import find_quantile_index


PROJECT_DIR = Path(__file__).resolve().parent.parent.parent.parent
CONFIG_PATH = PROJECT_DIR / "configs" / "yield_spread_validation.json"
OUTPUT_STEM = "usd_krw_chronos2_us_kr_3y_yield_spread_asof_h20_ctx756_validation_2018_2021"
FORECAST_PATH = PROJECT_DIR / "outputs" / "forecasts" / "experiments" / "yield_spread" / f"{OUTPUT_STEM}.csv"
METRICS_DIR = PROJECT_DIR / "outputs" / "metrics" / "experiments" / "yield_spread"
SUMMARY_PATH = METRICS_DIR / f"{OUTPUT_STEM}_summary.csv"
BY_ORIGIN_PATH = METRICS_DIR / f"{OUTPUT_STEM}_by_origin.csv"
BY_YEAR_PATH = METRICS_DIR / f"{OUTPUT_STEM}_by_year.csv"
BY_LEAD_SEGMENT_PATH = METRICS_DIR / f"{OUTPUT_STEM}_by_lead_segment.csv"
DECISION_PATH = METRICS_DIR / f"{OUTPUT_STEM}_decision.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_locked_snapshot(config_path: Path, snapshot: dict[str, str]) -> Path:
    path = Path(snapshot["path"])
    if not path.is_absolute():
        path = config_path.resolve().parent.parent / path
    if not path.exists():
        raise FileNotFoundError(f"고정 Validation 입력 파일이 없습니다: {path}")
    actual = sha256_file(path)
    if actual != snapshot["sha256"]:
        raise RuntimeError(f"고정 Validation 입력 SHA-256이 다릅니다: {path}")
    return path


def load_settings(
    config_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], Path, Path, str]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    validation = config["validation"]
    expected = {
        "expected_origins": 48,
        "expected_rows": 960,
        "context_length": 756,
        "prediction_length": 20,
        "device": "mps",
        "batch_size": 8,
        "cross_learning": False,
    }
    for key, value in expected.items():
        if validation[key] != value:
            raise RuntimeError(f"한미 금리차 Validation 고정 설정이 예상과 다릅니다: {key}")
    if config["future_covariates"]:
        raise RuntimeError("한미 금리차 Validation에 미래 공변량이 설정되어 있습니다.")
    data_path = resolve_locked_snapshot(config_path, config["input_snapshot"])
    reference_path = resolve_locked_snapshot(
        config_path, config["univariate_reference_snapshot"]
    )
    return (
        validation,
        config["candidate_entry_criteria"],
        data_path,
        reference_path,
        str(config["model_id"]),
    )


def build_validation_inputs(
    data: pd.DataFrame,
    reference: pd.DataFrame,
    context_length: int,
) -> tuple[list[dict[str, Any]], list[pd.DataFrame]]:
    inputs: list[dict[str, Any]] = []
    groups: list[pd.DataFrame] = []
    for requested_origin, rows in reference.groupby("requested_origin", sort=False):
        rows = rows.sort_values("forecast_step").reset_index(drop=True)
        model_input, history, forecast_origin = build_yield_spread_input(
            data, str(requested_origin), context_length
        )
        expected_origin = pd.Timestamp(rows["forecast_origin_date"].iloc[0])
        if forecast_origin != expected_origin:
            raise RuntimeError(
                f"한미 금리차와 기존 Validation 기준일이 다릅니다: {requested_origin}"
            )
        for safe_column in (
            "kr_yield_safe_from_krw_date",
            "us_yield_safe_from_krw_date",
        ):
            if not (history[safe_column] <= history["date"]).all():
                raise RuntimeError(f"한미 금리 공개시점 누수가 발견됐습니다: {requested_origin}")
        for observation_column in (
            "kr_yield_observation_date",
            "us_yield_observation_date",
        ):
            if not (history[observation_column] < history["date"]).all():
                raise RuntimeError(f"한미 금리 관측시점 누수가 발견됐습니다: {requested_origin}")
        rows["maximum_kr_yield_age_calendar_days"] = int(
            history["kr_yield_age_calendar_days"].max()
        )
        rows["maximum_us_yield_age_calendar_days"] = int(
            history["us_yield_age_calendar_days"].max()
        )
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
        raise RuntimeError("한미 금리차 예측 결과와 기준일 그룹 수가 다릅니다.")
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
                f"한미 금리차 예측 shape가 예상과 다릅니다: {prediction.shape} != {expected_shape}"
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
        output["past_covariate"] = "US 3Y - KR 3Y yield spread point-in-time as-of"
        output["future_covariates_provided"] = False
        output["context_length"] = context_length
        outputs.append(output)
    forecast = pd.concat(outputs, ignore_index=True)
    ordered = (
        (forecast["covariate_q0.1_lower"] <= forecast["covariate_q0.5_median"])
        & (forecast["covariate_q0.5_median"] <= forecast["covariate_q0.9_upper"])
    )
    if not ordered.all():
        raise RuntimeError("한미 금리차 Validation 분위수 순서가 올바르지 않습니다.")
    return forecast


def evaluate_forecast(
    forecast: pd.DataFrame,
    criteria: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    overall = metric_row(forecast)
    maximum_kr_age = int(forecast["maximum_kr_yield_age_calendar_days"].max())
    maximum_us_age = int(forecast["maximum_us_yield_age_calendar_days"].max())
    summary = pd.DataFrame(
        [
            {
                "split": "validation_2018_2021",
                "origins": 48,
                **overall,
                "maximum_kr_yield_age_calendar_days": maximum_kr_age,
                "maximum_us_yield_age_calendar_days": maximum_us_age,
            }
        ]
    )
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
        "lower_mae_than_univariate_chronos": overall["covariate_mae"]
        < overall["univariate_mae"],
        "lower_rmse_than_univariate_chronos": overall["covariate_rmse"]
        < overall["univariate_rmse"],
        "lower_mae_than_random_walk": overall["covariate_mae"]
        < overall["random_walk_mae"],
        "lower_rmse_than_random_walk": overall["covariate_rmse"]
        < overall["random_walk_rmse"],
        "minimum_origin_mae_wins_vs_univariate": mae_wins
        >= int(criteria["minimum_origin_mae_wins_vs_univariate"]),
        "minimum_origin_rmse_wins_vs_univariate": rmse_wins
        >= int(criteria["minimum_origin_rmse_wins_vs_univariate"]),
        "all_source_observations_and_safe_dates_must_precede_or_equal_input_dates": True,
    }
    passed = all(checks.values())
    decision = {
        "experiment": "usd_krw_with_us_kr_3y_yield_spread_asof_past_covariate",
        "selection_split": "validation_2018_2021",
        "final_test_2022_2025_used": False,
        "future_covariates_provided": False,
        "origin_mae_wins_vs_univariate": mae_wins,
        "origin_rmse_wins_vs_univariate": rmse_wins,
        "maximum_kr_yield_age_calendar_days": maximum_kr_age,
        "maximum_us_yield_age_calendar_days": maximum_us_age,
        "criteria_checks": checks,
        "passed_candidate_entry_criteria": passed,
        "next_action": (
            "eligible_for_additional_validation"
            if passed
            else "drop_yield_spread_covariate_and_do_not_run_lora"
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
        raise FileExistsError(f"기존 한미 금리차 Validation 결과를 덮어쓰지 않습니다: {existing}")
    settings, criteria, data_path, reference_path, model_id = load_settings(CONFIG_PATH)
    if not torch.backends.mps.is_available():
        raise RuntimeError("현재 실행 환경에서 MPS를 사용할 수 없습니다.")
    data = load_yield_spread_data(data_path)
    reference = load_reference(
        reference_path,
        int(settings["expected_rows"]),
        int(settings["expected_origins"]),
    )
    inputs, groups = build_validation_inputs(
        data, reference, int(settings["context_length"])
    )

    pipeline = Chronos2Pipeline.from_pretrained(model_id, device_map=str(settings["device"]))
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
