"""API 테스트."""
from __future__ import annotations

from tests.conftest import base_payload


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_recommend_valid_request(client):
    resp = client.post("/recommend", json=base_payload())
    assert resp.status_code == 200


def test_recommend_invalid_enum_returns_422(client):
    payload = base_payload()
    payload["companyProfile"]["tradeDirection"] = "NOT_A_DIRECTION"
    resp = client.post("/recommend", json=payload)
    assert resp.status_code == 422


def test_recommend_negative_amount_returns_422(client):
    payload = base_payload()
    payload["contracts"][0]["foreignAmount"] = -100
    resp = client.post("/recommend", json=payload)
    assert resp.status_code == 422


def test_recommend_negative_remaining_days_returns_422(client):
    payload = base_payload()
    payload["riskContext"]["remainingDays"] = -1
    resp = client.post("/recommend", json=payload)
    assert resp.status_code == 422


def test_recommend_hedge_target_min_gt_max_returns_422(client):
    payload = base_payload()
    payload["strategyContext"]["hedgeTargetMin"] = 0.8
    payload["strategyContext"]["hedgeTargetMax"] = 0.2
    resp = client.post("/recommend", json=payload)
    assert resp.status_code == 422


def test_recommend_currency_mismatch_returns_422(client):
    payload = base_payload()
    payload["companyProfile"]["currencies"] = ["EUR"]
    payload["contracts"][0]["currency"] = "USD"
    resp = client.post("/recommend", json=payload)
    assert resp.status_code == 422


def test_recommend_max_cards_out_of_range_returns_422(client):
    payload = base_payload()
    payload["options"]["maxCards"] = 20
    resp = client.post("/recommend", json=payload)
    assert resp.status_code == 422


def test_recommend_empty_contracts_returns_422(client):
    payload = base_payload()
    payload["contracts"] = []
    resp = client.post("/recommend", json=payload)
    assert resp.status_code == 422


def test_recommend_removed_fields_are_rejected_with_422(client):
    """companySize/hasExportPerformance/kSureEligible 등은 요청 모델에
    아예 존재하지 않는다. extra="forbid"로, 조용히 무시하는 대신 422로
    명시적으로 거부한다 — 호출 측이 "반영됐는지 무시됐는지" 헷갈릴 여지를
    없앤다(아직 외부 연동 전이라 지금 엄격하게 강제해도 무방)."""
    for field_name, value in (
        ("companySize", "SME"),
        ("kSureEligible", True),
        ("hasExportPerformance", True),
        ("hasForeignCurrencySurplus", True),
        ("importItemEligible", True),
    ):
        payload = base_payload()
        payload["companyProfile"][field_name] = value
        resp = client.post("/recommend", json=payload)
        assert resp.status_code == 422, field_name
        assert "extra_forbidden" in resp.text or "Extra inputs are not permitted" in resp.text


def test_recommend_no_matching_cards_returns_200_with_empty_list_and_notice(client):
    payload = {
        "companyProfile": {"tradeDirection": "IMPORT", "currencies": ["JPY"]},
        "contracts": [{"tradeDirection": "IMPORT", "foreignAmount": 1000, "currency": "JPY"}],
        "strategyContext": {"strategies": [{"strategyType": "EXPORT_RECEIVABLE_FINANCE", "allocationRatio": 1.0}]},
    }
    resp = client.post("/recommend", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["cards"] == []
    assert body["notices"]


def test_sources_existing_returns_200(client):
    resp = client.get("/sources/SRC-017")
    assert resp.status_code == 200
    assert resp.json()["sourceId"] == "SRC-017"


def test_sources_missing_returns_404(client):
    resp = client.get("/sources/NOT-EXIST")
    assert resp.status_code == 404
    assert resp.json()["detail"]["error"] == "source_not_found"


def test_products_existing_returns_200(client):
    resp = client.get("/products/FX-HEDGE-001")
    assert resp.status_code == 200
    assert resp.json()["productId"] == "FX-HEDGE-001"


def test_products_missing_returns_404(client):
    resp = client.get("/products/NOT-EXIST")
    assert resp.status_code == 404


def test_products_evidence_returns_200(client):
    resp = client.get("/products/FX-HEDGE-004/evidence")
    assert resp.status_code == 200
    body = resp.json()
    assert body["sourceIds"]
    assert any(g["documentId"] == "GUIDE-KB-OTC-001" for g in body["relatedGuides"])


def test_rag_endpoint_still_returns_410(client):
    resp = client.post("/rag", json={"question": "test"})
    assert resp.status_code == 410
    assert resp.json()["detail"]["error"] == "endpoint_removed"


def test_search_debug_endpoint_still_works(client):
    resp = client.post("/search", json={"query": "선물환 취소", "top_k": 3})
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_openapi_schema_is_generated(client):
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    schema = resp.json()
    assert "/recommend" in schema["paths"]
    assert "/rag" in schema["paths"]
