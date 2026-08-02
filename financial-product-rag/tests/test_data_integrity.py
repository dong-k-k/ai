"""15. 데이터 정합성 테스트."""
from __future__ import annotations

from app.store import knowledge_articles, products, rag_documents, review_queue, score_rules, sources


def test_product_id_unique():
    ids = [p["product_id"] for p in products()]
    assert len(ids) == len(set(ids))


def test_rule_id_unique():
    ids = [r["rule_id"] for r in score_rules()]
    assert len(ids) == len(set(ids))


def test_source_id_unique():
    ids = [s["source_id"] for s in sources().values()]
    assert len(ids) == len(set(ids))


def test_all_products_have_valid_source_ids():
    src_ids = set(sources().keys())
    for p in products():
        assert p["source_ids"], p["product_id"]
        assert set(p["source_ids"]) <= src_ids, p["product_id"]


def test_all_score_rules_reference_existing_product():
    product_ids = {p["product_id"] for p in products()}
    for r in score_rules():
        assert r["product_id"] in product_ids, r


def test_strategy_types_are_valid_enum():
    from app.models import StrategyType

    valid = {e.value for e in StrategyType}
    for p in products():
        for st in p.get("strategy_types", []):
            assert st in valid, (p["product_id"], st)


def test_card_eligible_products_have_card_summary():
    for p in products():
        if p.get("strategy_types"):
            assert p.get("display") and p["display"].get("card_summary"), p["product_id"]
            assert len(p["display"]["card_summary"]) <= 100


def test_no_exclude_mode_products_in_master():
    assert all(p["recommendation_mode"] != "EXCLUDE" for p in products())


def test_rag_documents_linked_to_known_ids():
    known = {p["product_id"] for p in products()} | {a["document_id"] for a in knowledge_articles()}
    rag_ids = {d["document_id"] for d in rag_documents()}
    assert rag_ids <= known
    assert len(rag_documents()) == len(products()) + len(knowledge_articles())


def test_review_queue_loaded_and_has_required_fields():
    entries = review_queue()
    assert len(entries) > 0
    for e in entries:
        assert {"input_name", "status", "recommendation_action", "reason"} <= set(e.keys())


def test_kb_fx_matching_is_flagged_not_verified_in_review_queue():
    entries = review_queue()
    matches = [e for e in entries if "FX Matching" in e["input_name"]]
    assert matches, "review_queue must still document the KB FX Matching case"
    assert matches[0]["recommendation_action"] == "EXCLUDE"
