from __future__ import annotations

import argparse
import importlib.util
import json
import random
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from chronos import Chronos2Pipeline

from src.evaluation.backtest import load_model_data as load_backtest_data
from src.evaluation.backtest import run_walk_forward_backtest
from src.evaluation.evaluate import build_grouped_metrics, calculate_metrics, save_without_overwrite
from src.models.prepare_finetuning import (
    BACKTEST_PATH,
    MODEL_DATA_PATH,
    SPLIT_MANIFEST_PATH,
    build_finetuning_inputs,
    load_model_data,
)


PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = PROJECT_DIR / "configs" / "finetuning.json"
ZERO_SHOT_COMPARISON_PATH = (
    PROJECT_DIR
    / "outputs"
    / "metrics"
    / "core"
    / "usd_krw_zero_shot_validation_context_comparison.csv"
)
METRICS_DIR = PROJECT_DIR / "outputs" / "metrics" / "finetuning"
DEVICE = "mps"
EXPECTED_VALIDATION_ORIGINS = 48
ORIGIN_CHUNK_SIZE = 12


def require_lora() -> None:
    """Prevent a missing PEFT dependency from triggering full fine-tuning."""
    if importlib.util.find_spec("peft") is None:
        raise RuntimeError("peft가 없어 LoRA 후보 학습을 실행할 수 없습니다.")
    if not torch.backends.mps.is_available():
        raise RuntimeError("현재 실행 환경에서 MPS를 사용할 수 없습니다.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train one pre-registered Chronos-2 LoRA candidate.")
    parser.add_argument("--learning-rate-index", type=int, choices=(0, 1), default=0)
    parser.add_argument("--num-steps-index", type=int, choices=(0, 1), default=0)
    return parser.parse_args()


def load_candidate_settings(
    learning_rate_index: int,
    num_steps_index: int,
) -> dict[str, object]:
    """Load and verify one pre-registered LoRA candidate."""
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    settings = {
        "model_id": config["model_id"],
        "prediction_length": int(config["prediction_length"]),
        "context_length": int(
            config["paired_zero_shot_context_selection"]["selected_context_length"]
        ),
        "learning_rate": float(
            config["lora"]["learning_rate_candidates"][learning_rate_index]
        ),
        "num_steps": int(config["lora"]["num_steps_candidates"][num_steps_index]),
        "batch_size": int(config["lora"]["batch_size"]),
        "min_past": int(config["lora"]["min_past"]),
        "seed": int(config["lora"]["seed"]),
    }
    expected = {
        "prediction_length": 20,
        "context_length": 756,
        "learning_rate": (1e-5, 3e-5)[learning_rate_index],
        "num_steps": (100, 300)[num_steps_index],
        "batch_size": 4,
        "seed": 42,
    }
    for key, expected_value in expected.items():
        if settings[key] != expected_value:
            raise RuntimeError(
                f"LoRA 후보 설정이 예상과 다릅니다: {key}={settings[key]}, 예상={expected_value}"
            )
    return settings


def build_output_paths(settings: dict[str, object]) -> tuple[str, dict[str, Path]]:
    learning_rate_label = f"{float(settings['learning_rate']):.0e}".replace("e-0", "e-")
    candidate_name = (
        f"chronos2_lora_h20_ctx{settings['context_length']}_lr{learning_rate_label}_"
        f"steps{settings['num_steps']}_seed{settings['seed']}"
    )
    paths = {
        "checkpoint": PROJECT_DIR / "outputs" / "checkpoints" / candidate_name,
        "forecast": PROJECT_DIR
        / "outputs"
        / "forecasts"
        / f"{candidate_name}_validation_2018_2021.csv",
        "summary": METRICS_DIR / f"{candidate_name}_validation_summary.csv",
        "by_origin": METRICS_DIR / f"{candidate_name}_validation_by_origin.csv",
        "by_lead": METRICS_DIR / f"{candidate_name}_validation_by_lead.csv",
    }
    return candidate_name, paths


def load_validation_origins() -> list[str]:
    manifest = pd.read_csv(SPLIT_MANIFEST_PATH)
    origins = manifest.loc[
        manifest["split"].eq("validation"), "requested_origin"
    ].tolist()
    if len(origins) != EXPECTED_VALIDATION_ORIGINS or len(origins) != len(set(origins)):
        raise RuntimeError("Validation 기준일은 중복 없이 48개여야 합니다.")
    return origins


def rename_chronos_as_lora(metrics: pd.DataFrame) -> pd.DataFrame:
    """Make it explicit that grouped Chronos columns came from the LoRA candidate."""
    return metrics.rename(
        columns={column: column.replace("chronos_", "lora_") for column in metrics.columns}
    )


