from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import torch
from chronos import Chronos2Pipeline

from src.evaluation.backtest import build_monthly_origins, load_model_data, run_walk_forward_backtest
from src.evaluation.evaluate import save_without_overwrite
from src.evaluation.evaluate_h60_locked_ensemble import sha256_file
from src.evaluation.evaluate_shrunk_ensemble import build_grouped_metrics, point_metrics


PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = PROJECT_DIR / "configs" / "h90_ensemble_validation.json"
OUTPUT_STEM = "usd_krw_shrunk_ensemble_h90_ctx756_alpha0.5_validation_2018_2021"
FORECAST_PATH = PROJECT_DIR / "outputs" / "forecasts" / "ensemble" / f"{OUTPUT_STEM}.csv"
METRICS_DIR = PROJECT_DIR / "outputs" / "metrics" / "ensemble"
SUMMARY_PATH = METRICS_DIR / f"{OUTPUT_STEM}_summary.csv"
BY_ORIGIN_PATH = METRICS_DIR / f"{OUTPUT_STEM}_by_origin.csv"
BY_LEAD_PATH = METRICS_DIR / f"{OUTPUT_STEM}_by_lead.csv"
DECISION_PATH = METRICS_DIR / f"{OUTPUT_STEM}_decision.json"


def load_settings(config_path: Path = CONFIG_PATH) -> tuple[dict[str, object], Path]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    validation = config["validation"]
    if int(validation["prediction_length"]) != 90:
        raise RuntimeError("H90 고정 평가의 prediction length가 90이 아닙니다.")
    if int(validation["context_length"]) != 756 or float(validation["alpha"]) != 0.5:
        raise RuntimeError("H90 고정 평가의 context 또는 alpha가 고정값과 다릅니다.")
    if bool(validation["alpha_reselected_for_h90"]):
        raise RuntimeError("H90 결과로 alpha를 다시 선택할 수 없습니다.")
    if bool(validation["cross_learning"]):
        raise RuntimeError("H90 고정 평가에서 cross learning을 사용할 수 없습니다.")
    for snapshot_name in ("input_snapshot", "alpha_provenance_snapshot"):
        snapshot = config[snapshot_name]
        path = PROJECT_DIR / snapshot["path"]
        if not path.exists() or sha256_file(path) != snapshot["sha256"]:
            raise RuntimeError(f"고정 파일 SHA-256이 다릅니다: {snapshot_name}")
    return config, PROJECT_DIR / config["input_snapshot"]["path"]


def requested_origins() -> list[str]:
    return build_monthly_origins(2018, 2021)[:-4]


def validate_forecast(forecast: pd.DataFrame, validation: dict[str, object]) -> None:
    required = {
        "requested_origin", "forecast_origin_date", "forecast_origin_value",
        "forecast_step", "target_date", "actual_value", "chronos_q0.1_lower",
        "chronos_q0.5_median", "chronos_q0.9_upper", "random_walk_forecast",
        "context_length",
    }
    missing = required - set(forecast.columns)
    if missing or forecast[list(required)].isna().any().any():
        raise RuntimeError(f"H90 예측에 필수 열이 없거나 결측입니다: {sorted(missing)}")
    if len(forecast) != int(validation["expected_rows"]):
        raise RuntimeError(f"H90 평가 행 수가 예상과 다릅니다: {len(forecast)}")
    if forecast["requested_origin"].nunique() != int(validation["expected_origins"]):
        raise RuntimeError("H90 평가 기준일 수가 예상과 다릅니다.")
    counts = forecast.groupby("requested_origin")["forecast_step"].agg(["size", "nunique"])
    if ((counts["size"] != 90) | (counts["nunique"] != 90)).any():
        raise RuntimeError("H90 기준일별 행 또는 step이 90개가 아닙니다.")
    if forecast.duplicated(["requested_origin", "forecast_step", "target_date"]).any():
        raise RuntimeError("H90 평가 결과에 중복 행이 있습니다.")
    dates = pd.to_datetime(forecast["target_date"])
    if dates.min() < pd.Timestamp(validation["target_start"]) or dates.max() > pd.Timestamp(validation["target_end"]):
        raise RuntimeError("H90 평가 결과에 Validation 밖 목표일이 있습니다.")
    if set(forecast["context_length"].astype(int).unique()) != {756}:
        raise RuntimeError("H90 평가 context가 756이 아닙니다.")


