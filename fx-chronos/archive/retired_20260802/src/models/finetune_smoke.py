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

from src.models.prepare_finetuning import (
    BACKTEST_PATH,
    MODEL_DATA_PATH,
    SPLIT_MANIFEST_PATH,
    build_finetuning_inputs,
    load_model_data,
)


PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
MODEL_ID = "amazon/chronos-2"
OUTPUT_ROOT = PROJECT_DIR / "outputs" / "archive"
SEED = 42


def require_peft() -> None:
    """Prevent Chronos from silently falling back from LoRA to full fine-tuning."""
    if importlib.util.find_spec("peft") is None:
        raise RuntimeError(
            "peft가 없어 LoRA를 실행할 수 없습니다. 전체 파인튜닝 자동 전환을 막기 위해 중단합니다."
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one safe Chronos-2 LoRA smoke step.")
    parser.add_argument("--device", choices=("cpu", "mps"), default="cpu")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    require_peft()
    output_dir = OUTPUT_ROOT / f"lora_smoke_{args.device}_1step"
    if output_dir.exists():
        raise FileExistsError(f"기존 LoRA 스모크 테스트를 덮어쓰지 않습니다: {output_dir}")
    if args.device == "mps" and not torch.backends.mps.is_available():
        raise RuntimeError("현재 실행 환경에서 MPS를 사용할 수 없습니다.")

    random.seed(SEED)
    np.random.seed(SEED)
    torch.manual_seed(SEED)

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

    print(f"LoRA smoke device: {args.device}")
    print("Training steps: 1")
    print("Training series: 1")
    print("Validation series: 1")
    pipeline = Chronos2Pipeline.from_pretrained(MODEL_ID, device_map=args.device)
    if str(pipeline.model.device).split(":")[0] != args.device:
        raise RuntimeError(
            f"모델 장치가 요청과 다릅니다: 요청={args.device}, 실제={pipeline.model.device}"
        )
    started_at = time.perf_counter()
    finetuned = pipeline.fit(
        inputs=train_inputs[:1],
        validation_inputs=validation_inputs[:1],
        prediction_length=20,
        finetune_mode="lora",
        context_length=64,
        learning_rate=1e-5,
        num_steps=1,
        batch_size=1,
        min_past=40,
        output_dir=output_dir,
        finetuned_ckpt_name="finetuned-ckpt",
        remove_printer_callback=True,
        disable_data_parallel=True,
        seed=SEED,
        data_seed=SEED,
    )
    elapsed_seconds = time.perf_counter() - started_at
    model_class = type(finetuned.model).__name__
    if "Peft" not in model_class:
        raise RuntimeError(f"LoRA 모델로 확인되지 않습니다: {model_class}")
    checkpoint_path = output_dir / "finetuned-ckpt"
    if not checkpoint_path.exists():
        raise RuntimeError(f"LoRA 체크포인트가 저장되지 않았습니다: {checkpoint_path}")

    summary = {
        "device": args.device,
        "model_class": model_class,
        "num_steps": 1,
        "batch_size": 1,
        "context_length": 64,
        "prediction_length": 20,
        "learning_rate": 1e-5,
        "elapsed_seconds": elapsed_seconds,
        "checkpoint_path": str(checkpoint_path),
    }
    (output_dir / "smoke_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Fine-tuned model class: {model_class}")
    print(f"Elapsed seconds: {elapsed_seconds:.4f}")
    print(f"Saved LoRA smoke checkpoint to {checkpoint_path}")


if __name__ == "__main__":
    main()
