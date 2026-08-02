"""v2.4: 존재하지 않거나 누락된 exposureGroupId를 조용히 무시하지 않고
구조화된 422로 명시적으로 거부한다."""
from __future__ import annotations

from tests.conftest import base_payload


def _mixed_payload() -> dict:
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


# 1. 존재하지 않는 strategy exposureGroupId → 422 ------------------------------


def test_unknown_strategy_exposure_group_id_returns_422(client):
    payload = _mixed_payload()
    payload["strategyContext"]["strategies"][1]["exposureGroupId"] = "EXPORT-EUR"  # 존재하지 않는 그룹
    resp = client.post("/recommend", json=payload)
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["error"] == "unknown_exposure_group_id"
    assert detail["invalidExposureGroupId"] == "EXPORT-EUR"
    assert detail["field"] == "strategyContext.strategies[1].exposureGroupId"
    assert set(detail["availableExposureGroupIds"]) == {"EXPORT-USD", "IMPORT-JPY"}


# 2. 존재하지 않는 groupTargets exposureGroupId → 422 --------------------------


def test_unknown_group_targets_exposure_group_id_returns_422(client):
    payload = _mixed_payload()
    payload["strategyContext"]["groupTargets"][0]["exposureGroupId"] = "EXPORT-GBP"
    resp = client.post("/recommend", json=payload)
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["error"] == "unknown_exposure_group_id"
    assert detail["invalidExposureGroupId"] == "EXPORT-GBP"
    assert detail["field"] == "strategyContext.groupTargets[0].exposureGroupId"
    assert set(detail["availableExposureGroupIds"]) == {"EXPORT-USD", "IMPORT-JPY"}


# 3. 다중 그룹에서 exposureGroupId 누락 → 422 -----------------------------------


def test_missing_exposure_group_id_in_multi_group_request_returns_422(client):
    payload = _mixed_payload()
    del payload["strategyContext"]["strategies"][2]["exposureGroupId"]  # IMPORT_PAYMENT_DEFERRAL, 3번째(index 2)
    resp = client.post("/recommend", json=payload)
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["error"] == "missing_exposure_group_id"
    assert detail["field"] == "strategyContext.strategies[2].exposureGroupId"
    assert set(detail["availableExposureGroupIds"]) == {"EXPORT-USD", "IMPORT-JPY"}


def test_missing_exposure_group_id_in_group_targets_multi_group_returns_422(client):
    payload = _mixed_payload()
    del payload["strategyContext"]["groupTargets"][1]["exposureGroupId"]
    resp = client.post("/recommend", json=payload)
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["error"] == "missing_exposure_group_id"
    assert detail["field"] == "strategyContext.groupTargets[1].exposureGroupId"


# 4. 단일 그룹에서 exposureGroupId 생략 → 자동 연결 및 200 -----------------------


def test_single_group_omitted_exposure_group_id_still_works(client):
    payload = base_payload()  # 단일 그룹(EXPORT-USD), strategies에 exposureGroupId 없음
    resp = client.post("/recommend", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["cards"]
    assert all(c["exposureGroupId"] == "EXPORT-USD" for c in body["cards"])


# 5. availableExposureGroupIds가 오류 응답에 포함 --------------------------------


def test_available_exposure_group_ids_included_in_error(client):
    payload = _mixed_payload()
    payload["strategyContext"]["strategies"][0]["exposureGroupId"] = "NOT-A-GROUP"
    resp = client.post("/recommend", json=payload)
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert "availableExposureGroupIds" in detail
    assert sorted(detail["availableExposureGroupIds"]) == ["EXPORT-USD", "IMPORT-JPY"]


# 6. 기존 다중통화 금액 계산 결과 유지 --------------------------------------------


def test_existing_multi_currency_amount_calculation_unchanged(client):
    """v2.3에서 검증했던 시나리오(EXPORT USD 200,000/1,350, IMPORT JPY
    5,000,000/9.1, 그룹별 targetHedgeRatio 0.5)가 이번 변경 후에도 동일한
    금액을 낸다."""
    body = client.post("/recommend", json=_mixed_payload()).json()
    usd_cards = {c["productId"]: c for c in body["cards"] if c["exposureGroupId"] == "EXPORT-USD"}
    jpy_cards = {c["productId"]: c for c in body["cards"] if c["exposureGroupId"] == "IMPORT-JPY"}

    assert usd_cards["KSURE-FX-001"]["groupExposureKrw"] == 270_000_000
    assert usd_cards["KSURE-FX-001"]["recommendedHedgeAmountKrw"] == 81_000_000
    assert usd_cards["FX-HEDGE-001"]["recommendedHedgeAmountKrw"] == 54_000_000
    assert jpy_cards["IMPORT-001"]["groupExposureKrw"] == 45_500_000
    assert jpy_cards["IMPORT-001"]["recommendedHedgeAmountKrw"] == 22_750_000


# riskContext.baseRate는 여전히 계산에 쓰이지 않음(deprecated 유지 확인) -------


def test_deprecated_risk_context_base_rate_still_unused_in_calculation(client):
    payload = base_payload()
    with_rate = client.post("/recommend", json=payload).json()

    payload2 = base_payload()
    payload2["riskContext"]["baseRate"] = 99999  # 말도 안 되는 값을 넣어도
    without_effect = client.post("/recommend", json=payload2).json()

    amounts_a = [(c["productId"], c["recommendedHedgeAmountKrw"]) for c in with_rate["cards"]]
    amounts_b = [(c["productId"], c["recommendedHedgeAmountKrw"]) for c in without_effect["cards"]]
    assert amounts_a == amounts_b
