"""다중 통화 원화 환산 + 노출 그룹별 목표 헤지금액 계산.

핵심 원칙: riskContext.baseRate 하나를 여러 통화에 공통 적용하지 않는다.
계산에 필요한 근거가 부족하면 절대 추측하지 않고 null + 계산 상태 코드를
반환한다.

원화 노출액(groupExposureKrw) 계산 우선순위:
  1) contracts[].exposureKrw (계약별로 이미 계산된 값)
  2) contracts[].foreignAmount × contracts[].baseRate (계약별 환율)
  3) 노출 그룹이 하나뿐일 때만 riskContext.exposureKrw
  4) 그래도 없으면 null (MISSING_RATE/MISSING_EXPOSURE)

목표 헤지금액:
  groupTargetHedgeAmountKrw = groupExposureKrw × targetHedgeRatio
  recommendedHedgeAmountKrw = groupTargetHedgeAmountKrw × allocationRatio
targetHedgeRatio가 없으면(hedgeTargetMax로 대체하지 않음) 두 값 모두 null.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.exposure import ExposureGroup
from app.models import ContractItem, RiskContextIn, StrategyContextIn


def _contract_exposure_krw(contract: ContractItem) -> float | None:
    if contract.exposure_krw is not None:
        return contract.exposure_krw
    if contract.base_rate is not None:
        return contract.foreign_amount * contract.base_rate
    return None


@dataclass(frozen=True)
class GroupExposure:
    exposure_krw: float | None
    status: str  # "PROVIDED" | "CALCULATED" | "MISSING_RATE" | "MISSING_EXPOSURE"


def compute_group_exposure(
    group: ExposureGroup,
    all_contracts: list[ContractItem],
    risk_context: RiskContextIn | None,
    is_single_group: bool,
) -> GroupExposure:
    group_contracts = group.contracts(all_contracts)
    per_contract = [_contract_exposure_krw(c) for c in group_contracts]

    if all(v is not None for v in per_contract):
        total = sum(v for v in per_contract if v is not None)
        used_calculation = any(
            c.exposure_krw is None and c.base_rate is not None for c in group_contracts
        )
        status = "CALCULATED" if used_calculation else "PROVIDED"
        return GroupExposure(exposure_krw=total, status=status)

    # 계약 단위로 다 채워지지 않았다 — 노출 그룹이 하나뿐일 때만 집계값으로 보완.
    if is_single_group and risk_context is not None and risk_context.exposure_krw is not None:
        return GroupExposure(exposure_krw=risk_context.exposure_krw, status="PROVIDED")

    # 추정하지 않는다. 근거가 아예 없는지(통화 자체를 모름) vs 금액은 있지만
    # 환율만 없는지 구분해서 더 구체적인 상태를 알려준다.
    any_resolved = any(v is not None for v in per_contract)
    status = "MISSING_RATE" if any_resolved or group_contracts else "MISSING_EXPOSURE"
    return GroupExposure(exposure_krw=None, status=status)


def get_target_hedge_ratio(group_id: str, strategy_context: StrategyContextIn | None, is_single_group: bool) -> float | None:
    if strategy_context is None:
        return None
    for target in strategy_context.group_targets:
        if target.exposure_group_id == group_id:
            return target.target_hedge_ratio
        if target.exposure_group_id is None and is_single_group:
            return target.target_hedge_ratio
    return None


@dataclass(frozen=True)
class HedgeAmountResult:
    group_exposure_krw: float | None
    target_hedge_ratio: float | None
    group_target_hedge_amount_krw: float | None
    recommended_hedge_amount_krw: float | None
    exposure_calculation_status: str


def compute_hedge_amounts(
    group: ExposureGroup,
    all_contracts: list[ContractItem],
    risk_context: RiskContextIn | None,
    strategy_context: StrategyContextIn | None,
    is_single_group: bool,
    allocation_ratio: float | None,
) -> HedgeAmountResult:
    exposure = compute_group_exposure(group, all_contracts, risk_context, is_single_group)
    target_ratio = get_target_hedge_ratio(group.group_id, strategy_context, is_single_group)

    group_target_amount = None
    if exposure.exposure_krw is not None and target_ratio is not None:
        group_target_amount = exposure.exposure_krw * target_ratio

    recommended_amount = None
    if group_target_amount is not None and allocation_ratio is not None:
        recommended_amount = max(0.0, round(group_target_amount * allocation_ratio))

    return HedgeAmountResult(
        group_exposure_krw=exposure.exposure_krw,
        target_hedge_ratio=target_ratio,
        group_target_hedge_amount_krw=group_target_amount,
        recommended_hedge_amount_krw=recommended_amount,
        exposure_calculation_status=exposure.status,
    )
