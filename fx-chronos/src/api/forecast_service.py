from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from threading import RLock
from typing import Callable, Protocol
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import torch
from chronos import Chronos2Pipeline

from src.evaluation.backtest import find_quantile_index, load_model_data
from src.hedging.forecast_provider import ForecastScenario, ScenarioSource


LOGGER = logging.getLogger(__name__)
PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_DATA_PATH = (
    PROJECT_DIR / "data" / "processed" / "usd_krw_model_weekdays_19640504_20260730.csv"
)
MODEL_ID = "amazon/chronos-2"
CONTEXT_LENGTH = 756
ALPHA = 0.5
HORIZONS = (20, 60, 90)
SEOUL = ZoneInfo("Asia/Seoul")
FORECAST_WARNING = (
    "미래 날짜는 월요일~금요일 기준의 임시 날짜이며 한국 공휴일을 별도로 제외하지 않습니다. "
    "Chronos 분위수는 참고용 시나리오이며 검증된 80% 신뢰구간이 아닙니다."
)


class PipelineProtocol(Protocol):
    quantiles: list[float]

    def predict(self, *args: object, **kwargs: object) -> object: ...


PipelineLoader = Callable[[str, str], PipelineProtocol]


@dataclass(frozen=True)
class ForecastSnapshot:
    created_at: datetime
    data_path: Path
    last_observation_date: date
    last_observation_value: float
    forecasts: dict[int, ForecastScenario]


def resolve_device() -> str:
    requested = os.getenv("FX_CHRONOS_DEVICE", "auto").strip().lower()
    if requested == "auto":
        return "mps" if torch.backends.mps.is_available() else "cpu"
    if requested not in {"cpu", "mps"}:
        raise RuntimeError("FX_CHRONOS_DEVICE는 auto, cpu 또는 mps여야 합니다.")
    if requested == "mps" and not torch.backends.mps.is_available():
        raise RuntimeError("현재 실행 환경에서 MPS를 사용할 수 없습니다.")
    return requested


def default_pipeline_loader(model_id: str, device: str) -> PipelineProtocol:
    return Chronos2Pipeline.from_pretrained(model_id, device_map=device)


def _prediction_to_numpy(prediction: object) -> np.ndarray:
    if hasattr(prediction, "detach"):
        prediction = prediction.detach().cpu().numpy()
    return np.asarray(prediction)


