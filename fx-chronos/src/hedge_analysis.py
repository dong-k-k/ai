from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from enum import Enum

from forecast_provider import ForecastScenario


class ExposureSide(str, Enum):
    PAYMENT = "payment"
    RECEIPT = "receipt"


@dataclass(frozen=True)
class FxExposure:
    """한 결제일에 지급하거나 수취할 외화 노출 정보."""

    currency_pair: str
    side: ExposureSide
    foreign_amount: float
    settlement_date: date
    reference_rate: float
    hedged_amount: float | None = None
    hedged_ratio: float | None = None
    hedge_rate: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.side, ExposureSide):
            raise ValueError("side는 ExposureSide.PAYMENT 또는 ExposureSide.RECEIPT여야 합니다.")
        if not isinstance(self.settlement_date, date):
            raise ValueError("settlement_date는 date 값이어야 합니다.")
        if "/" not in self.currency_pair or len(self.currency_pair.split("/")) != 2:
            raise ValueError("currency_pair 형식은 BASE/QUOTE여야 합니다.")
        _validate_positive_number(self.foreign_amount, "foreign_amount")
        _validate_positive_number(self.reference_rate, "reference_rate")
        if self.hedged_amount is not None and self.hedged_ratio is not None:
            raise ValueError("hedged_amount와 hedged_ratio는 동시에 입력할 수 없습니다.")
        if self.hedged_amount is not None:
            _validate_nonnegative_number(self.hedged_amount, "hedged_amount")
            if self.hedged_amount > self.foreign_amount:
                raise ValueError("hedged_amount는 foreign_amount를 초과할 수 없습니다.")
        if self.hedged_ratio is not None:
            _validate_nonnegative_number(self.hedged_ratio, "hedged_ratio")
            if self.hedged_ratio > 1:
                raise ValueError("hedged_ratio는 0과 1 사이여야 합니다.")

        resolved_hedged_amount = self.resolved_hedged_amount
        if resolved_hedged_amount > 0:
            if self.hedge_rate is None:
                raise ValueError("헤지 금액이 있으면 hedge_rate가 필요합니다.")
            _validate_positive_number(self.hedge_rate, "hedge_rate")
        elif self.hedge_rate is not None:
            raise ValueError("헤지 금액이 0이면 hedge_rate를 입력하지 않습니다.")

    @property
    def resolved_hedged_amount(self) -> float:
        if self.hedged_amount is not None:
            return float(self.hedged_amount)
        if self.hedged_ratio is not None:
            return float(self.foreign_amount) * float(self.hedged_ratio)
        return 0.0

    @property
    def unhedged_amount(self) -> float:
        return float(self.foreign_amount) - self.resolved_hedged_amount

    @property
    def risk_direction(self) -> str:
        if self.side is ExposureSide.PAYMENT:
            return "환율 상승 시 원화 지급액 증가로 불리"
        return "환율 하락 시 원화 수취액 감소로 불리"


@dataclass(frozen=True)
class ScenarioAmountResult:
    scenario_name: str
    fx_rate: float
    hedged_krw_amount: float
    unhedged_krw_amount: float
    total_krw_amount: float
    fully_unhedged_krw_amount: float
    reference_krw_amount: float
    favorable_pnl_vs_reference_krw: float
    hedge_effect_vs_unhedged_krw: float


@dataclass(frozen=True)
class HedgeAnalysisResult:
    currency_pair: str
    side: ExposureSide
    settlement_date: date
    foreign_amount: float
    hedged_amount: float
    unhedged_amount: float
    hedge_ratio: float
    risk_direction: str
    forecast_model_name: str
    scenario_source: str
    scenarios: tuple[ScenarioAmountResult, ...]
    warnings: tuple[str, ...]


def _validate_positive_number(value: object, field_name: str) -> None:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name}은 숫자여야 합니다.") from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{field_name}은 유한한 양수여야 합니다.")


def _validate_nonnegative_number(value: object, field_name: str) -> None:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name}은 숫자여야 합니다.") from exc
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{field_name}은 유한한 0 이상의 값이어야 합니다.")


