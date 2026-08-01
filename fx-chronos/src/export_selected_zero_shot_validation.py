from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import torch
from chronos import Chronos2Pipeline

from backtest import MODEL_ID, load_model_data, run_walk_forward_backtest
from evaluate import save_without_overwrite
from evaluate_validation import load_validation_rows


PROJECT_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_DIR / "configs" / "finetuning.json"
MODEL_DATA_PATH = (
    PROJECT_DIR
    / "data"
    / "processed"
    / "usd_krw_model_weekdays_19640504_20260730.csv"
)
BACKTEST_PATH = (
    PROJECT_DIR
    / "outputs"
    / "forecasts"
    / "usd_krw_walk_forward_h20_monthly_1997_2025.csv"
)
SPLIT_MANIFEST_PATH = (
    PROJECT_DIR
    / "outputs"
    / "metrics"
    / "usd_krw_walk_forward_h20_monthly_1997_2025_split_manifest.csv"
)
OUTPUT_PATH = (
    PROJECT_DIR
    / "outputs"
    / "forecasts"
    / "usd_krw_zero_shot_h20_ctx756_validation_2018_2021.csv"
)
DEVICE = "mps"
BATCH_SIZE = 8
ORIGIN_CHUNK_SIZE = 12
EXPECTED_ORIGINS = 48


def load_locked_settings(config_path: Path) -> tuple[int, int]:
    """선택이 끝난 context와 예측 길이만 설정 파일에서 읽는다."""
    config = json.loads(config_path.read_text(encoding="utf-8"))
    context_length = int(
        config["paired_zero_shot_context_selection"]["selected_context_length"]
    )
    prediction_length = int(config["prediction_length"])
    if context_length != 756:
        raise RuntimeError(f"선택된 context가 예상과 다릅니다: {context_length}")
    if prediction_length != 20:
        raise RuntimeError(f"예측 길이가 예상과 다릅니다: {prediction_length}")
    return context_length, prediction_length


def validate_export(forecast: pd.DataFrame, prediction_length: int) -> None:
    """앙상블 입력에 필요한 행·열·정렬·중복 조건을 확인한다."""
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
        "mase_scale_training_only",
    }
    missing_columns = required_columns - set(forecast.columns)
    if missing_columns:
        raise RuntimeError(f"Zero-shot 결과에 필수 열이 없습니다: {sorted(missing_columns)}")
    if forecast[list(required_columns)].isna().any().any():
        raise RuntimeError("Zero-shot Validation 결과에 결측값이 있습니다.")
    if len(forecast) != EXPECTED_ORIGINS * prediction_length:
        raise RuntimeError(
            f"Zero-shot Validation 행 수가 예상과 다릅니다: 실제={len(forecast)}, "
            f"예상={EXPECTED_ORIGINS * prediction_length}"
        )
    counts = forecast.groupby("requested_origin")["forecast_step"].agg(
        ["size", "nunique", "min", "max"]
    )
    invalid_counts = (
        (counts["size"] != prediction_length)
        | (counts["nunique"] != prediction_length)
        | (counts["min"] != 1)
        | (counts["max"] != prediction_length)
    )
    if invalid_counts.any():
        raise RuntimeError("기준일별 forecast_step이 1~20의 고유한 값이 아닙니다.")
    duplicate_keys = forecast.duplicated(
        subset=["requested_origin", "forecast_step", "target_date"]
    )
    if duplicate_keys.any():
        raise RuntimeError("Zero-shot Validation 결과에 중복 예측 행이 있습니다.")
    expected_order = forecast.sort_values(
        ["forecast_origin_date", "forecast_step"]
    ).index
    if not expected_order.equals(forecast.index):
        raise RuntimeError("Zero-shot Validation 결과가 기준일과 step 순으로 정렬되지 않았습니다.")


def main() -> None:
    if OUTPUT_PATH.exists():
        raise FileExistsError(f"기존 Zero-shot Validation 결과를 덮어쓰지 않습니다: {OUTPUT_PATH}")
    if DEVICE == "mps" and not torch.backends.mps.is_available():
        raise RuntimeError("현재 실행 환경에서 MPS를 사용할 수 없습니다.")

    context_length, prediction_length = load_locked_settings(CONFIG_PATH)
    validation = load_validation_rows(BACKTEST_PATH, SPLIT_MANIFEST_PATH)
    requested_origins = validation["requested_origin"].drop_duplicates().tolist()
    if len(requested_origins) != EXPECTED_ORIGINS:
        raise RuntimeError(
            f"Validation 기준일 수가 예상과 다릅니다: 실제={len(requested_origins)}, "
            f"예상={EXPECTED_ORIGINS}"
        )

    model_data = load_model_data(MODEL_DATA_PATH)
    pipeline = Chronos2Pipeline.from_pretrained(MODEL_ID, device_map=DEVICE)
    if str(pipeline.model.device).split(":")[0] != DEVICE:
        raise RuntimeError(
            f"모델 장치가 요청과 다릅니다: 요청={DEVICE}, 실제={pipeline.model.device}"
        )

    forecast = run_walk_forward_backtest(
        pipeline,
        model_data,
        requested_origins=requested_origins,
        horizon=prediction_length,
        context_length=context_length,
        batch_size=BATCH_SIZE,
        origin_chunk_size=ORIGIN_CHUNK_SIZE,
    ).sort_values(["forecast_origin_date", "forecast_step"]).reset_index(drop=True)
    validate_export(forecast, prediction_length)
    save_without_overwrite(forecast, OUTPUT_PATH)

    print(f"device: {DEVICE}")
    print(f"context_length: {context_length}")
    print(f"prediction_length: {prediction_length}")
    print(f"origins: {forecast['requested_origin'].nunique()}")
    print(f"rows: {len(forecast)}")
    print(f"target_start: {forecast['target_date'].min()}")
    print(f"target_end: {forecast['target_date'].max()}")
    print(f"saved: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
