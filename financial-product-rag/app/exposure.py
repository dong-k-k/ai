"""수출입 겸업 기업의 혼합 계약 처리.

contracts를 (tradeDirection, currency) 기준으로 그룹화한다. 각 상품 카드는
자신이 커버하는 노출 그룹 하나만 대상으로 하며, 서로 다른 방향·통화의
계약을 하나의 카드·헤지금액 계산에 뒤섞지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.models import ContractItem, StrategyItemIn

if TYPE_CHECKING:
    from app.models import RecommendRequest


@dataclass(frozen=True)
class ExposureGroup:
    group_id: str
    trade_direction: str
    currency: str
    contract_indexes: tuple[int, ...]

    def contracts(self, all_contracts: list[ContractItem]) -> list[ContractItem]:
        return [all_contracts[i] for i in self.contract_indexes]


def build_exposure_groups(contracts: list[ContractItem]) -> list[ExposureGroup]:
    buckets: dict[tuple[str, str], list[int]] = {}
    for i, c in enumerate(contracts):
        key = (c.trade_direction.value, c.currency)
        buckets.setdefault(key, []).append(i)
    groups = [
        ExposureGroup(
            group_id=f"{direction}-{currency}",
            trade_direction=direction,
            currency=currency,
            contract_indexes=tuple(idxs),
        )
        for (direction, currency), idxs in buckets.items()
    ]
    return sorted(groups, key=lambda g: g.group_id)


def resolve_strategy_group_id(item: StrategyItemIn, groups: list[ExposureGroup]) -> str | None:
    """전략이 적용될 노출 그룹을 정한다. 명시된 exposureGroupId가 있으면
    그대로 쓴다(존재하지 않는 그룹 id를 가리켜도 여기서는 그대로 반환하고,
    실제로 어떤 그룹과도 매칭되지 않으면 자연히 후보가 생기지 않는다).
    노출 그룹이 하나뿐이면 생략을 자동으로 그 그룹에 연결한다. 그룹이
    여러 개인데 생략됐으면 어느 그룹인지 알 수 없으므로 None(미배정)을
    반환한다 — 절대 임의로 그룹을 골라주지 않는다."""
    if item.exposure_group_id is not None:
        return item.exposure_group_id
    if len(groups) == 1:
        return groups[0].group_id
    return None


def split_strategies_by_group(
    strategies: list[StrategyItemIn], groups: list[ExposureGroup]
) -> tuple[dict[str, list[StrategyItemIn]], list[StrategyItemIn]]:
    """전략 목록을 그룹별로 나눈다. 반환값: (group_id -> 그 그룹에 배정된
    전략 목록, 어느 그룹에도 배정하지 못한 전략 목록).

    이 함수에 도달하는 시점에는 app.exposure.validate_exposure_group_references가
    이미 잘못되거나 누락된 exposureGroupId를 422로 걸러냈어야 하므로,
    정상적인 흐름에서는 반환되는 unresolved 목록이 항상 비어 있다 — 그래도
    이 함수 자체는 방어적으로 계속 두 값을 반환한다(내부 재사용·테스트
    용도)."""
    by_group: dict[str, list[StrategyItemIn]] = {g.group_id: [] for g in groups}
    unresolved: list[StrategyItemIn] = []
    for item in strategies:
        gid = resolve_strategy_group_id(item, groups)
        if gid is not None and gid in by_group:
            by_group[gid].append(item)
        else:
            unresolved.append(item)
    return by_group, unresolved


class UnknownExposureGroupError(ValueError):
    """strategies[]/groupTargets[]가 contracts에서 만들어지지 않는
    exposureGroupId를 가리킬 때."""

    def __init__(self, field: str, index: int, exposure_group_id: str, available: list[str]):
        self.field = field  # "strategies" | "groupTargets"
        self.index = index
        self.exposure_group_id = exposure_group_id
        self.available = available
        super().__init__(
            f"Unknown exposureGroupId '{exposure_group_id}' at strategyContext.{field}[{index}]. "
            f"Available: {available}"
        )


class MissingExposureGroupError(ValueError):
    """노출 그룹이 여러 개인데 strategies[]/groupTargets[] 항목이
    exposureGroupId를 지정하지 않았을 때 — 이 API는 이미 확정된 전략
    결과를 받는 API이므로 어느 그룹인지 임의로 추측하지 않고 명시적으로
    거부한다."""

    def __init__(self, field: str, index: int, available: list[str]):
        self.field = field
        self.index = index
        self.available = available
        super().__init__(
            f"exposureGroupId is required at strategyContext.{field}[{index}] because "
            f"multiple exposure groups exist. Available: {available}"
        )


def validate_exposure_group_references(request: "RecommendRequest") -> None:
    """contracts로 만들어지는 노출 그룹 id 목록과, strategyContext의
    strategies[]/groupTargets[]가 가리키는 exposureGroupId를 대조한다.

    - 존재하지 않는 id를 가리키면 UnknownExposureGroupError.
    - 노출 그룹이 여러 개인데 id를 생략했으면 MissingExposureGroupError.
    - 노출 그룹이 하나뿐이면 생략을 계속 허용한다(자동 연결).

    POST /recommend 핸들러가 이 함수를 호출해 구조화된 422로 변환한다."""
    if request.strategy_context is None:
        return

    groups = build_exposure_groups(request.contracts)
    available = [g.group_id for g in groups]
    available_set = set(available)
    is_single = len(groups) <= 1

    for idx, item in enumerate(request.strategy_context.strategies):
        gid = item.exposure_group_id
        if gid is None:
            if not is_single:
                raise MissingExposureGroupError("strategies", idx, available)
            continue
        if gid not in available_set:
            raise UnknownExposureGroupError("strategies", idx, gid, available)

    for idx, target in enumerate(request.strategy_context.group_targets):
        gid = target.exposure_group_id
        if gid is None:
            if not is_single:
                raise MissingExposureGroupError("groupTargets", idx, available)
            continue
        if gid not in available_set:
            raise UnknownExposureGroupError("groupTargets", idx, gid, available)
