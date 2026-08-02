"""카드용 문구 생성과 텍스트 길이/개수 제한, 분할 결제·혼합 노출그룹 반영.

여기서 만드는 모든 문장은 product_master.json에 이미 있는 검증된 필드
(summary/display/key_risks/required_documents/...)를 그대로 쓰거나 짧게
자른 것뿐입니다 — 이 함수들은 새로운 사실을 생성하지 않습니다.

"자격 충족"/"가입 가능"/"승인 가능"처럼 심사가 끝난 것으로 보이는 표현은
이 API 어디에서도 생성하지 않으며, 혹시라도 섞여 들어오면 _clean()이
걸러냅니다.
"""
from __future__ import annotations

from typing import Any

from app.evidence_retriever import get_product_evidence
from app.exposure import ExposureGroup
from app.models import (
    ELIGIBILITY_LABEL,
    ContractItem,
    RecommendationCard,
    RiskContextIn,
    ScoredCandidate,
    StrategyContextIn,
)
from app.valuation import compute_hedge_amounts

_BANNED_PHRASES = (
    "Mock",
    "mock",
    "테스트상품",
    "임의 상품명",
    "승인 확정",
    "가입 가능 확정",
    "대출 실행 확정",
    "자격 충족",
    "가입 가능",
    "승인 가능",
)

_CHANNEL_LABEL = {
    "BRANCH": "영업점",
    "DEALING_DESK": "딜링데스크",
    "INTERNET_BANKING": "기업인터넷뱅킹",
    "WEB": "웹",
    "MOBILE": "모바일",
    "MOBILE_BANKING": "모바일뱅킹",
    "KB_STAR_FX": "KB Star FX",
    "KB_STAR_BANKING": "KB Star뱅킹",
    "KB_STAR_CORPORATE_BANKING": "KB Star기업뱅킹",
    "MY_DEALING_ROOM_PRO": "마이딜링룸Pro",
    "WINDOWS_PC": "PC 프로그램",
    "EDI": "전자무역(EDI)",
    "BRANCH_SETUP": "영업점 등록",
    "BRANCH_CONTACT": "영업점 문의",
    "K_SURE_ON": "K-SURE ON",
    "K_SURE_CONSULTATION": "K-SURE 상담",
}


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[: limit - 1]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(".,;: ") + "…"


def _clean(items: list[str]) -> list[str]:
    out = []
    for item in items:
        if any(p in item for p in _BANNED_PHRASES):
            continue
        out.append(item)
    return out


def _channel_labels(channels: list[str]) -> list[str]:
    return [_CHANNEL_LABEL.get(c, c) for c in channels]


_EXPOSURE_STATUS_PENDING_TEXT = {
    "MISSING_RATE": "원화 노출액 계산에 필요한 환율(baseRate) 또는 노출액(exposureKrw) 확인이 필요합니다.",
    "MISSING_EXPOSURE": "원화 노출액을 계산할 근거가 부족합니다.",
}


def _payment_schedule_summary(candidate: ScoredCandidate, contracts: list[ContractItem]) -> str | None:
    covered = candidate.covered_contract_indexes
    if len(covered) <= 1:
        return None
    covered_contracts = [contracts[i] for i in covered]
    dates = sorted({c.settlement_date.isoformat() for c in covered_contracts if c.settlement_date})
    return f"총 {len(covered)}건 결제 예정" + (f" ({', '.join(dates)})" if dates else "")


