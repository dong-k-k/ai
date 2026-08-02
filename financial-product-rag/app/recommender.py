"""적합도 점수 계산 및 전략-상품 매칭/순위 — 노출 그룹(방향×통화) 단위.

TF-IDF나 LLM 검색 점수는 절대 fitScore에 반영하지 않습니다 — 여기서 쓰는
입력은 오직 구조화된 요청 필드(companyProfile/contracts/riskContext/
strategyContext)와 product_master.json/recommendation_rules.json뿐입니다.

fitScore는 "가입 자격 점수"가 아니라 "현재 전략·거래 조건과 상품의 적합도"
점수다 — companySize/kSureEligible처럼 이 서비스가 갖고 있지 않은 값은
어떤 가중치에도 관여하지 않는다(eligibility.py의 pendingConditions로만
표현됨).

수출입 겸업 기업의 혼합 계약(예: USD 수출 + JPY 수입)을 지원하기 위해
contracts를 (tradeDirection, currency) 기준 노출 그룹으로 나눈 뒤, 그룹마다
독립적으로 후보를 만든다 — 같은 상품이 여러 그룹에 각각 적합할 수 있으며,
그 경우 그룹별로 별도 카드 후보가 생긴다(하나로 합쳐서 방향·통화를
뒤섞지 않는다).
"""
from __future__ import annotations

from typing import Any

from app.eligibility import derive_remaining_days, evaluate
from app.exposure import ExposureGroup, build_exposure_groups, split_strategies_by_group
from app.models import (
    CompanyProfileIn,
    ContractItem,
    EligibilityStatus,
    RecommendRequest,
    RiskContextIn,
    ScoredCandidate,
    StrategyContextIn,
)
from app.scoring_config import (
    CERTAINTY_PREFERENCE_KEYWORDS,
    CERTAINTY_STRATEGY_TYPES,
    DIFFICULTY_PENALTY,
    DIFFICULTY_PENALTY_PRODUCT_TYPE_KEYWORDS,
    RATE_LOCKING_STRATEGY_TYPES,
    RECOMMENDATION_MODE_ADJUSTMENT,
    RISK_LEVEL_MULTIPLIER,
    UPSIDE_PREFERENCE_KEYWORDS,
    UPSIDE_STRATEGY_TYPES,
    WEIGHTS,
)
from app.store import products, score_rules
from app.verification import is_candidate_verified


def _strategy_type_rule_map() -> dict[str, set[str]]:
    """product_id -> set of strategyType values it has a SCORE rule for."""
    out: dict[str, set[str]] = {}
    for r in score_rules():
        if r["rule_type"] != "SCORE" or r["field"] != "strategy_types" or r["operator"] != "contains":
            continue
        out.setdefault(r["product_id"], set()).add(r["value"])
    return out


def _risk_preference_score(product: dict[str, Any], risk_context: RiskContextIn | None) -> tuple[int, str | None]:
    if risk_context is None or not risk_context.risk_preference:
        return 0, None
    pref = risk_context.risk_preference.upper()
    strategy_types = set(product.get("strategy_types", []))
    if any(k in pref for k in UPSIDE_PREFERENCE_KEYWORDS) and strategy_types & UPSIDE_STRATEGY_TYPES:
        return WEIGHTS["risk_preference_match"], "환율 상승 이익을 유지하려는 선호와 부합합니다."
    if any(k in pref for k in CERTAINTY_PREFERENCE_KEYWORDS) and strategy_types & CERTAINTY_STRATEGY_TYPES:
        return WEIGHTS["risk_preference_match"], "환율을 확정하려는 선호와 부합합니다."
    return 0, None


def _hedge_target_range_score(
    strategy_context: StrategyContextIn | None, allocation_ratio: float | None
) -> tuple[int, str | None]:
    if strategy_context is None or allocation_ratio is None:
        return 0, None
    lo, hi = strategy_context.hedge_target_min, strategy_context.hedge_target_max
    if lo is None or hi is None:
        return 0, None
    if lo <= allocation_ratio <= hi:
        return WEIGHTS["hedge_target_range_match"], "배분 비율이 입력한 헤지 목표 범위 안에 있습니다."
    return 0, None


