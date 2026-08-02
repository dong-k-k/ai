from __future__ import annotations

from fastapi import FastAPI, HTTPException, status

from app.evidence_retriever import get_product_evidence, search_documents
from app.exposure import MissingExposureGroupError, UnknownExposureGroupError, validate_exposure_group_references
from app.models import (
    ProductDetail,
    ProductEvidence,
    RecommendRequest,
    RecommendResponse,
    RelatedGuide,
    SearchHit,
    SearchRequest,
    SourceInfo,
)
from app.services.recommendation_service import generate_recommendations
from app.store import products, sources, validate_on_startup

# 14: 내부 데이터 파싱 실패 → 서버 시작 시 명확한 오류.
# store.DataLoadError를 그대로 전파해 uvicorn이 기동 자체를 실패시킵니다.
validate_on_startup()

app = FastAPI(
    title="KB & K-SURE FX 추천 카드 API",
    version="2.0.0",
    description=(
        "기업/계약/리스크/전략 입력을 받아 검증된 상품만으로 추천 금융상품 "
        "카드를 생성합니다. RAG 검색은 이미 선택된 상품의 공식 근거를 "
        "보강하는 용도로만 쓰이며, 상품 순위·자격 판정에는 관여하지 않습니다."
    ),
)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/recommend", response_model=RecommendResponse, tags=["recommend"])
def recommend(request: RecommendRequest) -> RecommendResponse:
    # exposureGroupId 존재 여부는 Pydantic 필드 검증만으로는 알 수 없다
    # (contracts와 대조해야 하는 교차 검증) — 여기서 구조화된 422로
    # 변환한다. 이 검사를 통과한 뒤에는 recommender/valuation 쪽에서
    # exposureGroupId가 항상 유효하거나 단일 그룹으로 자동 연결된
    # 상태라고 가정할 수 있다.
    try:
        validate_exposure_group_references(request)
    except UnknownExposureGroupError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "unknown_exposure_group_id",
                "field": f"strategyContext.{exc.field}[{exc.index}].exposureGroupId",
                "invalidExposureGroupId": exc.exposure_group_id,
                "availableExposureGroupIds": exc.available,
            },
        ) from exc
    except MissingExposureGroupError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "missing_exposure_group_id",
                "field": f"strategyContext.{exc.field}[{exc.index}].exposureGroupId",
                "availableExposureGroupIds": exc.available,
                "message": "노출 그룹이 여러 개이므로 exposureGroupId를 반드시 지정해야 합니다.",
            },
        ) from exc

    return generate_recommendations(request)


@app.post("/search", response_model=list[SearchHit], tags=["debug"])
def search(req: SearchRequest) -> list[SearchHit]:
    """운영자·개발자용 공식 문서 검색 디버깅 도구. 프론트엔드 상품 추천
    파이프라인은 이 엔드포인트를 호출하지 않습니다 (POST /recommend 사용)."""
    hits = search_documents(req.query, req.top_k)
    return [SearchHit(**h) for h in hits]


@app.get("/sources/{source_id}", response_model=SourceInfo, tags=["sources"])
def get_source(source_id: str) -> SourceInfo:
    src = sources().get(source_id)
    if src is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "source_not_found", "sourceId": source_id},
        )
    return SourceInfo(**src)


def _find_product(product_id: str) -> dict:
    for p in products():
        if p["product_id"] == product_id:
            return p
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"error": "product_not_found", "productId": product_id},
    )


@app.get("/products/{product_id}", response_model=ProductDetail, tags=["products"])
def get_product(product_id: str) -> ProductDetail:
    p = _find_product(product_id)
    return ProductDetail(
        product_id=p["product_id"],
        official_name=p["official_name"],
        provider=p.get("provider", ""),
        category=p.get("category", ""),
        product_type=p.get("product_type", ""),
        strategy_types=p.get("strategy_types", []),
        recommendation_mode=p["recommendation_mode"],
        verification_status=p.get("verification_status", ""),
        target_customer=p.get("target_customer", ""),
        currencies=p.get("currencies", []),
        term=p.get("term", ""),
        application_channels=p.get("channels", []),
        required_documents=p.get("required_documents", []),
        process_controls=p.get("process_controls", []),
        settlement_rules=p.get("settlement_rules", []),
        key_risks=p.get("key_risks", []),
        source_ids=p.get("source_ids", []),
    )


@app.get("/products/{product_id}/evidence", response_model=ProductEvidence, tags=["products"])
def get_product_evidence_endpoint(product_id: str) -> ProductEvidence:
    p = _find_product(product_id)
    ev = get_product_evidence(p)
    src_map = sources()
    return ProductEvidence(
        product_id=ev["product_id"],
        official_name=ev["official_name"],
        evidence=ev["evidence"],
        source_ids=ev["source_ids"],
        sources=[SourceInfo(**src_map[s]) for s in ev["source_ids"] if s in src_map],
        related_guides=[
            RelatedGuide(
                document_id=g["document_id"],
                title=g["title"],
                summary=g["summary"],
                source_ids=g["source_ids"],
            )
            for g in ev["related_guides"]
        ],
    )


# ---------------------------------------------------------------------------
# 3. 질의응답형 POST /rag 제거
#
# 선택: HTTP 410 Gone (완전 삭제도, 조용한 deprecated 유지도 아닌 이유는
# README "기존 /rag 마이그레이션 안내" 참고).
# ---------------------------------------------------------------------------


@app.post("/rag", status_code=status.HTTP_410_GONE, tags=["removed"])
def rag_removed():
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail={
            "error": "endpoint_removed",
            "message": "POST /rag는 카드 추천형 구조로 개편되며 제거되었습니다. POST /recommend를 사용하세요.",
            "migrateTo": "/recommend",
        },
    )
