import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import dashboard


class DashboardTests(unittest.TestCase):
    NOW = datetime(2026, 8, 1, 12, tzinfo=timezone.utc)

    @staticmethod
    def _listing(listing_id, retailer):
        return {
            "id": listing_id,
            "retailer": retailer,
            "url": f"https://{retailer}/p/{listing_id}",
            "source_urls": {"buyhatke.com": f"https://buyhatke.com/{listing_id}"},
        }

    def test_indian_currency_grouping(self):
        self.assertEqual(dashboard._money(1249900), "₹12,49,900")
        self.assertEqual(dashboard._money(99999), "₹99,999")
        self.assertEqual(dashboard._money(None), "—")

    def test_verdict_line_reports_stale_products_not_only_the_newest_price(self):
        products = [
            {"id": "fresh", "listings": [{"id": "fresh-listing"}]},
            {"id": "stale", "listings": [{"id": "stale-listing"}]},
        ]
        state = {
            "products": {},
            "listings": {
                "fresh-listing": {"last_success_ts": self.NOW.isoformat()},
                "stale-listing": {"last_success_ts": (self.NOW - timedelta(days=2)).isoformat()},
            },
        }
        headline, detail = dashboard._verdict_line(products, state, self.NOW)
        self.assertEqual(headline, "No products in the buy zone")
        self.assertEqual(detail, "2 tracked · 1 stale · newest price Just now")

    def test_out_of_stock_sibling_does_not_override_buyable_recommendation(self):
        amazon = self._listing("amazon-listing", "amazon.in")
        flipkart = self._listing("flipkart-listing", "flipkart.com")
        amazon_verdict = {
            "price": 100,
            "score": 80,
            "alert": True,
            "in_stock": True,
            "life_low": 80,
            "life_high": 200,
            "reasons": [],
        }
        flipkart_verdict = {"price": 90, "score": 80, "alert": False, "in_stock": False}
        state = {
            "products": {"product": {
                "status": "buy",
                "recommended_listing_id": amazon["id"],
                "last_verdict": amazon_verdict,
                "stale_offers": [{
                    **flipkart_verdict,
                    "listing_id": flipkart["id"],
                    "fresh": True,
                    "last_success_ts": (self.NOW - timedelta(hours=1)).isoformat(),
                }],
            }},
            "listings": {
                amazon["id"]: {
                    "last_success_ts": (self.NOW - timedelta(hours=1)).isoformat(),
                    "last_verdict": amazon_verdict,
                    "last_in_stock": True,
                },
                flipkart["id"]: {
                    "last_success_ts": (self.NOW - timedelta(hours=1)).isoformat(),
                    "last_verdict": flipkart_verdict,
                    "last_in_stock": False,
                },
            },
        }
        product = {"id": "product", "name": "Product", "listings": [amazon, flipkart]}
        text = dashboard._card(product, state, {amazon["id"]: "amazon.json"}, self.NOW)
        self.assertIn(
            '<div class="sub2">Amazon · Fresh · 1 hr ago · 1 of 2 offers current</div>',
            text,
        )
        self.assertIn('<div class="delta num">50% below peak</div>', text)

    def test_out_of_stock_fallback_uses_its_own_listing_chart_and_links(self):
        amazon = self._listing("amazon-listing", "amazon.in")
        flipkart = self._listing("flipkart-listing", "flipkart.com")
        fallback = {
            "listing_id": flipkart["id"],
            "price": 95,
            "score": 60,
            "alert": False,
            "in_stock": False,
            "life_low": 90,
            "life_high": 140,
            "last_success_ts": (self.NOW - timedelta(hours=1)).isoformat(),
        }
        state = {
            "products": {"product": {
                "status": "idle",
                "recommended_listing_id": None,
                "last_verdict": None,
                "stale_offers": [fallback],
            }},
            "listings": {
                amazon["id"]: {
                    "last_success_ts": (self.NOW - timedelta(days=2)).isoformat(),
                    "last_verdict": {"price": 110, "in_stock": True},
                },
                flipkart["id"]: {
                    "last_success_ts": (self.NOW - timedelta(hours=1)).isoformat(),
                    "last_verdict": {"price": 95, "in_stock": False},
                    "last_in_stock": False,
                    "last_source": "buyhatke.com",
                },
            },
        }
        product = {"id": "product", "name": "Product", "listings": [amazon, flipkart]}
        text = dashboard._card(
            product,
            state,
            {amazon["id"]: "amazon.json", flipkart["id"]: "flipkart.json"},
            self.NOW,
        )
        self.assertIn('data-listing="flipkart-listing"', text)
        self.assertIn(
            '<div class="sub2">Flipkart · Fresh · 1 hr ago · Out of stock · 0 of 2 offers current</div>',
            text,
        )
        self.assertIn("Price history — Flipkart", text)
        self.assertIn("Open on Flipkart", text)
        self.assertIn('<div class="price num">₹95</div>', text)

    def test_stored_fresh_flag_cannot_revive_days_old_fallback(self):
        amazon = self._listing("amazon-listing", "amazon.in")
        old = (self.NOW - timedelta(days=2)).isoformat()
        state = {
            "products": {"product": {
                "status": "idle",
                "last_verdict": None,
                "stale_offers": [{
                    "listing_id": amazon["id"],
                    "price": 95,
                    "in_stock": False,
                    "fresh": True,
                    "last_success_ts": old,
                }],
            }},
            "listings": {amazon["id"]: {"last_success_ts": old, "last_verdict": {"price": 95}}},
        }
        product = {"id": "product", "name": "Product", "listings": [amazon]}
        text = dashboard._card(product, state, {amazon["id"]: "amazon.json"}, self.NOW)
        self.assertIn('<div class="price num">—</div>', text)
        self.assertIn('<div class="delta num">No fresh offer</div>', text)
        self.assertNotIn("Stale · 2d ago · Out of stock", text)

    def test_collapsed_row_surfaces_cross_retailer_saving(self):
        amazon = self._listing("amazon-listing", "amazon.in")
        flipkart = self._listing("flipkart-listing", "flipkart.com")
        amazon_verdict = {"price": 110, "score": 50, "alert": False, "in_stock": True}
        flipkart_verdict = {"price": 90, "score": 80, "alert": True, "in_stock": True}
        stamp = (self.NOW - timedelta(minutes=1)).isoformat()
        state = {
            "products": {"product": {
                "status": "buy",
                "recommended_listing_id": flipkart["id"],
                "last_verdict": flipkart_verdict,
                "stale_offers": [],
            }},
            "listings": {
                amazon["id"]: {"last_success_ts": stamp, "last_verdict": amazon_verdict},
                flipkart["id"]: {"last_success_ts": stamp, "last_verdict": flipkart_verdict},
            },
        }
        product = {"id": "product", "name": "Product", "listings": [amazon, flipkart]}
        text = dashboard._card(product, state, {}, self.NOW)
        self.assertIn(
            "Flipkart · Fresh · 1 min ago · Cheapest of 2 · ₹20 less than Amazon",
            text,
        )

    def test_ordering_escaping_offer_table_and_lazy_chart_files(self):
        products = [
            {
                "id": "idle-product",
                "name": "Idle <product>",
                "target": None,
                "tier": "cold",
                "listings": [{"id": "idle-listing", "retailer": "amazon.in", "url": "https://amazon.in/idle", "source_urls": {"pricehistory.app": "https://pricehistory.app/p/idle"}}],
            },
            {
                "id": "buy-product",
                "name": "Buy & Best",
                "target": 100,
                "tier": "warm",
                "listings": [
                    {"id": "buy-listing", "retailer": "flipkart.com", "url": "https://flipkart.com/item?pid=BUY1", "source_urls": {"buyhatke.com": "https://buyhatke.com/buy"}},
                    {"id": "alt-listing", "retailer": "amazon.in", "url": "https://amazon.in/alt", "source_urls": {"pricehistory.app": "https://pricehistory.app/p/alt"}},
                ],
            },
        ]
        state = {
            "schema_version": 2,
            "products": {
                "idle-product": {"status": "idle", "last_checked_ts": "2026-08-01T11:00:00+00:00"},
                "buy-product": {
                    "status": "buy",
                    "last_checked_ts": "2026-08-01T11:59:00+00:00",
                    "recommended_listing_id": "buy-listing",
                    "last_verdict": {"price": 90, "score": 100, "alert": True, "life_low": 90, "life_avg": 120, "life_high": 200, "median": 110, "reasons": ["<buy now>"]},
                },
            },
            "listings": {
                "buy-listing": {"last_success_ts": "2026-08-01T11:59:00+00:00", "last_source": "buyhatke.com", "site_low": 90, "site_avg": 120, "site_high": 200, "last_verdict": {"price": 90}, "provider_history": [{"date": "2026-04-12", "price": 200}, {"date": "2026-08-01", "price": 90}]},
                "alt-listing": {"last_success_ts": "2026-07-30T11:59:00+00:00", "last_source": "pricehistory.app", "last_verdict": {"price": 110}},
            },
        }
        histories = {
            "buy-listing": [(datetime(2026, 7, 31, 12, tzinfo=timezone.utc), 95), (datetime(2026, 8, 1, 12, tzinfo=timezone.utc), 90)],
            "alt-listing": [],
            "idle-listing": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "index.html"
            chart_dir = Path(directory) / "chart-data"
            with patch.object(dashboard.analyze, "load_history", side_effect=lambda listing_id, days=None: histories[listing_id]):
                dashboard.build(products, state, output_path=output, chart_dir=chart_dir, now=datetime(2026, 8, 1, 12, tzinfo=timezone.utc))
            text = output.read_text(encoding="utf-8")
            self.assertLess(text.index("Buy &amp; Best"), text.index("Idle &lt;product&gt;"))
            self.assertIn("1 product in the buy zone", text)
            self.assertIn("&lt;buy now&gt;", text)
            self.assertIn("Best", text)
            self.assertIn('class="head" aria-expanded="false"', text)
            self.assertIn('aria-hidden="true"', text)
            self.assertIn("Open on Flipkart", text)
            self.assertIn("View price history", text)
            self.assertIn("Loading price history", text)
            self.assertIn("nativeChart(holder,selected", text)
            self.assertIn("new Path2D()", text)
            self.assertIn("ResizeObserver", text)
            self.assertNotIn("bezierCurveTo", text)
            self.assertNotIn("cdn.jsdelivr.net", text)
            self.assertNotIn("new Chart(", text)
            self.assertNotIn("Edit target", text)
            self.assertNotIn("Pause alerts", text)
            self.assertNotIn("labels:[", text)
            self.assertNotIn("datasets:[{data:[", text)
            self.assertIn("path=holder.dataset.chartPath", text)
            self.assertNotIn("<buy now>", text)
            self.assertEqual(json.loads((chart_dir / "buy-listing.json").read_text(encoding="utf-8")), [{"date": "2026-04-12", "price": 200.0}, {"date": "2026-08-01", "price": 90.0}])
            self.assertEqual(json.loads((chart_dir / "alt-listing.json").read_text(encoding="utf-8")), [])
            self.assertIn("No price history yet", text)


if __name__ == "__main__":
    unittest.main()