def _term_match_score(product: dict[str, Any], remaining_days: int | None) -> tuple[int, str | None]:
    rules = product.get("eligibility_rules") or {}
    observable = rules.get("observable", {})
    has_bound = any(
        k in observable for k in ("min_days", "max_days", "min_hedge_horizon_months", "max_hedge_horizon_months")
    )
    if not has_bound or remaining_days is None:
        return 0, None
    return WEIGHTS["term_match"], "결제 예정 기간이 상품의 기간 조건과 맞습니다."


def _risk_level_score(product: dict[str, Any], risk_context: RiskContextIn | None) -> tuple[int, str | None]:
    if risk_context is None or risk_context.risk_level is None:
        return 0, None
    if not set(product.get("strategy_types", [])) & RATE_LOCKING_STRATEGY_TYPES:
        return 0, None
    mult = RISK_LEVEL_MULTIPLIER.get(risk_context.risk_level.value, 0)
    score = round(WEIGHTS["risk_level_rate_lock_match"] * mult)
    if score <= 0:
        return 0, None
    return score, f"위험등급({risk_context.risk_level.value})에서 환율을 고정·확정하는 효과와 부합합니다."


def _currently_hedging_score(company_profile: CompanyProfileIn) -> tuple[int, str | None]:
    if company_profile.currently_hedging is False:
        return WEIGHTS["not_currently_hedging_bonus"], "현재 환리스크를 관리하고 있지 않아 헤지 상품 도입 필요성이 있습니다."
    return 0, None


def _build_candidates_for_group(
    request: RecommendRequest,
    group: ExposureGroup,
    group_strategies: list[Any],
    forced_product_ids: set[str],
    rule_map: dict[str, set[str]],
    prefer_risk_context_for_days: bool,
) -> list[ScoredCandidate]:
    # 이 그룹에 배정된 전략만 후보 대상이다 — exposureGroupId가 다른
    # 그룹을 가리키거나(app.exposure.split_strategies_by_group에서 이미
    # 걸러짐) 미배정(그룹이 여럿인데 생략)인 전략은 여기 들어오지 않는다.
    requested_by_type: dict[str, Any] = {}
    for item in group_strategies:
        requested_by_type.setdefault(item.strategy_type.value, item)

    group_contracts = group.contracts(request.contracts)
    remaining_days = derive_remaining_days(
        group_contracts, request.risk_context, prefer_risk_context=prefer_risk_context_for_days
    )

    candidates: list[ScoredCandidate] = []

    for product in products():
        if not is_candidate_verified(product):
            continue
        product_strategy_types = set(product.get("strategy_types", []))
        rule_types = rule_map.get(product["product_id"], set())
        matched_types = product_strategy_types & rule_types & set(requested_by_type.keys())

        is_forced = product["product_id"] in forced_product_ids
        if not matched_types and not is_forced:
            continue

        strategy_item = None
        matched_type: str | None = None
        if matched_types:
            matched_type = sorted(matched_types)[0]
            strategy_item = requested_by_type[matched_type]
        allocation_ratio = strategy_item.allocation_ratio if strategy_item else None
        priority = strategy_item.priority if strategy_item else None

        eligibility = evaluate(
            product,
            request.company_profile,
            group.trade_direction,
            group.currency,
            remaining_days,
        )
        if eligibility.status == EligibilityStatus.NOT_RECOMMENDED:
            candidates.append(
                ScoredCandidate(
                    product=product,
                    strategy_type_matched=matched_type,
                    allocation_ratio=allocation_ratio,
                    priority=priority,
                    eligibility=eligibility,
                    fit_score=0,
                    score_reasons=[],
                    exposure_group_id=group.group_id,
                    covered_trade_direction=group.trade_direction,
                    covered_currency=group.currency,
                    covered_contract_indexes=list(group.contract_indexes),
                )
            )
            continue

        score = 0
        reasons: list[str] = []

        if matched_type:
            score += WEIGHTS["strategy_type_match"]
            reasons.append(f"선택한 전략 유형({matched_type})과 상품이 직접 일치합니다.")

        if priority is not None:
            bonus = max(0, WEIGHTS["strategy_priority_bonus"] - (priority - 1) * 3)
            if bonus:
                score += bonus
                reasons.append(f"우선순위 {priority}로 지정한 전략입니다.")

        score += WEIGHTS["trade_direction_match"]
        reasons.append(f"{group.trade_direction} 거래 방향과 일치합니다.")

        product_currencies = product.get("currencies", [])
        if "MULTI" in product_currencies or group.currency in product_currencies:
            score += WEIGHTS["currency_match"]
            reasons.append(f"{group.currency} 통화 조건과 일치합니다.")

        rules = product.get("eligibility_rules") or {}
        observable = rules.get("observable", {})
        allowed_terms = observable.get("allowed_payment_terms")
        if allowed_terms and request.company_profile.payment_terms:
            requested_terms = {t.value for t in request.company_profile.payment_terms}
            if requested_terms & set(allowed_terms):
                score += WEIGHTS["payment_terms_match"]
                reasons.append("결제 방식 조건과 일치합니다.")

        term_score, term_reason = _term_match_score(product, remaining_days)
        score += term_score
        if term_reason:
            reasons.append(term_reason)

        risk_level_score, risk_level_reason = _risk_level_score(product, request.risk_context)
        score += risk_level_score
        if risk_level_reason:
            reasons.append(risk_level_reason)

        pref_score, pref_reason = _risk_preference_score(product, request.risk_context)
        score += pref_score
        if pref_reason:
            reasons.append(pref_reason)

        range_score, range_reason = _hedge_target_range_score(request.strategy_context, allocation_ratio)
        score += range_score
        if range_reason:
            reasons.append(range_reason)

        hedging_score, hedging_reason = _currently_hedging_score(request.company_profile)
        score += hedging_score
        if hedging_reason:
            reasons.append(hedging_reason)

        if allocation_ratio is not None:
            score += round(allocation_ratio * WEIGHTS["strategy_allocation_weight"])

        score += RECOMMENDATION_MODE_ADJUSTMENT.get(product["recommendation_mode"], 0)

        if any(k in product.get("product_type", "") for k in DIFFICULTY_PENALTY_PRODUCT_TYPE_KEYWORDS):
            score -= DIFFICULTY_PENALTY

        fit_score = max(0, min(100, round(score)))

        candidates.append(
            ScoredCandidate(
                product=product,
                strategy_type_matched=matched_type,
                allocation_ratio=allocation_ratio,
                priority=priority,
                eligibility=eligibility,
                fit_score=fit_score,
                score_reasons=reasons,
                exposure_group_id=group.group_id,
                covered_trade_direction=group.trade_direction,
                covered_currency=group.currency,
                covered_contract_indexes=list(group.contract_indexes),
            )
        )

    return candidates


