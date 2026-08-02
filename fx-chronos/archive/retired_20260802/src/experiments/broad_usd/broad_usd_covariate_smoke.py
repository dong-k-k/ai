from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch
from chronos import Chronos2Pipeline

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
    / "usd_broad_usd_covariates_weekdays_asof_20090114_20260730.csv"
)
OUTPUT_PATH = (
    PROJECT_DIR
    / "outputs"
    / "forecasts"
    / "experiments"
    / "broad_usd"
    / "usd_krw_chronos2_broad_usd_asof_smoke_origin20171101.csv"
)


def load_broad_usd_covariate_data(csv_path: Path) -> pd.DataFrame:
    required = {
        "date",
        "usd_krw_krw_per_usd",
        "broad_usd_index",
        "broad_usd_observation_date",
        "broad_usd_safe_from_krw_date",
    }
    dataframe = pd.read_csv(
        csv_path,
        parse_dates=[
            "date",
            "broad_usd_observation_date",
            "broad_usd_safe_from_krw_date",
        ],
    )
    missing = required - set(dataframe.columns)
    if missing:
        raise RuntimeError(f"Broad Dollar 공변량 데이터에 필수 열이 없습니다: {sorted(missing)}")
    if dataframe[list(required)].isna().any().any():
        raise RuntimeError("Broad Dollar 공변량 데이터에 필수값 결측이 있습니다.")
    if dataframe["date"].duplicated().any() or not dataframe["date"].is_monotonic_increasing:
        raise RuntimeError("Broad Dollar 공변량 날짜가 중복됐거나 오름차순이 아닙니다.")
    if not (dataframe["broad_usd_safe_from_krw_date"] <= dataframe["date"]).all():
        raise RuntimeError("아직 공개되지 않은 Broad Dollar 값이 연결됐습니다.")
    if not (dataframe["broad_usd_observation_date"] < dataframe["date"]).all():
        raise RuntimeError("현재 또는 미래 Broad Dollar 관측값이 연결됐습니다.")
    return dataframe


def build_broad_usd_input(
    dataframe: pd.DataFrame,
    requested_origin: str,
    context_length: int,
) -> tuple[dict[str, Any], pd.DataFrame, pd.Timestamp]:
    if context_length <= 0:
        raise ValueError("context_length는 1 이상이어야 합니다.")
    requested = pd.Timestamp(requested_origin)
    history = dataframe.loc[dataframe["date"] <= requested].tail(context_length).copy()
    if len(history) != context_length:
        raise RuntimeError(
            f"Broad Dollar smoke 입력 길이가 부족합니다: 실제={len(history)}, 필요={context_length}"
        )
    forecast_origin = pd.Timestamp(history["date"].iloc[-1])
    if not (history["broad_usd_safe_from_krw_date"] <= history["date"]).all():
        raise RuntimeError("smoke 입력에 공개 전 Broad Dollar 값이 포함되어 있습니다.")
    if not (history["broad_usd_observation_date"] < history["date"]).all():
        raise RuntimeError("smoke 입력에 현재 또는 미래 Broad Dollar 관측이 포함되어 있습니다.")

    model_input: dict[str, Any] = {
        "target": history["usd_krw_krw_per_usd"].to_numpy(dtype=np.float32),
        "past_covariates": {
            "broad_usd_index_asof": history["broad_usd_index"].to_numpy(
                dtype=np.float32
            )
        },
    }
    return model_input, history, forecast_origin