class ForecastService:
    """Chronos 모델과 고정 앙상블 예측 스냅샷을 원자적으로 교체한다."""

    def __init__(
        self,
        *,
        data_path: Path = DEFAULT_DATA_PATH,
        pipeline_loader: PipelineLoader = default_pipeline_loader,
        device: str | None = None,
    ) -> None:
        self._data_path = data_path
        self._pipeline_loader = pipeline_loader
        self._device = device or resolve_device()
        self._lock = RLock()
        self._snapshot: ForecastSnapshot | None = None

    @property
    def device(self) -> str:
        return self._device

    @property
    def snapshot(self) -> ForecastSnapshot:
        with self._lock:
            if self._snapshot is None:
                raise RuntimeError("예측 리소스가 아직 준비되지 않았습니다.")
            return self._snapshot

    def initialize(self) -> None:
        self.reload()

    def reload(self) -> None:
        """새 모델과 전체 예측을 먼저 완성한 뒤 정상 스냅샷 참조를 교체한다."""
        candidate = self._build_snapshot()
        with self._lock:
            self._snapshot = candidate
        LOGGER.info(
            "Forecast snapshot replaced: created_at=%s last_observation=%s device=%s",
            candidate.created_at.isoformat(),
            candidate.last_observation_date.isoformat(),
            self._device,
        )

    def _build_snapshot(self) -> ForecastSnapshot:
        dataframe = load_model_data(self._data_path)
        if len(dataframe) < CONTEXT_LENGTH:
            raise RuntimeError(
                f"Chronos 입력이 context length보다 짧습니다: {len(dataframe)} < {CONTEXT_LENGTH}"
            )
        pipeline = self._pipeline_loader(MODEL_ID, self._device)
        values = dataframe["value"].tail(CONTEXT_LENGTH).to_numpy(dtype=np.float32)
        origin_date = pd.Timestamp(dataframe.iloc[-1]["date"])
        origin_value = float(dataframe.iloc[-1]["value"])
        quantiles = [float(level) for level in pipeline.quantiles]
        q10_index = find_quantile_index(quantiles, 0.1)
        q50_index = find_quantile_index(quantiles, 0.5)
        q90_index = find_quantile_index(quantiles, 0.9)
        forecasts: dict[int, ForecastScenario] = {}

        for horizon in HORIZONS:
            predictions = pipeline.predict(
                [values],
                prediction_length=horizon,
                batch_size=1,
                context_length=CONTEXT_LENGTH,
                cross_learning=False,
            )
            if len(predictions) != 1:
                raise RuntimeError(f"Chronos H{horizon} 예측 결과 수가 1이 아닙니다.")
            forecast = _prediction_to_numpy(predictions[0])
            expected_shape = (1, len(quantiles), horizon)
            if forecast.shape != expected_shape:
                raise RuntimeError(
                    f"Chronos H{horizon} shape이 예상과 다릅니다: {forecast.shape} != {expected_shape}"
                )
            lower = forecast[0, q10_index, :].astype(float)
            median = forecast[0, q50_index, :].astype(float)
            upper = forecast[0, q90_index, :].astype(float)
            if not np.all((lower <= median) & (median <= upper)):
                raise RuntimeError(f"Chronos H{horizon} 분위수 순서가 올바르지 않습니다.")
            ensemble = origin_value + ALPHA * (median - origin_value)
            provisional_dates = tuple(
                timestamp.date()
                for timestamp in pd.bdate_range(
                    start=origin_date + pd.offsets.BDay(1), periods=horizon
                )
            )
            forecasts[horizon] = ForecastScenario(
                model_name=f"{MODEL_ID} + Random Walk fixed alpha={ALPHA} H{horizon}",
                scenario_source=ScenarioSource.SHRUNK_ENSEMBLE,
                currency_pair="USD/KRW",
                unit="KRW per USD",
                forecast_origin=origin_date.date(),
                prediction_length=horizon,
                forecast_dates=provisional_dates,
                point_forecast=tuple(float(value) for value in ensemble),
                lower_scenario=tuple(float(value) for value in lower),
                median_scenario=tuple(float(value) for value in median),
                upper_scenario=tuple(float(value) for value in upper),
                warning=FORECAST_WARNING,
            )

        return ForecastSnapshot(
            created_at=datetime.now(tz=SEOUL),
            data_path=self._data_path,
            last_observation_date=origin_date.date(),
            last_observation_value=origin_value,
            forecasts=forecasts,
        )

    def forecast_for_settlement(self, settlement_date: date) -> ForecastScenario:
        snapshot = self.snapshot
        for horizon in HORIZONS:
            forecast = snapshot.forecasts[horizon]
            if settlement_date in forecast.forecast_dates:
                return forecast
        first_date = snapshot.forecasts[20].forecast_dates[0]
        last_date = snapshot.forecasts[90].forecast_dates[-1]
        raise ValueError(
            "결제일이 현재 90개 예측 관측 범위에 없거나 임시 평일 날짜가 아닙니다: "
            f"지원 범위={first_date.isoformat()}~{last_date.isoformat()}"
        )

    def h90_forecast(self) -> tuple[datetime, ForecastScenario]:
        """동일 스냅샷의 생성 시각과 H90 예측을 함께 반환한다."""
        with self._lock:
            if self._snapshot is None:
                raise RuntimeError("예측 리소스가 아직 준비되지 않았습니다.")
            return self._snapshot.created_at, self._snapshot.forecasts[90]
