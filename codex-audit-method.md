# Codex technical audit methodology

## Purpose

This document explains how the Price Sentinel audit was performed. The audit was
read-only with respect to application code, data, workflows, and generated site
artifacts. No fixes were attempted.

The audit answered five questions:

1. Was `FIX_PLAN.md` implemented?
2. Can the runtime compare confirmed listings from different retailers?
3. Were the two supplied Amazon products added to tracking?
4. Are both products visible in the generated index?
5. Is the result operating as a GitHub Actions automation?

The repository state examined locally was commit `7c8a222`. Live GitHub Actions
evidence showed that the automation subsequently advanced `main` to `f22fa82` by
regenerating `docs/index.html`.

## Audit model

The audit used four independent evidence layers:

| Layer | Purpose |
|---|---|
| Git history and diffs | Identify the implementation boundary and exact files changed |
| Static code tracing | Verify control flow, data flow, retailer selection, and failure handling |
| Generated artifacts and persisted state | Confirm the requested products are actually tracked and rendered |
| Live GitHub Actions evidence | Confirm the workflow is active and verify the test result in its real environment |

A requirement was marked complete only when implementation evidence and an observable
artifact or runtime result agreed. The presence of generic code alone was not treated
as proof that the two requested products had cross-retailer comparisons configured.

## 1. Environment baseline

Repository instructions required using the parent workspace doctor instead of probing
the machine manually:

```powershell
& ..\doctor.ps1
```

Relevant doctor result:

```text
status: missing-required
price-sentinel: missing declared dependency setup: python:.
python on PATH: Hermes Python 3.11.15
Python 3.12 installation: present
git, gh, uv: usable
```

This result established an important test constraint: failures caused solely by absent
local packages could not be interpreted as repository test failures. The audit therefore
used the live Actions runner, which installs `requirements.txt`, as the authoritative
complete-suite result.

## 2. Repository snapshot and implementation boundary

The initial repository inspection used:

```powershell
git status --short --branch
git log --oneline --decorate -n 20
rg --files -uu
Get-ChildItem -Recurse -File -Include *plan*.md,*PLAN*.md
```

The relevant commit sequence was:

```text
e613291  Created Fix Plan
7e91a11  fix dashboard and track new products
f111895  Merge dashboard fixes and new products
7c8a222  data: add Nelko and Jenga tracking history
```

The implementation commit was isolated with:

```powershell
git show --stat --summary 7e91a11
git diff-tree --no-commit-id --name-status -r 7e91a11
git diff 6900f2b..7e91a11 -- `
  .github/workflows/track.yml `
  watchlist.json main.py dashboard.py requirements.txt HANDOFF.md
```

This separated Luna's implementation from earlier provider-neutral architecture and
later generated data. It prevented pre-existing comparison functionality from being
incorrectly attributed to the product-addition commit.

## 3. Plan-compliance inspection

`FIX_PLAN.md` and `LUNA_IMPLEMENTATION_PLAN.md` were read in full and converted into a
requirement matrix. Each fix-plan directive was checked against the corresponding source:

| Plan item | Evidence checked |
|---|---|
| Freshness uses successful data | `dashboard._verdict_line()` reads listing `last_success_ts` |
| Dashboard failure cannot discard collected data | `main.run()` catches dashboard exceptions |
| Commit step survives tracker failure | `Commit history` has `if: ${{ !cancelled() }}` |
| Indian numeric grouping | `_group_inr()` and `_money()` |
| Out-of-stock data remains visible | `_card()` fallback and stock-note branches |
| Lifetime average is not called a 180-day median | `median_label` selection |
| Score uses tabular figures | generated `class="mlabel num"` |
| Unbuyable product retains links | `display_listing` action-link branch |
| Prototype and handoff are restored/corrected | current files and historical prototype comparison |
| Tests execute in CI | `pytest` requirement and final workflow step |

The restored prototype was checked byte-for-byte against the designated historical
version:

```powershell
git diff --exit-code 9120a8a -- docs/prototype.html
```

The command returned no diff.

Whitespace and accidental patch corruption were checked with:

```powershell
git show --check --oneline 7e91a11
git diff --check
```

Both checks returned clean.

## 4. Cross-retailer comparison trace

The comparison path was traced from configuration to selection to rendering.

### 4.1 Configuration model

`watchlist.json` schema version 2 contains products, and each product contains an array
of confirmed retailer listings. Provider pages are stored below each listing in
`source_urls`.

