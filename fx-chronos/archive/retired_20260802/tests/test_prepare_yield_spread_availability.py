from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd


SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from src.experiments.yield_spread.prepare_yield_spread_availability import (  # noqa: E402
    assign_kr_yield_availability,
    assign_us_yield_availability,
    parse_h15_release_dates,
    serialize_availability,
)


class PrepareYieldSpreadAvailabilityTest(unittest.TestCase):
    def test_parse_h15_calendar_validates_time_and_dates(self) -> None:
        raw = b"""
        <title>Federal Reserve Board - Calendar: July 2024</title>
        <div><p>4:15 p.m.</p><p>H.15 - Selected Interest Rates</p>
        <p></p><p>1, 2, 3, 5, 8, 9, 10, 11</p></div>
        """
        dates = parse_h15_release_dates(raw, 2024, 7)
        self.assertEqual(
            dates.strftime("%Y-%m-%d").tolist(),
            [
                "2024-07-01", "2024-07-02", "2024-07-03", "2024-07-05",
                "2024-07-08", "2024-07-09", "2024-07-10", "2024-07-11",
            ],
        )

    def test_parse_h15_calendar_rejects_changed_release_time(self) -> None:
        raw = (
            b"<title>Calendar: July 2024</title><p>3:00 p.m.</p>"
            b"<p>H.15 - Selected Interest Rates</p><p>1, 2</p>"
        )
        with self.assertRaises(RuntimeError):
            parse_h15_release_dates(raw, 2024, 7)

    def test_kr_availability_starts_next_calendar_day(self) -> None:
        observations = pd.DataFrame(
            {
                "date": ["2024-07-01"],
                "value": [3.21],
                "stat_code": ["817Y002"],
                "item_code": ["010200000"],
                "item_name": ["국고채(3년)"],
                "unit_name": ["연%"],
            }
        )
        result = serialize_availability(assign_kr_yield_availability(observations))
        self.assertEqual(
            result.loc[0, "kr_yield_source_published_at_kst"],
            "2024-07-01T16:00:00+09:00",
        )
        self.assertEqual(result.loc[0, "kr_yield_safe_from_krw_date"], "2024-07-02")
        self.assertEqual(result.loc[0, "item_code"], "010200000")

    def test_kr_availability_restores_item_code_leading_zero(self) -> None:
        observations = pd.DataFrame(
            {
                "date": ["2024-07-01"],
                "value": [3.21],
                "stat_code": ["817Y002"],
                "item_code": [10200000],
                "item_name": ["국고채(3년)"],
                "unit_name": ["연%"],
            }
        )
        result = assign_kr_yield_availability(observations)
        self.assertEqual(result.loc[0, "item_code"], "010200000")

    def test_us_availability_uses_first_later_official_release(self) -> None:
        observations = pd.DataFrame(
            {
                "date": ["2024-07-03", "2024-07-04"],
                "us_treasury_3y_percent": [4.48, None],
                "series_id": ["DGS3", "DGS3"],
                "unit": ["Percent", "Percent"],
                "frequency": ["Daily", "Daily"],
            }
        )
        releases = pd.DatetimeIndex(pd.to_datetime(["2024-07-03", "2024-07-05"]))
        result = serialize_availability(
            assign_us_yield_availability(observations, releases)
        )
        self.assertEqual(result["h15_release_date"].tolist(), ["2024-07-05"] * 2)
        self.assertEqual(
            result["us_yield_available_at_kst"].tolist(),
            ["2024-07-06T05:15:00+09:00"] * 2,
        )
        self.assertEqual(
            result["us_yield_safe_from_krw_date"].tolist(), ["2024-07-07"] * 2
        )
        self.assertTrue(pd.isna(result.loc[1, "us_treasury_3y_percent"]))


if __name__ == "__main__":
    unittest.main()
