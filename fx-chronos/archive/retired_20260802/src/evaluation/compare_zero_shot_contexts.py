from __future__ import annotations

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
OUTPUT_PATH = (
    PROJECT_DIR
    / "outputs"
    / "metrics"
    / "core"
    / "usd_krw_zero_shot_validation_context_comparison.csv"
)
DEVICE = "mps"
HORIZON = 20
BATCH_SIZE = 8
ORIGIN_CHUNK_SIZE = 12
EXPECTED_VALIDATION_ORIGINS = 48


def load_context_candidates(config_path: Path) -> list[int]:
    """Load the pre-registered context candidates without changing their order."""
    config = json.loads(config_path.read_text(encoding="utf-8"))
    candidates = config["paired_zero_shot_context_selection"]["context_length_candidates"]
    if not candidates or len(candidates) != len(set(candidates)):
        raise RuntimeError("Zero-shot context 후보가 비어 있거나 중복되어 있습니다.")
    return [int(candidate) for candidate in candidates]


def load_validation_origins(manifest_path: Path) -> list[str]:
    """Use only origins assigned to Validation in the locked split manifest."""
    manifest = pd.read_csv(manifest_path)
    if manifest["requested_origin"].duplicated().any():
        raise RuntimeError("분할 명세에 중복 요청 기준일이 있습니다.")
    origins = manifest.loc[
        manifest["split"].eq("validation"), "requested_origin"
    ].tolist()
    if len(origins) != EXPECTED_VALIDATION_ORIGINS:
        raise RuntimeError(
            f"Validation 기준일 수가 예상과 다릅니다: "
            f"실제={len(origins)}, 예상={EXPECTED_VALIDATION_ORIGINS}"
        )
    return origins


def main() -> None:
    if OUTPUT_PATH.exists():
        raise FileExistsError(f"기존 context 비교 결과를 덮어쓰지 않습니다: {OUTPUT_PATH}")
    if DEVICE == "mps" and not torch.backends.mps.is_available():
        raise RuntimeError("현재 실행 환경에서 MPS를 사용할 수 없습니다.")

    context_candidates = load_context_candidates(CONFIG_PATH)
    validation_origins = load_validation_origins(SPLIT_MANIFEST_PATH)
    model_data = load_model_data(MODEL_DATA_PATH)
    pipeline = Chronos2Pipeline.from_pretrained(MODEL_ID, device_map=DEVICE)
    if str(pipeline.model.device).split(":")[0] != DEVICE:
        raise RuntimeError(
            f"모델 장치가 요청과 다릅니다: 요청={DEVICE}, 실제={pipeline.model.device}"
        )

    comparison_rows: list[dict[str, object]] = []
    for context_length in context_candidates:
        print(f"Evaluating Zero-shot context_length={context_length}")
        forecast = run_walk_forward_backtest(
            pipeline,
            model_data,
            requested_origins=validation_origins,
            horizon=HORIZON,
            context_length=context_length,
            batch_size=BATCH_SIZE,
            origin_chunk_size=ORIGIN_CHUNK_SIZE,
        )
        if len(forecast) != EXPECTED_VALIDATION_ORIGINS * HORIZON:
            raise RuntimeError(
                f"Validation 예측 행 수가 예상과 다릅니다: context={context_length}, "
                f"실제={len(forecast)}"
            )

        metrics = calculate_metrics(forecast)
        by_origin = build_grouped_metrics(forecast, "forecast_origin_date")
        comparison_rows.append(
            {
                "context_length": context_length,
                "device": DEVICE,
                "model_id": MODEL_ID,
                "origins": EXPECTED_VALIDATION_ORIGINS,
                **metrics,
                "origin_mae_win_rate_vs_random_walk": float(
                    (by_origin["chronos_mae"] < by_origin["random_walk_mae"]).mean()
                ),
                "origin_rmse_win_rate_vs_random_walk": float(
                    (by_origin["chronos_rmse"] < by_origin["random_walk_rmse"]).mean()
                ),
            }
        )

    comparison = pd.DataFrame.from_records(comparison_rows)
    save_without_overwrite(comparison, OUTPUT_PATH)
    print(f"Saved Zero-shot context comparison to {OUTPUT_PATH}")
    print(comparison.to_string(index=False))


if __name__ == "__main__":
    main()
