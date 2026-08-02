"""fitScore 가중치 상수. 6-4 요구사항: '점수 계산식과 각 가중치는 상수 또는
설정 파일로 분리'. recommender.py는 이 값만 참조하며 점수 계산 로직 자체를
바꾸지 않고 가중치만 조정하고 싶을 때는 이 파일만 수정하면 됩니다.

fitScore는 상품 가입 자격 점수가 아니라 "현재 전략·거래 조건과 이 상품이
얼마나 맞는가"의 적합도 점수다. companySize/kSureEligible처럼 확인할 수
없는 자격조건은 어떤 가중치에도 관여하지 않는다 — 그런 항목은
eligibility.py의 pendingConditions로만 표현된다.

합계는 100을 넘을 수 있으며 recommender.py가 최종적으로 0~100으로 clip
합니다 — strategy_type_match(직접 일치)가 가장 높은 가중치입니다.
"""
from __future__ import annotations

WEIGHTS: dict[str, int] = {
    # 1. strategyType 직접 일치
    "strategy_type_match": 40,
    # 2. 전략 priority (낮은 숫자=높은 우선순위). priority가 없으면 0.
    "strategy_priority_bonus": 8,
    # 3. allocationRatio에 비례 (여러 전략이 섞인 통합 카드 목록에서 배분
    #    비율이 큰 전략의 상품이 우선하도록 한다)
    "strategy_allocation_weight": 12,
    # 4. 수출·수입 방향 일치
    "trade_direction_match": 10,
    # 5. 계약통화 일치
    "currency_match": 10,
    # 6. 결제조건 일치 (companyProfile.paymentTerms ∩ 상품 허용 결제조건)
    "payment_terms_match": 8,
    # 7. 결제예정일까지의 기간이 상품의 기간 조건과 맞는지
    "term_match": 8,
    # 8. 위험등급(riskLevel)과 상품의 환율 고정 효과
    "risk_level_rate_lock_match": 6,
    # 9. 위험 성향(riskPreference)과 상품 구조
    "risk_preference_match": 6,
    "hedge_target_range_match": 5,
    # 10. 현재 환리스크 관리 여부(currentlyHedging=false → 미헤지 상태라
    #     헤지 상품 필요성이 더 큼)
    "not_currently_hedging_bonus": 5,
}

# recommendation_mode 자체는 소폭 조정만 한다 — "상품 신청 난이도"는 별도
# DIFFICULTY_PENALTY에서 상품 유형(장외파생상품 여부)으로 판단하므로,
# 여기서 RM_REVIEW_REQUIRED에 큰 페널티를 중복으로 주지 않는다.
RECOMMENDATION_MODE_ADJUSTMENT: dict[str, int] = {
    "AUTO_WITH_GUARDRAILS": 2,
    "SUPPLEMENTARY": 0,
    "RM_REVIEW_REQUIRED": 0,
}

# 상품 신청 난이도: 장외파생상품·구조화 상품처럼 실수요·적합성·한도 절차가
# 복잡한 상품 유형에만 페널티를 준다 — 확인 불가능한 자격조건에 대한
# 페널티가 아니라, 상품 자체의 정적인 유형 정보에 대한 페널티다.
DIFFICULTY_PENALTY_PRODUCT_TYPE_KEYWORDS = ("장외파생상품", "합성선물환")
DIFFICULTY_PENALTY = 5

# risk_preference 입력값(자유 문자열)에서 "상승 이익 유지/공격적" 성향으로
# 해석하는 키워드와 "환율 확정/보수적" 성향으로 해석하는 키워드.
# "보수적/중립적/공격적"과 기존 COST_OPPORTUNITY_FIRST류 값을 모두 인식한다.
UPSIDE_PREFERENCE_KEYWORDS = ("COST_OPPORTUNITY", "OPPORTUNITY", "UPSIDE", "AGGRESSIVE", "공격")
CERTAINTY_PREFERENCE_KEYWORDS = ("RATE_CERTAINTY", "CERTAINTY", "FIX", "CONSERVATIVE", "보수")

UPSIDE_STRATEGY_TYPES = {
    "FX_OPTION",
    "PARTICIPATING_FORWARD",
    "ENHANCED_FORWARD",
    "SEAGULL_FORWARD",
    "RANGE_FORWARD",
    "FX_INSURANCE_OPTION",
}
CERTAINTY_STRATEGY_TYPES = {"FORWARD", "MAR", "FX_INSURANCE_GENERAL"}

# 8. 위험등급-환율고정효과: riskLevel이 높을수록(HIGH) 환율을 확정/고정하는
# 상품일수록 가산점을 준다. LOW면 긴급성이 낮아 절반만 반영한다.
RATE_LOCKING_STRATEGY_TYPES = {
    "FORWARD",
    "MAR",
    "FX_INSURANCE_GENERAL",
    "RANGE_FORWARD",
    "ENHANCED_FORWARD",
}
RISK_LEVEL_MULTIPLIER = {"HIGH": 1.0, "MEDIUM": 0.6, "LOW": 0.3}
