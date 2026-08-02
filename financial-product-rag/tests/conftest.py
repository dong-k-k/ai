import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def base_payload() -> dict:
    """수출기업 혼합 헤지 시나리오의 기본 요청 바디. 각 테스트가 필요한
    부분만 얕게 덮어써서 재사용합니다. companySize/hasExportPerformance/
    kSureEligible처럼 서비스가 실제로 갖고 있지 않은 값은 어디에도 없습니다."""
    return {
        "companyProfile": {
            "tradeDirection": "EXPORT",
            "industry": "MANUFACTURING",
            "mainCountries": ["US"],
            "currencies": ["USD"],
            "monthlyTradeVolumeKrw": 300000000,
            "paymentTerms": ["T/T"],
            "currentlyHedging": False,
        },
        "contracts": [
            {
                "tradeDirection": "EXPORT",
                "foreignAmount": 220000,
                "currency": "USD",
                "settlementDate": "2026-10-31",
                "installmentOrder": 1,
            }
        ],
        "riskContext": {
            "exposureKrw": 300000000,
            "baseRate": 1363.64,
            "breakEvenRate": 1290,
            "remainingDays": 90,
            "remainingBusinessDays": 64,
            "expectedLossRate": 0.062,
            "expectedShortfallKrw": 18600000,
            "riskLevel": "HIGH",
            "riskPreference": "NEUTRAL",
        },
        "strategyContext": {
            "hedgeTargetMin": 0.2,
            "hedgeTargetMax": 0.5,
            # 노출 그룹이 하나뿐이라 groupTargets[].exposureGroupId는 생략해도
            # 자동으로 그 그룹에 연결된다.
            "groupTargets": [{"targetHedgeRatio": 0.5}],
            "strategies": [
                {"strategyType": "FX_INSURANCE_GENERAL", "allocationRatio": 0.5, "priority": 1},
                {"strategyType": "FORWARD", "allocationRatio": 0.5, "priority": 2},
            ],
        },
        "options": {"maxCards": 3, "includeConditional": True, "includeEvidenceMap": True},
    }
