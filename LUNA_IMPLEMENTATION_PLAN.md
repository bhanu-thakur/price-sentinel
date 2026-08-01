# Luna implementation specification

Follow this specification in order. Do not redesign it, add unrelated features, or
substitute different behavior. If a source cannot be verified from a real response,
stop and report that source as blocked; do not invent an API, URL, selector, field,
or product match.

## Outcome

Deliver these two changes together:

1. Replace the Amazon-specific fetch path with provider adapters in this exact order:
   `pricehistory.app`, `buyhatke.com`, then `pricehistoryapp.com`.
2. Make the approved `docs/prototype.html` design the generated `docs/index.html`.

Do not enable alerts. Do not configure secrets. Do not send test notifications. Do
not redesign the scoring engine.

## Non-negotiable behavior

- Never request an Amazon, Flipkart, or other retailer page in the scheduled run.
- Query a fallback only after the earlier provider fails, is invalid, or is explicitly
  stale. Do not query all providers for comparison on every run.
- Perform counterpart discovery only when adding a product, never on the schedule.
- Never use title similarity alone to declare two listings the same product.
- Keep separate history for every retailer listing.
- Preserve the 180-day recent window, lifetime overlay, lifetime-range score,
  seven-day cooldown, further-3%-drop override, and `daily_low()` chart data.
- Keep the runtime single-threaded. Do not parallelize source requests.
- Use only Python's standard library plus the dependencies already in
  `requirements.txt`. Use `unittest`, not pytest.
- Keep alert-related environment variables in the workflow but do not change
  `notify.py` unless a renamed product/listing key makes a compatibility edit
  unavoidable.

## Exact file layout

Create:

```text
providers/__init__.py
providers/base.py
providers/pricehistory_app.py
providers/buyhatke.py
providers/pricehistoryapp_com.py
catalog.py
add_product.py
tests/test_catalog.py
tests/test_fallbacks.py
tests/test_migration.py
tests/test_scoring.py
tests/test_dashboard.py
tests/fixtures/pricehistory_app/*.html
tests/fixtures/buyhatke/*.html
tests/fixtures/pricehistoryapp_com/*.html
```

Modify:

```text
watchlist.json
fetch.py
analyze.py
main.py
dashboard.py
README.md
HANDOFF.md
CHANGELOG.md
```

Delete only after its replacement is tested:

```text
docs/prototype.html
```

Do not hand-edit `docs/index.html`; regenerate it through `dashboard.py`.

## 1. Use this watchlist schema

Change `watchlist.json` to schema version 2. Use this structure and these exact key
names:

```json
{
  "schema_version": 2,
  "products": [
    {
      "id": "gillette-series-5-trimmer",
      "name": "Gillette Series 5 All-in-One Trimmer (Braun)",
      "target": 2850,
      "tier": "hot",
      "notes": "Seen at 2799 in July 2026. MRP 3999.",
      "rejected_candidate_urls": [],
      "listings": [
        {
          "id": "amazon-in-b0gsvfv3r4",
          "retailer": "amazon.in",
          "url": "https://www.amazon.in/dp/B0GSVFV3R4",
          "confirmed_by": "seed",
          "attributes": {
            "brand": "Gillette",
            "model": "Series 5",
            "variant": "All-in-One Trimmer"
          },
          "source_urls": {
            "pricehistory.app": "https://pricehistory.app/p/gillette-series-5-all-one-beard-body-5vQqMKIm"
          }
        }
      ]
    }
  ]
}
```

Rules:

- `product.id` is an internal stable identifier; it is not an ASIN or retailer ID.
- `listing.id` is stable and filesystem-safe: lowercase ASCII letters, digits, and
  hyphens only.
- `retailer` is the normalized retailer hostname without `www`.
- `source_urls` contains only verified provider product pages. Omit unresolved
  providers; do not store guessed URLs or `null`.
- `listings` contains only confirmed equivalent products.
- Store rejected normalized listing URLs in `rejected_candidate_urls` so intake does
  not propose them again.

For newly added products, create `product.id` from the normalized title slug. If the
slug already exists, append the first eight hex characters of SHA-256 of the
normalized seed URL. Never change an ID after it is committed.

## 2. Use this normalized observation contract

In `providers/base.py`, define an immutable `Observation` dataclass with these exact
fields:

