"""7. RAG 검색 역할 변경: 상품을 결정하는 데는 전혀 관여하지 않습니다.

- get_product_evidence(): 이미 선택된 상품의 공식 근거(sourceIds)와 관련
  운영 가이드를 모아줍니다. strategyType → 가이드 문서 연결은 자연어 유사도
  검색이 아니라 STRATEGY_GUIDE_MAP 명시적 매핑을 우선 사용합니다(16번
  요구사항: GUIDE-KB-OTC-001을 통화옵션/구조화 상품에 명시적으로 연결).
- search_documents(): /search 디버깅 엔드포인트 전용 TF-IDF 검색. 상품
  추천 파이프라인에서는 호출되지 않습니다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.store import knowledge_articles, products, rag_documents, sources

# strategyType -> 명시적으로 연결된 knowledge_articles.document_id 목록.
# 자연어 유사도 검색 결과에 의존하지 않도록 고정 매핑으로 관리합니다.
STRATEGY_GUIDE_MAP: dict[str, list[str]] = {
    "FORWARD": ["GUIDE-KB-FORWARD-OPS-001", "GUIDE-KB-OTC-001", "GUIDE-KB-EVIDENCE-001"],
    "MAR": [],
    "FX_OPTION": ["GUIDE-KB-OTC-001", "GUIDE-KB-EVIDENCE-001"],
    "RANGE_FORWARD": ["GUIDE-KB-OTC-001", "GUIDE-KB-EVIDENCE-001"],
    "ENHANCED_FORWARD": ["GUIDE-KB-OTC-001", "GUIDE-KB-EVIDENCE-001"],
    "PARTICIPATING_FORWARD": ["GUIDE-KB-OTC-001", "GUIDE-KB-EVIDENCE-001"],
    "SEAGULL_FORWARD": ["GUIDE-KB-OTC-001", "GUIDE-KB-EVIDENCE-001"],
    "FX_SWAP": ["GUIDE-KB-OTC-001"],
    "FX_INSURANCE_GENERAL": ["GUIDE-KSURE-001", "GUIDE-COMPARE-001"],
    "FX_INSURANCE_OPTION": ["GUIDE-KSURE-001", "GUIDE-COMPARE-001"],
    "FOREIGN_CURRENCY_DEPOSIT": [],
    "IMPORT_PAYMENT_DEFERRAL": [],
    "EXPORT_RECEIVABLE_FINANCE": [],
    "EXPORT_WORKING_CAPITAL": [],
    "INTERNAL_MATCHING_NETTING": ["GUIDE-KB-RISK-001"],
}


def _knowledge_by_id() -> dict[str, dict[str, Any]]:
    return {a["document_id"]: a for a in knowledge_articles()}


def related_guides_for_strategy_types(strategy_types: list[str]) -> list[dict[str, Any]]:
    kb = _knowledge_by_id()
    seen: list[str] = []
    for st in strategy_types:
        for doc_id in STRATEGY_GUIDE_MAP.get(st, []):
            if doc_id not in seen and doc_id in kb:
                seen.append(doc_id)
    return [kb[d] for d in seen]


def get_product_evidence(product: dict[str, Any]) -> dict[str, Any]:
    src_map = sources()
    source_ids = list(product.get("source_ids", []))
    guides = related_guides_for_strategy_types(product.get("strategy_types", []))
    for g in guides:
        for sid in g.get("source_ids", []):
            if sid not in source_ids:
                source_ids.append(sid)
    return {
        "product_id": product["product_id"],
        "official_name": product["official_name"],
        "evidence": product.get("evidence", ""),
        "source_ids": source_ids,
        "sources": [src_map[s] for s in source_ids if s in src_map],
        "related_guides": guides,
    }


def internal_technique_notice(strategy_type: str) -> dict[str, Any] | None:
    """매칭·네팅처럼 '가입형 상품이 아닌' strategyType이 요청되면 카드 대신
    이 안내를 준다 (5번: 매칭·네팅은 product card 후보에 넣지 않음)."""
    if strategy_type != "INTERNAL_MATCHING_NETTING":
        return None
    kb = _knowledge_by_id()
    guide = kb.get("GUIDE-KB-RISK-001")
    return {
        "strategyType": strategy_type,
        "message": "매칭·네팅은 가입형 금융상품이 아니라 기업이 스스로 운용하는 내부 환위험 관리기법입니다. 상품 카드로 제공하지 않습니다.",
        "guide": {"document_id": guide["document_id"], "title": guide["title"], "summary": guide["summary"]}
        if guide
        else None,
    }


# ---------------------------------------------------------------------------
# /search — operator/debug 전용 TF-IDF (카드 추천에는 절대 사용하지 않음)
# ---------------------------------------------------------------------------

_MIN_SIMILARITY = 0.05


@dataclass
class _Index:
    vectorizer: TfidfVectorizer
    matrix: Any
    docs: list[dict[str, Any]]


_index: _Index | None = None


def _build_index() -> _Index:
    docs = rag_documents()
    corpus = [d["text"] for d in docs]
    vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=1)
    matrix = vectorizer.fit_transform(corpus)
    return _Index(vectorizer=vectorizer, matrix=matrix, docs=docs)


def search_documents(
    query: str,
    top_k: int = 5,
    *,
    product_id: str | None = None,
    source_id: str | None = None,
    strategy_type: str | None = None,
    category: str | None = None,
) -> list[dict[str, Any]]:
    global _index
    if _index is None:
        _index = _build_index()

    strategy_products = None
    if strategy_type:
        strategy_products = {p["product_id"] for p in products() if strategy_type in p.get("strategy_types", [])}

    query_vec = _index.vectorizer.transform([query])
    scores = cosine_similarity(query_vec, _index.matrix)[0]
    order = np.argsort(scores)[::-1]

    hits: list[dict[str, Any]] = []
    for idx in order:
        if len(hits) >= top_k:
            break
        score = float(scores[idx])
        if score < _MIN_SIMILARITY:
            break  # scores are sorted descending — nothing further clears the bar
        doc = _index.docs[idx]
        meta = doc["metadata"]
        doc_id = doc["document_id"]
        if product_id and doc_id != product_id:
            continue
        if source_id and source_id not in meta.get("source_ids", []):
            continue
        if strategy_products is not None and doc_id not in strategy_products:
            continue
        if category and meta.get("category") != category:
            continue
        summary = ""
        if "\n요약: " in doc["text"]:
            summary = doc["text"].split("\n요약: ", 1)[1].split("\n", 1)[0]
        hits.append(
            {
                "document_id": doc_id,
                "document_type": meta["document_type"],
                "title": meta["official_name"],
                "provider": meta.get("provider"),
                "score": round(score, 6),
                "category": meta["category"],
                "summary": summary,
                "source_ids": meta.get("source_ids", []),
            }
        )
    return hits
