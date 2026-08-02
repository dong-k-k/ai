from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import torch
from chronos import Chronos2Pipeline

from src.evaluation.backtest import MODEL_ID, load_model_data, run_walk_forward_backtest
from src.evaluation.evaluate import save_without_overwrite
from src.evaluation.evaluate_shrunk_ensemble import build_grouped_metrics, point_metrics


PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = PROJECT_DIR / "configs" / "ensemble.json"
MODEL_DATA_PATH = (
    PROJECT_DIR
    / "data"
    / "processed"
    / "usd_krw_model_weekdays_19640504_20260730.csv"
)
OUTPUT_STEM = "usd_krw_shrunk_ensemble_h20_ctx756_alpha0.5_2026_locked"
FORECAST_PATH = PROJECT_DIR / "outputs" / "forecasts" / "ensemble" / f"{OUTPUT_STEM}.csv"
METRICS_DIR = PROJECT_DIR / "outputs" / "metrics" / "ensemble"
SUMMARY_PATH = METRICS_DIR / f"{OUTPUT_STEM}_summary.csv"
BY_ORIGIN_PATH = METRICS_DIR / f"{OUTPUT_STEM}_by_origin.csv"
BY_LEAD_PATH = METRICS_DIR / f"{OUTPUT_STEM}_by_lead.csv"
DECISION_PATH = METRICS_DIR / f"{OUTPUT_STEM}_decision.json"
DEVICE = "mps"
BATCH_SIZE = 7
ORIGIN_CHUNK_SIZE = 7


def load_locked_evaluation(config_path: Path) -> dict[str, object]:
    """결과를 보기 전에 고정한 2026년 평가 설정을 검증한다."""
    config = json.loads(config_path.read_text(encoding="utf-8"))
    locked = config["locked_2026_evaluation"]
    expected_origins = [
        "2026-01-01",
        "2026-02-01",
        "2026-03-01",
        "2026-04-01",
        "2026-05-01",
        "2026-06-01",
        "2026-07-01",
    ]
    if float(locked["alpha"]) != 0.5:
        raise RuntimeError("2026년 고정 평가 α가 0.5가 아닙니다.")
    if int(locked["context_length"]) != 756:
        raise RuntimeError("2026년 고정 평가 context가 756이 아닙니다.")
    if int(locked["prediction_length"]) != 20:
        raise RuntimeError("2026년 고정 평가 horizon이 20이 아닙니다.")
    if locked["requested_origins"] != expected_origins:
        raise RuntimeError("2026년 평가 기준일이 사전 고정 목록과 다릅니다.")
    if int(locked["expected_origins"]) != 7 or int(locked["expected_rows"]) != 140:
        raise RuntimeError("2026년 예상 기준일 또는 행 수가 고정값과 다릅니다.")
    return locked


