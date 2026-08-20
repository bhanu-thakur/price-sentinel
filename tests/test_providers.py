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
        session.get.assert_called_once_with(
            "https://www.buyhatke.com/amazon-gillette-series-5-price-history-63-110659581",
            timeout=60,
        )

    def test_buyhatke_apex_url_is_requested_on_the_www_host(self):
        # The apex host answers 403 for every request; only www serves pages.
        session = Mock()
        session.get.return_value = response_for(ROOT / "buyhatke" / "success.html")

        observation = buyhatke.fetch(
            "https://buyhatke.com/amazon-gillette-series-5-price-history-63-110659581",
            self.amazon_listing,
            session,
            now=NOW,
        )

        self.assertEqual(observation.price, 3119.0)
        session.get.assert_called_once_with(
            "https://www.buyhatke.com/amazon-gillette-series-5-price-history-63-110659581",
            timeout=60,
        )

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


class MarkupChangeTests(unittest.TestCase):
    """What happens when a source site quietly changes its page.

    The dangerous case is not a page that stops parsing — that raises and the
    orchestrator falls through to the next provider. The dangerous case is a page
    that still yields *a* number, but not the number we asked for.
    """

    def setUp(self):
        self.amazon_listing = {
            "id": "amazon-in-b0gsvfv3r4",
            "retailer": "amazon.in",
            "url": "https://www.amazon.in/dp/B0GSVFV3R4",
        }
        self.ph_body = (ROOT / "pricehistory_app" / "success.html").read_text(encoding="utf-8")
        self.bh_body = (ROOT / "buyhatke" / "success.html").read_text(encoding="utf-8")

    def _ph_fetch(self, body):
        session = Mock()
        session.get.return_value = SimpleNamespace(status_code=200, text=body)
        return pricehistory_app.fetch(
            "https://pricehistory.app/p/gillette-series-5",
            self.amazon_listing,
            session,
            now=NOW,
        )

    def _bh_fetch(self, body):
        session = Mock()
        session.get.return_value = SimpleNamespace(status_code=200, text=body)
        return buyhatke.fetch(
            "https://www.buyhatke.com/amazon-gillette-series-5-price-history-63-110659581",
            self.amazon_listing,
            session,
            now=NOW,
        )

    def test_pricehistory_rejects_a_page_that_now_describes_another_store(self):
        body = self.ph_body.replace("Store Name | Amazon", "Store Name | Flipkart")
        with self.assertRaises(SourceError) as raised:
            self._ph_fetch(body)
        self.assertEqual(raised.exception.kind, "identity")
        self.assertEqual(
            raised.exception.message,
            "page retailer 'flipkart.com' does not match listing retailer 'amazon.in'",
        )

    def test_pricehistory_rejects_a_page_that_now_describes_another_product(self):
        body = self.ph_body.replace("Store Product Code | B0GSVFV3R4", "Store Product Code | B0AAAAAAAA")
        with self.assertRaises(SourceError) as raised:
            self._ph_fetch(body)
        self.assertEqual(raised.exception.kind, "identity")
        self.assertEqual(
            raised.exception.message,
            "page product code 'B0AAAAAAAA' does not match listing product code 'B0GSVFV3R4'",
        )

    def test_pricehistory_rejects_a_page_that_dropped_the_product_code(self):
        body = self.ph_body.replace("<p>Store Product Code | B0GSVFV3R4</p>", "")
        with self.assertRaises(SourceError) as raised:
            self._ph_fetch(body)
        self.assertEqual(raised.exception.kind, "identity")
        self.assertEqual(raised.exception.message, "page product code is missing")

    def test_pricehistory_does_not_substitute_the_lowest_price_for_a_missing_current_price(self):
        """If the current-price line goes, the all-time low must not stand in for it."""
        body = self.ph_body.replace("Amazon Price in India on 01/08/2026: ₹3119.", "")
        body = body.replace("<p>Price in India | ₹3,119</p>", "")
        with self.assertRaises(SourceError) as raised:
            self._ph_fetch(body)
        self.assertEqual(raised.exception.kind, "parse")
        self.assertEqual(raised.exception.message, "current price is missing")

    def test_buyhatke_rejects_a_page_that_now_describes_another_store(self):
        body = self.bh_body.replace('cur_price:3119,site_name:"Amazon"', 'cur_price:3119,site_name:"Flipkart"')
        with self.assertRaises(SourceError) as raised:
            self._bh_fetch(body)
        self.assertEqual(raised.exception.kind, "identity")
        self.assertEqual(
            raised.exception.message,
            "page retailer 'flipkart.com' does not match listing retailer 'amazon.in'",
        )

    def test_buyhatke_rejects_a_page_that_now_describes_another_product(self):
        body = self.bh_body.replace('pid:"B0GSVFV3R4"', 'pid:"B0AAAAAAAA"')
        with self.assertRaises(SourceError) as raised:
            self._bh_fetch(body)
        self.assertEqual(raised.exception.kind, "identity")
        self.assertEqual(
            raised.exception.message,
            "page product ID 'B0AAAAAAAA' does not match listing product ID 'B0GSVFV3R4'",
        )

    @unittest.expectedFailure
    def test_pricehistory_records_the_observation_date_printed_on_its_own_page(self):
        """BUG: the page prints the date of the price and the adapter throws it away.

        `providers/pricehistory_app.py` matches the current price with the regex
        `r"Price in India on [^:|]+:\\s*" + _MONEY`. The `[^:|]+` steps straight
        over "01/08/2026" — the date that price was observed — and the Observation
        is built with a hardcoded `observed_ts=None` (line 200).

        `fetch._validate_observation` has a guard that rejects any observation more
        than 48 hours old, but it reads `observation.observed_ts`, so with None it
        can never fire. Both adapters hardcode None (buyhatke.py line 151 too), so
        that guard is dead code in production.

        The consequence is the failure this repo most needs to catch: the source
        serves a cached page from days ago, the price parses cleanly, and Price
        Sentinel records a stale number as today's and can alert on it.

        Not fixed here on instruction — reported instead.
        """
        body = self.ph_body.replace("on 01/08/2026:", "on 20/07/2026:")
        observation = self._ph_fetch(body)
        self.assertEqual(
            observation.observed_ts,
            datetime(2026, 7, 20, tzinfo=timezone.utc),
        )


if __name__ == "__main__":
    unittest.main()
