from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

import pandas as pd


SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from forecast_provider import (  # noqa: E402
    ForecastScenario,
    ScenarioSource,
    load_forecast_scenario_from_csv,
)


class ForecastScenarioTest(unittest.TestCase):
    def test_random_walk_point_only_is_valid(self) -> None:
        scenario = ForecastScenario(
            model_name="Random Walk",
            scenario_source=ScenarioSource.RANDOM_WALK,
            currency_pair="USD/KRW",
            unit="KRW per USD",
            forecast_origin=date(2026, 7, 1),
            prediction_length=2,
            forecast_dates=(date(2026, 7, 2), date(2026, 7, 3)),
            point_forecast=(1400.0, 1400.0),
        )
        self.assertFalse(scenario.has_interval_scenarios)

    def test_chronos_quantile_order_is_validated(self) -> None:
        with self.assertRaisesRegex(ValueError, "하한 ≤ 중앙 ≤ 상한"):
            ForecastScenario(
                model_name="Chronos-2",
                scenario_source=ScenarioSource.CHRONOS_ZERO_SHOT,
                currency_pair="USD/KRW",
                unit="KRW per USD",
                forecast_origin=date(2026, 7, 1),
                prediction_length=1,
                forecast_dates=(date(2026, 7, 2),),
                point_forecast=(1400.0,),
                lower_scenario=(1410.0,),
                median_scenario=(1400.0,),
                upper_scenario=(1420.0,),
                warning="참고용 분위수 시나리오",
            )

    def test_dates_must_be_unique_and_increasing(self) -> None:
        with self.assertRaisesRegex(ValueError, "중복 날짜"):
            ForecastScenario(
                model_name="사용자 시나리오",
                scenario_source=ScenarioSource.USER_DEFINED,
                currency_pair="USD/KRW",
                unit="KRW per USD",
                forecast_origin=date(2026, 7, 1),
                prediction_length=2,
                forecast_dates=(date(2026, 7, 2), date(2026, 7, 2)),
                point_forecast=(1400.0, 1410.0),
            )

    def test_csv_loader_selects_only_requested_origin(self) -> None:
        dataframe = pd.DataFrame(
            {
                "requested_origin": ["2026-06-01", "2026-07-01", "2026-07-01"],
                "forecast_origin_date": ["2026-05-29", "2026-06-30", "2026-06-30"],
                "forecast_step": [1, 1, 2],
                "target_date": ["2026-06-02", "2026-07-02", "2026-07-03"],
                "ensemble_forecast": [1370.0, 1380.0, 1385.0],
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "forecast.csv"
            dataframe.to_csv(csv_path, index=False)
            scenario = load_forecast_scenario_from_csv(
                csv_path,
                requested_origin="2026-07-01",
                model_name="축소 앙상블 α=0.5",
                scenario_source=ScenarioSource.SHRUNK_ENSEMBLE,
                point_column="ensemble_forecast",
                warning="소표본에서 잠정 검증된 점 예측",
            )
        self.assertEqual(scenario.prediction_length, 2)
        self.assertEqual(scenario.point_forecast, (1380.0, 1385.0))
        self.assertEqual(scenario.forecast_origin, date(2026, 6, 30))

    def test_csv_loader_rejects_missing_origin(self) -> None:
        dataframe = pd.DataFrame(
            {
                "requested_origin": ["2026-07-01"],
                "forecast_origin_date": ["2026-06-30"],
                "forecast_step": [1],
                "target_date": ["2026-07-02"],
                "random_walk_forecast": [1380.0],
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "forecast.csv"
            dataframe.to_csv(csv_path, index=False)
            with self.assertRaisesRegex(ValueError, "예측 행이 없습니다"):
                load_forecast_scenario_from_csv(
                    csv_path,
                    requested_origin="2026-08-01",
                    model_name="Random Walk",
                    scenario_source=ScenarioSource.RANDOM_WALK,
                    point_column="random_walk_forecast",
                )


if __name__ == "__main__":
    unittest.main()
