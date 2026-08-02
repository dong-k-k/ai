from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from src.data import collect_ecos  # noqa: E402


class CollectEcosRatesTest(unittest.TestCase):
    def test_collect_kr_treasury_3y_validates_identifiers_and_unit(self) -> None:
        rows = [
            {
                "STAT_CODE": "817Y002",
                "ITEM_CODE1": "010200000",
                "ITEM_NAME1": "국고채(3년)",
                "UNIT_NAME": "연%",
                "TIME": "20240701",
                "DATA_VALUE": "3.210",
            },
            {
                "STAT_CODE": "817Y002",
                "ITEM_CODE1": "010200000",
                "ITEM_NAME1": "국고채(3년)",
                "UNIT_NAME": "연%",
                "TIME": "20240702",
                "DATA_VALUE": "3.169",
            },
        ]
        payload = {"list_total_count": 2, "rows": rows}

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with (
                patch.object(collect_ecos, "RAW_DIR", root / "raw"),
                patch.object(collect_ecos, "ECOS_PROCESSED_DIR", root / "processed"),
                patch.object(collect_ecos, "fetch_ecos_series", return_value=payload),
            ):
                (root / "raw").mkdir()
                (root / "processed").mkdir()
                output_path = collect_ecos.collect_kr_treasury_3y("20240701", "20240702")

            content = output_path.read_text(encoding="utf-8")
            self.assertIn("3.21", content)
            self.assertIn("010200000", content)
            self.assertIn("연%", content)

    def test_collect_kr_treasury_3y_rejects_wrong_unit(self) -> None:
        payload = {
            "list_total_count": 1,
            "rows": [
                {
                    "STAT_CODE": "817Y002",
                    "ITEM_CODE1": "010200000",
                    "ITEM_NAME1": "국고채(3년)",
                    "UNIT_NAME": "억원",
                    "TIME": "20240701",
                    "DATA_VALUE": "3.210",
                }
            ],
        }
        with patch.object(collect_ecos, "fetch_ecos_series", return_value=payload):
            with self.assertRaises(RuntimeError):
                collect_ecos.collect_kr_treasury_3y("20240701", "20240701")


if __name__ == "__main__":
    unittest.main()