def build_card(
    rank: int,
    candidate: ScoredCandidate,
    contracts: list[ContractItem],
    risk_context: RiskContextIn | None,
    strategy_context: StrategyContextIn | None,
    is_single_group: bool,
) -> RecommendationCard:
    product: dict[str, Any] = candidate.product
    display = product.get("display") or {}
    one_line = display.get("card_summary") or product.get("summary", "")
    cautions = display.get("short_cautions") or product.get("key_risks", [])[:3]

    evidence = get_product_evidence(product)

    reasons = _clean(candidate.score_reasons)[:3]
    reasons = [_truncate(r, 70) for r in reasons]

    status = candidate.eligibility.status
    recommendation_mode = "RM_REVIEW_REQUIRED" if product["recommendation_mode"] == "RM_REVIEW_REQUIRED" else "STANDARD"

    group = ExposureGroup(
        group_id=candidate.exposure_group_id,
        trade_direction=candidate.covered_trade_direction,
        currency=candidate.covered_currency,
        contract_indexes=tuple(candidate.covered_contract_indexes),
    )
    hedge = compute_hedge_amounts(
        group, contracts, risk_context, strategy_context, is_single_group, candidate.allocation_ratio
    )
    summary = _payment_schedule_summary(candidate, contracts)

    # 금액 계산 관련 pendingCondition은 맨 앞에 둔다 — 자격 판정 관련
    # pendingConditions가 이미 4개를 채워도(예: 장외파생상품 review_requirements)
    # 잘려나가지 않도록 하기 위함이다(카드 표시 규칙상 최대 4개).
    pending: list[str] = []
    if hedge.group_exposure_krw is None and hedge.exposure_calculation_status in _EXPOSURE_STATUS_PENDING_TEXT:
        pending.append(_EXPOSURE_STATUS_PENDING_TEXT[hedge.exposure_calculation_status])
    elif hedge.group_exposure_krw is not None and hedge.target_hedge_ratio is None:
        pending.append("목표 헤지 비율(targetHedgeRatio)이 없어 목표 헤지금액을 확정할 수 없습니다.")
    pending.extend(candidate.eligibility.pending_conditions)

    return RecommendationCard(
        rank=rank,
        product_id=product["product_id"],
        product_name=product["official_name"],
        provider=product.get("provider", ""),
        category=product.get("category", ""),
        strategy_types=product.get("strategy_types", []),
        allocation_ratio=candidate.allocation_ratio,
        fit_score=candidate.fit_score,
        fit_label=f"적합도 {rank}위",
        eligibility_status=status,
        eligibility_label=ELIGIBILITY_LABEL[status],
        one_line_summary=_truncate(_clean([one_line])[0] if _clean([one_line]) else "", 100),
        recommendation_reasons=reasons,
        matched_conditions=_clean(candidate.eligibility.matched_conditions)[:4],
        pending_conditions=_clean(pending)[:4],
        cautions=_clean(cautions)[:3],
        required_documents=_clean(product.get("required_documents", []))[:5],
        application_channels=_channel_labels(product.get("channels", [])),
        source_ids=evidence["source_ids"],
        recommendation_mode=recommendation_mode,
        detail_available=True,
        covered_contract_indexes=candidate.covered_contract_indexes,
        payment_schedule_summary=summary,
        exposure_group_id=candidate.exposure_group_id,
        covered_trade_direction=candidate.covered_trade_direction,
        covered_currency=candidate.covered_currency,
        group_exposure_krw=hedge.group_exposure_krw,
        target_hedge_ratio=hedge.target_hedge_ratio,
        group_target_hedge_amount_krw=hedge.group_target_hedge_amount_krw,
        recommended_hedge_amount_krw=hedge.recommended_hedge_amount_krw,
        exposure_calculation_status=hedge.exposure_calculation_status,
    )


def build_excluded(candidate: ScoredCandidate) -> dict[str, Any]:
    product = candidate.product
    status = candidate.eligibility.status
    reasons = candidate.eligibility.block_reasons or candidate.eligibility.pending_conditions
    return {
        "product_id": product["product_id"],
        "product_name": product["official_name"],
        "eligibility_status": status,
        "eligibility_label": ELIGIBILITY_LABEL[status],
        "reasons": _clean(reasons)[:5],
        "exposure_group_id": candidate.exposure_group_id,
        "covered_trade_direction": candidate.covered_trade_direction,
        "covered_currency": candidate.covered_currency,
    }