def _calculate_scenario_amount(
    exposure: FxExposure,
    scenario_name: str,
    fx_rate: float,
) -> ScenarioAmountResult:
    foreign_amount = float(exposure.foreign_amount)
    reference_rate = float(exposure.reference_rate)
    hedged_krw = exposure.resolved_hedged_amount * float(exposure.hedge_rate or 0.0)
    unhedged_krw = exposure.unhedged_amount * fx_rate
    total_krw = hedged_krw + unhedged_krw
    fully_unhedged_krw = foreign_amount * fx_rate
    reference_krw = foreign_amount * reference_rate

    if exposure.side is ExposureSide.PAYMENT:
        favorable_pnl = reference_krw - total_krw
        hedge_effect = fully_unhedged_krw - total_krw
    else:
        favorable_pnl = total_krw - reference_krw
        hedge_effect = total_krw - fully_unhedged_krw

    return ScenarioAmountResult(
        scenario_name=scenario_name,
        fx_rate=float(fx_rate),
        hedged_krw_amount=float(hedged_krw),
        unhedged_krw_amount=float(unhedged_krw),
        total_krw_amount=float(total_krw),
        fully_unhedged_krw_amount=float(fully_unhedged_krw),
        reference_krw_amount=float(reference_krw),
        favorable_pnl_vs_reference_krw=float(favorable_pnl),
        hedge_effect_vs_unhedged_krw=float(hedge_effect),
    )


def analyze_fx_exposure(
    exposure: FxExposure,
    forecast: ForecastScenario,
) -> HedgeAnalysisResult:
    """모델 호출 없이 공통 환율 시나리오를 계약 금액으로 변환한다."""
    if exposure.currency_pair != forecast.currency_pair:
        raise ValueError(
            f"계약 통화와 예측 통화가 다릅니다: "
            f"계약={exposure.currency_pair}, 예측={forecast.currency_pair}"
        )
    if exposure.settlement_date not in forecast.forecast_dates:
        raise ValueError(
            "결제일이 예측 날짜에 없습니다. 가까운 날짜로 임의 이동하지 않습니다: "
            f"{exposure.settlement_date}"
        )
    date_index = forecast.forecast_dates.index(exposure.settlement_date)

    scenario_rates: list[tuple[str, float]] = [
        ("point", forecast.point_forecast[date_index])
    ]
    if forecast.has_interval_scenarios:
        if (
            forecast.lower_scenario is None
            or forecast.median_scenario is None
            or forecast.upper_scenario is None
        ):
            raise RuntimeError("ForecastScenario의 분위수 시나리오 상태가 일관되지 않습니다.")
        scenario_rates.extend(
            [
                ("lower", forecast.lower_scenario[date_index]),
                ("median", forecast.median_scenario[date_index]),
                ("upper", forecast.upper_scenario[date_index]),
            ]
        )

    scenarios = tuple(
        _calculate_scenario_amount(exposure, scenario_name, fx_rate)
        for scenario_name, fx_rate in scenario_rates
    )
    warnings = [
        "은행 스프레드, 환전 수수료, 세금 및 실제 헤지 상품 조건은 포함하지 않습니다.",
        "이 계산은 금융상품 또는 최적 헤지 비율을 추천하지 않습니다.",
    ]
    if forecast.warning.strip():
        warnings.insert(0, forecast.warning.strip())

    return HedgeAnalysisResult(
        currency_pair=exposure.currency_pair,
        side=exposure.side,
        settlement_date=exposure.settlement_date,
        foreign_amount=float(exposure.foreign_amount),
        hedged_amount=exposure.resolved_hedged_amount,
        unhedged_amount=exposure.unhedged_amount,
        hedge_ratio=float(exposure.resolved_hedged_amount / exposure.foreign_amount),
        risk_direction=exposure.risk_direction,
        forecast_model_name=forecast.model_name,
        scenario_source=forecast.scenario_source.value,
        scenarios=scenarios,
        warnings=tuple(warnings),
    )
