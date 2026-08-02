from __future__ import annotations

import gc
import json
from pathlib import Path

import pandas as pd
import torch
from chronos import Chronos2Pipeline

from src.evaluation.backtest import MODEL_ID, load_model_data, run_walk_forward_backtest
from src.evaluation.evaluate import build_grouped_metrics, calculate_metrics, save_without_overwrite


PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = PROJECT_DIR / "configs" / "finetuning.json"
MODEL_DATA_PATH = PROJECT_DIR / "data" / "processed" / "usd_krw_model_weekdays_19640504_20260730.csv"
SPLIT_MANIFEST_PATH = (
    PROJECT_DIR
    / "outputs"
    / "metrics"
    / "core"
    / "usd_krw_walk_forward_h20_monthly_1997_2025_split_manifest.csv"
)
DEVICE = "mps"
EXPECTED_TEST_ORIGINS = 48
ORIGIN_CHUNK_SIZE = 12
OUTPUT_STEM = "chronos2_lora_h20_ctx756_lr1e-5_steps300_seed42_final_test_2022_2025"
FORECAST_PATH = PROJECT_DIR / "outputs" / "forecasts" / "finetuning" / f"{OUTPUT_STEM}.csv"
METRICS_DIR = PROJECT_DIR / "outputs" / "metrics" / "finetuning"
SUMMARY_PATH = METRICS_DIR / f"{OUTPUT_STEM}_summary.csv"
BY_ORIGIN_PATH = METRICS_DIR / f"{OUTPUT_STEM}_by_origin.csv"
BY_LEAD_PATH = METRICS_DIR / f"{OUTPUT_STEM}_by_lead.csv"


def load_locked_settings() -> dict[str, object]:
    """Load the candidate selected before opening final-test metrics."""
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    selected = config["lora"]["selected_candidate"]
    if selected["status"] != "selected_for_one_final_test":
        raise RuntimeError("최종 Test용 LoRA 후보 상태가 잠겨 있지 않습니다.")
    settings = {
        "candidate": selected["name"],
        "context_length": int(
            config["paired_zero_shot_context_selection"]["selected_context_length"]
        ),
        "prediction_length": int(config["prediction_length"]),
    }
    if settings != {
        "candidate": "chronos2_lora_h20_ctx756_lr1e-5_steps300_seed42",
        "context_length": 756,
        "prediction_length": 20,
    }:
        raise RuntimeError(f"고정된 최종 Test 설정이 예상과 다릅니다: {settings}")
    return settings


def load_test_origins() -> list[str]:
    """Read only origins locked as final_test in the split manifest."""
    manifest = pd.read_csv(SPLIT_MANIFEST_PATH)
    origins = manifest.loc[
        manifest["split"].eq("final_test"), "requested_origin"
    ].tolist()
    if len(origins) != EXPECTED_TEST_ORIGINS or len(origins) != len(set(origins)):
        raise RuntimeError("최종 Test 기준일은 중복 없이 48개여야 합니다.")
    return origins


def prefix_model_metrics(metrics: pd.DataFrame, prefix: str) -> pd.DataFrame:
    """Prefix model-specific columns while retaining grouping and Random Walk metrics."""
    renamed: dict[str, str] = {}
    for column in metrics.columns:
        if column.startswith("chronos_"):
            renamed[column] = column.replace("chronos_", f"{prefix}_", 1)
        elif column.startswith("pinball_") or column.startswith("interval_"):
            renamed[column] = f"{prefix}_{column}"
        elif column.startswith("mae_improvement_") or column.startswith("rmse_improvement_"):
            renamed[column] = f"{prefix}_{column}"
    return metrics.rename(columns=renamed)


