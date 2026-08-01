import base64
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from providers import buyhatke, pricehistory_app
from providers.base import SourceError


ROOT = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)


def response_for(path):
    return SimpleNamespace(status_code=200, text=path.read_text(encoding="utf-8"))


class ProviderFixtureTests(unittest.TestCase):
    def setUp(self):
        self.amazon_listing = {
            "id": "amazon-in-b0gsvfv3r4",
            "retailer": "amazon.in",
            "url": "https://www.amazon.in/dp/B0GSVFV3R4",
        }
        self.flipkart_listing = {
            "id": "flipkart-com-trimmer123",
            "retailer": "flipkart.com",
            "url": "https://www.flipkart.com/gillette-series-5/p/itm123?pid=TRIMMER123",
        }

    def test_pricehistory_success_fixture(self):
        session = Mock()
        session.get.return_value = response_for(ROOT / "pricehistory_app" / "success.html")

        observation = pricehistory_app.fetch(
            "https://pricehistory.app/p/gillette-series-5",
            self.amazon_listing,
            session,
            now=NOW,
        )

        self.assertEqual(observation.price, 3119.0)
        self.assertEqual(observation.retailer, "amazon.in")
        self.assertEqual(observation.site_low, 2799.0)
        self.assertEqual(observation.site_avg, 3301.0)
        self.assertEqual(observation.site_high, 3999.0)
        session.get.assert_called_once_with("https://pricehistory.app/p/gillette-series-5", timeout=25)

    def test_pricehistory_decodes_public_embedded_chart_history(self):
        payload = {"History": {"Price": [
            {"x": "2026-04-12", "y": 3999},
            {"x": "2026-07-03", "y": 2799},
            {"x": "2026-08-01", "y": 3119},
        ]}}
        key = b"verified-test-key"
        raw = json.dumps(payload).encode("utf-8")
        encoded = base64.b64encode(bytes(value ^ key[index % len(key)] for index, value in enumerate(raw))).decode("ascii")
        body = (ROOT / "pricehistory_app" / "success.html").read_text(encoding="utf-8")
        body += f'<script>var PagePriceHistoryDataSet="{encoded}"; let CachedKey="{key.decode()}";</script>'
        session = Mock()
        session.get.return_value = SimpleNamespace(status_code=200, text=body)

        observation = pricehistory_app.fetch(
            "https://pricehistory.app/p/gillette-series-5",
            self.amazon_listing,
            session,
            now=NOW,
        )

        self.assertEqual(observation.history, (
            ("2026-04-12", 3999.0),
            ("2026-07-03", 2799.0),
            ("2026-08-01", 3119.0),
        ))

    def test_pricehistory_accepts_current_product_code_label(self):
        body = (ROOT / "pricehistory_app" / "success.html").read_text(encoding="utf-8")
        body = body.replace("Store Product Code | B0GSVFV3R4", "Store Product Code B0GSVFV3R4")
        session = Mock()
        session.get.return_value = SimpleNamespace(status_code=200, text=body)

        observation = pricehistory_app.fetch(
            "https://pricehistory.app/p/gillette-series-5",
            self.amazon_listing,
            session,
            now=NOW,
        )

        self.assertEqual(observation.listing_id, "amazon-in-b0gsvfv3r4")

    def test_pricehistory_missing_price_fixture_rejected(self):
        session = Mock()
        session.get.return_value = response_for(ROOT / "pricehistory_app" / "missing_price.html")

        with self.assertRaises(SourceError) as raised:
            pricehistory_app.fetch(
                "https://pricehistory.app/p/gillette-series-5",
                self.amazon_listing,
                session,
                now=NOW,
            )

        self.assertEqual(raised.exception.provider, "pricehistory.app")
        self.assertEqual(raised.exception.kind, "parse")

    def test_pricehistory_discover_returns_only_retailer_anchor(self):
        session = Mock()
        session.get.return_value = response_for(ROOT / "pricehistory_app" / "success.html")

        candidates = pricehistory_app.discover("https://pricehistory.app/p/gillette-series-5", session)

        self.assertEqual(candidates, [{"url": "https://www.amazon.in/dp/B0GSVFV3R4", "retailer": "amazon.in"}])

    def test_buyhatke_success_fixture(self):
        session = Mock()
        session.get.return_value = response_for(ROOT / "buyhatke" / "success.html")

        observation = buyhatke.fetch(
            "https://www.buyhatke.com/amazon-gillette-series-5-price-history-63-110659581",
            self.amazon_listing,
            session,
            now=NOW,
        )

        self.assertEqual(observation.price, 3119.0)
        self.assertEqual(observation.retailer, "amazon.in")
        self.assertTrue(observation.in_stock)
        self.assertEqual(observation.site_low, 2799.0)
        self.assertEqual(observation.site_avg, 3406.88)
        self.assertEqual(observation.site_high, 3999.0)

    def test_buyhatke_missing_price_fixture_rejected(self):
        session = Mock()
        session.get.return_value = response_for(ROOT / "buyhatke" / "missing_price.html")

        with self.assertRaises(SourceError) as raised:
            buyhatke.fetch(
                "https://www.buyhatke.com/amazon-gillette-series-5-price-history-63-110659581",
                self.amazon_listing,
                session,
                now=NOW,
            )

        self.assertEqual(raised.exception.provider, "buyhatke.com")
        self.assertEqual(raised.exception.kind, "parse")

    def test_buyhatke_discover_excludes_provider_and_keeps_direct_offers(self):
        session = Mock()
        session.get.return_value = response_for(ROOT / "buyhatke" / "success.html")

        candidates = buyhatke.discover("https://www.buyhatke.com/product", session)

        self.assertEqual(
            candidates,
            [
                {"url": "http://www.amazon.in/gp/product/B0GSVFV3R4", "retailer": "amazon.in"},
                {"url": "https://www.flipkart.com/gillette-series-5/p/itm123?pid=TRIMMER123", "retailer": "flipkart.com"},
            ],
        )


if __name__ == "__main__":
    unittest.main()
