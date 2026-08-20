import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import catalog
import main
from providers.base import Observation


NOW = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)


def listing(listing_id, retailer, source, url):
    return {
        "id": listing_id,
        "retailer": retailer,
        "url": url,
        "confirmed_by": "seed",
        "attributes": {"brand": "Gillette", "model": "Series 5"},
        "source_urls": {source: f"https://{source}/verified"},
    }


def observation(listing_value, price, history=None):
    return Observation(
        listing_id=listing_value["id"],
        price=price,
        mrp=3999.0,
        currency="INR",
        in_stock=True,
        title="Gillette Series 5",
        seller=None,
        retailer=listing_value["retailer"],
        listing_url=listing_value["url"],
        source=next(iter(listing_value["source_urls"])),
        source_url=next(iter(listing_value["source_urls"].values())),
        fetched_ts=NOW,
        observed_ts=None,
        site_low=2799.0,
        site_avg=3301.0,
        site_high=3999.0,
        history=history,
    )


class MainTests(unittest.TestCase):
    def test_no_due_products_leave_state_and_dashboard_unchanged(self):
        amazon = listing(
            "amazon-in-b0gsvfv3r4",
            "amazon.in",
            "pricehistory.app",
            "https://amazon.in/dp/B0GSVFV3R4",
        )
        watchlist = {
            "schema_version": 2,
            "products": [{
                "id": "gillette-series-5-trimmer",
                "name": "Gillette Series 5",
                "target": None,
                "tier": "warm",
                "notes": "",
                "rejected_candidate_urls": [],
                "listings": [amazon],
            }],
        }
        state = {
            "schema_version": 2,
            "providers": {},
            "products": {"gillette-series-5-trimmer": {
                "last_checked_ts": NOW.isoformat(),
                "auto_tier": "warm",
            }},
            "listings": {},
        }
        original = json.dumps(state, separators=(",", ":"))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            watchlist_path = root / "watchlist.json"
            state_path = root / "state.json"
            watchlist_path.write_text(json.dumps(watchlist), encoding="utf-8")
            state_path.write_text(original, encoding="utf-8")
            with patch.object(main, "WATCHLIST", str(watchlist_path)), \
                    patch.object(main, "STATE_PATH", str(state_path)), \
                    patch.object(main.fetcher, "fetch_listing") as fetch_listing, \
                    patch.object(main.dashboard, "build") as build, \
                    patch.object(main.notify, "dispatch") as dispatch:
                result = main.run(now=NOW, session=object())
            self.assertEqual(state_path.read_text(encoding="utf-8"), original)
        self.assertEqual(result, state)
        fetch_listing.assert_not_called()
        build.assert_not_called()
        dispatch.assert_not_called()

    def test_cheapest_fresh_offer_wins_and_only_one_alert_is_dispatched(self):
        amazon = listing(
            "amazon-in-b0gsvfv3r4",
            "amazon.in",
            "pricehistory.app",
            "https://amazon.in/dp/B0GSVFV3R4",
        )
        flipkart = listing(
            "flipkart-com-trimmer123",
            "flipkart.com",
            "buyhatke.com",
            "https://flipkart.com/p/trimmer?pid=TRIMMER123",
        )
        watchlist = {
            "schema_version": 2,
            "products": [{
                "id": "gillette-series-5-trimmer",
                "name": "Gillette Series 5",
                "target": 2850,
                "tier": "warm",
                "notes": "",
                "rejected_candidate_urls": [],
                "listings": [amazon, flipkart],
            }],
        }

        def fake_fetch(listing_value, provider_state, session=None, now=None):
            price = 3000.0 if listing_value["id"].startswith("amazon") else 2800.0
            history = (("2026-04-12", 3999.0), ("2026-08-01", 3000.0)) if listing_value["id"].startswith("amazon") else None
            return observation(listing_value, price, history=history), provider_state, [{"status": "success"}]

        def fake_evaluate(listing_id, obs_value, product):
            return {
                "listing_id": listing_id,
                "product_id": product["id"],
                "name": product["name"],
                "price": obs_value.price,
                "score": 80 if obs_value.price == 2800 else 50,
                "alert": obs_value.price <= 2850,
                "in_stock": True,
                "url": obs_value.listing_url,
                "reasons": [],
            }

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            watchlist_path = root / "watchlist.json"
            state_path = root / "state.json"
            watchlist_path.write_text(json.dumps(watchlist), encoding="utf-8")
            state_path.write_text(json.dumps({"schema_version": 2, "providers": {}, "products": {}, "listings": {}}), encoding="utf-8")
            with patch.object(main, "WATCHLIST", str(watchlist_path)), \
                    patch.object(main, "STATE_PATH", str(state_path)), \
                    patch.object(main.fetcher, "fetch_listing", side_effect=fake_fetch), \
                    patch.object(main.analyze, "append_observation"), \
                    patch.object(main.analyze, "evaluate", side_effect=fake_evaluate), \
                    patch.object(main.dashboard, "build"), \
                    patch.object(main.notify, "dispatch", return_value=True) as dispatch:
                state = main.run(now=NOW, session=object())

        product_state = state["products"]["gillette-series-5-trimmer"]
        self.assertEqual(product_state["recommended_listing_id"], "flipkart-com-trimmer123")
        self.assertEqual(product_state["status"], "buy")
        self.assertEqual(product_state["last_alert_price"], 2800.0)
        self.assertNotIn("last_alert_price", state["listings"]["flipkart-com-trimmer123"])
        self.assertEqual(dispatch.call_count, 1)
        self.assertEqual(len(dispatch.call_args.args[0]), 1)
        self.assertEqual(dispatch.call_args.args[0][0]["listing_id"], "flipkart-com-trimmer123")
        self.assertEqual(state["listings"]["amazon-in-b0gsvfv3r4"]["provider_history"], [
            {"date": "2026-04-12", "price": 3999.0},
            {"date": "2026-08-01", "price": 3000.0},
        ])

    def test_failed_notification_does_not_start_alert_cooldown(self):
        amazon = listing(
            "amazon-in-b0gsvfv3r4",
            "amazon.in",
            "pricehistory.app",
            "https://amazon.in/dp/B0GSVFV3R4",
        )
        watchlist = {
            "schema_version": 2,
            "products": [{
                "id": "gillette-series-5-trimmer",
                "name": "Gillette Series 5",
                "target": 3100,
                "tier": "warm",
                "notes": "",
                "rejected_candidate_urls": [],
                "listings": [amazon],
            }],
        }
        verdict = {
            "listing_id": amazon["id"],
            "product_id": "gillette-series-5-trimmer",
            "name": "Gillette Series 5",
            "price": 3000.0,
            "score": 80,
            "alert": True,
            "in_stock": True,
            "url": amazon["url"],
            "reasons": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            watchlist_path = root / "watchlist.json"
            state_path = root / "state.json"
            watchlist_path.write_text(json.dumps(watchlist), encoding="utf-8")
            state_path.write_text(
                json.dumps({"schema_version": 2, "providers": {}, "products": {}, "listings": {}}),
                encoding="utf-8",
            )
            with patch.object(main, "WATCHLIST", str(watchlist_path)), \
                    patch.object(main, "STATE_PATH", str(state_path)), \
                    patch.object(main.fetcher, "fetch_listing", return_value=(
                        observation(amazon, 3000.0), {}, [{"status": "success"}],
                    )), \
                    patch.object(main.analyze, "append_observation"), \
                    patch.object(main.analyze, "evaluate", return_value=verdict), \
                    patch.object(main.dashboard, "build"), \
                    patch.object(main.notify, "dispatch", return_value=False):
                state = main.run(now=NOW, session=object())
        product_state = state["products"]["gillette-series-5-trimmer"]
        self.assertNotIn("last_alert_ts", product_state)
        self.assertNotIn("last_alert_price", product_state)

    def test_failed_check_does_not_rewrite_last_success_timestamp(self):
        amazon = listing(
            "amazon-in-b0gsvfv3r4",
            "amazon.in",
            "pricehistory.app",
            "https://amazon.in/dp/B0GSVFV3R4",
        )
        old_success = "2026-08-01T00:00:00+00:00"
        old_verdict = {
            "listing_id": amazon["id"],
            "price": 3000.0,
            "score": 50,
            "alert": False,
            "in_stock": True,
            "url": amazon["url"],
        }
        watchlist = {
            "schema_version": 2,
            "products": [{
                "id": "gillette-series-5-trimmer",
                "name": "Gillette Series 5",
                "target": None,
                "tier": "warm",
                "notes": "",
                "rejected_candidate_urls": [],
                "listings": [amazon],
            }],
        }
        state = {
            "schema_version": 2,
            "providers": {},
            "products": {"gillette-series-5-trimmer": {"last_checked_ts": "2026-07-31T00:00:00+00:00", "auto_tier": "warm"}},
            "listings": {amazon["id"]: {"last_success_ts": old_success, "last_verdict": old_verdict}},
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            watchlist_path = root / "watchlist.json"
            state_path = root / "state.json"
            watchlist_path.write_text(json.dumps(watchlist), encoding="utf-8")
            state_path.write_text(json.dumps(state), encoding="utf-8")
            with patch.object(main, "WATCHLIST", str(watchlist_path)), \
                    patch.object(main, "STATE_PATH", str(state_path)), \
                    patch.object(main.fetcher, "fetch_listing", return_value=(None, {}, [{"status": "failed"}])), \
                    patch.object(main.dashboard, "build"), \
                    patch.object(main.notify, "dispatch"):
                result = main.run(now=NOW, session=object())
        record = result["listings"][amazon["id"]]
        self.assertEqual(record["last_success_ts"], old_success)
        self.assertEqual(record["last_attempt_ts"], "2026-08-01T12:00:00+00:00")

    def test_dashboard_failure_does_not_discard_collected_state(self):
        amazon = listing(
            "amazon-in-b0gsvfv3r4",
            "amazon.in",
            "pricehistory.app",
            "https://amazon.in/dp/B0GSVFV3R4",
        )
        watchlist = {
            "schema_version": 2,
            "products": [{
                "id": "gillette-series-5-trimmer",
                "name": "Gillette Series 5",
                "target": None,
                "tier": "warm",
                "notes": "",
                "rejected_candidate_urls": [],
                "listings": [amazon],
            }],
        }
        verdict = {
            "listing_id": amazon["id"],
            "price": 3000.0,
            "score": 50,
            "alert": False,
            "in_stock": True,
            "reasons": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            watchlist_path = root / "watchlist.json"
            state_path = root / "state.json"
            watchlist_path.write_text(json.dumps(watchlist), encoding="utf-8")
            state_path.write_text(
                json.dumps({"schema_version": 2, "providers": {}, "products": {}, "listings": {}}),
                encoding="utf-8",
            )
            with patch.object(main, "WATCHLIST", str(watchlist_path)), \
                    patch.object(main, "STATE_PATH", str(state_path)), \
                    patch.object(main.fetcher, "fetch_listing", return_value=(
                        observation(amazon, 3000.0), {}, [{"status": "success"}],
                    )), \
                    patch.object(main.analyze, "append_observation"), \
                    patch.object(main.analyze, "evaluate", return_value=verdict), \
                    patch.object(main.dashboard, "build", side_effect=RuntimeError("render failed")), \
                    patch.object(main.notify, "dispatch"):
                main.run(now=NOW, session=object())
            persisted = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(
            persisted["listings"][amazon["id"]]["last_price"],
            3000.0,
        )


class ShippedDataFilesTests(unittest.TestCase):
    """The files actually committed in this repo, not a fixture built in a tmpdir.

    Every other test here writes its own watchlist, so the suite stayed green when
    the watchlist was emptied on 2026-08-20 — it never read the real one. These
    tests do, so an empty watchlist has to keep being a state the app accepts
    rather than a state nothing happens to exercise.
    """

    REPO = Path(__file__).resolve().parents[1]

    def setUp(self):
        self.watchlist = json.loads(
            (self.REPO / "watchlist.json").read_text(encoding="utf-8")
        )
        self.state = json.loads(
            (self.REPO / "data" / "state.json").read_text(encoding="utf-8")
        )

    def test_the_shipped_watchlist_passes_the_repos_own_validator(self):
        # Not "does not raise" — validate_watchlist returns the data it accepted.
        self.assertEqual(catalog.validate_watchlist(self.watchlist), self.watchlist)
        self.assertEqual(self.watchlist["schema_version"], 2)

    def test_state_carries_no_entry_for_a_product_the_watchlist_dropped(self):
        """Orphan state is how a removed product comes back to life on the dashboard."""
        tracked_products = {product["id"] for product in self.watchlist["products"]}
        tracked_listings = {
            listing["id"]
            for product in self.watchlist["products"]
            for listing in product["listings"]
        }
        self.assertEqual(set(self.state["products"]), tracked_products)
        self.assertEqual(set(self.state["listings"]), tracked_listings)
        # Providers are configuration, not per-product, and survive an empty list.
        self.assertEqual(
            sorted(self.state["providers"]), ["buyhatke.com", "pricehistory.app"]
        )
        self.assertEqual(self.state["schema_version"], 2)

    def test_a_run_over_the_shipped_watchlist_with_no_products_does_nothing(self):
        """Zero products due means zero fetches, zero alerts, and no state rewrite.

        The real files are copied into a tmpdir first: the assertion is about their
        content, but a regression here must never be able to write the repo's own
        state.json.
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            watchlist_path = root / "watchlist.json"
            state_path = root / "state.json"
            watchlist_path.write_text(json.dumps(self.watchlist), encoding="utf-8")
            original = json.dumps(self.state, indent=2, sort_keys=True)
            state_path.write_text(original, encoding="utf-8")

            with patch.object(main, "WATCHLIST", str(watchlist_path)), \
                    patch.object(main, "STATE_PATH", str(state_path)), \
                    patch.object(main.fetcher, "fetch_listing") as fetch_listing, \
                    patch.object(main.dashboard, "build") as build, \
                    patch.object(main.notify, "dispatch") as dispatch:
                result = main.run(now=NOW, session=object())

            self.assertEqual(state_path.read_text(encoding="utf-8"), original)

        self.assertEqual(self.watchlist["products"], [])
        self.assertEqual(result["listings"], {})
        self.assertEqual(result["products"], {})
        fetch_listing.assert_not_called()
        build.assert_not_called()
        dispatch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