def build_candidates(request: RecommendRequest, forced_product_ids: set[str]) -> list[ScoredCandidate]:
    rule_map = _strategy_type_rule_map()
    groups = build_exposure_groups(request.contracts)
    # 노출 그룹이 하나뿐이면 riskContext.remainingDays를 그대로 신뢰한다
    # (기존 동작 유지). 그룹이 여러 개면 하나의 공유 값을 서로 다른
    # 그룹에 동일하게 적용할 수 없으므로 그룹별 계약 날짜를 우선한다.
    prefer_risk_context_for_days = len(groups) <= 1

    strategies = request.strategy_context.strategies if request.strategy_context else []
    by_group, _unresolved = split_strategies_by_group(strategies, groups)

    candidates: list[ScoredCandidate] = []
    for group in groups:
        candidates.extend(
            _build_candidates_for_group(
                request, group, by_group.get(group.group_id, []), forced_product_ids, rule_map, prefer_risk_context_for_days
            )
        )
    return candidates


def _priority_sort_key(priority: int | None) -> float:
    """priority=1이 최우선. None(우선순위 미지정)은 지정된 항목들보다 뒤로."""
    return priority if priority is not None else float("inf")


def rank(candidates: list[ScoredCandidate]) -> list[ScoredCandidate]:
    eligible = [c for c in candidates if c.eligibility.status != EligibilityStatus.NOT_RECOMMENDED]
    eligible.sort(
        key=lambda c: (
            _priority_sort_key(c.priority),
            -c.fit_score,
            -(c.allocation_ratio if c.allocation_ratio is not None else 0.0),
            c.product["official_name"],
        )
    )
    return eligible
