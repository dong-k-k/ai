from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from forecast_provider import ForecastScenario, ScenarioSource  # noqa: E402
from hedge_analysis import ExposureSide, FxExposure, analyze_fx_exposure  # noqa: E402


SETTLEMENT_DATE = date(2026, 7, 2)


def point_forecast(rate: float = 1500.0) -> ForecastScenario:
    return ForecastScenario(
        model_name="Random Walk",
        scenario_source=ScenarioSource.RANDOM_WALK,
        currency_pair="USD/KRW",
        unit="KRW per USD",
        forecast_origin=date(2026, 7, 1),
        prediction_length=1,
        forecast_dates=(SETTLEMENT_DATE,),
        point_forecast=(rate,),
    )


class HedgeAnalysisTest(unittest.TestCase):
    def test_unhedged_payment_rising_fx_is_unfavorable(self) -> None:
        exposure = FxExposure(
            currency_pair="USD/KRW",
            side=ExposureSide.PAYMENT,
            foreign_amount=100.0,
            settlement_date=SETTLEMENT_DATE,
            reference_rate=1400.0,
        )
        result = analyze_fx_exposure(exposure, point_forecast())
        point = result.scenarios[0]
        self.assertEqual(point.total_krw_amount, 150_000.0)
        self.assertEqual(point.favorable_pnl_vs_reference_krw, -10_000.0)
        self.assertIn("상승", result.risk_direction)

    def test_unhedged_receipt_rising_fx_is_favorable(self) -> None:
        exposure = FxExposure(
            currency_pair="USD/KRW",
            side=ExposureSide.RECEIPT,
            foreign_amount=100.0,
            settlement_date=SETTLEMENT_DATE,
            reference_rate=1400.0,
        )
        point = analyze_fx_exposure(exposure, point_forecast()).scenarios[0]
        self.assertEqual(point.total_krw_amount, 150_000.0)
        self.assertEqual(point.favorable_pnl_vs_reference_krw, 10_000.0)

    def test_half_hedged_payment_uses_hedge_rate(self) -> None:
        exposure = FxExposure(
            currency_pair="USD/KRW",
            side=ExposureSide.PAYMENT,
            foreign_amount=100.0,
            settlement_date=SETTLEMENT_DATE,
            reference_rate=1400.0,
            hedged_ratio=0.5,
            hedge_rate=1400.0,
        )
        result = analyze_fx_exposure(exposure, point_forecast())
        point = result.scenarios[0]
        self.assertEqual(result.hedged_amount, 50.0)
        self.assertEqual(result.unhedged_amount, 50.0)
        self.assertEqual(point.hedged_krw_amount, 70_000.0)
        self.assertEqual(point.unhedged_krw_amount, 75_000.0)
        self.assertEqual(point.total_krw_amount, 145_000.0)
        self.assertEqual(point.favorable_pnl_vs_reference_krw, -5_000.0)
        self.assertEqual(point.hedge_effect_vs_unhedged_krw, 5_000.0)

    def test_quantile_forecast_creates_four_named_results(self) -> None:
        forecast = ForecastScenario(
            model_name="Chronos-2 Zero-shot",
            scenario_source=ScenarioSource.CHRONOS_ZERO_SHOT,
            currency_pair="USD/KRW",
            unit="KRW per USD",
            forecast_origin=date(2026, 7, 1),
            prediction_length=1,
            forecast_dates=(SETTLEMENT_DATE,),
            point_forecast=(1500.0,),
            lower_scenario=(1450.0,),
            median_scenario=(1500.0,),
            upper_scenario=(1550.0,),
            warning="목표 포함률이 보장되지 않는 참고용 분위수 시나리오",
        )
        exposure = FxExposure(
            currency_pair="USD/KRW",
            side=ExposureSide.PAYMENT,
            foreign_amount=100.0,
            settlement_date=SETTLEMENT_DATE,
            reference_rate=1400.0,
        )
        result = analyze_fx_exposure(exposure, forecast)
        self.assertEqual(
            [scenario.scenario_name for scenario in result.scenarios],
            ["point", "lower", "median", "upper"],
        )
        self.assertEqual(result.scenarios[-1].total_krw_amount, 155_000.0)
        self.assertIn("참고용 분위수", result.warnings[0])

    def test_settlement_date_is_not_moved_silently(self) -> None:
        exposure = FxExposure(
            currency_pair="USD/KRW",
            side=ExposureSide.PAYMENT,
            foreign_amount=100.0,
            settlement_date=date(2026, 7, 4),
            reference_rate=1400.0,
        )
        with self.assertRaisesRegex(ValueError, "임의 이동하지 않습니다"):
            analyze_fx_exposure(exposure, point_forecast())

    def test_hedged_amount_and_ratio_are_mutually_exclusive(self) -> None:
        with self.assertRaisesRegex(ValueError, "동시에 입력할 수 없습니다"):
            FxExposure(
                currency_pair="USD/KRW",
                side=ExposureSide.PAYMENT,
                foreign_amount=100.0,
                settlement_date=SETTLEMENT_DATE,
                reference_rate=1400.0,
                hedged_amount=50.0,
                hedged_ratio=0.5,
                hedge_rate=1400.0,
            )


if __name__ == "__main__":
    unittest.main()
