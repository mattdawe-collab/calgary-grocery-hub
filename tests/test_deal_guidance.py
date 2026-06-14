import unittest

import pandas as pd

from deal_guidance import (
    ACTION_COMPARE,
    ACTION_SKIP,
    ACTION_STOCK_UP,
    action_label,
    add_deal_guidance,
    confidence_score,
    why_bullets,
)


class DealGuidanceTests(unittest.TestCase):
    def test_high_value_high_confidence_deal_is_stock_up(self):
        row = pd.Series(
            {
                "deal_score": 94,
                "historical_count": 18,
                "pct_below_avg": 42,
                "historical_avg": 6.99,
                "price_percentile": 100,
                "cross_store_rank": 1,
                "cross_store_count": 3,
                "unit_price": 4.25,
                "unit_type": "$/kg",
                "is_lowest_historical": True,
                "data_quality_score": 100,
                "quality_flags": "",
                "category_source": "ai",
            }
        )

        self.assertGreaterEqual(confidence_score(row), 72)
        self.assertEqual(action_label(row), ACTION_STOCK_UP)
        self.assertIn("42% below avg $6.99", why_bullets(row))
        self.assertIn("Lowest seen", why_bullets(row))

    def test_high_value_low_evidence_deal_is_compare_first(self):
        row = pd.Series(
            {
                "deal_score": 78,
                "historical_count": 0,
                "cross_store_count": 1,
                "data_quality_score": 82,
                "quality_flags": "no_history",
                "category_source": "fallback",
            }
        )

        self.assertLess(confidence_score(row), 58)
        self.assertEqual(action_label(row), ACTION_COMPARE)

    def test_low_score_deal_is_skip(self):
        row = pd.Series({"deal_score": 28, "historical_count": 10})

        self.assertEqual(action_label(row), ACTION_SKIP)

    def test_add_deal_guidance_adds_expected_columns(self):
        df = pd.DataFrame(
            [
                {
                    "deal_score": 88,
                    "historical_count": 8,
                    "pct_below_avg": 25,
                    "historical_avg": 4.00,
                    "cross_store_rank": 1,
                    "cross_store_count": 2,
                    "data_quality_score": 100,
                    "quality_flags": "",
                    "category_source": "ai",
                }
            ]
        )

        guided = add_deal_guidance(df)

        self.assertIn("confidence_score", guided.columns)
        self.assertIn("action_label", guided.columns)
        self.assertIn("why_bullets", guided.columns)
        self.assertTrue(guided.loc[0, "why_bullets"])


if __name__ == "__main__":
    unittest.main()
