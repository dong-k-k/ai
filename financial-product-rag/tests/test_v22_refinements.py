"""v2.2 연동 전 핵심 보완 테스트:
1) 카드 정렬 기준(priority→fitScore→allocationRatio→상품명)
2) 수출입 겸업 혼합 계약(노출 그룹화)
3) recommendedHedgeAmountKrw 불변조건
4) requestedProductNames 정규화 전체일치 매칭(오탐 방지)
5) 정의되지 않은 요청 필드 422(extra=forbid)
"""
from __future__ import annotations

from tests.conftest import base_payload


def _cards_by_id(body: dict) -> dict:
    return {c["productId"]: c for c in body["cards"]}


# 1. 카드 정렬 기준 ---------------------------------------------------------


def test_sort_priority_overrides_fit_score(client):
    """priority=1인 전략의 상품이, 관찰 조건 부족으로 fitScore가 더 높은
    priority=2 전략의 상품보다 항상 먼저 나와야 한다."""
    payload = base_payload()
    payload["strategyContext"] = {
        "strategies": [
            {"strategyType": "FOREIGN_CURRENCY_DEPOSIT", "allocationRatio": 0.5, "priority": 1},
            {"strategyType": "FORWARD", "allocationRatio": 0.5, "priority": 2},
        ]
    }
    payload["options"]["maxCards"] = 5
    body = client.post("/recommend", json=payload).json()
    cards = _cards_by_id(body)
    assert "FX-DEPOSIT-001" in cards or "FX-DEPOSIT-003" in cards
    deposit_card = cards.get("FX-DEPOSIT-001") or cards.get("FX-DEPOSIT-003")
    forward_card = cards.get("FX-HEDGE-001")
    assert forward_card is not None
    # priority=1(외화예금)이 priority=2(선물환)보다 먼저 나와야 한다 —
    # fitScore 크기와 무관하게.
    assert deposit_card["rank"] < forward_card["rank"]


def test_sort_ties_broken_by_fit_score_then_allocation_then_name(client):
    """같은 priority(둘 다 미지정=None)일 때는 fitScore 내림차순 → 동점이면
    allocationRatio 내림차순 → 그래도 동점이면 상품명 순으로만 최종 결정."""
    payload = base_payload()
    payload["strategyContext"] = {
        "strategies": [
            {"strategyType": "FX_INSURANCE_GENERAL", "allocationRatio": 0.7},
            {"strategyType": "FORWARD", "allocationRatio": 0.3},
        ]
    }
    body = client.post("/recommend", json=payload).json()
    scores = [(c["fitScore"], c["allocationRatio"], c["productName"]) for c in body["cards"]]
    assert scores == sorted(scores, key=lambda x: (-x[0], -x[1], x[2]))


def test_scenario1_card_order_matches_strategy_priority(client):
    """같은 전략 입력(KSURE priority1, FORWARD priority2)에서 카드 순위가
    전략 우선순위와 일치하는지."""
    body = client.post("/recommend", json=base_payload()).json()
    order = [c["productId"] for c in body["cards"]]
    assert order.index("KSURE-FX-001") < order.index("FX-HEDGE-001")


# 2. 수출입 겸업 혼합 계약(노출 그룹화) ---------------------------------------