def merge_forecasts(lora: pd.DataFrame, zero_shot: pd.DataFrame) -> pd.DataFrame:
    """Combine paired forecasts after verifying that their targets and baselines match."""
    key_columns = ["requested_origin", "forecast_origin_date", "forecast_step", "target_date"]
    shared_columns = [
        "forecast_origin_value",
        "actual_value",
        "random_walk_forecast",
        "history_rows",
        "context_length",
        "mase_scale_training_only",
    ]
    lora_columns = key_columns + shared_columns + [
        "chronos_q0.1_lower",
        "chronos_q0.5_median",
        "chronos_q0.9_upper",
    ]
    zero_columns = key_columns + shared_columns + [
        "chronos_q0.1_lower",
        "chronos_q0.5_median",
        "chronos_q0.9_upper",
    ]
    combined = lora[lora_columns].merge(
        zero_shot[zero_columns],
        on=key_columns,
        how="inner",
        validate="one_to_one",
        suffixes=("_lora", "_zero"),
    )
    for column in shared_columns:
        if not combined[f"{column}_lora"].equals(combined[f"{column}_zero"]):
            raise RuntimeError(f"LoRA와 Zero-shot의 공통 값이 다릅니다: {column}")
        combined[column] = combined.pop(f"{column}_lora")
        combined = combined.drop(columns=f"{column}_zero")
    return combined.rename(
        columns={
            "chronos_q0.1_lower_lora": "lora_q0.1_lower",
            "chronos_q0.5_median_lora": "lora_q0.5_median",
            "chronos_q0.9_upper_lora": "lora_q0.9_upper",
            "chronos_q0.1_lower_zero": "zero_shot_q0.1_lower",
            "chronos_q0.5_median_zero": "zero_shot_q0.5_median",
            "chronos_q0.9_upper_zero": "zero_shot_q0.9_upper",
        }
    )


