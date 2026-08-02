from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

from src.evaluation.evaluate import save_without_overwrite


PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = PROJECT_DIR / "configs" / "interval_calibration.json"
INPUT_PATH = (
    PROJECT_DIR
    / "outputs"
    / "forecasts"
    / "core"
    / "usd_krw_zero_shot_h20_ctx756_validation_2018_2021.csv"
)
OUTPUT_STEM = "usd_krw_chronos2_h20_ctx756_interval_calibration_2018_2021"
FORECAST_PATH = PROJECT_DIR / "outputs" / "forecasts" / "calibration" / f"{OUTPUT_STEM}.csv"
METRICS_DIR = PROJECT_DIR / "outputs" / "metrics" / "calibration"
SUMMARY_PATH = METRICS_DIR / f"{OUTPUT_STEM}_summary.csv"
BY_YEAR_PATH = METRICS_DIR / f"{OUTPUT_STEM}_by_year.csv"
BY_SEGMENT_PATH = METRICS_DIR / f"{OUTPUT_STEM}_by_lead_segment.csv"
DECISION_PATH = METRICS_DIR / f"{OUTPUT_STEM}_decision.json"


def load_config(config_path: Path) -> dict[str, object]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if float(config["nominal_coverage"]) != 0.8:
        raise RuntimeError("목표 포함률이 사전 고정값 0.8과 다릅니다.")
    if config["method"] != "global_symmetric_additive_conformal_widening":
        raise RuntimeError("사전 고정하지 않은 구간 보정 방법입니다.")
    if int(config["expected_calibration_origins"]) != 24:
        raise RuntimeError("보정 기준일 수가 사전 고정값과 다릅니다.")
    if int(config["expected_internal_evaluation_origins"]) != 24:
        raise RuntimeError("내부 평가 기준일 수가 사전 고정값과 다릅니다.")
    return config