def test_mixed_export_import_currency_groups_produce_separate_candidates(client):
    payload = {
        "companyProfile": {
            "tradeDirection": "BOTH",
            "currencies": ["USD", "JPY"],
            "paymentTerms": ["T/T"],
        },
        "contracts": [
            {"tradeDirection": "EXPORT", "foreignAmount": 200000, "currency": "USD", "settlementDate": "2026-10-31"},
            {"tradeDirection": "IMPORT", "foreignAmount": 5000000, "currency": "JPY", "settlementDate": "2026-11-30"},
        ],
        # allocationRatio 합계 검증은 이제 노출 그룹별이라, 서로 다른
        # 그룹은 각각 최대 1.0까지 배분할 수 있다 — exposureGroupId를
        # 명시해 각 전략이 어느 그룹에 적용되는지 분명히 한다.
        "strategyContext": {
            "strategies": [
                {"exposureGroupId": "EXPORT-USD", "strategyType": "FORWARD", "allocationRatio": 1.0, "priority": 1},
                {
                    "exposureGroupId": "IMPORT-JPY",
                    "strategyType": "FORWARD",
                    "allocationRatio": 0.5,
                    "priority": 1,
                },
                {
                    "exposureGroupId": "IMPORT-JPY",
                    "strategyType": "IMPORT_PAYMENT_DEFERRAL",
                    "allocationRatio": 0.5,
                    "priority": 2,
                },
            ]
        },
        "options": {"maxCards": 10},
    }
    body = client.post("/recommend", json=payload).json()

    # FORWARD는 방향·통화 제한이 없는 범용 상품이라 두 노출 그룹
    # (EXPORT-USD, IMPORT-JPY) 각각에 "별도의 상품 후보"로 등장해야 한다 —
    # 하나로 뭉뚱그리지 않는다.
    forward_cards = [c for c in body["cards"] if c["productId"] == "FX-HEDGE-001"]
    assert len(forward_cards) == 2
    groups_covered = {c["exposureGroupId"] for c in forward_cards}
    assert groups_covered == {"EXPORT-USD", "IMPORT-JPY"}

    usd_card = next(c for c in forward_cards if c["exposureGroupId"] == "EXPORT-USD")
    jpy_forward_card = next(c for c in forward_cards if c["exposureGroupId"] == "IMPORT-JPY")
    assert usd_card["coveredTradeDirection"] == "EXPORT"
    assert usd_card["coveredCurrency"] == "USD"
    assert usd_card["coveredContractIndexes"] == [0]
    assert jpy_forward_card["coveredTradeDirection"] == "IMPORT"
    assert jpy_forward_card["coveredCurrency"] == "JPY"
    assert jpy_forward_card["coveredContractIndexes"] == [1]
    # 서로 다른 그룹의 계약이 서로의 카드에 섞이지 않는다.
    assert set(usd_card["coveredContractIndexes"]) & set(jpy_forward_card["coveredContractIndexes"]) == set()

    import_cards = [c for c in body["cards"] if c["productId"] == "IMPORT-001"]
    assert len(import_cards) == 1  # IMPORT_PAYMENT_DEFERRAL은 IMPORT 전용이라 JPY 그룹에만 적용
    ic = import_cards[0]
    assert ic["coveredTradeDirection"] == "IMPORT"
    assert ic["coveredCurrency"] == "JPY"
    assert ic["coveredContractIndexes"] == [1]
    assert ic["exposureGroupId"] == "IMPORT-JPY"


def test_mixed_groups_do_not_cross_contaminate_eligibility(client):
    """FORWARD는 min_days=3 조건이 있다 — USD-EXPORT 그룹만 그 조건으로
    판정되고, JPY-IMPORT 그룹의 결제일이 이 판정에 영향을 주면 안 된다."""
    payload = {
        "companyProfile": {"tradeDirection": "BOTH", "currencies": ["USD", "JPY"]},
        "contracts": [
            {"tradeDirection": "EXPORT", "foreignAmount": 100000, "currency": "USD", "settlementDate": "2026-08-03"},  # 내일 (min_days=3 미달)
            {"tradeDirection": "IMPORT", "foreignAmount": 1000000, "currency": "JPY", "settlementDate": "2026-12-31"},  # 충분히 남음
        ],
        # 노출 그룹이 둘이라 각 전략에 exposureGroupId를 명시한다.
        "strategyContext": {
            "strategies": [
                {"exposureGroupId": "EXPORT-USD", "strategyType": "FORWARD", "allocationRatio": 1.0},
                {"exposureGroupId": "IMPORT-JPY", "strategyType": "FORWARD", "allocationRatio": 1.0},
            ]
        },
    }
    body = client.post("/recommend", json=payload).json()
    # USD-EXPORT 그룹(min_days=3 미달)의 몫만 카드에서 빠지고, JPY-IMPORT
    # 그룹(기간 충분)의 FORWARD 후보는 영향을 받지 않아야 한다.
    forward_cards = [c for c in body["cards"] if c["productId"] == "FX-HEDGE-001"]
    assert all(c["exposureGroupId"] != "EXPORT-USD" for c in forward_cards)
    assert any(c["exposureGroupId"] == "IMPORT-JPY" for c in forward_cards)

    excluded_usd = [
        e for e in body["excludedProducts"] if e["productId"] == "FX-HEDGE-001" and e["exposureGroupId"] == "EXPORT-USD"
    ]
    assert excluded_usd and excluded_usd[0]["eligibilityStatus"] == "NOT_RECOMMENDED"