def main() -> None:
    output_paths = (FORECAST_PATH, SUMMARY_PATH, BY_ORIGIN_PATH, BY_LEAD_PATH)
    existing = [path for path in output_paths if path.exists()]
    if existing:
        raise FileExistsError(f"최종 Test 결과를 다시 쓰지 않습니다: {existing}")
    if not torch.backends.mps.is_available():
        raise RuntimeError("현재 실행 환경에서 MPS를 사용할 수 없습니다.")

    settings = load_locked_settings()
    test_origins = load_test_origins()
    model_data = load_model_data(MODEL_DATA_PATH)
    checkpoint_path = (
        PROJECT_DIR
        / "outputs"
        / "checkpoints"
        / str(settings["candidate"])
        / "finetuned-ckpt"
    )
    if not checkpoint_path.exists():
        raise FileNotFoundError(f"선택된 LoRA 체크포인트가 없습니다: {checkpoint_path}")

    print("Running the single locked final-test evaluation")
    lora_pipeline = Chronos2Pipeline.from_pretrained(
        checkpoint_path,
        device_map=DEVICE,
        import_allowlist=["chronos.chronos2.model"],
    )
    lora_forecast = run_walk_forward_backtest(
        lora_pipeline,
        model_data,
        requested_origins=test_origins,
        horizon=int(settings["prediction_length"]),
        context_length=int(settings["context_length"]),
        batch_size=8,
        origin_chunk_size=ORIGIN_CHUNK_SIZE,
    )
    del lora_pipeline
    gc.collect()
    torch.mps.empty_cache()

    zero_pipeline = Chronos2Pipeline.from_pretrained(MODEL_ID, device_map=DEVICE)
    zero_forecast = run_walk_forward_backtest(
        zero_pipeline,
        model_data,
        requested_origins=test_origins,
        horizon=int(settings["prediction_length"]),
        context_length=int(settings["context_length"]),
        batch_size=8,
        origin_chunk_size=ORIGIN_CHUNK_SIZE,
    )

    expected_rows = EXPECTED_TEST_ORIGINS * int(settings["prediction_length"])
    if len(lora_forecast) != expected_rows or len(zero_forecast) != expected_rows:
        raise RuntimeError(
            f"최종 Test 행 수가 예상과 다릅니다: "
            f"LoRA={len(lora_forecast)}, Zero-shot={len(zero_forecast)}, 예상={expected_rows}"
        )
    lora_metrics = calculate_metrics(lora_forecast)
    zero_metrics = calculate_metrics(zero_forecast)
    lora_origin = prefix_model_metrics(
        build_grouped_metrics(lora_forecast, "forecast_origin_date"), "lora"
    )
    zero_origin = prefix_model_metrics(
        build_grouped_metrics(zero_forecast, "forecast_origin_date"), "zero_shot"
    )
    lora_lead = prefix_model_metrics(
        build_grouped_metrics(lora_forecast, "forecast_step"), "lora"
    )
    zero_lead = prefix_model_metrics(
        build_grouped_metrics(zero_forecast, "forecast_step"), "zero_shot"
    )
    by_origin = lora_origin.merge(
        zero_origin.drop(
            columns=[column for column in zero_origin.columns if column.startswith("random_walk_") or column == "rows"]
        ),
        on="forecast_origin_date",
        validate="one_to_one",
    )
    by_lead = lora_lead.merge(
        zero_lead.drop(
            columns=[column for column in zero_lead.columns if column.startswith("random_walk_") or column == "rows"]
        ),
        on="forecast_step",
        validate="one_to_one",
    )

    lora_mae = float(lora_metrics["chronos_mae"])
    zero_mae = float(zero_metrics["chronos_mae"])
    random_walk_mae = float(lora_metrics["random_walk_mae"])
    lora_rmse = float(lora_metrics["chronos_rmse"])
    zero_rmse = float(zero_metrics["chronos_rmse"])
    random_walk_rmse = float(lora_metrics["random_walk_rmse"])
    summary = pd.DataFrame(
        [
            {
                "candidate": settings["candidate"],
                "split": "final_test",
                "device": DEVICE,
                "context_length": settings["context_length"],
                "prediction_length": settings["prediction_length"],
                "origins": EXPECTED_TEST_ORIGINS,
                "rows": expected_rows,
                "lora_mae": lora_mae,
                "zero_shot_mae": zero_mae,
                "random_walk_mae": random_walk_mae,
                "lora_rmse": lora_rmse,
                "zero_shot_rmse": zero_rmse,
                "random_walk_rmse": random_walk_rmse,
                "lora_mae_improvement_vs_zero_shot_percent": 100.0
                * (zero_mae - lora_mae)
                / zero_mae,
                "lora_rmse_improvement_vs_zero_shot_percent": 100.0
                * (zero_rmse - lora_rmse)
                / zero_rmse,
                "lora_mae_improvement_vs_random_walk_percent": 100.0
                * (random_walk_mae - lora_mae)
                / random_walk_mae,
                "lora_rmse_improvement_vs_random_walk_percent": 100.0
                * (random_walk_rmse - lora_rmse)
                / random_walk_rmse,
                "lora_mean_pinball_loss": lora_metrics["mean_pinball_loss"],
                "zero_shot_mean_pinball_loss": zero_metrics["mean_pinball_loss"],
                "lora_interval_80_coverage": lora_metrics["interval_80_coverage"],
                "zero_shot_interval_80_coverage": zero_metrics["interval_80_coverage"],
                "lora_interval_mean_width": lora_metrics["interval_mean_width"],
                "zero_shot_interval_mean_width": zero_metrics["interval_mean_width"],
                "origin_mae_win_rate_lora_vs_zero_shot": float(
                    (by_origin["lora_mae"] < by_origin["zero_shot_mae"]).mean()
                ),
                "origin_rmse_win_rate_lora_vs_zero_shot": float(
                    (by_origin["lora_rmse"] < by_origin["zero_shot_rmse"]).mean()
                ),
                "passes_point_success_criteria": bool(
                    lora_mae < zero_mae
                    and lora_rmse < zero_rmse
                    and lora_mae < random_walk_mae
                    and lora_rmse < random_walk_rmse
                ),
            }
        ]
    )
    combined_forecast = merge_forecasts(lora_forecast, zero_forecast)
    save_without_overwrite(combined_forecast, FORECAST_PATH)
    save_without_overwrite(summary, SUMMARY_PATH)
    save_without_overwrite(by_origin, BY_ORIGIN_PATH)
    save_without_overwrite(by_lead, BY_LEAD_PATH)
    print(f"Saved final-test forecasts to {FORECAST_PATH}")
    print(f"Saved final-test summary to {SUMMARY_PATH}")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
