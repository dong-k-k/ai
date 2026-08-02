"""전체 파이프라인 오케스트레이션:
검증 상태 필터 → 하드 조건 판정 → 적합도 점수 → 전략-상품 연결 →
근거 조회 → 카드 생성 → source_id 포함 응답.

LLM은 이 파이프라인 어디에도 관여하지 않으며, LLM 키가 없어도 전체 흐름이
동일하게 동작합니다.
"""
from __future__ import annotations

import random
import string
from datetime import datetime, timedelta, timezone

from app import card_builder, recommender
from app.evidence_retriever import get_product_evidence, internal_technique_notice
from app.exposure import build_exposure_groups
from app.models import (
    EligibilityStatus,
    EvidenceMapEntry,
    RecommendRequest,
    RecommendResponse,
)
from app.store import sources
from app.verification import check_requested_names

_KST = timezone(timedelta(hours=9))

_STANDARD_NOTICES = [
    "적합도는 입력된 기업 및 계약 정보를 기준으로 산정한 참고 결과입니다.",
    "실제 가입·거래 가능 여부는 각 기관의 심사와 영업점 확인 후 결정됩니다.",
]


def _new_request_id() -> str:
    ts = datetime.now(_KST).strftime("%Y%m%d")
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"rec_{ts}_{suffix}"


def generate_recommendations(request: RecommendRequest) -> RecommendResponse:
    notices: list[str] = list(_STANDARD_NOTICES)

    verification = check_requested_names(request.requested_product_names)

    # exposureGroupId 유효성(존재 여부·다중 그룹에서 누락 여부)은
    # app.main의 /recommend 핸들러가 이 함수를 호출하기 전에
    # validate_exposure_group_references()로 이미 422 처리했다 — 여기
    # 도달한 시점에는 모든 strategies[]/groupTargets[]가 유효한
    # exposureGroupId를 갖거나(명시 또는 단일 그룹 자동연결) 있다고
    # 가정한다.
    groups = build_exposure_groups(request.contracts)
    is_single_group = len(groups) <= 1
    strategies = request.strategy_context.strategies if request.strategy_context else []

    requested_strategy_types = {s.strategy_type.value for s in strategies}
    internal_notice = internal_technique_notice("INTERNAL_MATCHING_NETTING")
    if internal_notice and "INTERNAL_MATCHING_NETTING" in requested_strategy_types:
        notices.append(internal_notice["message"])

    if not requested_strategy_types:
        notices.append("strategyContext.strategies가 비어 있어 추천할 상품이 없습니다. 전략 정보를 입력해주세요.")

    candidates = recommender.build_candidates(request, forced_product_ids=verification.resolved_product_ids)
    ranked = recommender.rank(candidates)

    excluded_raw = [c for c in candidates if c.eligibility.status == EligibilityStatus.NOT_RECOMMENDED]

    if not request.options.include_conditional:
        kept = []
        for c in ranked:
            if c.eligibility.status == EligibilityStatus.CONDITIONAL:
                excluded_raw.append(c)
            else:
                kept.append(c)
        ranked = kept

    max_cards = request.options.max_cards
    top = ranked[:max_cards]
    overflow = ranked[max_cards:]

    cards = [
        card_builder.build_card(
            i + 1, c, request.contracts, request.risk_context, request.strategy_context, is_single_group
        )
        for i, c in enumerate(top)
    ]
    excluded = [card_builder.build_excluded(c) for c in excluded_raw + overflow]

    if not cards:
        notices.append("입력한 조건에 맞는 추천 금융상품 카드가 없습니다.")

    evidence_map: dict[str, EvidenceMapEntry] = {}
    if request.options.include_evidence_map:
        src_map = sources()
        for c in top:
            for sid in get_product_evidence(c.product)["source_ids"]:
                if sid in evidence_map or sid not in src_map:
                    continue
                s = src_map[sid]
                evidence_map[sid] = EvidenceMapEntry(
                    title=s["title"], provider=s.get("provider"), source_type=s["source_type"], checked_at=s["checked_at"]
                )

    return RecommendResponse(
        request_id=_new_request_id(),
        generated_at=datetime.now(_KST),
        recommendation_version="2.4",
        cards=cards,
        excluded_products=excluded,
        evidence_map=evidence_map,
        verification_notices=verification.notices,
        notices=notices,
    )