This distinction was essential:

```text
listing.retailer     = the shop being compared, such as amazon.in or flipkart.com
listing.source_urls  = services used to observe that listing, such as
                       pricehistory.app or buyhatke.com
```

Two provider URLs observing one Amazon listing do not constitute an Amazon-versus-
Flipkart comparison.

### 4.2 Scheduled collection path

The following `main.py` flow was traced:

```text
watchlist products
  -> products whose tier cadence is due
  -> every confirmed listing for each due product
  -> fetch_listing(listing, provider_state)
  -> append successful observation to listing-specific CSV
  -> evaluate listing price
  -> combine current and still-fresh stored offers
  -> filter to fresh and in-stock offers
  -> select minimum price
  -> store one product-level recommended verdict
  -> generate dashboard
```

The decisive implementation is the loop over `product["listings"]` followed by:

```python
recommended = min(
    fresh,
    key=lambda offer: (offer["price"], offer.get("retailer", "")),
) if fresh else None
```

This proves that the engine can compare multiple confirmed retailer listings without
merging their histories.

### 4.3 Provider orchestration

`fetch.py` was inspected to confirm that provider fallback is not retailer comparison.
For each retailer listing it:

1. Iterates configured provider URLs in priority order.
2. Stops on the first valid observation.
3. Validates listing ID, source, positive INR price, retailer identity, and freshness.
4. Applies provider circuit breakers.

Thus, PriceHistory versus BuyHatke is a fallback-source choice for one retailer listing;
Amazon versus Flipkart requires two separate entries in `product.listings`.

### 4.4 Test coverage for comparison

`tests/test_main.py::test_cheapest_fresh_offer_wins_and_only_one_alert_is_dispatched`
constructs one Amazon listing and one Flipkart listing, gives Flipkart the lower price,
and asserts that Flipkart becomes `recommended_listing_id` and the single alert target.

This establishes generic comparison support. It does not establish that the two real
requested products have confirmed Flipkart listings.

## 5. Requested-product verification

`watchlist.json` was inspected directly for the supplied ASINs:

```text
B0CHJR8NLD -> amazon-in-b0chjr8nld
B08675PSBT -> amazon-in-b08675psbt
```

For every product the audit counted:

- confirmed listing IDs;
- unique `listing.retailer` values;
- provider source URLs;
- persisted listing-state records;
- CSV observations;
- generated chart points;
- offer rows in `docs/index.html`.

The persisted-state summary was produced with PowerShell JSON parsing rather than by
running the tracker:

```powershell
$state = Get-Content -Raw data/state.json | ConvertFrom-Json
$state.products.PSObject.Properties
$state.listings.PSObject.Properties
```

Observed result:

| Product | Confirmed retailers | CSV | Initial stored observation |
|---|---:|---|---:|
| Nelko P21 | `amazon.in` only | `data/amazon-in-b0chjr8nld.csv` | ₹2,748.06 |
| Hasbro Jenga | `amazon.in` only | `data/amazon-in-b08675psbt.csv` | ₹660.00 |

Each CSV contained a header and one locally committed observation. `data/state.json`
also contained provider-derived history and a successful `last_success_ts` for each
listing.

The generated chart files were parsed as JSON and counted:

```text
amazon-in-b0chjr8nld.json: 67 daily points
amazon-in-b08675psbt.json: 550 daily points
amazon-in-b0gsvfv3r4.json: 32 daily points
```

## 6. Generated-index verification

`docs/index.html` was searched for product names, retailer offer rows, freshness text,
prices, chart paths, and outbound links:

```powershell
rg -n "Nelko|Jenga|Gillette|Amazon|Flipkart|tracked|priced|Open on" docs/index.html
```

The index contained:

- a three-product headline;
- a Nelko card and chart path;
- a Jenga card and chart path;
- real stored prices;
- one Amazon offer row for each requested product;
- no Flipkart offer for either requested product.

This is why “tracked and visible” was marked complete while “actual cross-platform
comparison for these products” was marked incomplete.

## 7. Static defect analysis

The audit did not stop at checklist matching. Data relationships were traced through
failure and edge-case paths.

### 7.1 Out-of-stock retailer attribution

In `dashboard._card()`:

1. A fallback verdict is selected from `product_state["stale_offers"]`.
2. When there is no recommended listing, `chart_offer` independently becomes
   `offer_items[0]`.
3. Price and stock state can therefore come from the fallback verdict while retailer,
   link, listing state, and chart come from the first configured listing.