def validate_forecast(forecast: pd.DataFrame, locked: dict[str, object]) -> None:
    required_columns = {
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
    missing = required_columns - set(forecast.columns)
    if missing:
        raise RuntimeError(f"2026년 평가 결과에 필수 열이 없습니다: {sorted(missing)}")
    if forecast[list(required_columns)].isna().any().any():
        raise RuntimeError("2026년 평가 결과에 결측값이 있습니다.")
    if len(forecast) != int(locked["expected_rows"]):
        raise RuntimeError(f"2026년 평가 행 수가 예상과 다릅니다: {len(forecast)}")
    if forecast["requested_origin"].nunique() != int(locked["expected_origins"]):
        raise RuntimeError("2026년 평가 기준일 수가 예상과 다릅니다.")
    counts = forecast.groupby("requested_origin")["forecast_step"].agg(["size", "nunique"])
    if ((counts["size"] != 20) | (counts["nunique"] != 20)).any():
        raise RuntimeError("2026년 기준일별 예측 행 또는 step이 20개가 아닙니다.")
    if forecast.duplicated(["requested_origin", "forecast_step", "target_date"]).any():
        raise RuntimeError("2026년 평가 결과에 중복 행이 있습니다.")
    target_dates = pd.to_datetime(forecast["target_date"])
    if target_dates.min() < pd.Timestamp("2026-01-01") or target_dates.max() > pd.Timestamp("2026-07-30"):
        raise RuntimeError("2026년 평가 결과에 고정 범위 밖 목표일이 있습니다.")


def main() -> None:
    output_paths = (FORECAST_PATH, SUMMARY_PATH, BY_ORIGIN_PATH, BY_LEAD_PATH, DECISION_PATH)
    existing = [path for path in output_paths if path.exists()]
    if existing:
        raise FileExistsError(f"기존 2026년 고정 평가를 덮어쓰지 않습니다: {existing}")
    if DEVICE == "mps" and not torch.backends.mps.is_available():
        raise RuntimeError("현재 실행 환경에서 MPS를 사용할 수 없습니다.")

    locked = load_locked_evaluation(CONFIG_PATH)
    model_data = load_model_data(MODEL_DATA_PATH)
    pipeline = Chronos2Pipeline.from_pretrained(MODEL_ID, device_map=DEVICE)
    if str(pipeline.model.device).split(":")[0] != DEVICE:
        raise RuntimeError(
            f"모델 장치가 요청과 다릅니다: 요청={DEVICE}, 실제={pipeline.model.device}"
        )

    forecast = run_walk_forward_backtest(
        pipeline,
        model_data,
        requested_origins=locked["requested_origins"],
        horizon=int(locked["prediction_length"]),
        context_length=int(locked["context_length"]),
        batch_size=BATCH_SIZE,
        origin_chunk_size=ORIGIN_CHUNK_SIZE,
    ).sort_values(["forecast_origin_date", "forecast_step"]).reset_index(drop=True)
    validate_forecast(forecast, locked)
    forecast["alpha"] = float(locked["alpha"])
    forecast["ensemble_forecast"] = forecast["forecast_origin_value"] + forecast["alpha"] * (
        forecast["chronos_q0.5_median"] - forecast["forecast_origin_value"]
    )

    metrics = point_metrics(forecast)
    summary = pd.DataFrame(
        [
            {
                "evaluation": "locked_2026_january_to_july",
                "alpha": locked["alpha"],
                "context_length": locked["context_length"],
                "horizon": locked["prediction_length"],
                "origins": locked["expected_origins"],
                **metrics,
            }
        ]
    )
    by_origin = build_grouped_metrics(forecast, "requested_origin")
    by_lead = build_grouped_metrics(forecast, "forecast_step")
    mae_win_count = int((by_origin["ensemble_mae"] < by_origin["random_walk_mae"]).sum())
    rmse_win_count = int((by_origin["ensemble_rmse"] < by_origin["random_walk_rmse"]).sum())
    overall_pass = bool(
        metrics["ensemble_mae"] < metrics["random_walk_mae"]
        and metrics["ensemble_rmse"] < metrics["random_walk_rmse"]
    )
    consistency_pass = mae_win_count >= 4 and rmse_win_count >= 4
    passed = overall_pass and consistency_pass
    decision = {
        "evaluation": "locked_2026_january_to_july",
        "settings_were_locked_before_forecast": True,
        "alpha_was_reselected": False,
        "final_test_2022_2025_used": False,
        "alpha": locked["alpha"],
        "context_length": locked["context_length"],
        "prediction_length": locked["prediction_length"],
        "origin_count": locked["expected_origins"],
        "mae_origin_win_count_vs_random_walk": mae_win_count,
        "rmse_origin_win_count_vs_random_walk": rmse_win_count,
        "overall_pass": overall_pass,
        "origin_consistency_pass": consistency_pass,
        "passed_pre_registered_criteria": passed,
        "status": (
            "provisional_due_to_small_sample"
            if passed
            else "not_confirmed_do_not_retune_with_2026_results"
        ),
        "small_sample_warning": locked["small_sample_warning"],
    }

    save_without_overwrite(forecast, FORECAST_PATH)
    save_without_overwrite(summary, SUMMARY_PATH)
    save_without_overwrite(by_origin, BY_ORIGIN_PATH)
    save_without_overwrite(by_lead, BY_LEAD_PATH)
    DECISION_PATH.parent.mkdir(parents=True, exist_ok=True)
    DECISION_PATH.write_text(
        json.dumps(decision, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(summary.to_string(index=False))
    print(json.dumps(decision, ensure_ascii=False, indent=2))
    print(f"target_start: {forecast['target_date'].min()}")
    print(f"target_end: {forecast['target_date'].max()}")
    print(f"saved_forecast: {FORECAST_PATH}")
    print(f"saved_decision: {DECISION_PATH}")


if __name__ == "__main__":
    main()