# 3. recommendedHedgeAmountKrw 불변조건 ---------------------------------------


def test_hedge_amount_non_negative(client):
    body = client.post("/recommend", json=base_payload()).json()
    for c in body["cards"]:
        if c["recommendedHedgeAmountKrw"] is not None:
            assert c["recommendedHedgeAmountKrw"] >= 0


def test_hedge_amount_excludes_uncovered_contracts(client):
    """USD 수출 계약과 JPY 수입 계약이 섞인 요청에서, FORWARD(USD-EXPORT
    전용) 카드의 헤지금액이 JPY 계약금액을 포함해서는 안 된다."""
    payload = {
        "companyProfile": {"tradeDirection": "BOTH", "currencies": ["USD", "JPY"]},
        "contracts": [
            {"tradeDirection": "EXPORT", "foreignAmount": 100000, "currency": "USD", "settlementDate": "2026-10-31", "baseRate": 1350},
            {"tradeDirection": "IMPORT", "foreignAmount": 50000000, "currency": "JPY", "settlementDate": "2026-11-30", "baseRate": 9.1},
        ],
        "strategyContext": {
            "hedgeTargetMax": 1.0,
            "groupTargets": [
                {"exposureGroupId": "EXPORT-USD", "targetHedgeRatio": 1.0},
                {"exposureGroupId": "IMPORT-JPY", "targetHedgeRatio": 1.0},
            ],
            "strategies": [
                {"exposureGroupId": "EXPORT-USD", "strategyType": "FORWARD", "allocationRatio": 1.0},
                {"exposureGroupId": "IMPORT-JPY", "strategyType": "FORWARD", "allocationRatio": 1.0},
            ],
        },
    }
    body = client.post("/recommend", json=payload).json()
    forward_cards = [c for c in body["cards"] if c["productId"] == "FX-HEDGE-001"]
    usd_card = next(c for c in forward_cards if c["exposureGroupId"] == "EXPORT-USD")
    jpy_card = next(c for c in forward_cards if c["exposureGroupId"] == "IMPORT-JPY")
    # USD 100,000 * 1350(계약별 baseRate) * targetHedgeRatio(1.0) * allocation(1.0)
    assert usd_card["groupExposureKrw"] == 135_000_000
    assert usd_card["recommendedHedgeAmountKrw"] == 135_000_000
    # 반대로 JPY 카드에는 USD 계약금액이 섞이면 안 됨: 50,000,000 * 9.1(JPY 자신의 baseRate)
    assert jpy_card["groupExposureKrw"] == 455_000_000
    assert jpy_card["recommendedHedgeAmountKrw"] == 455_000_000


def test_hedge_amount_sum_does_not_exceed_group_total_exposure(client):
    """카드별 추천금액(recommendedHedgeAmountKrw) 합계는 그 그룹의
    목표 헤지금액(groupTargetHedgeAmountKrw)을 넘을 수 없다 — allocationRatio
    합계가 그룹별로 1.0을 넘지 못하도록 검증되기 때문에 구조적으로 보장된다."""
    payload = base_payload()  # KSURE 0.5 + FORWARD 0.5, 둘 다 같은 EXPORT-USD 그룹
    body = client.post("/recommend", json=payload).json()
    cards = body["cards"]
    assert len(cards) == 2
    group_target = cards[0]["groupTargetHedgeAmountKrw"]
    assert group_target is not None
    assert all(c["groupTargetHedgeAmountKrw"] == group_target for c in cards)
    total = sum(c["recommendedHedgeAmountKrw"] for c in cards if c["recommendedHedgeAmountKrw"] is not None)
    assert total <= group_target + 1  # 반올림 오차 허용


