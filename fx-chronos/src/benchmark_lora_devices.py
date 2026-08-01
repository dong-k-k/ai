from __future__ import annotations

import argparse
import gc
import importlib.util
import json
import random
import tempfile
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from chronos import Chronos2Pipeline

from prepare_finetuning import (
    BACKTEST_PATH,
    MODEL_DATA_PATH,
    SPLIT_MANIFEST_PATH,
    build_finetuning_inputs,
    load_model_data,
)


PROJECT_DIR = Path(__file__).resolve().parent.parent
MODEL_ID = "amazon/chronos-2"
OUTPUT_DIR = PROJECT_DIR / "outputs" / "metrics"
DEVICES = ("cpu", "mps")
CONTEXT_LENGTH = 252
PREDICTION_LENGTH = 20
BATCH_SIZE = 4
DEFAULT_NUM_STEPS = 10
VALIDATION_SERIES = 4
LEARNING_RATE = 1e-5
SEED = 42


def require_runtime() -> None:
    """Fail before loading the model when LoRA or MPS is unavailable."""
    if importlib.util.find_spec("peft") is None:
        raise RuntimeError("peft가 없어 장치별 LoRA 벤치마크를 실행할 수 없습니다.")
    if not torch.backends.mps.is_available():
        raise RuntimeError("현재 실행 환경에서 MPS를 사용할 수 없습니다.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark Chronos-2 LoRA on CPU and MPS.")
    parser.add_argument("--num-steps", type=int, choices=(10, 100), default=DEFAULT_NUM_STEPS)
    return parser.parse_args()


def run_benchmark(
    device: str,
    train_inputs: list[np.ndarray],
    validation_inputs: list[np.ndarray],
    num_steps: int,
) -> dict[str, object]:
    """Run the same short LoRA workload on one device without retaining its checkpoint."""
    random.seed(SEED)
    np.random.seed(SEED)
    torch.manual_seed(SEED)

    pipeline = Chronos2Pipeline.from_pretrained(MODEL_ID, device_map=device)
    if str(pipeline.model.device).split(":")[0] != device:
        raise RuntimeError(f"모델 장치가 요청과 다릅니다: 요청={device}, 실제={pipeline.model.device}")

    with tempfile.TemporaryDirectory(prefix=f"chronos2-lora-{device}-") as temp_dir:
        started_at = time.perf_counter()
        finetuned = pipeline.fit(
            inputs=train_inputs,
            validation_inputs=validation_inputs[:VALIDATION_SERIES],
            prediction_length=PREDICTION_LENGTH,
            finetune_mode="lora",
            context_length=CONTEXT_LENGTH,
            learning_rate=LEARNING_RATE,
            num_steps=num_steps,
            batch_size=BATCH_SIZE,
            min_past=CONTEXT_LENGTH,
            output_dir=temp_dir,
            finetuned_ckpt_name="finetuned-ckpt",
            remove_printer_callback=True,
            disable_data_parallel=True,
            seed=SEED,
            data_seed=SEED,
        )
        elapsed_seconds = time.perf_counter() - started_at
        checkpoint_path = Path(temp_dir) / "finetuned-ckpt"
        if not checkpoint_path.exists():
            raise RuntimeError(f"임시 LoRA 체크포인트가 저장되지 않았습니다: {device}")
        model_class = type(finetuned.model).__name__
        if "Peft" not in model_class:
            raise RuntimeError(f"LoRA 모델로 확인되지 않습니다: {device}, {model_class}")

    del finetuned
    del pipeline
    gc.collect()
    if device == "mps":
        torch.mps.empty_cache()

    return {
        "device": device,
        "elapsed_seconds": elapsed_seconds,
        "steps_per_second": num_steps / elapsed_seconds,
        "model_class": model_class,
    }


def main() -> None:
    args = parse_args()
    require_runtime()
    output_path = (
        OUTPUT_DIR
        / f"chronos2_lora_device_benchmark_context{CONTEXT_LENGTH}_steps{args.num_steps}.json"
    )
    if output_path.exists():
        raise FileExistsError(f"기존 장치 벤치마크를 덮어쓰지 않습니다: {output_path}")

    model_data = load_model_data(MODEL_DATA_PATH)
    backtest = pd.read_csv(
        BACKTEST_PATH,
        parse_dates=["forecast_origin_date", "target_date"],
    )
    split_manifest = pd.read_csv(SPLIT_MANIFEST_PATH)
    train_inputs, validation_inputs, _ = build_finetuning_inputs(
        model_data,
        backtest,
        split_manifest,
    )

    results = [
        run_benchmark(device, train_inputs, validation_inputs, args.num_steps)
        for device in DEVICES
    ]
    cpu_seconds = float(results[0]["elapsed_seconds"])
    mps_seconds = float(results[1]["elapsed_seconds"])
    summary = {
        "model_id": MODEL_ID,
        "context_length": CONTEXT_LENGTH,
        "prediction_length": PREDICTION_LENGTH,
        "batch_size": BATCH_SIZE,
        "num_steps": args.num_steps,
        "validation_series": VALIDATION_SERIES,
        "learning_rate": LEARNING_RATE,
        "seed": SEED,
        "results": results,
        "mps_speedup_vs_cpu": cpu_seconds / mps_seconds,
        "faster_device": "mps" if mps_seconds < cpu_seconds else "cpu",
        "scope": "runtime benchmark only; losses are not used for model selection",
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Saved device benchmark to {output_path}")


if __name__ == "__main__":
    main()