```text
listing_id: str
price: float
mrp: float | None
currency: str
in_stock: bool
title: str | None
seller: str | None
retailer: str
listing_url: str
source: str
source_url: str
fetched_ts: datetime
observed_ts: datetime | None
site_low: float | None
site_avg: float | None
site_high: float | None
```

Also define `SourceError` with `provider`, `kind`, and `message`. `kind` must be one
of: `network`, `blocked`, `http`, `parse`, `identity`, `stale`, or `unsupported`.

An adapter result is acceptable only when:

- price is finite and greater than zero;
- currency is `INR`;
- parsed retailer agrees with the stored listing retailer;
- the page describes the stored listing, verified by retailer product ID when
  available, otherwise by the confirmed identity attributes;
- an explicit `observed_ts`, when present, is not more than 48 hours old.

Missing lifetime statistics do not invalidate a current price. If lifetime fields are
present, require `0 < site_low <= site_high`; discard only the invalid lifetime fields.
When a provider does not expose an observation timestamp, set `observed_ts=None` and
do not call it stale solely for that reason.

## 3. Implement provider adapters without guessing

Each provider module must expose:

```python
PROVIDER = "exact.provider.name"
def fetch(source_url, listing, session, now=None) -> Observation: ...
def resolve(retailer_url, session) -> str | None: ...
def discover(source_url, session) -> list[dict]: ...
```

Use these exact provider names and priority:

1. `pricehistory.app`
2. `buyhatke.com`
3. `pricehistoryapp.com`

Instructions for every adapter:

1. Inspect a real public response.
2. Save a minimal sanitized HTML fixture containing the fields the parser uses.
3. Write the parser against that fixture.
4. Add a fixture for a missing-price or malformed response.
5. Make `fetch`, `resolve`, and `discover` return/raise deterministically.

Prefer server-rendered meta tags or JSON-LD over visual CSS selectors. Do not call a
private API copied from browser traffic. Do not bypass a CAPTCHA, login, bot check, or
rate limit. If resolution or discovery requires JavaScript, a private API, login, or
CAPTCHA, raise `SourceError(kind="unsupported")` and report the limitation.

`discover` returns retailer candidates only when the provider's public product page
already exposes comparison listings. It must not run a broad web search.

Reference facts verified on 2026-08-01:

- `pricehistory.app` accepts a product link or name and says price tracking is enabled
  for Amazon and Flipkart: https://pricehistory.app/
- BuyHatke accepts Amazon/Flipkart links and advertises cross-store comparison:
  https://www.buyhatke.com/
- `pricehistoryapp.com` product pages expose “same product” offers, but examples mix
  nearby models/variants. Treat every result as a candidate, not as truth:
  https://pricehistoryapp.com/product/google-pixel-10-frost-256-gb

## 4. Make `fetch.py` only orchestrate providers

Delete the direct Amazon `fetch()` implementation, Amazon selectors, ASIN URL
construction, and retailer-page parsing from `fetch.py`.

Implement:

```python
def fetch_listing(listing, provider_state, session=None, now=None):
    """Return (Observation | None, updated_provider_state, attempts_log)."""
```

For one listing, iterate only through verified keys present in `listing.source_urls`,
using the fixed provider priority. Make at most one HTTP request per provider during a
scheduled run. Return immediately on the first valid observation.

Maintain global provider health under `data/state.json`:

```json
"providers": {
  "pricehistory.app": {
    "consecutive_failures": 0,
    "disabled_until": null,
    "last_error": null
  }
}
```

Apply these exact circuit-breaker rules:

- HTTP 403 or 429: set that provider's `disabled_until` to six hours from now.
- Network, HTTP 5xx, parse, identity, or stale failure: increment
  `consecutive_failures`; after three consecutive failures, disable for three hours.
- HTTP 404: remove/mark only that listing's source URL invalid; do not disable the
  provider globally.
- Success: reset the provider's failure count and error, and clear an expired breaker.
- A disabled provider is skipped without a request.

Keep requests single-threaded. Enforce a randomized 4–11 second gap between all
outbound requests, including requests for two listings of the same product. Do not
sleep before the first request.

If all providers fail, return `None`, do not append history, retain the last-known-good
state, and record a failure. Never present last-known-good data as newly checked.

## 5. Implement one-link product intake

Create this command:

```powershell
python add_product.py "<retailer-url>" --target 2850 --tier hot
```

`--target` is optional. `--tier` defaults to `warm` and accepts only `hot`, `warm`, or
`cold`.

The command must:

