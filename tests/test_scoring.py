import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import analyze


def obs(price, low=2799.0, avg=3301.0, high=3999.0):
    return {
        "price": price,
        "mrp": 3999.0,
        "in_stock": True,
        "site_low": low,
        "site_avg": avg,
        "site_high": high,
        "retailer": "amazon.in",
        "source": "pricehistory.app",
        "listing_url": "https://amazon.in/dp/B0GSVFV3R4",
    }


class ScoringTests(unittest.TestCase):
    product = {"id": "gillette-series-5-trimmer", "name": "Gillette", "target": None}

    def test_lifetime_score_examples(self):
        for price, expected in ((3359, 53.3), (3250, 62.4), (2799, 100.0)):
            with self.subTest(price=price):
                verdict = analyze.evaluate("amazon-in-b0gsvfv3r4", obs(price), self.product)
                self.assertEqual(verdict["score"], expected)

    def test_recent_and_lifetime_alert_routes_are_independent(self):
        recent_history = [(datetime(2026, 7, 1, tzinfo=timezone.utc), 3000.0)] * 8
        with patch("analyze.load_history", return_value=recent_history):
            recent = analyze.evaluate(
                "listing", obs(3000, low=2500, avg=3400, high=4000), self.product
            )
        self.assertTrue(recent["alert"])
        self.assertTrue(any("180 days" in reason for reason in recent["reasons"]))

        lifetime_history = [(datetime(2026, 7, 1, tzinfo=timezone.utc), 3200.0)] * 8
        with patch("analyze.load_history", return_value=lifetime_history):
            lifetime = analyze.evaluate(
                "listing", obs(2799, low=2799, avg=3301, high=3999), self.product
            )
        self.assertTrue(lifetime["alert"])
        self.assertTrue(any("EVER" in reason for reason in lifetime["reasons"]))

    def test_cooldown_and_further_three_percent_drop(self):
        verdict = {
            "listing_id": "listing-b",
            "product_id": "product",
            "alert": True,
            "price": 100.0,
        }
        recent = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        state = {
            "products": {
                "product": {"last_alert_ts": recent, "last_alert_price": 100.0}
            },
            "listings": {"listing-a": {}, "listing-b": {}},
        }
        self.assertFalse(analyze.should_notify(verdict, state))
        verdict["price"] = 96.9
        self.assertTrue(analyze.should_notify(verdict, state))


if __name__ == "__main__":
    unittest.main()
