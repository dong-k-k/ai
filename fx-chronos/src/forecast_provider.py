from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Mapping, Sequence

import pandas as pd


class ScenarioSource(str, Enum):
    RANDOM_WALK = "random_walk"
    CHRONOS_ZERO_SHOT = "chronos_zero_shot"
    SHRUNK_ENSEMBLE = "shrunk_ensemble"
    USER_DEFINED = "user_defined"
    HISTORICAL_STRESS = "historical_stress"
    VOLATILITY_BASED = "volatility_based"


def _to_date(value: object, field_name: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        raise ValueError(f"{field_name}을 날짜로 변환할 수 없습니다: {value!r}")
    return parsed.date()


def _to_float_tuple(values: Sequence[object], field_name: str) -> tuple[float, ...]:
    converted: list[float] = []
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field_name}에 숫자로 변환할 수 없는 값이 있습니다: {value!r}") from exc
        if not math.isfinite(number) or number <= 0:
            raise ValueError(f"{field_name}의 환율은 유한한 양수여야 합니다: {number}")
        converted.append(number)
    return tuple(converted)


@dataclass(frozen=True)
class ForecastScenario:
    """예측 모델과 환위험 계산 엔진 사이의 공통 환율 시나리오 형식."""

    model_name: str
    scenario_source: ScenarioSource
    currency_pair: str
    unit: str
    forecast_origin: date
    prediction_length: int
    forecast_dates: tuple[date, ...]
    point_forecast: tuple[float, ...]
    lower_scenario: tuple[float, ...] | None = None
    median_scenario: tuple[float, ...] | None = None
    upper_scenario: tuple[float, ...] | None = None
    validation_metrics: Mapping[str, float] = field(default_factory=dict)
    warning: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.scenario_source, ScenarioSource):
            raise ValueError("scenario_source는 ScenarioSource 값이어야 합니다.")
        normalized_origin = _to_date(self.forecast_origin, "forecast_origin")
        normalized_dates = tuple(
            _to_date(value, "forecast_dates") for value in self.forecast_dates
        )
        normalized_point = _to_float_tuple(self.point_forecast, "point_forecast")
        object.__setattr__(self, "forecast_origin", normalized_origin)
        object.__setattr__(self, "forecast_dates", normalized_dates)
        object.__setattr__(self, "point_forecast", normalized_point)
        if not self.model_name.strip():
            raise ValueError("model_name은 비어 있을 수 없습니다.")
        if "/" not in self.currency_pair or len(self.currency_pair.split("/")) != 2:
            raise ValueError(f"currency_pair 형식은 BASE/QUOTE여야 합니다: {self.currency_pair!r}")
        if not self.unit.strip():
            raise ValueError("unit은 비어 있을 수 없습니다.")
        if self.prediction_length <= 0:
            raise ValueError("prediction_length는 양수여야 합니다.")
        if len(self.forecast_dates) != self.prediction_length:
            raise ValueError("forecast_dates 길이가 prediction_length와 다릅니다.")
        if len(self.point_forecast) != self.prediction_length:
            raise ValueError("point_forecast 길이가 prediction_length와 다릅니다.")
        if tuple(sorted(self.forecast_dates)) != self.forecast_dates:
            raise ValueError("forecast_dates는 오름차순이어야 합니다.")
        if len(set(self.forecast_dates)) != len(self.forecast_dates):
            raise ValueError("forecast_dates에 중복 날짜가 있습니다.")
        if any(forecast_date <= self.forecast_origin for forecast_date in self.forecast_dates):
            raise ValueError("모든 forecast_date는 forecast_origin보다 뒤여야 합니다.")

        scenario_values = (
            self.lower_scenario,
            self.median_scenario,
            self.upper_scenario,
        )
        provided_count = sum(value is not None for value in scenario_values)
        if provided_count not in (0, 3):
            raise ValueError("하한·중앙·상한 시나리오는 모두 제공하거나 모두 생략해야 합니다.")
        if provided_count == 3:
            lower = _to_float_tuple(self.lower_scenario or (), "lower_scenario")
            median = _to_float_tuple(self.median_scenario or (), "median_scenario")
            upper = _to_float_tuple(self.upper_scenario or (), "upper_scenario")
            object.__setattr__(self, "lower_scenario", lower)
            object.__setattr__(self, "median_scenario", median)
            object.__setattr__(self, "upper_scenario", upper)
            if any(len(values) != self.prediction_length for values in (lower, median, upper)):
                raise ValueError("시나리오 배열 길이가 prediction_length와 다릅니다.")
            if any(not (low <= middle <= high) for low, middle, high in zip(lower, median, upper)):
                raise ValueError("각 날짜에서 하한 ≤ 중앙 ≤ 상한이어야 합니다.")

        if self.scenario_source in {
            ScenarioSource.CHRONOS_ZERO_SHOT,
            ScenarioSource.SHRUNK_ENSEMBLE,
        } and not self.warning.strip():
            raise ValueError("Chronos 기반 시나리오에는 검증 한계를 설명하는 warning이 필요합니다.")
        for metric_name, metric_value in self.validation_metrics.items():
            if not metric_name.strip() or not math.isfinite(float(metric_value)):
                raise ValueError("validation_metrics의 이름과 값은 유효해야 합니다.")

    @property
    def has_interval_scenarios(self) -> bool:
        return self.lower_scenario is not None


