"""v2.3: 다중 통화 환산 + 노출 그룹별 전략 배분 테스트."""
from __future__ import annotations

import copy

from tests.conftest import base_payload


def _cards_by_group(body: dict, product_id: str) -> dict:
    return {c["exposureGroupId"]: c for c in body["cards"] if c["productId"] == product_id}


def _verification_scenario_payload() -> dict:
    """검증 시나리오: EXPORT USD 200,000/baseRate 1,350, IMPORT JPY
    5,000,000/baseRate 9.1, 그룹별 targetHedgeRatio 0.5, EXPORT-USD 배분
    0.6/0.4, IMPORT-JPY 배분 1.0."""
    return {
        "companyProfile": {"tradeDirection": "BOTH", "currencies": ["USD", "JPY"], "paymentTerms": ["T/T"]},
        "contracts": [
            {
                "tradeDirection": "EXPORT",
                "foreignAmount": 200000,
                "currency": "USD",
                "settlementDate": "2026-10-31",
                "baseRate": 1350,
            },
            {
                "tradeDirection": "IMPORT",
                "foreignAmount": 5000000,
                "currency": "JPY",
                "settlementDate": "2026-11-30",
                "baseRate": 9.1,
            },
        ],
        "strategyContext": {
            "groupTargets": [
                {"exposureGroupId": "EXPORT-USD", "targetHedgeRatio": 0.5},
                {"exposureGroupId": "IMPORT-JPY", "targetHedgeRatio": 0.5},
            ],
            "strategies": [
                {"exposureGroupId": "EXPORT-USD", "strategyType": "FX_INSURANCE_GENERAL", "allocationRatio": 0.6, "priority": 1},
                {"exposureGroupId": "EXPORT-USD", "strategyType": "FORWARD", "allocationRatio": 0.4, "priority": 2},
                {"exposureGroupId": "IMPORT-JPY", "strategyType": "IMPORT_PAYMENT_DEFERRAL", "allocationRatio": 1.0, "priority": 1},
            ],
        },
        "options": {"maxCards": 10},
    }


# 1. USD/JPY 서로 다른 baseRate ------------------------------------------------


def test_different_base_rate_per_currency(client):
    body = client.post("/recommend", json=_verification_scenario_payload()).json()
    usd_cards = _cards_by_group(body, "FX-HEDGE-001")  # FORWARD, EXPORT-USD만
    assert "EXPORT-USD" in usd_cards
    usd = usd_cards["EXPORT-USD"]
    # groupExposureKrw = 200,000 * 1,350 = 270,000,000 (JPY의 9.1이 섞이지 않음)
    assert usd["groupExposureKrw"] == 270_000_000

    jpy_cards = _cards_by_group(body, "IMPORT-001")
    jpy = jpy_cards["IMPORT-JPY"]
    # groupExposureKrw = 5,000,000 * 9.1 = 45,500,000 (USD의 1,350이 섞이지 않음)
    assert jpy["groupExposureKrw"] == 45_500_000


# 2. 계약별 exposureKrw 우선 사용 -----------------------------------------------


def test_contract_exposure_krw_takes_priority_over_base_rate(client):
    payload = base_payload()
    # foreignAmount*baseRate로 계산하면 220,000*1363.64≈300,000,800이지만
    # exposureKrw를 직접 주면 그 값을 그대로 써야 한다.
    payload["contracts"][0]["exposureKrw"] = 250_000_000
    payload["contracts"][0]["baseRate"] = 1363.64
    body = client.post("/recommend", json=payload).json()
    card = next(c for c in body["cards"] if c["productId"] == "FX-HEDGE-001")
    assert card["groupExposureKrw"] == 250_000_000
    assert card["exposureCalculationStatus"] == "PROVIDED"


# 3. 다중 통화, 계약별 환율 없음 → 금액 생성하지 않음 ---------------------------


def test_multi_currency_without_contract_rate_returns_null_not_guess(client):
    payload = {
        "companyProfile": {"tradeDirection": "BOTH", "currencies": ["USD", "JPY"]},
        "contracts": [
            {"tradeDirection": "EXPORT", "foreignAmount": 200000, "currency": "USD"},  # baseRate/exposureKrw 없음
            {"tradeDirection": "IMPORT", "foreignAmount": 5000000, "currency": "JPY"},  # baseRate/exposureKrw 없음
        ],
        "riskContext": {"exposureKrw": 999_999_999},  # 다중 그룹이라 이 집계값은 쓰면 안 됨
        "strategyContext": {
            "strategies": [
                {"exposureGroupId": "EXPORT-USD", "strategyType": "FORWARD", "allocationRatio": 1.0},
                {"exposureGroupId": "IMPORT-JPY", "strategyType": "IMPORT_PAYMENT_DEFERRAL", "allocationRatio": 1.0},
            ]
        },
    }
    body = client.post("/recommend", json=payload).json()
    for c in body["cards"]:
        assert c["groupExposureKrw"] is None, c["productId"]
        assert c["recommendedHedgeAmountKrw"] is None
        assert c["exposureCalculationStatus"] in ("MISSING_RATE", "MISSING_EXPOSURE")
        assert any("환율" in p or "노출액" in p for p in c["pendingConditions"])


