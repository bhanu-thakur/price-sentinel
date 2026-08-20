import contextlib
import io
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import add_product
from providers.base import Observation, SourceError


NOW = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)


class FakeAdapter:
    def __init__(self, candidates, provider="fake-provider.example", fail_retailers=()):
        self.PROVIDER = provider
        self.candidates = candidates
        self.fail_retailers = set(fail_retailers)
        self.resolved = []

    def resolve(self, retailer_url, session):
        self.resolved.append(retailer_url)
        return f"https://{self.PROVIDER}/product/{len(self.resolved)}"

    def fetch(self, source_url, listing, session, now=None):
        if listing["retailer"] in self.fail_retailers:
            raise SourceError(self.PROVIDER, "parse", "fixture failure")
        return Observation(
            listing_id=listing["id"],
            price=3119.0,
            mrp=3999.0,
            currency="INR",
            in_stock=True,
            title="Gillette Series 5 Trimmer",
            seller=None,
            retailer=listing["retailer"],
            listing_url=listing["url"],
            source=self.PROVIDER,
            source_url=source_url,
            fetched_ts=now or NOW,
            observed_ts=None,
            site_low=2799.0,
            site_avg=3301.0,
            site_high=3999.0,
        )

    def discover(self, source_url, session):
        return list(self.candidates)


class IntakeTests(unittest.TestCase):
    seed_url = "https://www.amazon.in/dp/B0GSVFV3R4?tag=tracking"
    candidate_url = "https://www.flipkart.com/gillette-series-5/p/itm123?pid=TRIMMER123"

    def setUp(self):
        self.empty_watchlist = {"schema_version": 2, "products": []}

    def _build(self, candidates, answers):
        adapter = FakeAdapter(candidates)
        with patch.object(add_product, "ADAPTERS", (adapter,)), patch.object(
            add_product, "_load_watchlist", return_value=self.empty_watchlist
        ):
            proposed = add_product.build_product(
                self.seed_url,
                target=2850,
                tier="hot",
                session=object(),
                confirm=lambda prompt: answers.pop(0),
            )
        return proposed, adapter

    def test_ambiguous_candidate_rejection_is_persisted_and_not_repeated(self):
        candidate = {
            "url": self.candidate_url,
            "attributes": {"brand": "Gillette"},
        }
        proposed, adapter = self._build([candidate, candidate], ["n"])

        product = proposed["products"][0]
        normalized_candidate = "https://flipkart.com/gillette-series-5/p/itm123?pid=TRIMMER123"
        # Not "one listing" — the seed listing, and only it.
        self.assertEqual(
            [(item["id"], item["retailer"], item["url"]) for item in product["listings"]],
            [("amazon-in-b0gsvfv3r4", "amazon.in", "https://amazon.in/dp/B0GSVFV3R4")],
        )
        self.assertEqual(product["rejected_candidate_urls"], [normalized_candidate])
        self.assertEqual(
            adapter.resolved,
            ["https://amazon.in/dp/B0GSVFV3R4", normalized_candidate],
        )

    def test_confirmed_candidate_is_added_to_schema_v2_product(self):
        candidate = {
            "url": self.candidate_url,
            "attributes": {"brand": "Gillette"},
        }
        proposed, adapter = self._build([candidate], ["y"])

        product = proposed["products"][0]
        self.assertEqual(
            [(item["id"], item["retailer"], item["url"], item["confirmed_by"]) for item in product["listings"]],
            [
                ("amazon-in-b0gsvfv3r4", "amazon.in", "https://amazon.in/dp/B0GSVFV3R4", "seed"),
                (
                    "flipkart-com-trimmer123",
                    "flipkart.com",
                    "https://flipkart.com/gillette-series-5/p/itm123?pid=TRIMMER123",
                    "user",
                ),
            ],
        )
        self.assertEqual(product["rejected_candidate_urls"], [])
        self.assertEqual(product["target"], 2850)
        self.assertEqual(product["tier"], "hot")
        self.assertEqual(
            adapter.resolved,
            [
                "https://amazon.in/dp/B0GSVFV3R4",
                "https://flipkart.com/gillette-series-5/p/itm123?pid=TRIMMER123",
            ],
        )

    def test_only_successfully_fetched_seed_sources_are_stored(self):
        failing = FakeAdapter([], provider="bad-provider.example", fail_retailers={"amazon.in"})
        working = FakeAdapter([], provider="good-provider.example")
        with patch.object(add_product, "ADAPTERS", (failing, working)), patch.object(
            add_product, "_load_watchlist", return_value=self.empty_watchlist
        ):
            proposed = add_product.build_product(
                self.seed_url,
                target=None,
                tier="warm",
                session=object(),
                confirm=lambda prompt: "n",
            )
        sources = proposed["products"][0]["listings"][0]["source_urls"]
        self.assertEqual(sources, {"good-provider.example": "https://good-provider.example/product/1"})

    def test_candidate_details_are_shown_before_confirmation(self):
        candidate = {
            "url": self.candidate_url,
            "title": "Gillette Series 5 Trimmer",
            "attributes": {"brand": "Gillette"},
        }
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self._build([candidate], ["n"])
        rendered = output.getvalue()
        self.assertIn("Candidate counterpart", rendered)
        self.assertIn("flipkart.com", rendered)
        self.assertIn("https://flipkart.com/gillette-series-5/p/itm123?pid=TRIMMER123", rendered)

    def test_candidate_with_no_parseable_source_is_not_added(self):
        candidate = {"url": self.candidate_url, "attributes": {"brand": "Gillette"}}
        adapter = FakeAdapter([candidate], fail_retailers={"flipkart.com"})
        with patch.object(add_product, "ADAPTERS", (adapter,)), patch.object(
            add_product, "_load_watchlist", return_value=self.empty_watchlist
        ):
            proposed = add_product.build_product(
                self.seed_url,
                target=None,
                tier="warm",
                session=object(),
                confirm=lambda prompt: self.fail("confirmation must not run"),
            )
        self.assertEqual(
            [item["id"] for item in proposed["products"][0]["listings"]],
            ["amazon-in-b0gsvfv3r4"],
        )

    def test_same_retailer_identity_is_not_proposed_as_a_counterpart(self):
        candidate = {
            "url": "https://amazon.in/gp/product/B0GSVFV3R4/ref=alternate?psc=1",
            "attributes": {"brand": "Gillette", "model": "Series 5"},
        }
        proposed, adapter = self._build([candidate], [])
        product = proposed["products"][0]
        # Not "one listing" — the seed listing itself, undisturbed by a candidate
        # that pointed at the same amazon.in product through a different URL.
        self.assertEqual(
            [(item["id"], item["retailer"], item["url"]) for item in product["listings"]],
            [("amazon-in-b0gsvfv3r4", "amazon.in", "https://amazon.in/dp/B0GSVFV3R4")],
        )
        self.assertEqual(product["rejected_candidate_urls"], [])
        self.assertEqual(adapter.resolved, ["https://amazon.in/dp/B0GSVFV3R4"])


if __name__ == "__main__":
    unittest.main()
