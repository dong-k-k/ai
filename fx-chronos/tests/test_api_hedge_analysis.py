from __future__ import annotations

import asyncio
import unittest
from datetime import date, datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from src.api.forecast_service import ForecastService, ForecastSnapshot
from src.api.main import create_app
from src.api.scheduler import create_scheduler, reload_forecasts_safely
from src.hedging.forecast_provider import ForecastScenario, ScenarioSource


SETTLEMENT_DATE = date(2026, 10, 30)
SEOUL = ZoneInfo("Asia/Seoul")


def scenario() -> ForecastScenario:
    return ForecastScenario(
        model_name="test fixed alpha ensemble",
        scenario_source=ScenarioSource.SHRUNK_ENSEMBLE,
        currency_pair="USD/KRW",
        unit="KRW per USD",
        forecast_origin=date(2026, 7, 30),
        prediction_length=1,
        forecast_dates=(SETTLEMENT_DATE,),
        point_forecast=(1550.0,),
        lower_scenario=(1500.0,),
        median_scenario=(1552.0,),
        upper_scenario=(1600.0,),
        warning="test warning",
    )


def h90_scenario() -> ForecastScenario:
    dates = tuple(pd.bdate_range("2026-07-31", periods=90).date)
    return ForecastScenario(
        model_name="test fixed alpha ensemble H90",
        scenario_source=ScenarioSource.SHRUNK_ENSEMBLE,
        currency_pair="USD/KRW",
        unit="KRW per USD",
        forecast_origin=date(2026, 7, 30),
        prediction_length=90,
        forecast_dates=dates,
        point_forecast=tuple(1500.0 + index for index in range(90)),
        lower_scenario=tuple(1450.0 + index for index in range(90)),
        median_scenario=tuple(1502.0 + index for index in range(90)),
        upper_scenario=tuple(1550.0 + index for index in range(90)),
        warning="test warning",
    )


class FakeForecastService:
    def __init__(self) -> None:
        self.initialize_calls = 0
        self.forecast_calls = 0
        self.h90_calls = 0

    def initialize(self) -> None:
        self.initialize_calls += 1

    def forecast_for_settlement(self, settlement_date: date) -> ForecastScenario:
        self.forecast_calls += 1
        if settlement_date != SETTLEMENT_DATE:
            raise ValueError("결제일이 예측 범위에 없습니다.")
        return scenario()

    def h90_forecast(self) -> tuple[datetime, ForecastScenario]:
        self.h90_calls += 1
        return datetime(2026, 8, 3, 3, 0, tzinfo=SEOUL), h90_scenario()


VALID_REQUEST = {
    "currency_pair": "USD/KRW",
    "side": "PAYABLE",
    "foreign_amount": 1_000_000,
    "settlement_date": "2026-10-30",
    "reference_rate": 1548.4,
    "hedged_amount": 500_000,
    "hedge_rate": 1548.4,
}


class HedgeAnalysisApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.service = FakeForecastService()
        self.client_context = TestClient(
            create_app(forecast_service=self.service, enable_scheduler=False)
        )
        self.client = self.client_context.__enter__()

    def tearDown(self) -> None:
        self.client_context.__exit__(None, None, None)

    def test_valid_request_returns_complete_result(self) -> None:
        response = self.client.post("/internal/hedge-analysis", json=VALID_REQUEST)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["currency_pair"], "USD/KRW")
        self.assertEqual(body["side"], "payment")
        self.assertEqual(body["settlement_date"], "2026-10-30")
        self.assertEqual([row["scenario_name"] for row in body["scenarios"]], ["point", "lower", "median", "upper"])
        self.assertIn("warnings", body)
        self.assertEqual(self.service.initialize_calls, 1)

    def test_endpoint_calls_existing_analysis_function(self) -> None:
        with patch(
            "src.api.main.analyze_fx_exposure",
            wraps=__import__(
                "src.hedging.hedge_analysis", fromlist=["analyze_fx_exposure"]
            ).analyze_fx_exposure,
        ) as spy:
            response = self.client.post("/internal/hedge-analysis", json=VALID_REQUEST)
        self.assertEqual(response.status_code, 200)
        spy.assert_called_once()
        self.assertEqual(self.service.forecast_calls, 1)

    def test_invalid_requests_return_422(self) -> None:
        invalid_cases = (
            {"foreign_amount": 0},
            {"reference_rate": 0},
            {"hedged_amount": -1},
            {"hedged_amount": 1_000_001},
            {"hedge_rate": None},
            {"side": "UNKNOWN"},
            {"settlement_date": "not-a-date"},
            {"currency_pair": "JPY/KRW"},
        )
        for change in invalid_cases:
            with self.subTest(change=change):
                payload = {**VALID_REQUEST, **change}
                response = self.client.post("/internal/hedge-analysis", json=payload)
                self.assertEqual(response.status_code, 422)


class FxForecastApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.service = FakeForecastService()
        self.client_context = TestClient(
            create_app(forecast_service=self.service, enable_scheduler=False)
        )
        self.client = self.client_context.__enter__()

    def tearDown(self) -> None:
        self.client_context.__exit__(None, None, None)

    def test_returns_complete_h90_forecast_without_model_reload(self) -> None:
        response = self.client.get("/internal/fx-forecast")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["currency_pair"], "USD/KRW")
        self.assertEqual(body["horizon"], 90)
        self.assertEqual(len(body["forecast"]), 90)
        self.assertEqual(
            list(body["forecast"][0]),
            ["date", "point", "lower", "median", "upper"],
        )
        dates = [row["date"] for row in body["forecast"]]
        self.assertEqual(dates, sorted(dates))
        self.assertGreater(dates[0], body["forecast_origin"])
        self.assertEqual(self.service.h90_calls, 1)
        self.assertEqual(self.service.initialize_calls, 1)

    def test_does_not_return_history(self) -> None:
        response = self.client.get("/internal/fx-forecast")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("history", response.json())


class FakePipeline:
    quantiles = [0.1, 0.5, 0.9]

    def predict(self, inputs: object, *, prediction_length: int, **kwargs: object) -> list[np.ndarray]:
        values = np.zeros((1, 3, prediction_length), dtype=np.float32)
        values[:, 0, :] = 1400.0
        values[:, 1, :] = 1500.0
        values[:, 2, :] = 1600.0
        return [values]


class ForecastServiceLoadingTest(unittest.TestCase):
    def test_loader_runs_once_for_three_horizons(self) -> None:
        calls: list[tuple[str, str]] = []

        def loader(model_id: str, device: str) -> FakePipeline:
            calls.append((model_id, device))
            return FakePipeline()

        service = ForecastService(pipeline_loader=loader, device="cpu")
        service.initialize()
        self.assertEqual(len(calls), 1)
        self.assertEqual(set(service.snapshot.forecasts), {20, 60, 90})

    def test_failed_reload_keeps_previous_snapshot(self) -> None:
        service = ForecastService(pipeline_loader=lambda *_: FakePipeline(), device="cpu")
        service.initialize()
        original = service.snapshot

        def fail_loader(model_id: str, device: str) -> FakePipeline:
            raise RuntimeError("reload failed")

        service._pipeline_loader = fail_loader
        with self.assertRaisesRegex(RuntimeError, "reload failed"):
            service.reload()
        self.assertIs(service.snapshot, original)

    def test_snapshot_metadata_is_json_safe_types(self) -> None:
        service = ForecastService(pipeline_loader=lambda *_: FakePipeline(), device="cpu")
        service.initialize()
        snapshot: ForecastSnapshot = service.snapshot
        self.assertIsInstance(snapshot.created_at, datetime)
        self.assertEqual(snapshot.created_at.tzinfo, ZoneInfo("Asia/Seoul"))


class SchedulerTest(unittest.TestCase):
    def test_daily_job_uses_0300_asia_seoul(self) -> None:
        service = FakeForecastService()
        scheduler = create_scheduler(service)  # type: ignore[arg-type]
        job = scheduler.get_job("daily_forecast_reload")
        self.assertIsNotNone(job)
        self.assertEqual(str(job.trigger.timezone), "Asia/Seoul")  # type: ignore[union-attr]
        self.assertEqual(str(job.trigger.fields[5]), "3")  # type: ignore[union-attr]
        self.assertEqual(str(job.trigger.fields[6]), "0")  # type: ignore[union-attr]

    def test_scheduled_reload_failure_is_swallowed(self) -> None:
        class FailingService:
            def reload(self) -> None:
                raise RuntimeError("expected reload failure")

        asyncio.run(reload_forecasts_safely(FailingService()))  # type: ignore[arg-type]
