import unittest
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_quality import filter_grocery_relevant, repair_category, sanitize_unit_prices
from get_deals import extract_unit_price


class DataQualityTests(unittest.TestCase):
    def test_extract_unit_price_does_not_treat_5g_as_grams(self):
        unit_price, unit_type, grams = extract_unit_price(
            'ONN 75" 4K UHD HDR Roku Smart TV 5G',
            698.00,
        )

        self.assertIsNone(unit_price)
        self.assertIsNone(unit_type)
        self.assertIsNone(grams)

    def test_extract_unit_price_accepts_compact_grocery_grams(self):
        unit_price, unit_type, grams = extract_unit_price(
            "Lactantia Cream Cheese 227g",
            2.97,
        )

        self.assertEqual(unit_type, "$/kg")
        self.assertEqual(grams, 227)
        self.assertAlmostEqual(unit_price, 13.08, places=2)

    def test_filter_grocery_relevant_excludes_general_merchandise(self):
        df = pd.DataFrame(
            [
                {"Item": 'ONN 75" 4K UHD HDR Roku Smart TV', "Store": "Walmart"},
                {"Item": "Corn", "Store": "Walmart"},
                {"Item": "Paper towel", "Store": "Sobeys"},
            ]
        )

        kept, excluded = filter_grocery_relevant(df)

        self.assertEqual(set(kept["Item"]), {"Corn", "Paper towel"})
        self.assertEqual(excluded["Item"].tolist(), ['ONN 75" 4K UHD HDR Roku Smart TV'])

    def test_repair_category_overrides_obvious_category_drift(self):
        self.assertEqual(repair_category("Ahi Tuna Steak", "Beef"), ("Seafood", "corrected"))
        self.assertEqual(repair_category("Potato Chips", "Produce"), ("Snacks", "corrected"))
        self.assertEqual(repair_category("Avocados", "Other"), ("Produce", "inferred"))

    def test_sanitize_unit_prices_clears_outliers_and_flags_rows(self):
        df = pd.DataFrame(
            [
                {
                    "Item": "Smartphone",
                    "unit_price": 139600.0,
                    "unit_type": "$/kg",
                    "grams_equivalent": 5,
                }
            ]
        )

        cleaned, issue_count = sanitize_unit_prices(df)

        self.assertEqual(issue_count, 1)
        self.assertTrue(pd.isna(cleaned.loc[0, "unit_price"]))
        self.assertIn("unit_price_outlier", cleaned.loc[0, "quality_flags"])


if __name__ == "__main__":
    unittest.main()