def evaluate_forecast(forecast: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, object]]:
    metrics = point_metrics(forecast)
    by_origin = build_grouped_metrics(forecast, "requested_origin")
    by_lead = build_grouped_metrics(forecast, "forecast_step")
    mae_wins = int((by_origin["ensemble_mae"] < by_origin["random_walk_mae"]).sum())
    rmse_wins = int((by_origin["ensemble_rmse"] < by_origin["random_walk_rmse"]).sum())
    checks = {
        "lower_mae_than_random_walk": metrics["ensemble_mae"] < metrics["random_walk_mae"],
        "lower_rmse_than_random_walk": metrics["ensemble_rmse"] < metrics["random_walk_rmse"],
    }
    summary = pd.DataFrame([{"split": "validation_2018_2021", "horizon": 90, "alpha": 0.5, "origins": forecast["requested_origin"].nunique(), **metrics}])
    passed = all(checks.values())
    decision = {
        "evaluation": "h90_locked_alpha0.5_validation_2018_2021",
        "alpha": 0.5,
        "alpha_was_reselected_for_h90": False,
        "final_test_2022_2025_used": False,
        "origin_mae_wins_vs_random_walk": mae_wins,
        "origin_rmse_wins_vs_random_walk": rmse_wins,
        "criteria_checks": {key: bool(value) for key, value in checks.items()},
        "passed_h90_service_candidate_criteria": passed,
        "next_action": "include_h90_service_candidate" if passed else "drop_h90_service_candidate_do_not_retune_alpha",
    }
    return summary, by_origin, by_lead, decision


def main() -> None:
    outputs = (FORECAST_PATH, SUMMARY_PATH, BY_ORIGIN_PATH, BY_LEAD_PATH, DECISION_PATH)
    existing = [path for path in outputs if path.exists()]
    if existing:
        raise FileExistsError(f"기존 H90 고정 평가를 덮어쓰지 않습니다: {existing}")
    config, input_path = load_settings()
    validation = config["validation"]
    if validation["device"] == "mps" and not torch.backends.mps.is_available():
        raise RuntimeError("현재 실행 환경에서 MPS를 사용할 수 없습니다.")
    pipeline = Chronos2Pipeline.from_pretrained(config["model_id"], device_map=validation["device"])
    forecast = run_walk_forward_backtest(
        pipeline, load_model_data(input_path), requested_origins(), horizon=90,
        context_length=756, batch_size=int(validation["batch_size"]),
        origin_chunk_size=int(validation["origin_chunk_size"]),
    ).sort_values(["forecast_origin_date", "forecast_step"]).reset_index(drop=True)
    validate_forecast(forecast, validation)
    forecast["alpha"] = 0.5
    forecast["ensemble_forecast"] = forecast["forecast_origin_value"] + 0.5 * (
        forecast["chronos_q0.5_median"] - forecast["forecast_origin_value"]
    )
    summary, by_origin, by_lead, decision = evaluate_forecast(forecast)
    save_without_overwrite(forecast, FORECAST_PATH)
    save_without_overwrite(summary, SUMMARY_PATH)
    save_without_overwrite(by_origin, BY_ORIGIN_PATH)
    save_without_overwrite(by_lead, BY_LEAD_PATH)
    DECISION_PATH.parent.mkdir(parents=True, exist_ok=True)
    DECISION_PATH.write_text(json.dumps(decision, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(summary.to_string(index=False))
    print(json.dumps(decision, ensure_ascii=False, indent=2))
    print(f"device: {pipeline.model.device}")
    print(f"saved_forecast: {FORECAST_PATH}")
    print(f"saved_decision: {DECISION_PATH}")


if __name__ == "__main__":
    main()
