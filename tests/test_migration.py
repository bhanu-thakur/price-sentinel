import csv
import json
import unittest
from pathlib import Path

import catalog


ROOT = Path(__file__).resolve().parents[1]


class MigrationTests(unittest.TestCase):
    def test_migrated_gillette_history_keeps_seven_rows_and_values(self):
        path = ROOT / "data" / "amazon-in-b0gsvfv3r4.csv"
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertGreaterEqual(len(rows), 7)
        migrated_rows = rows[:7]
        self.assertEqual([row["price"] for row in migrated_rows], [
            "3359.00", "3359.00", "3359.00", "3359.00", "3359.00", "3119.00", "3119.00"
        ])
        self.assertEqual(migrated_rows[0]["ts"], "2026-07-31T21:07:49+00:00")
        self.assertEqual(migrated_rows[-1]["ts"], "2026-08-01T07:27:43+00:00")

    def test_state_migration_preserves_legacy_fields(self):
        old = {
            "B0GSVFV3R4": {
                "auto_tier": "hot",
                "consecutive_failures": 0,
                "last_checked_ts": "2026-08-01T07:27:43+00:00",
                "last_price": 3119.0,
                "last_score": 73.3,
                "site_avg": 3301.0,
                "site_high": 3999.0,
                "site_low": 2799.0,
                "last_alert_ts": "2026-07-31T21:07:49+00:00",
                "last_alert_price": 3000.0,
            }
        }
        migrated = catalog.migrate_legacy_state(
            old, "gillette-series-5-trimmer", "amazon-in-b0gsvfv3r4", "hot"
        )
        listing = migrated["listings"]["amazon-in-b0gsvfv3r4"]
        self.assertEqual(migrated["schema_version"], 2)
        self.assertEqual(listing["last_checked_ts"], old["B0GSVFV3R4"]["last_checked_ts"])
        self.assertEqual(listing["last_success_ts"], old["B0GSVFV3R4"]["last_checked_ts"])
        self.assertEqual(listing["last_price"], 3119.0)
        self.assertEqual(listing["last_score"], 73.3)
        self.assertEqual(listing["site_low"], 2799.0)
        product = migrated["products"]["gillette-series-5-trimmer"]
        self.assertEqual(product["last_alert_ts"], old["B0GSVFV3R4"]["last_alert_ts"])
        self.assertEqual(product["last_alert_price"], 3000.0)
