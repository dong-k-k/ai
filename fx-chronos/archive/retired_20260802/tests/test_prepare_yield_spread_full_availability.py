from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd


SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from src.experiments.yield_spread.prepare_yield_spread_full_availability import (  # noqa: E402
    assign_us_yield_full_availability,
    load_daily_release_dates,
)


class PrepareYieldSpreadFullAvailabilityTest(unittest.TestCase):
    def test_regimes_and_unavailable_periods_are_conservative(self) -> None:
        observations = pd.DataFrame(
            {
                "date": ["2016-09-23", "2016-10-03", "2019-09-03"],
                "us_treasury_3y_percent": [1.08, 1.2, 1.5],
                "series_id": ["DGS3"] * 3,
                "unit": ["Percent"] * 3,
                "frequency": ["Daily"] * 3,
            }
        )
        weekly = pd.DatetimeIndex(pd.to_datetime(["2016-09-26"]))
        daily = pd.DatetimeIndex(pd.to_datetime(["2017-01-03", "2019-08-30", "2019-10-01"]))

        result = assign_us_yield_full_availability(observations, weekly, daily)

        self.assertEqual(
            result["h15_release_date"].dt.strftime("%Y-%m-%d").tolist(),
            ["2016-09-26", "2017-01-03", "2019-10-01"],
        )
        self.assertIn("weekly", result.loc[0, "us_yield_release_regime"])
        self.assertIn("first confirmed", result.loc[1, "us_yield_gap_policy"])
        self.assertIn("missing 2019-09", result.loc[2, "us_yield_gap_policy"])
        self.assertEqual(result.loc[0, "us_yield_available_at_et"].hour, 23)
        self.assertEqual(result.loc[1, "us_yield_available_at_et"].hour, 16)

    def test_daily_archive_hash_and_month_are_verified(self) -> None:
        raw = (
            b"<title>Calendar: January 2017</title><p>4:15 p.m.</p>"
            b"<p>H.15 - Selected Interest Rates</p><p>3, 4</p>"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive_path = root / "daily.zip"
            manifest_path = root / "daily.json"
            with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
                archive.writestr("2017-01.html", raw)
            import hashlib

            manifest = {
                "unavailable_months": {
                    "2019-09": "official Federal Reserve monthly calendar page returns 404"
                },
                "files": [
                    {
                        "month": "2017-01",
                        "archive_name": "2017-01.html",
                        "byte_count": len(raw),
                        "sha256": hashlib.sha256(raw).hexdigest(),
                        "release_date_count": 2,
                    }
                ],
            }
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            dates = load_daily_release_dates(manifest_path, archive_path)

        self.assertEqual(dates.strftime("%Y-%m-%d").tolist(), ["2017-01-03", "2017-01-04"])


if __name__ == "__main__":
    unittest.main()
