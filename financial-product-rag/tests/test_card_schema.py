"""15. 카드 스키마 테스트."""
from __future__ import annotations

import json

from tests.conftest import base_payload

_BANNED = (
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


def test_response_is_camel_case(client):
    resp = client.post("/recommend", json=base_payload())
    assert resp.status_code == 200
    body = resp.json()
    assert "requestId" in body
    assert "generatedAt" in body
    assert "recommendationVersion" in body
    assert "cards" in body
    assert body["cards"], "expected at least one card for the mixed-hedge scenario"
    card = body["cards"][0]
    for key in (
        "productId",
        "productName",
        "fitScore",
        "fitLabel",
        "eligibilityStatus",
        "eligibilityLabel",
        "oneLineSummary",
        "recommendationReasons",
        "sourceIds",
        "recommendationMode",
        "detailAvailable",
    ):
        assert key in card, key


def test_cards_respect_max_cards(client):
    payload = base_payload()
    payload["options"]["maxCards"] = 1
    body = client.post("/recommend", json=payload).json()
    assert len(body["cards"]) <= 1


def test_rank_is_sequential_from_one(client):
    body = client.post("/recommend", json=base_payload()).json()
    ranks = [c["rank"] for c in body["cards"]]
    assert ranks == list(range(1, len(ranks) + 1))


def test_fit_score_descending(client):
    body = client.post("/recommend", json=base_payload()).json()
    scores = [c["fitScore"] for c in body["cards"]]
    assert scores == sorted(scores, reverse=True)


def test_fit_score_in_range(client):
    body = client.post("/recommend", json=base_payload()).json()
    for c in body["cards"]:
        assert 0 <= c["fitScore"] <= 100


def test_every_card_has_product_id_name_provider(client):
    body = client.post("/recommend", json=base_payload()).json()
    for c in body["cards"]:
        assert c["productId"]
        assert c["productName"]
        assert c["provider"]


def test_every_card_has_source_ids(client):
    body = client.post("/recommend", json=base_payload()).json()
    for c in body["cards"]:
        assert c["sourceIds"], c["productId"]


def test_all_card_source_ids_exist_in_evidence_map(client):
    body = client.post("/recommend", json=base_payload()).json()
    evidence_ids = set(body["evidenceMap"].keys())
    for c in body["cards"]:
        assert set(c["sourceIds"]) <= evidence_ids, c["productId"]


def test_no_banned_phrases_anywhere(client):
    body = client.post("/recommend", json=base_payload()).json()
    text = json.dumps(body, ensure_ascii=False)
    for phrase in _BANNED:
        assert phrase not in text, phrase


def test_no_freeform_answer_field(client):
    body = client.post("/recommend", json=base_payload()).json()
    assert "answer" not in body
    for c in body["cards"]:
        assert "answer" not in c
