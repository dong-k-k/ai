"""하드 조건 판정 및 자격 상태(enum) 결정 — 노출 그룹(방향×통화) 단위.

이 API는 가입 자격을 최종 판정하지 않는다. 두 종류의 "확인이 필요한 항목"을
구분한다:

- observable: contracts/companyProfile/riskContext에서 실제로 관찰 가능한
  사실(통화, 결제조건, 기간 등). 값이 있고 명백히 불충족이면 NOT_RECOMMENDED,
  판단할 자료 자체가 없으면 절대 하드 차단하지 않고 CONDITIONAL로 유보한다.
- review_requirements: 장외파생상품 거래처럼 어떤 입력이 주어지든 항상
  직원 확인이 필요한 절차상 단계 — 존재 자체가 RM_REVIEW_REQUIRED를
  강제한다.
- unknown_eligibility_notes: 이 서비스가 애초에 갖고 있지 않은 사실
  (K-SURE 프로그램 대상 여부, 신용심사, 외화 여유자금 등). 있으면
  pendingConditions에 표시하고 CONDITIONAL로 유보하지만, 그 자체로
  RM_REVIEW_REQUIRED를 강제하지는 않는다(상품 recommendation_mode가 이미
  RM_REVIEW_REQUIRED면 그 기준이 우선한다).

수출입 겸업 기업의 혼합 계약을 지원하기 위해, 방향·통화·기간 판정은
전체 contracts가 아니라 하나의 노출 그룹(ExposureGroup)에 스코핑된
contracts만 본다 — 그래야 "USD 수출 30일"과 "JPY 수입 200일"이 서로의
판정에 섞이지 않는다.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.models import CompanyProfileIn, ContractItem, EligibilityResult, EligibilityStatus, RiskContextIn


def derive_remaining_days(
    contracts: list[ContractItem],
    risk_context: RiskContextIn | None,
    *,
    prefer_risk_context: bool = True,
) -> int | None:
    """결제까지 남은 기간을 계산한다.

    - 노출 그룹이 하나뿐인 요청(prefer_risk_context=True, 기본값)에서는
      riskContext.remainingDays(이미 계산된 값, 영업일 보정 등을 반영했을
      수 있음)를 우선 쓰고, 없으면 계약 결제예정일로 역산한다.
    - 노출 그룹이 여러 개인 요청(prefer_risk_context=False)에서는 하나의
      공유 riskContext 값을 서로 다른 그룹에 그대로 적용하면 부정확하므로,
      그 그룹 자신의 계약 결제예정일을 우선 쓰고, 그룹에 날짜 정보가 아예
      없을 때만 riskContext로 보완한다.
    """
    if prefer_risk_context and risk_context is not None and risk_context.remaining_days is not None:
        return risk_context.remaining_days

    dated = [c.settlement_date for c in contracts if c.settlement_date is not None]
    if dated:
        nearest = min(dated)
        return max(0, (nearest - date.today()).days)

    if risk_context is not None and risk_context.remaining_days is not None:
        return risk_context.remaining_days
    return None


def _hedge_horizon_months(remaining_days: int | None) -> float | None:
    if remaining_days is None:
        return None
    return remaining_days / 30.0


def evaluate(
    product: dict[str, Any],
    company_profile: CompanyProfileIn,
    group_trade_direction: str,
    group_currency: str,
    remaining_days: int | None,
) -> EligibilityResult:
    matched: list[str] = []
    pending: list[str] = []
    blocked: list[str] = []

    rules: dict[str, Any] = product.get("eligibility_rules") or {}
    observable: dict[str, Any] = rules.get("observable", {})
    review_requirements: list[str] = rules.get("review_requirements", [])
    unknown_notes: list[str] = rules.get("unknown_eligibility_notes", [])

    if observable.get("product_discontinued"):
        blocked.append("판매가 종료된 상품입니다.")

    # 거래 방향 — 이 노출 그룹의 방향 기준으로 판정한다.
    supported = set(product.get("trade_directions", []))
    if group_trade_direction in supported or "BOTH" in supported:
        matched.append("거래 방향 조건을 충족합니다.")
    else:
        blocked.append(f"이 상품은 {group_trade_direction} 거래 방향을 지원하지 않습니다.")

    # 결제까지 기간 (min/max days) — 관찰 가능한 값이 없으면 CONDITIONAL로 유보
    min_days, max_days = observable.get("min_days"), observable.get("max_days")
    if min_days is not None or max_days is not None:
        if remaining_days is None:
            pending.append("결제까지 남은 기간 확인이 필요합니다.")
        else:
            if min_days is not None and remaining_days < min_days:
                blocked.append(f"결제까지 최소 {min_days}일 이상 남아 있어야 합니다.")
            elif max_days is not None and remaining_days > max_days:
                blocked.append(f"결제까지 {max_days}일 이내여야 합니다.")
            else:
                matched.append("결제 예정일까지의 기간 조건을 충족합니다.")

    # 헤지 기간 (월, K-SURE 옵션형 등)
    min_h, max_h = observable.get("min_hedge_horizon_months"), observable.get("max_hedge_horizon_months")
    if min_h is not None or max_h is not None:
        horizon = _hedge_horizon_months(remaining_days)
        if horizon is None:
            pending.append("헤지 예상 기간 확인이 필요합니다.")
        else:
            if min_h is not None and horizon < min_h:
                blocked.append(f"헤지 기간이 최소 {min_h}개월 이상이어야 합니다.")
            elif max_h is not None and horizon > max_h:
                blocked.append(f"헤지 기간이 최장 {max_h}개월 이내여야 합니다.")
            else:
                matched.append("입력한 헤지 기간이 상품 기간 조건에 포함됩니다.")

    # 대상 통화 — 이 노출 그룹의 통화(단일값) 기준으로 판정한다.
    allowed_currencies = observable.get("allowed_currencies")
    if allowed_currencies:
        if group_currency not in allowed_currencies:
            blocked.append(f"대상 통화가 아닙니다 (지원 통화: {', '.join(allowed_currencies)}).")
        else:
            matched.append(f"{group_currency} 대상 통화 조건을 충족합니다.")

    # 결제 방식 — companyProfile.paymentTerms(리스트)와 상품 허용 목록 대조
    allowed_terms = observable.get("allowed_payment_terms")
    if allowed_terms:
        if not company_profile.payment_terms:
            pending.append("결제 방식 확인이 필요합니다.")
        else:
            requested_terms = {t.value for t in company_profile.payment_terms}
            if requested_terms & set(allowed_terms):
                matched.append("결제 방식 조건을 충족합니다.")
            else:
                blocked.append(f"지원하는 결제 방식이 아닙니다 (지원: {', '.join(allowed_terms)}).")

    # 절차상 항상 필요한 직원 확인 항목 (장외파생상품 등)
    requires_rm = product["recommendation_mode"] == "RM_REVIEW_REQUIRED"
    for item in review_requirements:
        pending.append(item)
        requires_rm = True

    # 이 서비스가 갖고 있지 않은 사실 — 있으면 CONDITIONAL로만 유보, 하드 차단 금지
    for item in unknown_notes:
        pending.append(item)

    if blocked:
        return EligibilityResult(status=EligibilityStatus.NOT_RECOMMENDED, block_reasons=blocked)

    if requires_rm:
        status = EligibilityStatus.RM_REVIEW_REQUIRED
    elif pending:
        status = EligibilityStatus.CONDITIONAL
    else:
        status = EligibilityStatus.RECOMMENDED

    return EligibilityResult(status=status, matched_conditions=matched, pending_conditions=pending)
