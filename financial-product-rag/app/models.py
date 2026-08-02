from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """Base for all external request/response models: internal fields stay
    snake_case, JSON in/out is camelCase (frontend/dongkk-server convention).

    extra="forbid": 아직 외부 연동 전이라, 정의되지 않은 요청 필드(예:
    제거된 companySize/kSureEligible)를 조용히 무시하지 않고 422로
    거부한다 — 호출 측이 "무시됐는지 반영됐는지" 헷갈릴 여지를 없앤다."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TradeDirection(str, Enum):
    EXPORT = "EXPORT"
    IMPORT = "IMPORT"
    BOTH = "BOTH"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class PaymentMethod(str, Enum):
    TT = "T/T"
    LC = "L/C"
    DP = "D/P"
    DA = "D/A"


class StrategyType(str, Enum):
    FORWARD = "FORWARD"
    MAR = "MAR"
    FX_OPTION = "FX_OPTION"
    RANGE_FORWARD = "RANGE_FORWARD"
    ENHANCED_FORWARD = "ENHANCED_FORWARD"
    PARTICIPATING_FORWARD = "PARTICIPATING_FORWARD"
    SEAGULL_FORWARD = "SEAGULL_FORWARD"
    FX_SWAP = "FX_SWAP"
    FX_INSURANCE_GENERAL = "FX_INSURANCE_GENERAL"
    FX_INSURANCE_OPTION = "FX_INSURANCE_OPTION"
    FOREIGN_CURRENCY_DEPOSIT = "FOREIGN_CURRENCY_DEPOSIT"
    IMPORT_PAYMENT_DEFERRAL = "IMPORT_PAYMENT_DEFERRAL"
    EXPORT_RECEIVABLE_FINANCE = "EXPORT_RECEIVABLE_FINANCE"
    EXPORT_WORKING_CAPITAL = "EXPORT_WORKING_CAPITAL"
    INTERNAL_MATCHING_NETTING = "INTERNAL_MATCHING_NETTING"


class EligibilityStatus(str, Enum):
    """추천 API는 가입 자격을 최종 판정하지 않는다 — 이 상태는 어디까지나
    "현재 보유한 정보로 판단한 추천 적합도"이지 심사 결과가 아니다."""

    RECOMMENDED = "RECOMMENDED"
    CONDITIONAL = "CONDITIONAL"
    RM_REVIEW_REQUIRED = "RM_REVIEW_REQUIRED"
    NOT_RECOMMENDED = "NOT_RECOMMENDED"


ELIGIBILITY_LABEL: dict[EligibilityStatus, str] = {
    EligibilityStatus.RECOMMENDED: "추천 적합",
    EligibilityStatus.CONDITIONAL: "조건 확인 필요",
    EligibilityStatus.RM_REVIEW_REQUIRED: "직원 확인 필요",
    EligibilityStatus.NOT_RECOMMENDED: "추천 제외",
}


# ---------------------------------------------------------------------------
# POST /recommend — request
#
# 아래 필드만 요청에 담을 수 있다: 실제 서비스가 추천 시점에 확정적으로
# 보유한 정보뿐이다. companySize/hasExportPerformance/kSureEligible/
# hasForeignCurrencySurplus/importItemEligible/신용등급/담보·보증/거래한도/
# 투자자 적합성 심사결과/K-SURE 실제 인수 가능 여부는 이 서비스가 갖고
# 있지 않으므로 요청 모델에 아예 없다 — 그래서 그 값이 없다는 이유로
# NOT_RECOMMENDED가 될 수 없다(애초에 판정에 쓸 필드가 존재하지 않는다).
# ---------------------------------------------------------------------------


class CompanyProfileIn(CamelModel):
    trade_direction: TradeDirection
    industry: str | None = None
    main_countries: list[str] = Field(default_factory=list)
    currencies: list[str] = Field(default_factory=list)
    monthly_trade_volume_krw: float | None = Field(default=None, ge=0)
    payment_terms: list[PaymentMethod] = Field(default_factory=list)
    currently_hedging: bool | None = None


class ContractItem(CamelModel):
    trade_direction: TradeDirection
    foreign_amount: float = Field(ge=0)
    currency: str = Field(min_length=3, max_length=3)
    settlement_date: date | None = None
    installment_order: int | None = Field(default=None, ge=1)
    # 이 계약 하나만의 원화 환산 정보(선택). 노출액 계산 우선순위는
    # app/valuation.py 참고 — riskContext.baseRate를 여러 통화에 공통
    # 적용하지 않기 위해 계약 단위로 받는다.
    base_rate: float | None = Field(default=None, ge=0)
    exposure_krw: float | None = Field(default=None, ge=0)


class RiskContextIn(CamelModel):
    exposure_krw: float | None = Field(default=None, ge=0)
    # deprecated(v2.3부터): 여러 통화쌍에 환율 하나를 공통 적용하는 문제를
    #없애기 위해 원화 노출액 계산에서 완전히 제외했다(app/valuation.py는
    # 이 필드를 절대 읽지 않는다 — contracts[].baseRate/exposureKrw만
    # 쓴다). 하위 호환을 위해 필드 자체와 값 전달은 계속 허용하지만,
    # 계산에는 관여하지 않는 참고용 값으로만 취급해야 한다.
    base_rate: float | None = Field(default=None, ge=0, deprecated=True)
    break_even_rate: float | None = Field(default=None, ge=0)
    remaining_days: int | None = Field(default=None, ge=0)
    remaining_business_days: int | None = Field(default=None, ge=0)
    expected_loss_rate: float | None = None
    expected_shortfall_krw: float | None = None
    risk_level: RiskLevel | None = None
    # "보수적/중립적/공격적" 또는 기존 시스템의 자유 문자열 값을 모두 받는다
    # (정확한 enum이 명세에 주어지지 않아 열어둠). 키워드 인식은
    # scoring_config.py 참고.
    risk_preference: str | None = None


class StrategyItemIn(CamelModel):
    strategy_type: StrategyType
    allocation_ratio: float = Field(ge=0, le=1)
    priority: int | None = Field(default=None, ge=1)
    # 이 전략이 어느 노출 그룹(방향×통화)에 적용되는지. 노출 그룹이
    # 하나뿐인 요청에서는 생략을 허용하고 그 그룹으로 자동 연결한다.
    # 그룹이 여러 개인데 생략하면 임의로 배정하지 않고(어느 그룹인지 알 수
    # 없으므로) 이 전략은 후보 생성에서 제외되며 notices에 안내된다.
    exposure_group_id: str | None = None


class GroupHedgeTarget(CamelModel):
    """노출 그룹별 목표 헤지 비율. 노출 그룹이 하나뿐이면 exposureGroupId를
    생략할 수 있다(자동 연결)."""

    exposure_group_id: str | None = None
    target_hedge_ratio: float = Field(ge=0, le=1)


class StrategyContextIn(CamelModel):
    # hedgeTargetMin/Max는 "이 allocationRatio가 합리적인 범위인가"를
    # 점수(fitScore)에 반영하는 데만 쓰인다. 실제 헤지금액 계산에는 아래
    # groupTargets(targetHedgeRatio)만 쓰인다 — 두 개념을 섞지 않는다.
    hedge_target_min: float | None = Field(default=None, ge=0, le=1)
    hedge_target_max: float | None = Field(default=None, ge=0, le=1)
    group_targets: list[GroupHedgeTarget] = Field(default_factory=list)
    strategies: list[StrategyItemIn] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_hedge_target_range(self) -> "StrategyContextIn":
        if self.hedge_target_min is not None and self.hedge_target_max is not None:
            if self.hedge_target_min > self.hedge_target_max:
                raise ValueError("hedgeTargetMin must not be greater than hedgeTargetMax")
        return self


class OptionsIn(CamelModel):
    max_cards: int = Field(default=3, ge=1, le=10)
    include_conditional: bool = True
    include_evidence_map: bool = True


class RecommendRequest(CamelModel):
    company_profile: CompanyProfileIn
    contracts: list[ContractItem] = Field(min_length=1)
    risk_context: RiskContextIn | None = None
    strategy_context: StrategyContextIn | None = None
    options: OptionsIn = Field(default_factory=OptionsIn)
    requested_product_names: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_currency_consistency(self) -> "RecommendRequest":
        allowed = self.company_profile.currencies
        if allowed:
            bad = [c.currency for c in self.contracts if c.currency not in allowed]
            if bad:
                raise ValueError(
                    f"contract currencies {bad} are not in companyProfile.currencies ({allowed})"
                )
        return self

    @model_validator(mode="after")
    def _check_allocation_ratio_by_exposure_group(self) -> "RecommendRequest":
        """allocationRatio 합계는 요청 전체가 아니라 노출 그룹(방향×통화)
        별로 검증한다 — 서로 다른 그룹은 각각 최대 1.0까지 배분할 수 있다.
        exposureGroupId를 명시하지 않은 전략은, 노출 그룹이 하나뿐일 때만
        그 그룹으로 자동 연결해 합산하고, 그룹이 여러 개면 어느 그룹인지
        알 수 없으므로 이 합계 검증에서 제외한다(추천 파이프라인에서도
        같은 기준으로 제외되고 notices로 안내된다 — app/exposure.py 참고)."""
        if not self.strategy_context or not self.strategy_context.strategies:
            return self

        group_ids = {(c.trade_direction.value, c.currency) for c in self.contracts}
        single_group_id = None
        if len(group_ids) == 1:
            direction, currency = next(iter(group_ids))
            single_group_id = f"{direction}-{currency}"

        totals: dict[str, float] = {}
        for item in self.strategy_context.strategies:
            gid = item.exposure_group_id or single_group_id
            if gid is None:
                continue
            totals[gid] = totals.get(gid, 0.0) + item.allocation_ratio

        over = {gid: t for gid, t in totals.items() if t > 1.0 + 1e-6}
        if over:
            detail = ", ".join(f"{gid}={t:.3f}" for gid, t in over.items())
            raise ValueError(f"allocationRatio sum exceeds 1.0 within exposure group(s): {detail}")
        return self


# ---------------------------------------------------------------------------
# POST /recommend — response
# ---------------------------------------------------------------------------


class RecommendationCard(CamelModel):
    rank: int
    product_id: str
    product_name: str
    provider: str
    category: str
    strategy_types: list[str]
    allocation_ratio: float | None = None
    fit_score: int = Field(ge=0, le=100)
    fit_label: str
    eligibility_status: EligibilityStatus
    eligibility_label: str
    one_line_summary: str
    recommendation_reasons: list[str]
    matched_conditions: list[str]
    pending_conditions: list[str]
    cautions: list[str]
    required_documents: list[str]
    application_channels: list[str]
    source_ids: list[str]
    recommendation_mode: str
    detail_available: bool = True
    # 분할 결제(복수 contracts) 지원 — 단일 결제 가정 금지.
    covered_contract_indexes: list[int] | None = None
    payment_schedule_summary: str | None = None
    # 수출입 겸업 혼합 계약 지원 — 이 카드가 어느 노출 그룹(방향×통화)을
    # 커버하는지 명시한다. 서로 다른 그룹의 계약금액이 섞이지 않는다.
    exposure_group_id: str | None = None
    covered_trade_direction: str | None = None
    covered_currency: str | None = None
    # 다중 통화 원화환산 + 노출 그룹별 헤지금액. 계산식:
    #   groupTargetHedgeAmountKrw = groupExposureKrw × targetHedgeRatio
    #   recommendedHedgeAmountKrw = groupTargetHedgeAmountKrw × allocationRatio
    # 근거가 부족한 단계가 있으면 그 이후 값은 추측하지 않고 null이다.
    group_exposure_krw: float | None = None
    target_hedge_ratio: float | None = None
    group_target_hedge_amount_krw: float | None = None
    recommended_hedge_amount_krw: float | None = None
    exposure_calculation_status: str


class ExcludedProduct(CamelModel):
    product_id: str
    product_name: str
    eligibility_status: EligibilityStatus
    eligibility_label: str
    reasons: list[str]
    exposure_group_id: str | None = None
    covered_trade_direction: str | None = None
    covered_currency: str | None = None


class EvidenceMapEntry(CamelModel):
    title: str
    provider: str | None = None
    source_type: str
    checked_at: str


class VerificationNotice(CamelModel):
    requested_name: str
    status: str
    canonical_name: str | None = None
    message: str
    action: str


class RecommendResponse(CamelModel):
    request_id: str
    generated_at: datetime
    recommendation_version: str = "2.4"
    cards: list[RecommendationCard]
    excluded_products: list[ExcludedProduct] = Field(default_factory=list)
    evidence_map: dict[str, EvidenceMapEntry] = Field(default_factory=dict)
    verification_notices: list[VerificationNotice] = Field(default_factory=list)
    notices: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# /search (operator/debug tool — not used by the product card pipeline)
# ---------------------------------------------------------------------------


class SearchRequest(CamelModel):
    query: str = Field(min_length=2)
    top_k: int = Field(default=5, ge=1, le=20)


class SearchHit(CamelModel):
    document_id: str
    document_type: str
    title: str
    provider: str | None = None
    score: float
    category: str
    summary: str
    source_ids: list[str]


# ---------------------------------------------------------------------------
# /sources/{source_id}
# ---------------------------------------------------------------------------


class SourceInfo(CamelModel):
    source_id: str
    title: str
    provider: str | None = None
    source_type: str
    url: str
    checked_at: str
    scope: str


# ---------------------------------------------------------------------------
# /products/{product_id}, /products/{product_id}/evidence
# ---------------------------------------------------------------------------


class ProductDetail(CamelModel):
    product_id: str
    official_name: str
    provider: str
    category: str
    product_type: str
    strategy_types: list[str]
    recommendation_mode: str
    verification_status: str
    target_customer: str
    currencies: list[str]
    term: str
    application_channels: list[str]
    required_documents: list[str]
    process_controls: list[str]
    settlement_rules: list[str]
    key_risks: list[str]
    source_ids: list[str]


class RelatedGuide(CamelModel):
    document_id: str
    title: str
    summary: str
    source_ids: list[str]


class ProductEvidence(CamelModel):
    product_id: str
    official_name: str
    evidence: str
    source_ids: list[str]
    sources: list[SourceInfo]
    related_guides: list[RelatedGuide]


# ---------------------------------------------------------------------------
# Internal (non-API) working types shared between pipeline stages
# ---------------------------------------------------------------------------


class EligibilityResult(BaseModel):
    """Internal pipeline value — not serialized directly to the API."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    status: EligibilityStatus
    matched_conditions: list[str] = Field(default_factory=list)
    pending_conditions: list[str] = Field(default_factory=list)
    block_reasons: list[str] = Field(default_factory=list)


class ScoredCandidate(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    product: dict[str, Any]
    strategy_type_matched: str | None
    allocation_ratio: float | None
    priority: int | None
    eligibility: EligibilityResult
    fit_score: int
    # (우선순위, 문장) 튜플 목록 — ReasonRank(scoring_config.py) 값과 사람이
    # 읽을 문장. card_builder._select_reasons()가 우선순위로 정렬해 상위
    # 3개만 recommendationReasons로 내보낸다.
    score_reasons: list[tuple[int, str]]
    # 수출입 겸업 혼합 계약: 이 후보가 커버하는 노출 그룹(방향×통화) 정보.
    exposure_group_id: str
    covered_trade_direction: str
    covered_currency: str
    covered_contract_indexes: list[int]
