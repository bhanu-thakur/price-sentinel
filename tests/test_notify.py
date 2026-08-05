import unittest
from unittest.mock import patch

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