def test_hedge_amount_no_double_counting_across_installments(client):
    """분할 결제 2건이 같은 그룹(EXPORT-USD)에 속할 때, 헤지금액은 두 계약
    금액의 합만 반영해야 한다(중복 합산 없음)."""
    payload = base_payload()
    payload["contracts"] = [
        {"tradeDirection": "EXPORT", "foreignAmount": 100000, "currency": "USD", "settlementDate": "2026-09-30", "installmentOrder": 1, "baseRate": 1350},
        {"tradeDirection": "EXPORT", "foreignAmount": 100000, "currency": "USD", "settlementDate": "2026-11-30", "installmentOrder": 2, "baseRate": 1350},
    ]
    del payload["riskContext"]["exposureKrw"]  # 계약별 baseRate 기반 계산 강제
    payload["strategyContext"]["groupTargets"] = [{"targetHedgeRatio": 1.0}]
    payload["strategyContext"]["strategies"] = [{"strategyType": "FORWARD", "allocationRatio": 1.0}]
    body = client.post("/recommend", json=payload).json()
    card = _cards_by_id(body)["FX-HEDGE-001"]
    # (100,000 + 100,000) * 1350 * targetHedgeRatio(1.0) * allocation(1.0) = 270,000,000
    assert card["groupExposureKrw"] == 270_000_000
    assert card["recommendedHedgeAmountKrw"] == 270_000_000
    assert card["exposureCalculationStatus"] == "CALCULATED"


# 4. requestedProductNames 정규화 매칭(오탐 방지) ------------------------------


def test_partial_substring_does_not_falsely_match(client):
    """다른 상품명의 일부 문자열만 겹치는 경우 매칭되면 안 된다. "MAR"는
    "MARS"(review_queue 별칭), "Market Average Rate"(상품 별칭)의 부분
    문자열이지만 어느 쪽과도 완전히 같지 않으므로 NOT_VERIFIED여야 한다
    (개편 전 substring 매칭이었다면 "MARS"/"Market Average Rate"에 걸려
    잘못 매칭됐을 사례)."""
    payload = base_payload()
    payload["requestedProductNames"] = ["MAR"]
    body = client.post("/recommend", json=payload).json()
    notice = body["verificationNotices"][0]
    assert notice["status"] == "NOT_VERIFIED"
    assert notice["action"] == "EXCLUDE"


def test_kb_mars_scenario_still_resolves_via_normalization(client):
    payload = base_payload()
    payload["requestedProductNames"] = ["kb   mars"]  # 대소문자/공백 변형
    body = client.post("/recommend", json=payload).json()
    notice = body["verificationNotices"][0]
    assert notice["canonicalName"] == "MAR 거래"


def test_kb_fx_matching_scenario_still_excluded(client):
    payload = base_payload()
    payload["requestedProductNames"] = ["KB FX Matching"]
    body = client.post("/recommend", json=payload).json()
    notice = body["verificationNotices"][0]
    assert notice["status"] == "NOT_VERIFIED"
    assert notice["action"] == "EXCLUDE"


def test_kb_one_trade_scenario_still_excluded(client):
    payload = base_payload()
    payload["requestedProductNames"] = ["KB ONE TRADE"]
    body = client.post("/recommend", json=payload).json()
    notice = body["verificationNotices"][0]
    assert notice["status"] == "RETIRED"
    assert notice["action"] == "EXCLUDE"


# 5. 정의되지 않은 요청 필드 -----------------------------------------------------


def test_unknown_top_level_field_returns_422(client):
    payload = base_payload()
    payload["someUnknownField"] = "x"
    resp = client.post("/recommend", json=payload)
    assert resp.status_code == 422


def test_unknown_nested_field_returns_422(client):
    payload = base_payload()
    payload["riskContext"]["someUnknownField"] = 1
    resp = client.post("/recommend", json=payload)
    assert resp.status_code == 422