def load_and_split(
    input_path: Path,
    config: dict[str, object],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    dataframe = pd.read_csv(input_path, parse_dates=["requested_origin", "target_date"])
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
        raise RuntimeError(f"구간 보정 입력에 필수 열이 없습니다: {sorted(missing)}")
    if dataframe[list(required_columns)].isna().any().any():
        raise RuntimeError("구간 보정 입력에 결측값이 있습니다.")
    if set(dataframe["context_length"].astype(int).unique()) != {756}:
        raise RuntimeError("구간 보정 입력이 context 756 예측이 아닙니다.")
    if dataframe.duplicated(["requested_origin", "forecast_step", "target_date"]).any():
        raise RuntimeError("구간 보정 입력에 중복 행이 있습니다.")

    calibration = dataframe[dataframe["requested_origin"].between(
        pd.Timestamp(str(config["calibration_requested_origin_start"])),
        pd.Timestamp(str(config["calibration_requested_origin_end"])),
    )].copy()
    evaluation = dataframe[dataframe["requested_origin"].between(
        pd.Timestamp(str(config["internal_evaluation_requested_origin_start"])),
        pd.Timestamp(str(config["internal_evaluation_requested_origin_end"])),
    )].copy()
    expected_rows_per_origin = int(config["expected_rows_per_origin"])
    expected_calibration_rows = int(config["expected_calibration_origins"]) * expected_rows_per_origin
    expected_evaluation_rows = int(config["expected_internal_evaluation_origins"]) * expected_rows_per_origin
    if len(calibration) != expected_calibration_rows:
        raise RuntimeError(f"보정 행 수가 예상과 다릅니다: {len(calibration)}")
    if len(evaluation) != expected_evaluation_rows:
        raise RuntimeError(f"내부 평가 행 수가 예상과 다릅니다: {len(evaluation)}")
    return calibration, evaluation


def finite_sample_correction(calibration: pd.DataFrame, nominal_coverage: float) -> tuple[float, int]:
    lower = calibration["chronos_q0.1_lower"].astype(float)
    actual = calibration["actual_value"].astype(float)
    upper = calibration["chronos_q0.9_upper"].astype(float)
    scores = pd.concat(
        [lower - actual, actual - upper, pd.Series(0.0, index=calibration.index)],
        axis=1,
    ).max(axis=1)
    rank = math.ceil((len(scores) + 1) * nominal_coverage)
    rank = min(max(rank, 1), len(scores))
    correction = float(scores.sort_values().iloc[rank - 1])
    if correction < 0 or not math.isfinite(correction):
        raise RuntimeError("구간 보정값이 유효한 0 이상의 값이 아닙니다.")
    return correction, rank


def interval_metrics(group: pd.DataFrame) -> dict[str, float | int]:
    actual = group["actual_value"].astype(float)
    original_lower = group["chronos_q0.1_lower"].astype(float)
    original_upper = group["chronos_q0.9_upper"].astype(float)
    corrected_lower = group["corrected_q0.1_lower"].astype(float)
    corrected_upper = group["corrected_q0.9_upper"].astype(float)
    original_covered = actual.between(original_lower, original_upper, inclusive="both")
    corrected_covered = actual.between(corrected_lower, corrected_upper, inclusive="both")
    original_width = original_upper - original_lower
    corrected_width = corrected_upper - corrected_lower
    return {
        "rows": len(group),
        "original_coverage": float(original_covered.mean()),
        "corrected_coverage": float(corrected_covered.mean()),
        "coverage_change_percentage_points": float(
            100 * (corrected_covered.mean() - original_covered.mean())
        ),
        "original_mean_width": float(original_width.mean()),
        "corrected_mean_width": float(corrected_width.mean()),
        "mean_width_increase": float((corrected_width - original_width).mean()),
        "mean_width_increase_percent": float(
            100 * (corrected_width.mean() - original_width.mean()) / original_width.mean()
        ),
        "corrected_below_rate": float((actual < corrected_lower).mean()),
        "corrected_above_rate": float((actual > corrected_upper).mean()),
    }


def grouped_metrics(dataframe: pd.DataFrame, group_column: str) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for group_value, group in dataframe.groupby(group_column, observed=True, sort=True):
        rows.append({group_column: group_value, **interval_metrics(group)})
    return pd.DataFrame(rows)


def main() -> None:
    output_paths = (FORECAST_PATH, SUMMARY_PATH, BY_YEAR_PATH, BY_SEGMENT_PATH, DECISION_PATH)
    existing = [path for path in output_paths if path.exists()]
    if existing:
        raise FileExistsError(f"기존 구간 보정 결과를 덮어쓰지 않습니다: {existing}")

    config = load_config(CONFIG_PATH)
    calibration, evaluation = load_and_split(INPUT_PATH, config)
    correction, rank = finite_sample_correction(
        calibration, float(config["nominal_coverage"])
    )
    evaluation = evaluation.sort_values(
        ["requested_origin", "forecast_step"]
    ).reset_index(drop=True)
    evaluation["interval_correction"] = correction
    evaluation["corrected_q0.1_lower"] = evaluation["chronos_q0.1_lower"] - correction
    evaluation["corrected_q0.5_median"] = evaluation["chronos_q0.5_median"]
    evaluation["corrected_q0.9_upper"] = evaluation["chronos_q0.9_upper"] + correction
    evaluation["evaluation_role"] = "internal_evaluation_2020_2021"
    evaluation["year"] = evaluation["requested_origin"].dt.year
    evaluation["lead_segment"] = pd.cut(
        evaluation["forecast_step"],
        bins=[0, 5, 10, 20],
        labels=["D+1~D+5", "D+6~D+10", "D+11~D+20"],
    )

    metrics = interval_metrics(evaluation)
    summary = pd.DataFrame(
        [
            {
                "method": config["method"],
                "nominal_coverage": config["nominal_coverage"],
                "calibration_origins": config["expected_calibration_origins"],
                "internal_evaluation_origins": config["expected_internal_evaluation_origins"],
                "calibration_rows": len(calibration),
                "internal_evaluation_rows": len(evaluation),
                "finite_sample_rank": rank,
                "interval_correction": correction,
                **metrics,
            }
        ]
    )
    by_year = grouped_metrics(evaluation, "year")
    by_segment = grouped_metrics(evaluation, "lead_segment")
    passed = bool(metrics["corrected_coverage"] >= float(config["nominal_coverage"]))
    decision = {
        "method": config["method"],
        "nominal_coverage": config["nominal_coverage"],
        "interval_correction": correction,
        "point_forecast_changed": False,
        "final_test_2022_2025_used": False,
        "observations_2026_used": False,
        "passed_pre_registered_internal_rule": passed,
        "status": "internal_rule_passed" if passed else "internal_rule_not_met_do_not_retune",
        "interpretation_warning": config["interpretation_warning"],
    }

    save_without_overwrite(evaluation, FORECAST_PATH)
    save_without_overwrite(summary, SUMMARY_PATH)
    save_without_overwrite(by_year, BY_YEAR_PATH)
    save_without_overwrite(by_segment, BY_SEGMENT_PATH)
    DECISION_PATH.parent.mkdir(parents=True, exist_ok=True)
    DECISION_PATH.write_text(
        json.dumps(decision, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(summary.to_string(index=False))
    print("\nBy year")
    print(by_year.to_string(index=False))
    print("\nBy lead segment")
    print(by_segment.to_string(index=False))
    print("\nDecision")
    print(json.dumps(decision, ensure_ascii=False, indent=2))
    print(f"saved_forecast: {FORECAST_PATH}")
    print(f"saved_decision: {DECISION_PATH}")


if __name__ == "__main__":
    main()
