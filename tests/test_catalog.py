import json
import tempfile
import unittest
from pathlib import Path

import catalog


class CatalogTests(unittest.TestCase):
    def test_normalize_url_strips_tracking_and_www(self):
        value = catalog.normalize_url(
            "https://www.amazon.in/dp/B0GSVFV3R4?utm_source=x&tag=demo&psc=1"
        )
        self.assertEqual(value, "https://amazon.in/dp/B0GSVFV3R4")
        self.assertEqual(catalog.retailer_hostname(value), "amazon.in")

    def test_normalize_url_upgrades_discovered_http_links(self):
        value = catalog.normalize_url(
            "http://www.flipkart.com/classic-jenga/p/item?pid=GAME123&utm_source=x"
        )
        self.assertEqual(value, "https://flipkart.com/classic-jenga/p/item?pid=GAME123")

    def test_amazon_paths_share_one_listing_identity(self):
        paths = [
            "https://www.amazon.in/Title/dp/B08675PSBT?tag=demo",
            "https://amazon.in/gp/product/B08675PSBT/ref=cart?psc=1",
            "https://amazon.in/dp/B08675PSBT",
        ]
        self.assertEqual(
            {catalog.normalize_url(value) for value in paths},
            {"https://amazon.in/dp/B08675PSBT"},
        )
        self.assertEqual(
            {catalog.listing_identity(value) for value in paths},
            {("amazon.in", "b08675psbt")},
        )

    def test_ids_are_stable_and_filesystem_safe(self):
        self.assertEqual(
            catalog.listing_id_for("https://www.amazon.in/dp/B0GSVFV3R4"),
            "amazon-in-b0gsvfv3r4",
        )
        product_id = catalog.product_id_for("Gillette Series 5 Trimmer", "https://amazon.in/dp/B0GSVFV3R4")
        self.assertEqual(product_id, "gillette-series-5-trimmer")
        collision = catalog.product_id_for(
            "Gillette Series 5 Trimmer",
            "https://amazon.in/dp/OTHER12345",
            [product_id],
        )
        self.assertRegex(collision, r"^gillette-series-5-trimmer-[0-9a-f]{8}$")

    def test_exact_match_and_variant_conflict(self):
        seed = {"brand": "Sony", "model": "WH1000XM5", "storage": "256 GB"}
        self.assertEqual(
            catalog.match_candidate(seed, {"brand": "sony", "model": "wh1000xm5", "storage": "256 gb"}),
            "accept",
        )
        self.assertEqual(
            catalog.match_candidate(seed, {"brand": "Sony", "model": "WH1000XM5", "storage": "128 GB"}),
            "reject",
        )
        self.assertEqual(catalog.match_candidate(seed, {"brand": "Sony", "model": "WH1000XM5"}), "confirm")
        self.assertEqual(catalog.match_candidate(seed, {"brand": "Sony", "model": "OTHER"}), "reject")

    def test_heuristic_brand_mismatch_requires_confirmation(self):
        seed = {"brand": "Hasbro", "model": "Jenga"}
        candidate = {"brand": "Original", "model": "Jenga"}
        self.assertEqual(catalog.match_candidate(seed, candidate), "confirm")

    def test_schema_v2_write(self):
        data = {
            "schema_version": 2,
            "products": [{
                "id": "demo",
                "name": "Demo",
                "rejected_candidate_urls": [],
                "listings": [{
                    "id": "amazon-in-demo123456",
                    "retailer": "amazon.in",
                    "url": "https://amazon.in/dp/DEMO123456",
                    "confirmed_by": "seed",
                    "attributes": {},
                    "source_urls": {},
                }],
            }],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "watchlist.json"
            catalog.write_watchlist(path, data)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), data)

    def test_watchlist_rejects_duplicate_retailer_identity(self):
        listing = {
            "id": "amazon-in-b08675psbt",
            "retailer": "amazon.in",
            "url": "https://amazon.in/dp/B08675PSBT",
            "confirmed_by": "seed",
            "attributes": {},
            "source_urls": {},
        }
        data = {
            "schema_version": 2,
            "products": [{
                "id": "jenga",
                "name": "Jenga",
                "rejected_candidate_urls": [],
                "listings": [listing, {**listing, "url": "https://amazon.in/gp/product/B08675PSBT"}],
            }],
        }
        with self.assertRaisesRegex(ValueError, "duplicate retailer listing"):
            catalog.validate_watchlist(data)
