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


class ThresholdBoundaryTests(unittest.TestCase):
    """Each alert band must fire on its own side of the line and stay silent past it.

    `site_avg` is left out of most of these on purpose. With an average present the
    "below the lifetime average" rule catches prices that the all-time-low bands
    just missed, so a single verdict cannot tell you which line was crossed.
    """

    product = {"id": "gillette-series-5-trimmer", "name": "Gillette", "target": None}
    LOW = 2799.0

    def verdict(self, price, product=None, low=None, avg=None, high=3999.0, history=()):
        """Evaluate one price with the tracker's own history pinned.

        Without pinning it, `analyze.load_history` reads the real CSV in `data/`,
        so these boundaries would move whenever the tracker collects a new sample.
        Empty history keeps us on the lifetime-stats branch, which is where the
        all-time-low bands live.
        """
        with patch("analyze.load_history", return_value=list(history)):
            return analyze.evaluate(
                "amazon-in-b0gsvfv3r4",
                obs(price, low=self.LOW if low is None else low, avg=avg, high=high),
                product or self.product,
            )

    def test_all_time_low_band_is_inclusive_at_half_a_percent(self):
        # 2799 * 1.005 == 2812.995 exactly.
        at = self.verdict(2812.99)
        self.assertTrue(at["alert"])
        self.assertEqual(
            at["reasons"],
            ["At the lowest price ever recorded (Rs 2,799)", "Own history still building (0 samples)"],
        )

        past = self.verdict(2813.0)
        self.assertTrue(past["alert"])
        self.assertEqual(
            past["reasons"],
            ["Within 3% of the all-time low (Rs 2,799)", "Own history still building (0 samples)"],
        )

    def test_three_percent_band_is_inclusive_and_silent_one_paisa_past_it(self):
        # 2799 * 1.03 == 2882.9700000000003, so 2882.97 is inside the band.
        inside = self.verdict(2882.97)
        self.assertTrue(inside["alert"])
        self.assertEqual(
            inside["reasons"],
            ["Within 3% of the all-time low (Rs 2,799)", "Own history still building (0 samples)"],
        )

        outside = self.verdict(2882.98)
        self.assertFalse(outside["alert"])
        self.assertEqual(outside["reasons"], ["Own history still building (0 samples)"])

    def test_lifetime_average_band_fires_at_seven_percent_under_and_not_a_paisa_less(self):
        # avg 3301 * 0.93 == 3069.93.
        inside = self.verdict(3069.93, avg=3301.0)
        self.assertTrue(inside["alert"])
        self.assertEqual(
            inside["reasons"],
            ["7.0% below the lifetime average", "Own history still building (0 samples)"],
        )

        outside = self.verdict(3069.94, avg=3301.0)
        self.assertFalse(outside["alert"])
        self.assertEqual(outside["reasons"], ["Own history still building (0 samples)"])

    def test_target_alert_is_inclusive_at_the_target_and_silent_one_paisa_above(self):
        product = {"id": "gillette-series-5-trimmer", "name": "Gillette", "target": 2850}
        # A low of 1000 keeps every all-time-low band well clear of 2850.
        at = self.verdict(2850.0, product=product, low=1000.0, high=5000.0)
        self.assertTrue(at["alert"])
        self.assertEqual(
            at["reasons"],
            ["At or below your target of Rs 2,850", "Own history still building (0 samples)"],
        )

        above = self.verdict(2850.01, product=product, low=1000.0, high=5000.0)
        self.assertFalse(above["alert"])
        self.assertEqual(above["reasons"], ["Own history still building (0 samples)"])

    def test_out_of_stock_suppresses_an_alert_that_would_otherwise_fire(self):
        value = obs(2799.0)
        value["in_stock"] = False
        history = [(datetime(2026, 7, 1, tzinfo=timezone.utc), 3000.0)] * 8
        with patch("analyze.load_history", return_value=history):
            verdict = analyze.evaluate("amazon-in-b0gsvfv3r4", value, self.product)
        self.assertFalse(verdict["alert"])
        self.assertEqual(verdict["reasons"][-1], "Out of stock - suppressed")

    def test_cooldown_needs_strictly_more_than_a_three_percent_further_drop(self):
        base = {
            "listing_id": "listing-b",
            "product_id": "product",
            "alert": True,
            "price": 100.0,
        }
        recent = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        state = {
            "products": {"product": {"last_alert_ts": recent, "last_alert_price": 100.0}},
            "listings": {"listing-b": {}},
        }
        # 100 * 0.97 == 97.0 exactly, and the comparison is a strict `<`.
        self.assertFalse(analyze.should_notify({**base, "price": 97.0}, state))
        self.assertTrue(analyze.should_notify({**base, "price": 96.99}, state))

    def test_cooldown_expiry_is_seven_days_and_a_non_alert_never_notifies(self):
        base = {"listing_id": "listing-b", "product_id": "product", "alert": True, "price": 100.0}

        def state_aged(days):
            stamp = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
            return {
                "products": {"product": {"last_alert_ts": stamp, "last_alert_price": 100.0}},
                "listings": {"listing-b": {}},
            }

        self.assertFalse(analyze.should_notify(base, state_aged(6)))
        self.assertTrue(analyze.should_notify(base, state_aged(8)))
        # A verdict that is not an alert is never notified, cooldown or not.
        self.assertFalse(analyze.should_notify({**base, "alert": False}, state_aged(8)))


if __name__ == "__main__":
    unittest.main()