1. Accept one `https` retailer URL and strip tracking query parameters.
2. Normalize the retailer hostname without `www`.
3. Resolve provider product URLs in fixed priority order and store only successful,
   parseable final product URLs.
4. Fetch the seed listing through the first working provider and extract title and
   identity attributes.
5. Create the product and seed listing in schema v2.
6. Run `discover` once against verified provider pages.
7. Exclude URLs already confirmed or rejected.
8. Evaluate candidates using the matching rules below.
9. Write `watchlist.json` only after showing the complete proposed change and receiving
   confirmation. On Ctrl+C or “no”, write nothing.

Do not add a dashboard form. GitHub Pages is static and has no safe write backend.
Do not add a scheduled discovery job. Manual JSON editing remains supported.

### Exact counterpart matching rules

Normalize case, whitespace, punctuation, and retailer marketing words. Do not use an
LLM or fuzzy-title score to auto-confirm.

Auto-confirm a candidate only when:

- brand matches; and
- an exact manufacturer model/part number, GTIN, EAN, UPC, or ISBN matches; and
- every available price-relevant variant attribute matches, including storage,
  memory, capacity, size, pack count, generation, and colour when colour changes the
  SKU.

If an exact identifier is absent, any identifier conflicts, or either side is missing
a price-relevant variant attribute, print the candidate and ask:

```text
Add this as the same product? [y/N]
```

`Enter` means no. A rejected URL is stored in `rejected_candidate_urls`. Never alert
across an unconfirmed candidate.

## 6. Migrate the current data exactly once

Commit the migration with the code; do not perform it dynamically in every run.

- Use product ID `gillette-series-5-trimmer`.
- Use listing ID `amazon-in-b0gsvfv3r4`.
- Rename `data/B0GSVFV3R4.csv` to `data/amazon-in-b0gsvfv3r4.csv` without changing
  rows or timestamps.
- Convert the old ASIN state record into the new listing record without losing
  `last_checked_ts`, `last_price`, `last_score`, or lifetime statistics.
- Preserve the product's target, tier, notes, Amazon URL, and existing
  `pricehistory.app` URL.

Use this state layout:

```json
{
  "schema_version": 2,
  "providers": {},
  "products": {
    "gillette-series-5-trimmer": {
      "auto_tier": "hot",
      "last_verdict": null
    }
  },
  "listings": {
    "amazon-in-b0gsvfv3r4": {
      "consecutive_failures": 0,
      "last_checked_ts": "...",
      "last_success_ts": "...",
      "last_price": 3119.0,
      "last_score": 73.3,
      "site_avg": 3301.0,
      "site_high": 3999.0,
      "site_low": 2799.0,
      "last_source": "pricehistory.app"
    }
  }
}
```

Replace `"..."` with the existing timestamp. `last_verdict` may remain `null` until
the first successful run. Add a migration unit test that proves the seven existing
CSV observations remain seven observations with unchanged values.

## 7. Track listings and derive one product verdict

In `main.py`:

1. Determine whether the product is due using its product tier.
2. For every confirmed listing of a due product, call `fetch_listing` sequentially.
3. Append a successful observation to that listing's CSV.
4. Evaluate each successful listing with the existing engine and the product target.
5. Define a fresh offer as an in-stock successful observation whose
   `last_success_ts` is no more than 24 hours old.
6. Choose the product's recommended offer as the lowest-priced fresh offer.
7. Store `products[product_id].last_verdict` from that recommended offer.
8. Set product status to `buy` when the recommended verdict has `alert=True`, `watch`
   when it is not an alert and score is at least 60, otherwise `idle`.
9. Set `auto_tier=hot` when the recommended score is at least 60; otherwise use the
   configured product tier.

Do not compare prices across different currencies or unconfirmed listings. Show stale
offers separately, but never choose one as the recommended offer.

In `analyze.py`, change the history key from ASIN to `listing_id` and rename user-facing
“90d” labels/comments to “180d” where they are wrong. Do not change thresholds,
formulas, or cooldown behavior.

Leave `notify.dispatch` wired as it is so future alert activation remains possible,
but do not add secrets or send a test. Pass only the recommended product verdict to
the notification path; do not send one alert per retailer listing.

## 8. Generate the final dashboard exactly as follows

Port the CSS and structure from `docs/prototype.html` into `dashboard.py`. Replace all
sample data. Generate `docs/index.html` from the schema-v2 watchlist and state.
Add a `__main__` entry point to `dashboard.py` that loads those files and performs the
same build, so `python dashboard.py` regenerates the dashboard without fetching prices.

