from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from calibrate_prediction_interval import grouped_metrics, interval_metrics
from evaluate import save_without_overwrite


PROJECT_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_DIR / "configs" / "interval_calibration.json"
INPUT_PATH = (
    PROJECT_DIR
    / "outputs"
    / "forecasts"
    / "usd_krw_shrunk_ensemble_h20_ctx756_alpha0.5_2026_locked.csv"
)
OUTPUT_STEM = "usd_krw_chronos2_h20_ctx756_interval_correction3.0085_2026_locked"
FORECAST_PATH = PROJECT_DIR / "outputs" / "forecasts" / f"{OUTPUT_STEM}.csv"
METRICS_DIR = PROJECT_DIR / "outputs" / "metrics"
SUMMARY_PATH = METRICS_DIR / f"{OUTPUT_STEM}_summary.csv"
BY_ORIGIN_PATH = METRICS_DIR / f"{OUTPUT_STEM}_by_origin.csv"
BY_LEAD_PATH = METRICS_DIR / f"{OUTPUT_STEM}_by_lead.csv"
DECISION_PATH = METRICS_DIR / f"{OUTPUT_STEM}_decision.json"
EXPECTED_CORRECTION = 3.008544921875


def load_locked_config(config_path: Path) -> tuple[dict[str, object], dict[str, object]]:
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
    if float(config["nominal_coverage"]) != 0.8:
        raise RuntimeError("목표 포함률이 고정값 0.8과 다릅니다.")
    if float(locked["interval_correction"]) != EXPECTED_CORRECTION:
        raise RuntimeError("2026년 고정 보정값이 3.008544921875원과 다릅니다.")
    if locked["requested_origins"] != expected_origins:
        raise RuntimeError("2026년 구간 평가 기준일이 고정 목록과 다릅니다.")
    if int(locked["expected_origins"]) != 7 or int(locked["expected_rows"]) != 140:
        raise RuntimeError("2026년 예상 기준일 또는 행 수가 고정값과 다릅니다.")
    return config, locked


def load_2026_forecast(input_path: Path, locked: dict[str, object]) -> pd.DataFrame:
    dataframe = pd.read_csv(
        input_path,
        parse_dates=["requested_origin", "forecast_origin_date", "target_date"],
    )
    required_columns = {
        "requested_origin",
        "forecast_origin_date",
        "forecast_step",
        "target_date",
        "actual_value",
        "chronos_q0.1_lower",
        "chronos_q0.5_median",
        "chronos_q0.9_upper",
        "context_length",
    }
    missing = required_columns - set(dataframe.columns)
    if missing:
        raise RuntimeError(f"2026년 구간 평가 입력에 필수 열이 없습니다: {sorted(missing)}")
    if dataframe[list(required_columns)].isna().any().any():
        raise RuntimeError("2026년 구간 평가 입력에 결측값이 있습니다.")
    if set(dataframe["context_length"].astype(int).unique()) != {756}:
        raise RuntimeError("2026년 구간 평가 입력이 context 756 예측이 아닙니다.")
    if len(dataframe) != int(locked["expected_rows"]):
        raise RuntimeError(f"2026년 구간 평가 행 수가 예상과 다릅니다: {len(dataframe)}")
    actual_origins = dataframe["requested_origin"].dt.strftime("%Y-%m-%d").drop_duplicates().tolist()
    if actual_origins != locked["requested_origins"]:
        raise RuntimeError("입력 CSV의 2026년 기준일이 고정 목록과 다릅니다.")
    counts = dataframe.groupby("requested_origin")["forecast_step"].agg(["size", "nunique"])
    if ((counts["size"] != 20) | (counts["nunique"] != 20)).any():
        raise RuntimeError("2026년 기준일별 행 또는 forecast_step이 20개가 아닙니다.")
    if dataframe.duplicated(["requested_origin", "forecast_step", "target_date"]).any():
        raise RuntimeError("2026년 구간 평가 입력에 중복 행이 있습니다.")
    return dataframe.sort_values(
        ["requested_origin", "forecast_step"]
    ).reset_index(drop=True)


def main() -> None:
    output_paths = (FORECAST_PATH, SUMMARY_PATH, BY_ORIGIN_PATH, BY_LEAD_PATH, DECISION_PATH)
    existing = [path for path in output_paths if path.exists()]
    if existing:
        raise FileExistsError(f"기존 2026년 구간 평가를 덮어쓰지 않습니다: {existing}")

    config, locked = load_locked_config(CONFIG_PATH)
    forecast = load_2026_forecast(INPUT_PATH, locked)
    correction = float(locked["interval_correction"])
    forecast["interval_correction"] = correction
    forecast["corrected_q0.1_lower"] = forecast["chronos_q0.1_lower"] - correction
    forecast["corrected_q0.5_median"] = forecast["chronos_q0.5_median"]
    forecast["corrected_q0.9_upper"] = forecast["chronos_q0.9_upper"] + correction
    forecast["evaluation_role"] = "out_of_calibration_2026_small_sample"

    metrics = interval_metrics(forecast)
    summary = pd.DataFrame(
        [
            {
                "evaluation": "locked_2026_january_to_july",
                "nominal_coverage": config["nominal_coverage"],
                "origins": locked["expected_origins"],
                "interval_correction": correction,
                **metrics,
            }
        ]
    )
    by_origin = grouped_metrics(forecast, "requested_origin")
    by_lead = grouped_metrics(forecast, "forecast_step")
    passed = bool(metrics["corrected_coverage"] >= float(config["nominal_coverage"]))
    origins_at_or_above_target = int(
        (by_origin["corrected_coverage"] >= float(config["nominal_coverage"])).sum()
    )
    decision = {
        "evaluation": "locked_2026_january_to_july",
        "interval_correction_was_reselected": False,
        "interval_correction": correction,
        "correction_source": locked["correction_source"],
        "nominal_coverage": config["nominal_coverage"],
        "origin_count": locked["expected_origins"],
        "origins_at_or_above_nominal_coverage": origins_at_or_above_target,
        "passed_pre_registered_rule": passed,
        "status": (
            locked["status_if_passed"] if passed else locked["status_if_failed"]
        ),
        "point_forecast_changed": False,
        "visibility_warning": locked["visibility_warning"],
        "retuning_policy": config["retuning_policy"],
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
    print("\nBy origin")
    print(by_origin.to_string(index=False))
    print("\nBy lead")
    print(by_lead.to_string(index=False))
    print("\nDecision")
    print(json.dumps(decision, ensure_ascii=False, indent=2))
    print(f"saved_forecast: {FORECAST_PATH}")
    print(f"saved_decision: {DECISION_PATH}")


if __name__ == "__main__":
    main()
