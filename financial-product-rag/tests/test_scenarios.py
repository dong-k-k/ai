"""주요 상담 시나리오 + 이번 개편(실제 보유 정보 기준)으로 추가된 12개 항목."""
from __future__ import annotations

import copy

from tests.conftest import base_payload


def _cards_by_id(body: dict) -> dict:
    return {c["productId"]: c for c in body["cards"]}


# 시나리오 1: 수출기업 혼합 헤지 -------------------------------------------------


def test_scenario1_mixed_hedge(client):
    body = client.post("/recommend", json=base_payload()).json()
    cards = _cards_by_id(body)

    assert "KSURE-FX-001" in cards
    assert "FX-HEDGE-001" in cards
    assert cards["KSURE-FX-001"]["allocationRatio"] == 0.5
    assert cards["FX-HEDGE-001"]["allocationRatio"] == 0.5
    assert any("이익금" in c for c in cards["KSURE-FX-001"]["cautions"])
    assert cards["FX-HEDGE-001"]["eligibilityStatus"] == "RM_REVIEW_REQUIRED"
    assert cards["FX-HEDGE-001"]["eligibilityLabel"] == "직원 확인 필요"
    assert cards["KSURE-FX-001"]["sourceIds"]
    assert cards["FX-HEDGE-001"]["sourceIds"]


# 시나리오 2: 상승 이익 유지 ------------------------------------------------------


def test_scenario2_upside_participation(client):
    payload = base_payload()
    payload["riskContext"]["riskPreference"] = "AGGRESSIVE"
    payload["strategyContext"] = {
        "strategies": [{"strategyType": "FX_INSURANCE_OPTION", "allocationRatio": 1.0}]
    }
    body = client.post("/recommend", json=payload).json()
    cards = _cards_by_id(body)

    assert "KSURE-FX-002" in cards
    assert cards["KSURE-FX-002"]["rank"] == 1
    option_card = cards["KSURE-FX-002"]
    assert option_card["strategyTypes"] == ["FX_INSURANCE_OPTION"]
    combined = " ".join(option_card["pendingConditions"] + option_card["cautions"])
    assert "6개월" in combined or "청약금액" in combined or "보험료" in combined
    full_text = str(body)
    for phrase in ("승인 확정", "가입 가능 확정"):
        assert phrase not in full_text


# 시나리오 3: 수입기업 결제 유예 ---------------------------------------------------


def test_scenario3_import_payment_deferral(client):
    payload = {
        "companyProfile": {"tradeDirection": "IMPORT", "currencies": ["USD"], "paymentTerms": ["T/T"]},
        "contracts": [
            {"tradeDirection": "IMPORT", "foreignAmount": 100000, "currency": "USD", "settlementDate": "2027-01-15"}
        ],
        "riskContext": {"remainingDays": 120},
        "strategyContext": {
            "strategies": [
                {"strategyType": "IMPORT_PAYMENT_DEFERRAL", "allocationRatio": 0.7, "priority": 1},
                {"strategyType": "FORWARD", "allocationRatio": 0.3, "priority": 2},
            ]
        },
        "options": {"maxCards": 5, "includeConditional": True, "includeEvidenceMap": True},
    }
    body = client.post("/recommend", json=payload).json()
    cards = _cards_by_id(body)

    assert "IMPORT-001" in cards
    assert cards["IMPORT-001"]["rank"] == 1
    if "FX-HEDGE-001" in cards:
        assert cards["FX-HEDGE-001"]["rank"] > cards["IMPORT-001"]["rank"]
    combined = " ".join(cards["IMPORT-001"]["pendingConditions"] + cards["IMPORT-001"]["cautions"])
    assert combined


# 시나리오 4: 부적격 상품 제거 -----------------------------------------------------


