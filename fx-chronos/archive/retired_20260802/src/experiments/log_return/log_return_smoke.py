from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch
from chronos import Chronos2Pipeline

from src.evaluation.backtest import load_model_data, resolve_origin_index
from src.models.zero_shot import find_quantile_index


PROJECT_DIR = Path(__file__).resolve().parent.parent.parent.parent
MODEL_ID = "amazon/chronos-2"
DEVICE = "mps"
CONTEXT_LENGTH = 756
PREDICTION_LENGTH = 20
REQUESTED_ORIGIN = "2017-11-01"
DATA_PATH = (
    PROJECT_DIR
    / "data"
    / "processed"
    / "usd_krw_model_weekdays_19640504_20260730.csv"
)
OUTPUT_PATH = (
    PROJECT_DIR
    / "outputs"
    / "forecasts"
    / "experiments"
    / "log_return"
    / "usd_krw_chronos2_log_return_smoke_origin20171101.csv"
)


def levels_to_log_returns(levels: np.ndarray) -> np.ndarray:
    """양수인 환율 수준값을 인접 관측 사이의 로그수익률로 변환한다."""
    values = np.asarray(levels, dtype=np.float64)
    if values.ndim != 1 or len(values) < 2:
        raise ValueError("로그수익률 변환에는 2개 이상의 1차원 환율값이 필요합니다.")
    if not np.isfinite(values).all() or (values <= 0).any():
        raise ValueError("로그수익률 변환 대상에는 양수인 유한 환율값만 허용됩니다.")
    return np.diff(np.log(values))


def reconstruct_levels(last_level: float, log_returns: np.ndarray) -> np.ndarray:
    """마지막 실제 환율과 미래 로그수익률로 미래 환율 수준을 복원한다."""
    returns = np.asarray(log_returns, dtype=np.float64)
    if returns.ndim != 1 or not np.isfinite(returns).all():
        raise ValueError("환율 복원에는 유한한 1차원 로그수익률이 필요합니다.")
    if not np.isfinite(last_level) or last_level <= 0:
        raise ValueError("환율 복원의 기준값은 양수인 유한 값이어야 합니다.")
    return float(last_level) * np.exp(np.cumsum(returns))


def build_log_return_input(
    dataframe: pd.DataFrame,
    requested_origin: str,
    context_length: int,
    prediction_length: int,
) -> tuple[np.ndarray, int]:
    """미래 관측을 보지 않고 기준일까지의 로그수익률 입력을 만든다."""
    if context_length <= 0:
        raise ValueError("context_length는 1 이상이어야 합니다.")
    origin_index = resolve_origin_index(dataframe, requested_origin, prediction_length)
    level_history = dataframe.loc[:origin_index, "value"].to_numpy(dtype=np.float64)
    required_levels = context_length + 1
    if len(level_history) < required_levels:
        raise RuntimeError(
            f"로그수익률 입력용 환율 이력이 부족합니다: "
            f"실제={len(level_history)}, 필요={required_levels}"
        )
    log_returns = levels_to_log_returns(level_history[-required_levels:])
    return log_returns.astype(np.float32), origin_index


def run_log_return_smoke(
    pipeline: Any,
    dataframe: pd.DataFrame,
    requested_origin: str = REQUESTED_ORIGIN,
    context_length: int = CONTEXT_LENGTH,
    prediction_length: int = PREDICTION_LENGTH,
) -> pd.DataFrame:
    model_input, origin_index = build_log_return_input(
        dataframe,
        requested_origin,
        context_length,
        prediction_length,
    )
    predictions = pipeline.predict(
        [model_input],
        prediction_length=prediction_length,
        context_length=context_length,
        cross_learning=False,
    )
    if len(predictions) != 1:
        raise RuntimeError(f"로그수익률 예측 결과 목록 길이가 1이 아닙니다: {len(predictions)}")

    forecast = predictions[0]
    if hasattr(forecast, "detach"):
        forecast = forecast.detach().cpu().numpy()
    forecast = np.asarray(forecast)
    quantile_levels = [float(level) for level in pipeline.quantiles]
    expected_shape = (1, len(quantile_levels), prediction_length)
    if forecast.shape != expected_shape:
        raise RuntimeError(
            f"로그수익률 예측 shape가 예상과 다릅니다: "
            f"실제={forecast.shape}, 예상={expected_shape}"
        )

    q50 = forecast[0, find_quantile_index(quantile_levels, 0.5), :]
    if not np.isfinite(q50).all():
        raise RuntimeError("중앙 로그수익률 예측에 유한하지 않은 값이 있습니다.")

    origin_date = pd.Timestamp(dataframe.loc[origin_index, "date"])
    origin_value = float(dataframe.loc[origin_index, "value"])
    reconstructed_q50 = reconstruct_levels(origin_value, q50)
    actual = dataframe.iloc[origin_index + 1 : origin_index + prediction_length + 1]
    if len(actual) != prediction_length:
        raise RuntimeError(
            f"smoke 평가용 실제값이 부족합니다: 실제={len(actual)}, 필요={prediction_length}"
        )

    return pd.DataFrame(
        {
            "requested_origin": requested_origin,
            "forecast_origin_date": origin_date,
            "forecast_origin_value": origin_value,
            "forecast_step": np.arange(1, prediction_length + 1),
            "target_date": actual["date"].to_numpy(),
            "actual_value": actual["value"].to_numpy(dtype=float),
            "predicted_log_return_q0.5": q50,
            "reconstructed_chronos_q0.5": reconstructed_q50,
            "random_walk_forecast": origin_value,
            "history_log_return_rows": len(model_input),
            "context_length": context_length,
            "model_id": MODEL_ID,
        }
    )


def main() -> None:
    if OUTPUT_PATH.exists():
        raise FileExistsError(f"기존 로그수익률 smoke 결과를 덮어쓰지 않습니다: {OUTPUT_PATH}")
    if not torch.backends.mps.is_available():
        raise RuntimeError("현재 실행 환경에서 MPS를 사용할 수 없습니다.")

    dataframe = load_model_data(DATA_PATH)
    pipeline = Chronos2Pipeline.from_pretrained(MODEL_ID, device_map=DEVICE)
    if str(pipeline.model.device).split(":")[0] != DEVICE:
        raise RuntimeError(
            f"모델 장치가 요청과 다릅니다: 요청={DEVICE}, 실제={pipeline.model.device}"
        )
    result = run_log_return_smoke(pipeline, dataframe)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(OUTPUT_PATH, index=False, date_format="%Y-%m-%d")

    chronos_error = result["actual_value"] - result["reconstructed_chronos_q0.5"]
    random_walk_error = result["actual_value"] - result["random_walk_forecast"]
    print(f"장치: {pipeline.model.device}")
    print(f"요청 기준일: {REQUESTED_ORIGIN}")
    print(f"실제 입력 종료일: {result['forecast_origin_date'].iloc[0].date()}")
    print(f"로그수익률 입력 행 수: {result['history_log_return_rows'].iloc[0]}")
    print(f"예측 행 수: {len(result)}")
    print(f"Chronos 복원 수준 MAE: {chronos_error.abs().mean():.6f}")
    print(f"Random Walk MAE: {random_walk_error.abs().mean():.6f}")
    print(f"저장 경로: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
