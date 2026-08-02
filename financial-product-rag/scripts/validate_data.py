"""데이터 정합성 검증 (신규 카드 추천 스키마 기준).

python scripts/validate_data.py 로 실행합니다. 하나라도 실패하면 AssertionError와
함께 0이 아닌 종료 코드를 반환합니다 (CI/서버 기동 전 점검용).
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

VALID_STRATEGY_TYPES = {
    "FORWARD",
    "MAR",
    "FX_OPTION",
    "RANGE_FORWARD",
    "ENHANCED_FORWARD",
    "PARTICIPATING_FORWARD",
    "SEAGULL_FORWARD",
    "FX_SWAP",
    "FX_INSURANCE_GENERAL",
    "FX_INSURANCE_OPTION",
    "FOREIGN_CURRENCY_DEPOSIT",
    "IMPORT_PAYMENT_DEFERRAL",
    "EXPORT_RECEIVABLE_FINANCE",
    "EXPORT_WORKING_CAPITAL",
    "INTERNAL_MATCHING_NETTING",
}

products = json.loads((DATA / "product_master.json").read_text(encoding="utf-8"))
source_rows = json.loads((DATA / "source_registry.json").read_text(encoding="utf-8"))
sources = {x["source_id"] for x in source_rows}
rules = json.loads((DATA / "recommendation_rules.json").read_text(encoding="utf-8"))
knowledge = json.loads((DATA / "knowledge_articles.json").read_text(encoding="utf-8"))
review_queue = json.loads((DATA / "review_queue.json").read_text(encoding="utf-8"))
rag_lines = [
    json.loads(line) for line in (DATA / "rag_documents.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()
]

product_ids = [p["product_id"] for p in products]
rule_ids = [r["rule_id"] for r in rules]

# --- product_id / rule_id / source_id 고유성 ---
assert len(product_ids) == len(set(product_ids)), "duplicate product_id"
assert len(rule_ids) == len(set(rule_ids)), "duplicate rule_id"
assert len(sources) == len(source_rows), "duplicate source_id"

# --- 모든 상품 source_id 존재 ---
for p in products:
    assert p["source_ids"], f"{p['product_id']} missing source_ids"
    missing = set(p["source_ids"]) - sources
    assert not missing, f"{p['product_id']} missing sources: {missing}"
    assert p.get("provider"), f"{p['product_id']} missing provider"

# --- knowledge_articles source_id 존재 ---
for a in knowledge:
    missing = set(a["source_ids"]) - sources
    assert not missing, f"{a['document_id']} missing sources: {missing}"

# --- 모든 추천 규칙 product_id 존재, rule_type=SCORE만 사용 ---
for r in rules:
    assert r["product_id"] in set(product_ids), f"rule references unknown product: {r}"
    assert r["rule_type"] == "SCORE", f"unexpected rule_type in {r['rule_id']} (hard conditions live in product.eligibility_rules)"

# --- strategy_types가 유효 enum ---
for p in products:
    for st in p.get("strategy_types", []):
        assert st in VALID_STRATEGY_TYPES, f"{p['product_id']} has invalid strategy_type: {st}"

# --- 검증 상품(전략 연결 상품)에 card_summary 존재 ---
for p in products:
    if p.get("strategy_types"):
        display = p.get("display")
        assert display and display.get("card_summary"), f"{p['product_id']} missing display.card_summary"
        assert len(display["card_summary"]) <= 100, f"{p['product_id']} card_summary too long"

# --- EXCLUDE 상품이 후보에 들어가지 않음 (product_master에는 애초에 EXCLUDE 상품이 없어야 함) ---
for p in products:
    assert p["recommendation_mode"] != "EXCLUDE", f"{p['product_id']} is EXCLUDE mode but present in product_master"

# --- review_queue: 필수 필드 존재 ---
required_review_fields = {"input_name", "status", "recommendation_action", "reason", "source_ids"}
for entry in review_queue:
    assert required_review_fields <= set(entry.keys()), f"review_queue entry missing fields: {entry}"

# --- RAG 문서 연결 정상 (product/knowledge와 1:1, 중복 없음) ---
assert len(rag_lines) == len(products) + len(knowledge), "rag document count mismatch"
rag_ids = [x["document_id"] for x in rag_lines]
assert len(set(rag_ids)) == len(rag_ids), "duplicate RAG document id"
known_ids = {p["product_id"] for p in products} | {a["document_id"] for a in knowledge}
missing_links = set(rag_ids) - known_ids
assert not missing_links, f"rag_documents.jsonl has unlinked ids: {missing_links}"

# --- eligibility_rules를 가진 상품은 전략이 연결된 상품이어야 함 (고아 규칙 방지) ---
for p in products:
    if p.get("eligibility_rules") is not None:
        assert p.get("strategy_types"), f"{p['product_id']} has eligibility_rules but no strategy_types"

# --- eligibility_rules는 observable/review_requirements/unknown_eligibility_notes
#     3개 키만 사용해야 한다(하드 차단은 observable에서만, 나머지 두 개는
#     pendingConditions로만 표현되고 절대 하드 차단하지 않는다는 계약을
#     데이터 레벨에서도 강제) ---
ALLOWED_ELIGIBILITY_KEYS = {"observable", "review_requirements", "unknown_eligibility_notes"}
ALLOWED_OBSERVABLE_KEYS = {
    "min_days",
    "max_days",
    "min_hedge_horizon_months",
    "max_hedge_horizon_months",
    "allowed_currencies",
    "allowed_payment_terms",
    "product_discontinued",
}
for p in products:
    elig_rules = p.get("eligibility_rules")
    if elig_rules is None:
        continue
    assert set(elig_rules.keys()) <= ALLOWED_ELIGIBILITY_KEYS, f"{p['product_id']} has unexpected eligibility_rules keys: {elig_rules.keys()}"
    assert set(elig_rules.get("observable", {}).keys()) <= ALLOWED_OBSERVABLE_KEYS, (
        f"{p['product_id']} observable has unknown/unobservable keys: {elig_rules.get('observable', {}).keys()}"
    )
    assert isinstance(elig_rules.get("review_requirements", []), list)
    assert isinstance(elig_rules.get("unknown_eligibility_notes", []), list)

card_eligible = [p for p in products if p.get("strategy_types")]
print(
    f"OK: {len(products)} products ({len(card_eligible)} card-eligible), {len(sources)} sources, "
    f"{len(rules)} SCORE rules, {len(knowledge)} knowledge articles, {len(rag_lines)} RAG docs, "
    f"{len(review_queue)} review_queue entries"
)