### Page behavior

- Header verdict: `1 product in the buy zone · 4 tracked · checked 6 min ago`, with
  correct singular/plural forms and real data.
- Sort products in this order: `buy`, `watch`, `idle`; within a status, sort by score
  descending and then name ascending.
- Remove the prototype banner and filter chips.
- Keep the coloured left rail, collapsed rows, score meter, tabular numbers, dark
  styling, mobile layout, and single-open-card behavior.
- Collapsed row fields: product name, recommended retailer, freshness, score,
  recommended price, and percent below that listing's lifetime high.
- Expanded fields: range controls, chart, all-time low, 180-day median, all-time high,
  target, verdict reasons, and a table of confirmed retailer offers.
- Offer table fields: retailer, price, freshness, source, and `Open` link. Mark the
  recommended offer `Best`.
- Remove `Edit target` and `Pause alerts`. They cannot work on a static page.
- Escape every product name, retailer, reason, URL, and source string before inserting
  it into HTML or JavaScript.

### Real lazy charts

Do not embed all chart arrays in `index.html`.

- Write one file per listing to `docs/chart-data/<listing-id>.json`.
- Each JSON file contains only `daily_low()` points as ISO date plus numeric price.
- On the first card expansion, dynamically load Chart.js if it is not loaded, fetch
  only that recommended listing's JSON, and create the chart.
- Cache the chart instance in the page so reopening does not fetch again.
- Filter the loaded daily points in the browser for 1M, 3M, 6M, 1Y, and All.
- Default to 6M.
- Draw dotted labelled lines for lifetime low and target with a small local Chart.js
  plugin; do not add another CDN dependency.
- If chart JSON is missing or empty, show `No price history yet` without an exception.

The chart title must identify the retailer whose history is being shown. Alternative
offers remain in the table; do not merge multiple retailers into one line.

After the generated dashboard matches the approved prototype and passes visual QA,
delete `docs/prototype.html` and remove prototype links from documentation.

## 9. Required tests

Run all tests offline with:

```powershell
python -m unittest discover -s tests -v
```

Tests must cover:

- all three adapters parsing a saved successful fixture;
- malformed/missing-price fixture rejection for all three adapters;
- exact fallback order and immediate stop after success;
- disabled provider skipped without a request;
- 403/429 six-hour breaker and three-failure three-hour breaker;
- no direct retailer hostname requested;
- URL normalization and schema-v2 write;
- exact-identifier match accepted;
- same title but conflicting storage/size/pack/model rejected;
- ambiguous candidate requires confirmation;
- rejected candidate not proposed again;
- seven-row Gillette history survives migration unchanged;
- existing score examples remain: 3359 -> 53.3, 3250 -> 62.4, 2799 -> 100.0
  for lifetime range 2799–3999, allowing only normal one-decimal rounding;
- 180-day and lifetime alert routes still fire independently;
- cooldown still suppresses for seven days unless price falls more than 3%;
- dashboard ordering, escaping, singular/plural verdict, offer table, and missing-data
  states;
- generated `index.html` contains no chart price arrays and chart JSON contains only
  daily lows.

Mock every network request. Unit tests must not access the internet.

## 10. Verification commands and stop conditions

Before handoff run:

```powershell
python -m unittest discover -s tests -v
python -m compileall -q .
python dashboard.py
git diff --check
git status --short
```

Also render/open the generated dashboard at desktop and mobile widths and verify one
card expansion, every range button, one missing-chart state, and HTML size.

Stop and report a blocker instead of improvising when:

- a provider cannot be resolved through a documented public page;
- a provider requires login, CAPTCHA bypass, or a private API;
- a real response does not expose the required current price;
- a candidate lacks enough identity data for confirmation;
- migration would discard or rewrite an existing observation;
- a requested UI action requires a backend that does not exist.

## Done means all of these are true

- Scheduled runtime makes no direct retailer-page requests.
- One pasted supported retailer URL creates a schema-v2 product after confirmation.
- Only verified stable source URLs are stored.
- Fallback requests are failure-driven, bounded, sequential, and circuit-broken.
- Confirmed alternatives keep separate histories and the cheapest fresh offer wins.
- Ambiguous variants are never silently combined.
- The generated main dashboard matches the approved prototype and lazy-loads chart
  data on expansion.
- Existing history and scoring behavior are preserved.
- Tests and verification commands pass.
- Alert secrets remain unset and no notification was sent.