def test_scenario4_wrong_direction_excluded(client):
    payload = base_payload()
    payload["strategyContext"] = {"strategies": [{"strategyType": "IMPORT_PAYMENT_DEFERRAL", "allocationRatio": 1.0}]}
    body = client.post("/recommend", json=payload).json()
    ids = {c["productId"] for c in body["cards"]}
    assert "IMPORT-001" not in ids


def test_scenario4_days_too_short_excluded(client):
    payload = base_payload()
    payload["riskContext"]["remainingDays"] = 1  # FORWARD의 min_days=3 미달
    payload["strategyContext"] = {"strategies": [{"strategyType": "FORWARD", "allocationRatio": 1.0}]}
    body = client.post("/recommend", json=payload).json()
    card_ids = {c["productId"] for c in body["cards"]}
    assert "FX-HEDGE-001" not in card_ids
    excluded_ids = {e["productId"]: e for e in body["excludedProducts"]}
    assert "FX-HEDGE-001" in excluded_ids
    assert excluded_ids["FX-HEDGE-001"]["eligibilityStatus"] == "NOT_RECOMMENDED"


# 시나리오 5(개편): K-SURE 자격 정보 없이도 CONDITIONAL(자격 미확정 표현 없음) ------


def test_scenario5_missing_k_sure_info_is_conditional_not_excluded(client):
    payload = base_payload()
    payload["strategyContext"] = {"strategies": [{"strategyType": "FX_INSURANCE_GENERAL", "allocationRatio": 1.0}]}
    body = client.post("/recommend", json=payload).json()
    cards = _cards_by_id(body)
    assert "KSURE-FX-001" in cards
    assert cards["KSURE-FX-001"]["eligibilityStatus"] == "CONDITIONAL"
    assert cards["KSURE-FX-001"]["eligibilityLabel"] == "조건 확인 필요"
    assert any("K-SURE" in c for c in cards["KSURE-FX-001"]["pendingConditions"])


# 시나리오 6: 미검증 상품 --------------------------------------------------------


def test_scenario6_unverified_product_names_excluded(client):
    payload = base_payload()
    payload["requestedProductNames"] = ["KB FX Matching", "EDI 수출팩토링"]
    body = client.post("/recommend", json=payload).json()

    card_names = {c["productName"] for c in body["cards"]}
    assert not any("Matching" in n for n in card_names)
    assert not any("팩토링" in n for n in card_names)

    notices = {n["requestedName"]: n for n in body["verificationNotices"]}
    assert "KB FX Matching" in notices
    assert notices["KB FX Matching"]["action"] == "EXCLUDE"
    assert "EDI 수출팩토링" in notices
    assert notices["EDI 수출팩토링"]["action"] == "EXCLUDE"


# 시나리오 7: 명칭 정정 ----------------------------------------------------------


def test_scenario7_kb_mars_renamed_to_mar(client):
    payload = base_payload()
    payload["requestedProductNames"] = ["KB MARS"]
    body = client.post("/recommend", json=payload).json()
    notices = {n["requestedName"]: n for n in body["verificationNotices"]}
    assert "KB MARS" in notices
    assert notices["KB MARS"]["canonicalName"] == "MAR 거래"


# 시나리오 8: 결정론 -------------------------------------------------------------


def test_scenario8_deterministic_ranking_and_scores(client):
    payload = base_payload()
    r1 = client.post("/recommend", json=payload).json()
    r2 = client.post("/recommend", json=copy.deepcopy(payload)).json()

    ranks1 = [(c["productId"], c["fitScore"], c["eligibilityStatus"]) for c in r1["cards"]]
    ranks2 = [(c["productId"], c["fitScore"], c["eligibilityStatus"]) for c in r2["cards"]]
    assert ranks1 == ranks2


def test_scenario8_llm_env_vars_do_not_affect_result(client, monkeypatch):
    payload = base_payload()
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    without_key = client.post("/recommend", json=payload).json()

    monkeypatch.setenv("LLM_API_KEY", "sk-does-not-matter")
    monkeypatch.setenv("LLM_BASE_URL", "http://example.invalid")
    with_key = client.post("/recommend", json=payload).json()

    ranks_a = [(c["productId"], c["fitScore"]) for c in without_key["cards"]]
    ranks_b = [(c["productId"], c["fitScore"]) for c in with_key["cards"]]
    assert ranks_a == ranks_b