# 4~5. 노출 그룹별 allocationRatio 합계 검증 ------------------------------------


def test_allocation_ratio_validated_per_exposure_group(client):
    """서로 다른 두 그룹에서 각각 allocationRatio 1.0까지 허용된다(합쳐서
    2.0이어도 그룹이 다르면 유효)."""
    payload = _verification_scenario_payload()
    payload["strategyContext"]["strategies"] = [
        {"exposureGroupId": "EXPORT-USD", "strategyType": "FORWARD", "allocationRatio": 1.0},
        {"exposureGroupId": "IMPORT-JPY", "strategyType": "IMPORT_PAYMENT_DEFERRAL", "allocationRatio": 1.0},
    ]
    resp = client.post("/recommend", json=payload)
    assert resp.status_code == 200


def test_allocation_ratio_over_1_within_same_group_returns_422(client):
    payload = base_payload()  # 단일 그룹(EXPORT-USD)
    payload["strategyContext"]["strategies"] = [
        {"strategyType": "FX_INSURANCE_GENERAL", "allocationRatio": 0.7},
        {"strategyType": "FORWARD", "allocationRatio": 0.5},  # 0.7+0.5=1.2 > 1.0
    ]
    resp = client.post("/recommend", json=payload)
    assert resp.status_code == 422
    assert "exceeds 1.0" in resp.text


def test_allocation_ratio_over_1_with_explicit_group_ids_returns_422(client):
    payload = _verification_scenario_payload()
    payload["strategyContext"]["strategies"] = [
        {"exposureGroupId": "EXPORT-USD", "strategyType": "FX_INSURANCE_GENERAL", "allocationRatio": 0.7},
        {"exposureGroupId": "EXPORT-USD", "strategyType": "FORWARD", "allocationRatio": 0.5},
    ]
    resp = client.post("/recommend", json=payload)
    assert resp.status_code == 422


# 7. 카드별 추천금액 합계가 그룹 목표 헤지금액을 초과하지 않음 -------------------


def test_card_amounts_do_not_exceed_group_target_hedge_amount(client):
    body = client.post("/recommend", json=_verification_scenario_payload()).json()
    usd_cards = [c for c in body["cards"] if c["exposureGroupId"] == "EXPORT-USD"]
    target = usd_cards[0]["groupTargetHedgeAmountKrw"]
    assert target == 270_000_000 * 0.5  # groupExposureKrw(270,000,000) * targetHedgeRatio(0.5)
    total = sum(c["recommendedHedgeAmountKrw"] for c in usd_cards)
    assert total <= target + 1


# 8. 다른 통화 계약금액이 서로 섞이지 않음 ---------------------------------------


def test_different_currency_amounts_never_mix(client):
    body = client.post("/recommend", json=_verification_scenario_payload()).json()
    usd_card = next(c for c in body["cards"] if c["exposureGroupId"] == "EXPORT-USD")
    jpy_card = next(c for c in body["cards"] if c["exposureGroupId"] == "IMPORT-JPY")
    assert usd_card["groupExposureKrw"] == 270_000_000
    assert jpy_card["groupExposureKrw"] == 45_500_000
    assert usd_card["groupExposureKrw"] != jpy_card["groupExposureKrw"]
    assert set(usd_card["coveredContractIndexes"]) & set(jpy_card["coveredContractIndexes"]) == set()


# 9. 단일 노출 그룹 기존 요청 호환성 유지 ----------------------------------------


def test_single_group_backward_compatibility(client):
    """노출 그룹이 하나면 exposureGroupId/groupTargets에 exposureGroupId를
    생략해도 자동 연결되고, riskContext.exposureKrw가 그대로 쓰인다."""
    body = client.post("/recommend", json=base_payload()).json()
    assert body["cards"]
    for c in body["cards"]:
        assert c["exposureGroupId"] == "EXPORT-USD"
        assert c["groupExposureKrw"] == 300_000_000  # riskContext.exposureKrw
        assert c["exposureCalculationStatus"] == "PROVIDED"
        assert c["targetHedgeRatio"] == 0.5
        assert c["recommendedHedgeAmountKrw"] is not None


# 10. 동일 요청의 금액·순위 결정론 유지 -------------------------------------------


def test_deterministic_amounts_and_ranking(client):
    payload = _verification_scenario_payload()
    r1 = client.post("/recommend", json=copy.deepcopy(payload)).json()
    r2 = client.post("/recommend", json=copy.deepcopy(payload)).json()
    sig1 = [
        (c["productId"], c["exposureGroupId"], c["fitScore"], c["recommendedHedgeAmountKrw"], c["rank"])
        for c in r1["cards"]
    ]
    sig2 = [
        (c["productId"], c["exposureGroupId"], c["fitScore"], c["recommendedHedgeAmountKrw"], c["rank"])
        for c in r2["cards"]
    ]
    assert sig1 == sig2