This is harmless for the current one-listing products, but it becomes a correctness
problem after a real second retailer is added.

### 7.2 Same-ASIN URL deduplication

The Jenga product contains a rejected Amazon URL with ASIN `B08675PSBT` while its seed
listing has the same ASIN under a different Amazon path.

The intake implementation deduplicates using exact normalized URL strings. URL
normalization removes selected query parameters and `www`, but it does not canonicalize
different `/gp/product/<ASIN>` and title-based `/dp/<ASIN>` paths to one product key.

The audit therefore classified this as an identity/deduplication issue rather than a
mere formatting inconsistency.

## 8. Workflow and live automation verification

The local workflow was inspected for:

- cron schedule;
- manual dispatch and `force_all` input;
- write permission;
- concurrency behavior;
- dependency installation;
- tracker environment variables;
- commit/push behavior;
- test ordering and failure conditions.

Commands used for live verification:

```powershell
gh auth status
gh workflow view "Price Sentinel"
gh run list --workflow "Price Sentinel" --limit 15 `
  --json databaseId,status,conclusion,createdAt,updatedAt,event,headBranch,headSha,displayTitle,url
gh run view 30715385666 --log
```

The latest audited run was:

```text
Run:        30715385666
Event:      schedule
Created:    2026-08-01 19:43:20 UTC
Conclusion: success
Tracker:    0/3 products due
Tests:      30 passed, 5 subtests passed
```

The log also showed that a run with zero due products regenerated the index and pushed
commit `f22fa82`. This was the evidence for the no-op commit-churn finding.

The preceding scheduled-run timestamps were compared. Despite a `*/30` cron expression,
observed gaps included periods substantially longer than 30 minutes, with the largest in
the inspected window approximately 3 hours 44 minutes. Therefore the workflow was
reported as active, but a strict 30-minute operational cadence was not claimed.

## 9. Test execution and interpretation

### Local pytest attempt

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -m pytest tests -q -p no:cacheprovider
```

Result:

```text
No module named pytest
```

This matched the doctor result and was classified as an unprepared local environment,
not a product-code test failure.

### Local standard-library discovery

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
py -3.12 -m unittest discover -s tests -v
```

Ten dependency-free tests passed. Four test modules could not import because `requests`
was absent from that Python installation. This partial run was not used to claim a green
suite.

### Authoritative complete run

The live Actions runner installed `requirements.txt` and then executed:

```text
python -m pytest tests -q
```

Result:

```text
30 passed, 5 subtests passed in 18.97s
```

This was used as the complete regression-test result.

## 10. Severity assignment

Findings were prioritized by user-visible consequence:

- **High:** a directly requested outcome is absent from the real configuration or UI.
- **Medium:** the feature exists but can produce incorrect retailer identity, candidate
  handling, or materially misleading behavior under a realistic supported state.
- **Low:** automation quality, repository hygiene, or operational behavior that does not
  currently corrupt a tracked price.

The lack of actual Flipkart listings for the two products was rated High because the
real dashboard cannot perform the requested platform comparison, even though the generic
engine and its synthetic test are present.

## 11. Audit limitations

The audit intentionally did not:

- modify source, tests, workflow, watchlist, state, CSV, or generated site files;
- install dependencies;
- run `main.py`, because that performs network requests and mutates tracking state;
- send notifications;
- add or confirm retailer candidates;
- treat provider pages as retailer alternatives;
- claim that a safe Flipkart counterpart exists without confirmed identity evidence;
- perform a new visual redesign or browser compatibility review.

The audit evaluated the committed configuration and live automation. It did not search
retailer sites for new product counterparts, because that would be implementation/intake
work rather than verification of what Luna delivered.

## 12. Reproduction checklist

An independent reviewer can reproduce the core audit with:

```powershell
& ..\doctor.ps1
git status --short --branch
git log --oneline --decorate -n 20
git diff 6900f2b..7e91a11
Get-Content watchlist.json
Get-Content .github/workflows/track.yml
rg -n "B0CHJR8NLD|B08675PSBT|flipkart|amazon" watchlist.json docs/index.html tests
git diff --exit-code 9120a8a -- docs/prototype.html
git show --check 7e91a11
git diff --check
gh run list --workflow "Price Sentinel" --limit 15
gh run view 30715385666 --log
```

No command in this checklist applies a fix. Running the tracker itself is deliberately
excluded because it changes repository data and can contact external providers.