# =============================================================================
# 이번 개편(실제 보유 정보 기준)으로 추가된 12개 테스트
# =============================================================================


# 1. K-SURE 자격 정보가 없어도 카드에서 제외되지 않고 CONDITIONAL이 됨
def test_added1_k_sure_missing_info_stays_conditional(client):
    payload = base_payload()
    payload["strategyContext"] = {"strategies": [{"strategyType": "FX_INSURANCE_GENERAL", "allocationRatio": 1.0}]}
    body = client.post("/recommend", json=payload).json()
    cards = _cards_by_id(body)
    assert "KSURE-FX-001" in cards
    assert cards["KSURE-FX-001"]["eligibilityStatus"] != "NOT_RECOMMENDED"
    assert cards["KSURE-FX-001"]["eligibilityStatus"] == "CONDITIONAL"


# 2. K-SURE 실제 인수 가능성을 확정적으로 표현하지 않음
def test_added2_k_sure_never_states_final_underwriting_as_confirmed(client):
    payload = base_payload()
    payload["strategyContext"] = {"strategies": [{"strategyType": "FX_INSURANCE_GENERAL", "allocationRatio": 1.0}]}
    body = client.post("/recommend", json=payload).json()
    card = _cards_by_id(body)["KSURE-FX-001"]
    all_text = " ".join(card["cautions"] + card["pendingConditions"] + card["recommendationReasons"])
    assert "인수 가능 여부" in all_text or "심사 후 결정" in " ".join(card["cautions"])
    for banned in ("인수 확정", "가입 확정", "승인 확정", "자격 충족"):
        assert banned not in str(body)


# 3. 선물환은 계약 정보가 충분해도 RM_REVIEW_REQUIRED
def test_added3_forward_always_rm_review_even_with_full_info(client):
    payload = base_payload()
    payload["riskContext"]["remainingDays"] = 90
    payload["strategyContext"] = {"strategies": [{"strategyType": "FORWARD", "allocationRatio": 1.0}]}
    body = client.post("/recommend", json=payload).json()
    card = _cards_by_id(body)["FX-HEDGE-001"]
    assert card["eligibilityStatus"] == "RM_REVIEW_REQUIRED"


# 4. Payment Usance는 신용정보가 없으므로 CONDITIONAL 또는 RM_REVIEW_REQUIRED
def test_added4_payment_usance_never_recommended_outright(client):
    payload = {
        "companyProfile": {"tradeDirection": "IMPORT", "currencies": ["USD"], "paymentTerms": ["T/T"]},
        "contracts": [{"tradeDirection": "IMPORT", "foreignAmount": 50000, "currency": "USD"}],
        "strategyContext": {"strategies": [{"strategyType": "IMPORT_PAYMENT_DEFERRAL", "allocationRatio": 1.0}]},
    }
    body = client.post("/recommend", json=payload).json()
    card = _cards_by_id(body)["IMPORT-001"]
    assert card["eligibilityStatus"] in ("CONDITIONAL", "RM_REVIEW_REQUIRED")


# 5. 외화예금은 여유 외화 정보가 없으면 CONDITIONAL
def test_added5_fx_deposit_conditional_without_surplus_info(client):
    payload = base_payload()
    payload["strategyContext"] = {"strategies": [{"strategyType": "FOREIGN_CURRENCY_DEPOSIT", "allocationRatio": 1.0}]}
    body = client.post("/recommend", json=payload).json()
    card = _cards_by_id(body)["FX-DEPOSIT-001"]
    assert card["eligibilityStatus"] == "CONDITIONAL"
    assert any("여유자금" in c for c in card["pendingConditions"])


