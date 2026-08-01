import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import dashboard


class DashboardTests(unittest.TestCase):
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
