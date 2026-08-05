import unittest
from unittest.mock import Mock, patch

import notify


class NotifyTests(unittest.TestCase):
    def test_dispatch_reports_whether_any_channel_delivered(self):
        verdicts = [{"name": "Product", "price": 100, "score": 80, "reasons": [], "url": "https://example.com"}]
        with patch.object(notify, "push_ntfy", return_value=False), patch.object(
            notify, "send_email", return_value=True
        ):
            self.assertTrue(notify.dispatch(verdicts))
        with patch.object(notify, "push_ntfy", return_value=False), patch.object(
            notify, "send_email", return_value=False
        ):
            self.assertFalse(notify.dispatch(verdicts))

    def test_empty_dispatch_is_not_delivery(self):
        self.assertFalse(notify.dispatch([]))

    def test_each_product_gets_its_own_push(self):
        verdicts = [
            {"name": "Nelko P21 Label Maker Machine with Tape", "price": 2748.06, "score": 83.5,
             "reasons": ["Lowest price in 180 days"], "url": "https://amazon.in/dp/B0CHJR8NLD",
             "retailer": "amazon.in", "life_low": 2639.0, "life_avg": 2978.0, "life_high": 3299.0},
            {"name": "Jenga", "price": 660, "score": 98.3, "reasons": ["Cheapest ever"],
             "url": "https://flipkart.com/item?pid=BUY1", "retailer": "flipkart.com"},
        ]
        with patch.object(notify, "NTFY_TOPIC", "topic"), patch.object(notify, "requests") as http:
            self.assertTrue(notify.push_ntfy(verdicts))

        self.assertEqual(http.post.call_count, 2)
        # Highest score first, each addressed to its own retailer and URL.
        first, second = http.post.call_args_list
        self.assertEqual(first.kwargs["headers"]["Title"], b"Rs 660 - Jenga")
        self.assertIn("Open on Flipkart", first.kwargs["headers"]["Actions"])
        self.assertEqual(
            second.kwargs["headers"]["Title"], b"Rs 2,748 - Nelko P21 Label Maker Machine"
        )
        self.assertIn("Open on Amazon", second.kwargs["headers"]["Actions"])

    def test_body_uses_provider_history_and_omits_own_90d_stats(self):
        verdict = {
            "name": "Nelko", "price": 2748.06, "score": 83.5, "retailer": "amazon.in",
            "reasons": ["Lowest price in 180 days"],
            "life_low": 2639.0, "life_avg": 2978.0, "life_high": 3299.0,
            # Degenerate self-collected window that must not reach the alert.
            "min90": 2748.06, "median": 2748.06, "max90": 2748.06, "percentile": 0,
        }
        body = notify.format_alert(verdict)
        self.assertEqual(
            body,
            "Lowest price in 180 days\n\n"
            "All-time low Rs 2,639 · avg Rs 2,978 · high Rs 3,299\n"
            "Score 84/100 · Amazon",
        )
        self.assertNotIn("90d", body)
        self.assertNotIn("percentile", body)

    def test_partial_push_failure_is_not_reported_as_delivered(self):
        verdicts = [
            {"name": "A", "price": 100, "score": 80, "reasons": [], "url": "https://a", "retailer": "amazon.in"},
            {"name": "B", "price": 200, "score": 70, "reasons": [], "url": "https://b", "retailer": "amazon.in"},
        ]
        with patch.object(notify, "NTFY_TOPIC", "topic"), patch.object(notify, "requests") as http:
            http.post.side_effect = [Mock(), RuntimeError("boom")]
            self.assertFalse(notify.push_ntfy(verdicts))
        self.assertEqual(http.post.call_count, 2)

    def test_action_button_names_the_listing_retailer(self):
        verdicts = [{
            "name": "Jenga",
            "price": 660,
            "score": 98.3,
            "reasons": [],
            "url": "https://flipkart.com/item?pid=BUY1",
            "retailer": "flipkart.com",
        }]
        with patch.object(notify, "NTFY_TOPIC", "topic"), patch.object(notify, "requests") as http:
            self.assertTrue(notify.push_ntfy(verdicts))

        headers = http.post.call_args.kwargs["headers"]
        self.assertEqual(
            headers["Actions"], "view, Open on Flipkart, https://flipkart.com/item?pid=BUY1"
        )
        self.assertEqual(headers["Priority"], "urgent")


if __name__ == "__main__":
    unittest.main()