# 6. 명백한 거래 방향 불일치 상품은 NOT_RECOMMENDED 또는 카드 제외
def test_added6_clear_direction_mismatch_not_recommended(client):
    payload = base_payload()  # EXPORT 기업
    payload["strategyContext"] = {"strategies": [{"strategyType": "IMPORT_PAYMENT_DEFERRAL", "allocationRatio": 1.0}]}
    body = client.post("/recommend", json=payload).json()
    assert "IMPORT-001" not in {c["productId"] for c in body["cards"]}
    excluded = {e["productId"]: e for e in body["excludedProducts"]}
    if "IMPORT-001" in excluded:
        assert excluded["IMPORT-001"]["eligibilityStatus"] == "NOT_RECOMMENDED"


# 7. 미입력 조건이 fitScore를 과도하게 낮추지 않음
def test_added7_missing_optional_info_does_not_tank_fit_score(client):
    payload = base_payload()
    payload["strategyContext"] = {"strategies": [{"strategyType": "FX_INSURANCE_GENERAL", "allocationRatio": 1.0}]}
    body = client.post("/recommend", json=payload).json()
    card = _cards_by_id(body)["KSURE-FX-001"]
    # K-SURE 자격/인수 여부는 전혀 입력하지 않았지만(CONDITIONAL이어도)
    # 전략 직접 일치(40) 등 관찰 가능한 요소만으로 여전히 높은 점수가 나와야 한다.
    assert card["fitScore"] >= 50


# 8. 분할 결제 2건 이상 입력이 정상 처리됨
def test_added8_multiple_installments_handled(client):
    payload = base_payload()
    payload["contracts"] = [
        {"tradeDirection": "EXPORT", "foreignAmount": 100000, "currency": "USD", "settlementDate": "2026-09-30", "installmentOrder": 1},
        {"tradeDirection": "EXPORT", "foreignAmount": 120000, "currency": "USD", "settlementDate": "2026-11-30", "installmentOrder": 2},
    ]
    resp = client.post("/recommend", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    card = _cards_by_id(body)["FX-HEDGE-001"]
    assert card["paymentScheduleSummary"] is not None
    assert "2건" in card["paymentScheduleSummary"]
    assert card["coveredContractIndexes"] == [0, 1]


# 9. 같은 입력을 여러 번 호출해도 순위와 점수가 동일 (test_scenario8과 별개 케이스)
def test_added9_deterministic_across_repeated_calls(client):
    payload = base_payload()
    results = [client.post("/recommend", json=copy.deepcopy(payload)).json() for _ in range(3)]
    signatures = [[(c["productId"], c["fitScore"], c["rank"]) for c in r["cards"]] for r in results]
    assert signatures[0] == signatures[1] == signatures[2]


# 10. 응답에 자격 충족, 가입 확정, 승인 확정 표현이 없음
def test_added10_no_finalized_approval_language(client):
    body = client.post("/recommend", json=base_payload()).json()
    text = str(body)
    for phrase in ("자격 충족", "가입 확정", "승인 확정", "가입 가능 확정", "승인 가능"):
        assert phrase not in text


# 11. review_queue의 미검증·종료 상품 차단 기능이 유지됨
def test_added11_review_queue_blocking_still_works(client):
    payload = base_payload()
    payload["requestedProductNames"] = ["KB ONE TRADE"]
    body = client.post("/recommend", json=payload).json()
    notices = {n["requestedName"]: n for n in body["verificationNotices"]}
    assert "KB ONE TRADE" in notices
    assert notices["KB ONE TRADE"]["status"] == "RETIRED"
    assert notices["KB ONE TRADE"]["action"] == "EXCLUDE"


# 12. sourceIds와 evidenceMap의 정합성이 유지됨
def test_added12_source_ids_consistent_with_evidence_map(client):
    body = client.post("/recommend", json=base_payload()).json()
    evidence_ids = set(body["evidenceMap"].keys())
    for c in body["cards"]:
        assert set(c["sourceIds"]) <= evidence_ids