def run_broad_usd_smoke(
    pipeline: Any,
    dataframe: pd.DataFrame,
    requested_origin: str = REQUESTED_ORIGIN,
    context_length: int = CONTEXT_LENGTH,
    prediction_length: int = PREDICTION_LENGTH,
) -> pd.DataFrame:
    model_input, history, forecast_origin = build_broad_usd_input(
        dataframe, requested_origin, context_length
    )
    predictions = pipeline.predict(
        [model_input],
        prediction_length=prediction_length,
        context_length=context_length,
    )
    if len(predictions) != 1:
        raise RuntimeError(f"Broad Dollar 예측 결과 목록 길이가 1이 아닙니다: {len(predictions)}")
    forecast = predictions[0]
    if hasattr(forecast, "detach"):
        forecast = forecast.detach().cpu().numpy()
    forecast = np.asarray(forecast)
    quantiles = [float(level) for level in pipeline.quantiles]
    expected_shape = (1, len(quantiles), prediction_length)
    if forecast.shape != expected_shape:
        raise RuntimeError(
            f"Broad Dollar 예측 shape가 예상과 다릅니다: 실제={forecast.shape}, 예상={expected_shape}"
        )
    q10 = forecast[0, find_quantile_index(quantiles, 0.1), :]
    q50 = forecast[0, find_quantile_index(quantiles, 0.5), :]
    q90 = forecast[0, find_quantile_index(quantiles, 0.9), :]
    if not np.all((q10 <= q50) & (q50 <= q90)):
        raise RuntimeError("Broad Dollar smoke 예측 분위수 순서가 올바르지 않습니다.")

    actual = dataframe.loc[dataframe["date"] > forecast_origin].head(prediction_length)
    if len(actual) != prediction_length:
        raise RuntimeError(
            f"Broad Dollar smoke 실제값이 부족합니다: 실제={len(actual)}, 필요={prediction_length}"
        )
    origin_value = float(history["usd_krw_krw_per_usd"].iloc[-1])
    return pd.DataFrame(
        {
            "requested_origin": requested_origin,
            "forecast_origin_date": forecast_origin,
            "forecast_origin_value": origin_value,
            "forecast_step": np.arange(1, prediction_length + 1),
            "target_date": actual["date"].to_numpy(),
            "actual_value": actual["usd_krw_krw_per_usd"].to_numpy(dtype=float),
            "chronos_q0.1_lower": q10,
            "chronos_q0.5_median": q50,
            "chronos_q0.9_upper": q90,
            "random_walk_forecast": origin_value,
            "target_series": "USD/KRW",
            "past_covariate": "DTWEXBGS broad_usd_index point-in-time as-of",
            "future_covariates_provided": False,
            "history_rows": len(history),
            "context_length": context_length,
            "prediction_length": prediction_length,
        }
    )


def main() -> None:
    if OUTPUT_PATH.exists():
        raise FileExistsError(f"기존 Broad Dollar smoke 결과를 덮어쓰지 않습니다: {OUTPUT_PATH}")
    if not torch.backends.mps.is_available():
        raise RuntimeError("현재 실행 환경에서 MPS를 사용할 수 없습니다.")
    dataframe = load_broad_usd_covariate_data(DATA_PATH)
    pipeline = Chronos2Pipeline.from_pretrained(MODEL_ID, device_map=DEVICE)
    if str(pipeline.model.device).split(":")[0] != DEVICE:
        raise RuntimeError(
            f"모델 장치가 요청과 다릅니다: 요청={DEVICE}, 실제={pipeline.model.device}"
        )
    result = run_broad_usd_smoke(pipeline, dataframe)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(OUTPUT_PATH, index=False, date_format="%Y-%m-%d")

    chronos_mae = float((result["actual_value"] - result["chronos_q0.5_median"]).abs().mean())
    random_walk_mae = float((result["actual_value"] - result["random_walk_forecast"]).abs().mean())
    print(f"장치: {pipeline.model.device}")
    print(f"요청 기준일: {REQUESTED_ORIGIN}")
    print(f"실제 입력 종료일: {result['forecast_origin_date'].iloc[0].date()}")
    print(f"입력 행 수: {result['history_rows'].iloc[0]}")
    print(f"예측 행 수: {len(result)}")
    print(f"Broad Dollar Chronos MAE: {chronos_mae:.6f}")
    print(f"Random Walk MAE: {random_walk_mae:.6f}")
    print(f"저장 경로: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
