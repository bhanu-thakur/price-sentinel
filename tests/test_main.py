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

    def test_removed_products_are_pruned_even_when_no_products_are_due(self):
        watchlist = {"schema_version": 2, "products": []}
        state = {
            "schema_version": 2,
            "providers": {"pricehistory.app": {}},
            "products": {"already-bought": {"status": "buy"}},
            "listings": {"amazon-in-b000000000": {"last_price": 999.0}},
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            watchlist_path = root / "watchlist.json"
            state_path = root / "state.json"
            watchlist_path.write_text(json.dumps(watchlist), encoding="utf-8")
            state_path.write_text(json.dumps(state), encoding="utf-8")

            with patch.object(main, "WATCHLIST", str(watchlist_path)), \
                    patch.object(main, "STATE_PATH", str(state_path)), \
                    patch.object(main.fetcher, "fetch_listing") as fetch_listing, \
                    patch.object(main.dashboard, "build") as build, \
                    patch.object(main.notify, "dispatch") as dispatch:
                result = main.run(now=NOW, session=object())

            persisted = json.loads(state_path.read_text(encoding="utf-8"))

        self.assertEqual(result["products"], {})
        self.assertEqual(result["listings"], {})
        self.assertEqual(persisted, result)
        fetch_listing.assert_not_called()
        dispatch.assert_not_called()
        build.assert_called_once_with([], result)


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

    def test_shipped_watchlist_contains_the_researched_seltos_catalog(self):
        """Pin the exact retailer identities and useful-price alert thresholds."""
        expected = {
            "agaro-supreme-pressure-washer": ("amazon-in-b09vkwgzd7", 5500),
            "shakti-s3-pressure-washer": ("amazon-in-b0bbwjfk5c", 4200),
            "black-decker-bepw1600-pressure-washer": ("amazon-in-b0b1d2g6cc", 5999),
            "70mai-a510-dual-channel-dashcam": ("amazon-in-b0cvh2k929", 10999),
            "michelin-12266-tyre-inflator": ("amazon-in-b00ierqc80", 3600),
            "amazon-basics-4-gauge-jumper-cable": ("amazon-in-b074dmn1xm", 1750),
            "stanley-tubeless-tyre-repair-kit": ("amazon-in-b085s7nj2v", 450),
            "siago-car-safety-hammer": ("amazon-in-b0dlgxl3nj", 399),
            "jopasu-car-duster": ("amazon-in-b00rjq8xhu", 799),
            "vahan-expo-7d-floor-mats-seltos-2026": ("amazon-in-b0gmr9pn1w", 3200),
        }
        actual = {
            product["id"]: (product["listings"][0]["id"], product["target"])
            for product in self.watchlist["products"]
        }

        self.assertEqual(actual, expected)
        self.assertEqual(len(self.watchlist["products"]), 10)
        for product in self.watchlist["products"]:
            research = product["research"]
            self.assertEqual(research["as_of"], "2026-09-11")
            self.assertIn(research["community_consensus"], {"positive", "mixed", "category-supported"})
            self.assertGreaterEqual(research["marketplace_rating"]["review_count"], 1)
            self.assertIn("pricehistory.app", research["marketplace_rating"]["source_url"])
            evidence_hosts = {item["source"] for item in research["evidence"]}
            self.assertIn("Team-BHP", evidence_hosts)
            self.assertIn("Reddit", evidence_hosts)
            self.assertTrue(research["caveats"])

    def test_washer_research_preserves_budget_and_negative_evidence(self):
        products = {product["id"]: product for product in self.watchlist["products"]}
        expected_ratings = {
            "agaro-supreme-pressure-washer": (7.8, 10196),
            "shakti-s3-pressure-washer": (8.4, 6542),
            "black-decker-bepw1600-pressure-washer": (8.4, 323),
        }
        for product_id, expected in expected_ratings.items():
            research = products[product_id]["research"]
            rating = research["marketplace_rating"]
            self.assertEqual((rating["score_out_of_10"], rating["review_count"]), expected)

        agaro = products["agaro-supreme-pressure-washer"]["research"]
        self.assertEqual(agaro["community_consensus"], "mixed")
        self.assertIn("negative", {item["sentiment"] for item in agaro["evidence"]})
        self.assertIn("warranty", " ".join(agaro["caveats"]).lower())

        shakti = products["shakti-s3-pressure-washer"]["research"]
        self.assertIn("6-month", " ".join(shakti["caveats"]).lower())
        self.assertIn("china", " ".join(shakti["caveats"]).lower())

        self.assertEqual(
            {product_id: products[product_id]["research"]["budget_position"] for product_id in expected_ratings},
            {
                "agaro-supreme-pressure-washer": "within-requested-range",
                "shakti-s3-pressure-washer": "below-requested-range",
                "black-decker-bepw1600-pressure-washer": "near-upper-bound",
            },
        )

    def test_removed_and_legacy_product_artifacts_are_not_shipped(self):
        forbidden = {
            "amazon-in-b073j92g1j",
            "amazon-in-b07g9mpy1x",
            "amazon-in-b07v1x58xv",
            "amazon-in-b08675psbt",
            "amazon-in-b0chjr8nld",
            "amazon-in-b0gsvfv3r4",
            "flipkart-com-cwrfjrhymdtemr3g",
            "flipkart-com-hasbro-gaming-classic-jenga-hardwood-blocks-stacking-tower-game-kids-ages-6-up-1-1ed14897",
        }
        self.assertEqual(
            forbidden & {path.stem for path in (self.REPO / "data").glob("*.csv")},
            set(),
        )
        self.assertEqual(
            forbidden & {path.stem for path in (self.REPO / "docs" / "chart-data").glob("*.json")},
            set(),
        )
        shipped_text = json.dumps(self.watchlist).lower()
        for listing_id in forbidden:
            self.assertNotIn(listing_id, shipped_text)
        self.assertNotIn("shampoo", shipped_text)
        self.assertNotIn("microfiber", shipped_text)


if __name__ == "__main__":
    unittest.main()