def main() -> None:
    args = parse_args()
    require_lora()
    settings = load_candidate_settings(args.learning_rate_index, args.num_steps_index)
    candidate_name, output_paths = build_output_paths(settings)
    existing = [path for path in output_paths.values() if path.exists()]
    if existing:
        raise FileExistsError(f"기존 LoRA 후보 결과를 덮어쓰지 않습니다: {existing}")

    seed = int(settings["seed"])
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)

    model_data = load_model_data(MODEL_DATA_PATH)
    historical_backtest = pd.read_csv(
        BACKTEST_PATH,
        parse_dates=["forecast_origin_date", "target_date"],
    )
    split_manifest = pd.read_csv(SPLIT_MANIFEST_PATH)
    train_inputs, validation_inputs, _ = build_finetuning_inputs(
        model_data,
        historical_backtest,
        split_manifest,
    )
    validation_origins = load_validation_origins()

    pipeline = Chronos2Pipeline.from_pretrained(str(settings["model_id"]), device_map=DEVICE)
    if str(pipeline.model.device).split(":")[0] != DEVICE:
        raise RuntimeError(
            f"모델 장치가 요청과 다릅니다: 요청={DEVICE}, 실제={pipeline.model.device}"
        )

    print(f"Training LoRA candidate: {candidate_name}")
    started_at = time.perf_counter()
    finetuned = pipeline.fit(
        inputs=train_inputs,
        validation_inputs=validation_inputs,
        prediction_length=int(settings["prediction_length"]),
        finetune_mode="lora",
        context_length=int(settings["context_length"]),
        learning_rate=float(settings["learning_rate"]),
        num_steps=int(settings["num_steps"]),
        batch_size=int(settings["batch_size"]),
        min_past=int(settings["min_past"]),
        output_dir=output_paths["checkpoint"],
        finetuned_ckpt_name="finetuned-ckpt",
        remove_printer_callback=True,
        disable_data_parallel=True,
        seed=seed,
        data_seed=seed,
    )
    training_elapsed_seconds = time.perf_counter() - started_at
    if "Peft" not in type(finetuned.model).__name__:
        raise RuntimeError(f"LoRA 모델로 확인되지 않습니다: {type(finetuned.model).__name__}")

    backtest_data = load_backtest_data(MODEL_DATA_PATH)
    forecast = run_walk_forward_backtest(
        finetuned,
        backtest_data,
        requested_origins=validation_origins,
        horizon=int(settings["prediction_length"]),
        context_length=int(settings["context_length"]),
        batch_size=8,
        origin_chunk_size=ORIGIN_CHUNK_SIZE,
    )
    raw_metrics = calculate_metrics(forecast)
    by_origin = rename_chronos_as_lora(
        build_grouped_metrics(forecast, "forecast_origin_date")
    )
    by_lead = rename_chronos_as_lora(build_grouped_metrics(forecast, "forecast_step"))

    zero_shot = pd.read_csv(ZERO_SHOT_COMPARISON_PATH)
    zero_row = zero_shot.loc[
        zero_shot["context_length"].eq(int(settings["context_length"]))
    ]
    if len(zero_row) != 1:
        raise RuntimeError("선택 context의 Zero-shot 기준 성능을 하나만 찾을 수 없습니다.")
    zero = zero_row.iloc[0]
    lora_mae = float(raw_metrics["chronos_mae"])
    lora_rmse = float(raw_metrics["chronos_rmse"])
    zero_mae = float(zero["chronos_mae"])
    zero_rmse = float(zero["chronos_rmse"])

    summary = pd.DataFrame(
        [
            {
                "candidate": candidate_name,
                "device": DEVICE,
                **settings,
                "validation_origins": EXPECTED_VALIDATION_ORIGINS,
                "validation_rows": len(forecast),
                "training_elapsed_seconds": training_elapsed_seconds,
                "lora_mae": lora_mae,
                "zero_shot_mae": zero_mae,
                "random_walk_mae": float(raw_metrics["random_walk_mae"]),
                "lora_rmse": lora_rmse,
                "zero_shot_rmse": zero_rmse,
                "random_walk_rmse": float(raw_metrics["random_walk_rmse"]),
                "lora_mae_improvement_vs_zero_shot_percent": 100.0
                * (zero_mae - lora_mae)
                / zero_mae,
                "lora_rmse_improvement_vs_zero_shot_percent": 100.0
                * (zero_rmse - lora_rmse)
                / zero_rmse,
                "lora_mae_improvement_vs_random_walk_percent": raw_metrics[
                    "mae_improvement_vs_random_walk_percent"
                ],
                "lora_rmse_improvement_vs_random_walk_percent": raw_metrics[
                    "rmse_improvement_vs_random_walk_percent"
                ],
                "lora_direction_accuracy": raw_metrics["chronos_direction_accuracy"],
                "lora_mase": raw_metrics["chronos_mase"],
                "mean_pinball_loss": raw_metrics["mean_pinball_loss"],
                "interval_80_coverage": raw_metrics["interval_80_coverage"],
                "interval_mean_width": raw_metrics["interval_mean_width"],
                "origin_mae_win_rate_vs_random_walk": float(
                    (by_origin["lora_mae"] < by_origin["random_walk_mae"]).mean()
                ),
                "origin_rmse_win_rate_vs_random_walk": float(
                    (by_origin["lora_rmse"] < by_origin["random_walk_rmse"]).mean()
                ),
            }
        ]
    )

    forecast = forecast.rename(
        columns={
            "chronos_q0.1_lower": "lora_q0.1_lower",
            "chronos_q0.5_median": "lora_q0.5_median",
            "chronos_q0.9_upper": "lora_q0.9_upper",
        }
    )
    save_without_overwrite(forecast, output_paths["forecast"])
    save_without_overwrite(summary, output_paths["summary"])
    save_without_overwrite(by_origin, output_paths["by_origin"])
    save_without_overwrite(by_lead, output_paths["by_lead"])
    print(f"Saved LoRA Validation forecasts to {output_paths['forecast']}")
    print(f"Saved LoRA Validation summary to {output_paths['summary']}")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