def load_forecast_scenario_from_csv(
    csv_path: Path,
    *,
    requested_origin: str | date,
    model_name: str,
    scenario_source: ScenarioSource,
    point_column: str,
    currency_pair: str = "USD/KRW",
    unit: str = "KRW per USD",
    lower_column: str | None = None,
    median_column: str | None = None,
    upper_column: str | None = None,
    validation_metrics: Mapping[str, float] | None = None,
    warning: str = "",
) -> ForecastScenario:
    """다중 기준일 예측 CSV에서 한 기준일을 명시적으로 선택해 변환한다."""
    dataframe = pd.read_csv(csv_path)
    scenario_columns = (lower_column, median_column, upper_column)
    if sum(column is not None for column in scenario_columns) not in (0, 3):
        raise ValueError("하한·중앙·상한 열 이름은 모두 제공하거나 모두 생략해야 합니다.")

    required_columns = {
        "requested_origin",
        "forecast_origin_date",
        "forecast_step",
        "target_date",
        point_column,
    }
    required_columns.update(column for column in scenario_columns if column is not None)
    missing_columns = required_columns - set(dataframe.columns)
    if missing_columns:
        raise ValueError(f"예측 CSV에 필수 열이 없습니다: {sorted(missing_columns)}")

    requested_date = _to_date(requested_origin, "requested_origin")
    dataframe["requested_origin"] = pd.to_datetime(
        dataframe["requested_origin"], errors="coerce"
    ).dt.date
    selected = dataframe[dataframe["requested_origin"].eq(requested_date)].copy()
    if selected.empty:
        raise ValueError(f"요청 기준일의 예측 행이 없습니다: {requested_date}")
    selected = selected.sort_values("forecast_step").reset_index(drop=True)
    if selected["forecast_step"].duplicated().any():
        raise ValueError("선택한 기준일에 중복 forecast_step이 있습니다.")

    forecast_origins = {
        _to_date(value, "forecast_origin_date")
        for value in selected["forecast_origin_date"]
    }
    if len(forecast_origins) != 1:
        raise ValueError("선택한 기준일에 forecast_origin_date가 여러 개입니다.")
    forecast_dates = tuple(
        _to_date(value, "target_date") for value in selected["target_date"]
    )
    point_forecast = _to_float_tuple(selected[point_column].tolist(), point_column)

    lower = median = upper = None
    if lower_column and median_column and upper_column:
        lower = _to_float_tuple(selected[lower_column].tolist(), lower_column)
        median = _to_float_tuple(selected[median_column].tolist(), median_column)
        upper = _to_float_tuple(selected[upper_column].tolist(), upper_column)

    return ForecastScenario(
        model_name=model_name,
        scenario_source=scenario_source,
        currency_pair=currency_pair,
        unit=unit,
        forecast_origin=forecast_origins.pop(),
        prediction_length=len(selected),
        forecast_dates=forecast_dates,
        point_forecast=point_forecast,
        lower_scenario=lower,
        median_scenario=median,
        upper_scenario=upper,
        validation_metrics=dict(validation_metrics or {}),
        warning=warning,
    )
