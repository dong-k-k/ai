"""recommendationReasons가 내부 구현을 노출하지 않고, 상품마다 실제로
다른 자연스러운 한국어 문장으로 나오는지 검증한다.

배경: 예전에는 recommender.py가 `f"선택한 전략 유형({matched_type})과 상품이
직접 일치합니다."`처럼 StrategyType enum, EXPORT/IMPORT, priority 숫자를
문장에 그대로 끼워 넣었다. 이 테스트들은 그 회귀를 막는다.
"""
from __future__ import annotations

import re

from tests.conftest import base_payload

_ENUM_TOKEN_RE = re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b")  # e.g. FX_INSURANCE_GENERAL
_BANNED_WORDS = ("EXPORT", "IMPORT", "LOW", "MEDIUM", "HIGH")


def _import_payload() -> dict:
    payload = base_payload()
    payload["companyProfile"]["tradeDirection"] = "IMPORT"
    payload["contracts"][0]["tradeDirection"] = "IMPORT"
    payload["strategyContext"]["strategies"] = [
        {"strategyType": "IMPORT_PAYMENT_DEFERRAL", "allocationRatio": 0.5, "priority": 1},
        {"strategyType": "FOREIGN_CURRENCY_DEPOSIT", "allocationRatio": 0.5, "priority": 2},
    ]
    return payload


def _all_reasons(body: dict) -> list[str]:
    return [reason for card in body["cards"] for reason in card["recommendationReasons"]]


def test_reasons_contain_no_internal_enum_tokens(client):
    body = client.post("/recommend", json=base_payload()).json()
    reasons = _all_reasons(body)
    assert reasons, "expected at least one recommendation reason"
    for reason in reasons:
        assert not _ENUM_TOKEN_RE.search(reason), reason


def test_reasons_do_not_mention_priority_ranking(client):
    body = client.post("/recommend", json=base_payload()).json()
    for reason in _all_reasons(body):
        assert "우선순위" not in reason, reason


def test_reasons_do_not_contain_banned_raw_words(client):
    body = client.post("/recommend", json=base_payload()).json()
    for reason in _all_reasons(body):
        for word in _BANNED_WORDS:
            assert not re.search(rf"\b{word}\b", reason), (word, reason)


def test_reasons_have_no_semicolons(client):
    body = client.post("/recommend", json=base_payload()).json()
    for reason in _all_reasons(body):
        assert ";" not in reason, reason


def test_reasons_respect_max_count_and_length(client):
    body = client.post("/recommend", json=base_payload()).json()
    for card in body["cards"]:
        reasons = card["recommendationReasons"]
        assert len(reasons) <= 3, card["productId"]
        for reason in reasons:
            assert len(reason) <= 70, (card["productId"], reason)


def test_reasons_differ_across_products(client):
    """모든 카드가 같은 공통 문장만 반복하지 않는지 — 첫 번째 근거(상품 핵심
    효과)는 product_master.json의 display.card_summary에서 나오므로 상품마다
    달라야 한다."""
    body = client.post("/recommend", json=base_payload()).json()
    first_reasons = [c["recommendationReasons"][0] for c in body["cards"] if c["recommendationReasons"]]
    assert len(first_reasons) >= 2, "need at least two cards with reasons to check differentiation"
    assert len(set(first_reasons)) > 1, first_reasons


def test_reason_sets_are_not_identical_between_products(client):
    body = client.post("/recommend", json=base_payload()).json()
    reason_sets = [tuple(c["recommendationReasons"]) for c in body["cards"] if c["recommendationReasons"]]
    assert len(reason_sets) >= 2
    assert len(set(reason_sets)) > 1, reason_sets


def test_export_risk_wording_differs_from_import(client):
    export_body = client.post("/recommend", json=base_payload()).json()
    import_body = client.post("/recommend", json=_import_payload()).json()

    export_reasons = " ".join(_all_reasons(export_body))
    import_reasons = " ".join(_all_reasons(import_body))

    assert "환율 하락" in export_reasons and "수출대금" in export_reasons
    assert "환율 상승" in import_reasons and "수입대금" in import_reasons
    # 두 방향 설명 문장 자체가 다른 문자열이어야 한다(같은 문장을 재사용하지 않음).
    assert "환율 하락으로 수출대금의 원화 환산액이 줄어드는 위험을 관리하는 데 적합한 상품입니다." in export_reasons
    assert "환율 상승으로 수입대금의 원화 지급 부담이 늘어나는 위험을 관리하는 데 적합한 상품입니다." in import_reasons


def test_reasons_use_real_product_summary_as_first_reason(client):
    """상품 핵심 효과 문장은 product_master.json의 display.card_summary를
    그대로 옮긴 것이어야 한다(지어낸 문장이 아님)."""
    import json

    from app.store import products

    catalog = {p["product_id"]: p for p in products()}
    body = client.post("/recommend", json=base_payload()).json()
    for card in body["cards"]:
        product = catalog[card["productId"]]
        card_summary = ((product.get("display") or {}).get("card_summary") or "").strip()
        if not card_summary or not card["recommendationReasons"]:
            continue
        expected = f"{card_summary}입니다."
        if len(expected) <= 70:
            assert card["recommendationReasons"][0] == expected, json.dumps(card, ensure_ascii=False)
