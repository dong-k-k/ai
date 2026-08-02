from __future__ import annotations

import sys
import unittest
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile


SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from src.experiments.yield_spread.collect_h15_calendars import (  # noqa: E402
    build_calendar_archive,
    collect_calendar_payloads,
    iter_months,
)


def calendar_html(days: str, month: str) -> bytes:
    return (
        f"<title>Calendar: {month} 2024</title>"
        "<p>4:15 p.m.</p><p>H.15 - Selected Interest Rates</p>"
        f"<p>{days}</p>"
    ).encode()


class CollectH15CalendarsTest(unittest.TestCase):
    def test_iter_months_is_inclusive(self) -> None:
        months = iter_months("2024-07", "2024-09")
        self.assertEqual([month.strftime("%Y-%m") for month in months], [
            "2024-07", "2024-08", "2024-09"
        ])

    def test_collect_calendar_payloads_preserves_all_months(self) -> None:
        months = iter_months("2024-07", "2024-08")

        def fake_fetcher(url: str) -> bytes:
            return calendar_html("1, 2", "July") if "july" in url else calendar_html("1, 5", "August")

        payloads = collect_calendar_payloads(months, fake_fetcher, max_workers=2)
        self.assertEqual(list(payloads), ["2024-07", "2024-08"])

    def test_archive_contains_raw_html_and_manifest_checksums(self) -> None:
        payloads = {
            "2024-07": calendar_html("1, 2", "July"),
            "2024-08": calendar_html("1, 5", "August"),
        }
        archive_bytes, manifest, release_dates = build_calendar_archive(payloads)
        with ZipFile(BytesIO(archive_bytes)) as archive:
            self.assertEqual(archive.namelist(), ["2024-07.html", "2024-08.html"])
            self.assertEqual(archive.read("2024-07.html"), payloads["2024-07"])
        self.assertEqual(len(manifest), 2)
        self.assertEqual(len(manifest[0]["sha256"]), 64)
        self.assertEqual(len(release_dates), 4)


if __name__ == "__main__":
    unittest.main()
