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


if __name__ == "__main__":
    unittest.main()
