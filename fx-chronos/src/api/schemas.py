from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ApiExposureSide(str, Enum):
    PAYABLE = "PAYABLE"
    RECEIVABLE = "RECEIVABLE"


class HedgeAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    currency_pair: str = Field(pattern=r"^[A-Z]{3}/[A-Z]{3}$")
    side: ApiExposureSide
    foreign_amount: float = Field(gt=0)
    settlement_date: date
    reference_rate: float = Field(gt=0)
    hedged_amount: float = Field(default=0.0, ge=0)
    hedge_rate: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_supported_contract(self) -> HedgeAnalysisRequest:
        if self.currency_pair != "USD/KRW":
            raise ValueError("현재 지원하는 통화쌍은 USD/KRW입니다.")
        if self.hedged_amount > self.foreign_amount:
            raise ValueError("hedged_amount는 foreign_amount를 초과할 수 없습니다.")
        if self.hedged_amount > 0 and self.hedge_rate is None:
            raise ValueError("hedged_amount가 0보다 크면 hedge_rate가 필요합니다.")
        if self.hedged_amount == 0 and self.hedge_rate is not None:
            raise ValueError("hedged_amount가 0이면 hedge_rate를 입력하지 않습니다.")
        return self


class ScenarioAmountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    scenario_name: str
    fx_rate: float
    hedged_krw_amount: float
    unhedged_krw_amount: float
    total_krw_amount: float
    fully_unhedged_krw_amount: float
    reference_krw_amount: float
    favorable_pnl_vs_reference_krw: float
    hedge_effect_vs_unhedged_krw: float


class HedgeAnalysisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    currency_pair: str
    side: str
    settlement_date: date
    foreign_amount: float
    hedged_amount: float
    unhedged_amount: float
    hedge_ratio: float
    risk_direction: str
    forecast_model_name: str
    scenario_source: str
    scenarios: tuple[ScenarioAmountResponse, ...]
    warnings: tuple[str, ...]
