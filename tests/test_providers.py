import base64
import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import fetch
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

    def test_pricehistory_records_the_observation_date_printed_on_its_own_page(self):
        """The page prints the date of the price, and the adapter now keeps it.

        This was xfail from 2026-08-20 until the fix later the same day. The old
        regex `r"Price in India on [^:|]+:\\s*" + _MONEY` stepped straight over
        "01/08/2026" and the Observation was built with a hardcoded
        `observed_ts=None`, which made fetch.py's 48-hour staleness guard dead
        code — its `if observation.observed_ts and ...` could never get past the
        first term.

        That is the failure this repo most needs to catch: the source serves a
        cached page from days ago, the price parses cleanly, and Price Sentinel
        records a stale number as today's and can alert on it.
        """
        body = self.ph_body.replace("on 01/08/2026:", "on 20/07/2026:")
        observation = self._ph_fetch(body)
        self.assertEqual(
            observation.observed_ts,
            datetime(2026, 7, 20, tzinfo=timezone.utc),
        )


class ObservationDateTests(unittest.TestCase):
    """The date a page prints next to its price, and what we are allowed to infer.

    THE DATE FORMAT IS AN ASSUMPTION, WRITTEN DOWN HERE ON PURPOSE.
    pricehistory.app prints `01/08/2026`, which is 1 August under day-first and
    8 January under month-first. No page saved in this repo carries a day above
    12, so no fixture settles it on its own. What does point one way is a
    cross-check inside the fixture: `tests/fixtures/pricehistory_app/success.html`
    prints "Price in India on 01/08/2026: 3119", and the same page's embedded
    chart series, which uses unambiguous ISO dates, carries 3119 at "2026-08-01"
    (see test_pricehistory_decodes_public_embedded_chart_history). Same page,
    same price, one date written both ways, and it reads day-first. Day-first is
    also the Indian retail norm, and pricehistory.app prints prices in rupees.

    Confidence: good, not certain. Should a real capture ever show a day above
    12 in a position that contradicts this, the parser is wrong and this docstring
    is where to start.
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

    def test_a_day_above_twelve_is_read_day_first_and_settles_the_format(self):
        """29/07/2026 can only be 29 July — there is no 29th month.

        This is the test that makes the day-first decision visible instead of
        buried. Under month-first this date is not a date at all.
        """
        body = self.ph_body.replace("on 01/08/2026:", "on 29/07/2026:")
        self.assertEqual(
            self._ph_fetch(body).observed_ts,
            datetime(2026, 7, 29, tzinfo=timezone.utc),
        )

    def test_the_ambiguous_fixture_date_is_read_as_the_first_of_august(self):
        """01/08/2026 is 1 August, not 8 January. The assumption, asserted."""
        self.assertEqual(
            self._ph_fetch(self.ph_body).observed_ts,
            datetime(2026, 8, 1, tzinfo=timezone.utc),
        )

    def test_the_date_is_midnight_utc_so_a_page_is_never_treated_as_fresher_than_it_is(self):
        """The page prints a day with no clock time, so we take the start of it.

        Taking midnight makes an observation look up to a day older than it may
        really be. That is the safe direction: it can only make the staleness
        guard fire early, never late.
        """
        observed = self._ph_fetch(self.ph_body).observed_ts
        self.assertEqual((observed.hour, observed.minute, observed.second), (0, 0, 0))
        self.assertEqual(observed.tzinfo, timezone.utc)
        self.assertEqual(NOW - observed, timedelta(hours=12))

    def test_an_unreadable_date_on_the_price_line_is_markup_drift_not_a_shrug(self):
        """We read the price off that same line, so a date we cannot read means
        the line changed shape. Refusing sends the listing to the next provider,
        which is the whole point of having one."""
        body = self.ph_body.replace("on 01/08/2026:", "on some fine day:")
        with self.assertRaises(SourceError) as raised:
            self._ph_fetch(body)
        self.assertEqual(raised.exception.kind, "parse")
        self.assertEqual(raised.exception.message, "observation date is unreadable")

    def test_an_impossible_date_is_refused_rather_than_guessed_at(self):
        body = self.ph_body.replace("on 01/08/2026:", "on 31/02/2026:")
        with self.assertRaises(SourceError) as raised:
            self._ph_fetch(body)
        self.assertEqual(raised.exception.kind, "parse")
        self.assertEqual(raised.exception.message, "observation date is unreadable")

    def test_a_date_in_the_future_is_refused_because_it_cannot_be_an_observation(self):
        """Nothing was observed tomorrow. A future date means either the page is
        broken or our reading of the format is wrong, and both must be loud."""
        body = self.ph_body.replace("on 01/08/2026:", "on 02/08/2026:")
        with self.assertRaises(SourceError) as raised:
            self._ph_fetch(body)
        self.assertEqual(raised.exception.kind, "parse")
        self.assertEqual(raised.exception.message, "observation date is in the future")

    def test_buyhatke_reports_no_date_because_its_page_prints_none(self):
        """Not an oversight — a documented gap.

        The saved BuyHatke page is a `productData` blob with cur_price, min, avg,
        maxall, mrpFloat, pid, site_name and inStock, and no date field anywhere.
        There is nothing to parse, so observed_ts stays None, meaning "unknown",
        and the 48-hour guard cannot fire for this provider. Inventing a field
        name that no saved page contains would be a guess wearing a fix's clothes.
        """
        session = Mock()
        session.get.return_value = SimpleNamespace(status_code=200, text=self.bh_body)
        observation = buyhatke.fetch(
            "https://www.buyhatke.com/amazon-gillette-series-5-price-history-63-110659581",
            self.amazon_listing,
            session,
            now=NOW,
        )
        self.assertIsNone(observation.observed_ts)
        self.assertEqual(observation.fetched_ts, NOW)
        self.assertNotIn("date", self.bh_body.lower())


class StalenessGuardEndToEndTests(unittest.TestCase):
    """The guard in fetch.py, fed by the real adapter rather than a hand-built
    Observation. Both sides of the 48-hour line, because a guard tested only on
    the failing side is half tested."""

    LISTING = {
        "id": "amazon-in-b0gsvfv3r4",
        "retailer": "amazon.in",
        "url": "https://www.amazon.in/dp/B0GSVFV3R4",
        "source_urls": {"pricehistory.app": "https://pricehistory.app/p/gillette-series-5"},
    }
    SOURCE_URL = "https://pricehistory.app/p/gillette-series-5"

    def _observation_dated(self, printed_date):
        body = (ROOT / "pricehistory_app" / "success.html").read_text(encoding="utf-8")
        body = body.replace("on 01/08/2026:", f"on {printed_date}:")
        session = Mock()
        session.get.return_value = SimpleNamespace(status_code=200, text=body)
        return pricehistory_app.fetch(self.SOURCE_URL, self.LISTING, session, now=NOW)

    def _validate(self, observation):
        return fetch._validate_observation(
            observation, self.LISTING, "pricehistory.app", self.SOURCE_URL, NOW
        )

    def test_a_page_dated_three_days_ago_is_refused_as_stale(self):
        # NOW is 2026-08-01 12:00 UTC, so 29/07 midnight is 3 days 12 hours old.
        observation = self._observation_dated("29/07/2026")
        self.assertEqual(observation.observed_ts, datetime(2026, 7, 29, tzinfo=timezone.utc))
        self.assertEqual(NOW - observation.observed_ts, timedelta(days=3, hours=12))
        with self.assertRaises(SourceError) as raised:
            self._validate(observation)
        self.assertEqual(raised.exception.kind, "stale")
        self.assertEqual(raised.exception.message, "observation is more than 48 hours old")

    def test_a_page_dated_today_is_accepted_and_keeps_its_price(self):
        observation = self._observation_dated("01/08/2026")
        self.assertEqual(NOW - observation.observed_ts, timedelta(hours=12))
        self.assertIs(self._validate(observation), observation)
        self.assertEqual(observation.price, 3119.0)

    def test_an_observation_two_hours_old_passes_and_one_of_forty_nine_hours_does_not(self):
        """The page only prints a day, so the fine-grained line is checked on an
        Observation built by hand from a page that was dated today."""
        from dataclasses import replace

        today = self._observation_dated("01/08/2026")
        two_hours = replace(today, observed_ts=NOW - timedelta(hours=2))
        self.assertIs(self._validate(two_hours), two_hours)

        forty_nine = replace(today, observed_ts=NOW - timedelta(hours=49))
        with self.assertRaises(SourceError) as raised:
            self._validate(forty_nine)
        self.assertEqual(raised.exception.kind, "stale")


if __name__ == "__main__":
    unittest.main()
