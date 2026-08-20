import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import fetch
from providers.base import Observation, SourceError


NOW = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)


def observation(provider, listing):
    return Observation(
        listing_id=listing["id"],
        price=3119.0,
        mrp=3999.0,
        currency="INR",
        in_stock=True,
        title="Gillette Series 5",
        seller=None,
        retailer=listing["retailer"],
        listing_url=listing["url"],
        source=provider,
        source_url=listing["source_urls"][provider],
        fetched_ts=NOW,
        observed_ts=None,
        site_low=2799.0,
        site_avg=3301.0,
        site_high=3999.0,
    )


class FakeAdapter:
    def __init__(self, provider, result=None, error=None):
        self.PROVIDER = provider
        self.result = result
        self.error = error
        self.calls = []

    def fetch(self, source_url, listing, session, now=None):
        self.calls.append(source_url)
        if self.error:
            raise self.error
        return self.result


class FallbackTests(unittest.TestCase):
    def setUp(self):
        fetch._last_request_at = None
        self.listing = {
            "id": "amazon-in-b0gsvfv3r4",
            "retailer": "amazon.in",
            "url": "https://amazon.in/dp/B0GSVFV3R4",
            "source_urls": {
                "pricehistory.app": "https://pricehistory.app/p/one",
                "buyhatke.com": "https://buyhatke.com/two",
            },
        }

    def test_fallback_order_and_stop_after_success(self):
        first = FakeAdapter("pricehistory.app", error=SourceError("pricehistory.app", "parse", "bad"))
        second = FakeAdapter("buyhatke.com", result=observation("buyhatke.com", self.listing))
        with patch.dict(fetch.PROVIDER_ADAPTERS, {
            "pricehistory.app": first,
            "buyhatke.com": second,
        }, clear=True), patch("fetch.time.sleep"):
            result, _, attempts = fetch.fetch_listing(self.listing, {}, now=NOW)
        self.assertEqual(result.source, "buyhatke.com")
        self.assertEqual(first.calls, ["https://pricehistory.app/p/one"])
        self.assertEqual(second.calls, ["https://buyhatke.com/two"])
        self.assertEqual([item["status"] for item in attempts], ["failed", "success"])

    def test_disabled_provider_is_skipped_without_request(self):
        first = FakeAdapter("pricehistory.app", result=observation("pricehistory.app", self.listing))
        second = FakeAdapter("buyhatke.com", result=observation("buyhatke.com", self.listing))
        state = {
            "pricehistory.app": {
                "consecutive_failures": 2,
                "disabled_until": (NOW + timedelta(hours=1)).isoformat(),
                "last_error": "parse: bad",
            }
        }
        with patch.dict(fetch.PROVIDER_ADAPTERS, {
            "pricehistory.app": first,
            "buyhatke.com": second,
        }, clear=True), patch("fetch.time.sleep"):
            result, _, attempts = fetch.fetch_listing(self.listing, state, now=NOW)
        self.assertEqual(result.source, "buyhatke.com")
        self.assertEqual(first.calls, [])
        self.assertEqual(attempts[0]["reason"], "disabled")

    def test_403_and_429_disable_for_six_hours(self):
        for status in (403, 429):
            with self.subTest(status=status):
                adapter = FakeAdapter(
                    "pricehistory.app",
                    error=SourceError("pricehistory.app", "blocked", f"HTTP {status}"),
                )
                with patch.dict(
                    fetch.PROVIDER_ADAPTERS, {"pricehistory.app": adapter}, clear=True
                ), patch("fetch.time.sleep"):
                    _, state, _ = fetch.fetch_listing(
                        {**self.listing, "source_urls": {"pricehistory.app": "https://pricehistory.app/p/one"}},
                        {},
                        now=NOW,
                    )
                disabled = datetime.fromisoformat(state["pricehistory.app"]["disabled_until"])
                self.assertEqual(disabled, NOW + timedelta(hours=6))

    def test_three_failures_disable_for_three_hours(self):
        adapter = FakeAdapter(
            "pricehistory.app",
            error=SourceError("pricehistory.app", "parse", "malformed"),
        )
        state = {}
        listing = {**self.listing, "source_urls": {"pricehistory.app": "https://pricehistory.app/p/one"}}
        with patch.dict(
            fetch.PROVIDER_ADAPTERS, {"pricehistory.app": adapter}, clear=True
        ), patch("fetch.time.sleep"):
            for _ in range(3):
                _, state, _ = fetch.fetch_listing(listing, state, now=NOW)
        disabled = datetime.fromisoformat(state["pricehistory.app"]["disabled_until"])
        self.assertEqual(state["pricehistory.app"]["consecutive_failures"], 3)
        self.assertEqual(disabled, NOW + timedelta(hours=3))

    def test_only_source_url_is_requested(self):
        adapter = FakeAdapter("pricehistory.app", result=observation("pricehistory.app", self.listing))
        with patch.dict(fetch.PROVIDER_ADAPTERS, {"pricehistory.app": adapter}, clear=True):
            fetch.fetch_listing(self.listing, {}, now=NOW)
        self.assertEqual(adapter.calls, ["https://pricehistory.app/p/one"])
        self.assertNotIn("amazon.in", adapter.calls[0])


if __name__ == "__main__":
    unittest.main()
