# Codex audit report

## Executive summary

**Overall verdict: partially complete.**

The implementation successfully applied the dashboard and workflow corrections in
`FIX_PLAN.md`. The two requested Amazon products were added, collected into persisted
state and CSV history, and rendered on the main dashboard. The GitHub Actions workflow
is active, installs dependencies, runs the tracker, commits generated artifacts, and
passes the complete test suite.

The principal gap is the requested real cross-platform comparison. The runtime supports
comparing multiple confirmed retailer listings and choosing the cheapest fresh offer,
but both requested products currently contain only an Amazon listing. Their dashboard
cards therefore do not compare Amazon against Flipkart or any other retailer.

No application code, tests, workflow configuration, tracking data, or generated site
artifacts were changed during the audit.

## Audit scope

The audit evaluated:

1. Compliance with `FIX_PLAN.md`.
2. The generic multi-retailer comparison implementation.
3. Tracking configuration for ASINs `B0CHJR8NLD` and `B08675PSBT`.
4. Persisted price state, CSV history, and chart artifacts.
5. Visibility of the requested products in `docs/index.html`.
6. GitHub Actions configuration and live run history.
7. Relevant failure and edge-case behavior.

The detailed procedures, commands, and evidence model are recorded in
[`codex-audit-method.md`](codex-audit-method.md).

## Requirement status

| Requirement | Status | Evidence |
|---|---|---|
| Apply the dashboard fix plan | Complete | Required source, documentation, prototype, dependency, and workflow changes are present |
| Track `B0CHJR8NLD` | Complete | Watchlist entry, listing state, CSV observation, provider history, chart JSON, and dashboard card exist |
| Track `B08675PSBT` | Complete | Watchlist entry, listing state, CSV observation, provider history, chart JSON, and dashboard card exist |
| Show both products on the index | Complete | Both names, prices, charts, links, and offer rows appear in `docs/index.html` |
| Add generic cross-retailer comparison | Complete | Runtime evaluates every confirmed listing and selects the cheapest fresh offer; Amazon/Flipkart test exists |
| Compare the two requested products across Amazon and Flipkart | **Incomplete** | Each product has exactly one confirmed retailer: `amazon.in` |
| Update GitHub workflow where required | Complete | Commit-on-failure protection and CI test step were added |
| Operate as an automation | Complete, with operational concerns | Scheduled workflow is active and green, but observed cadence is irregular and no-op runs create commits |

## Prioritized findings

### 1. High — The requested products have no real cross-platform comparison

The Nelko and Jenga products each have one confirmed listing:

```text
amazon-in-b0chjr8nld -> amazon.in
amazon-in-b08675psbt -> amazon.in
```

The `pricehistory.app` and `buyhatke.com` values stored under `source_urls` are provider
pages used to observe the associated Amazon listing. They are not alternative retailer
offers. In particular, two provider pages for one Amazon listing do not represent an
Amazon-versus-Flipkart comparison.

The generated index accurately reflects the configuration: each requested product has
one Amazon offer row and no Flipkart offer row.

The generic engine is implemented correctly for the normal in-stock case. `main.py`
iterates every listing for a product, retains separate listing histories, filters to
fresh in-stock offers, and chooses the minimum price. A unit test constructs Amazon and
Flipkart listings and verifies that the cheaper Flipkart offer becomes the product
recommendation. The missing element is real, identity-confirmed Flipkart configuration
for the requested products.

### 2. Medium — Multi-retailer out-of-stock rendering can attribute data to the wrong retailer

In `dashboard._card()`, an out-of-stock fallback verdict is selected from the product's
`stale_offers`. If there is no recommended in-stock listing, the code independently
selects the first configured listing as `chart_offer`.

With multiple retailers, this creates a mismatch when the fallback belongs to a listing
other than the first one:

- price, score, reasons, and stock state can come from the fallback retailer;
- retailer name, outbound link, listing state, and chart can come from the first listing.

The current requested products each have only one listing, so they do not presently
exhibit this fault. The defect becomes relevant as soon as a real Amazon/Flipkart pair
is added and all offers are temporarily unbuyable.

### 3. Medium — Same-ASIN Amazon URLs are not deduplicated by product identity

The Jenga product's `rejected_candidate_urls` contains an Amazon URL for ASIN
`B08675PSBT`, while the confirmed seed listing is also ASIN `B08675PSBT` under a
different Amazon path.

The intake path deduplicates candidates using normalized URL strings. Normalization
removes selected tracking parameters and `www`, but it does not canonicalize all Amazon
path forms to the retailer product ID. Therefore:

- `/gp/product/B08675PSBT` and a title-based `/dp/B08675PSBT` URL remain different;
- the same retail listing can be proposed as a counterpart;
- it can be recorded as rejected despite already being confirmed;
- if accepted, both URLs would derive the same listing ID and could collide in state.

This is direct evidence that URL-level deduplication is weaker than the identity model
required for reliable counterpart discovery.

### 4. Low — The workflow is active but does not demonstrate a strict 30-minute cadence

The workflow declares:

```yaml
schedule:
  - cron: "*/30 * * * *"
```

Live Actions history confirms that scheduled runs are active and successful. However,
the inspected run timestamps contained gaps substantially longer than 30 minutes, with
the largest observed gap approximately 3 hours 44 minutes.

The automation should therefore be described as a best-effort GitHub Actions schedule,
not as a guaranteed 30-minute monitoring service. The configured product cadence cannot
be met when GitHub does not dispatch the scheduled workflow at that frequency.

### 5. Low — Runs with no due products still create commits

The latest audited scheduled run reported:

```text
0/3 products due
checked=0 failed=0 alerts=0
```

It nevertheless regenerated `docs/index.html`, changing relative-time text, and pushed
commit `f22fa82` containing a one-line generated-page change.

Consequences include:

- commit history noise;
- unnecessary pushes and Pages rebuilds;
- difficulty distinguishing actual price observations from presentation-only refreshes.

No tracked price was corrupted, so this was classified as an automation-quality issue
rather than a correctness failure.

### 6. Low — Fix-plan cleanup directive was not completed

The opening instructions in `FIX_PLAN.md` say to delete the file after all phases are
merged. The implementation and merge are present, but `FIX_PLAN.md` remains tracked.

This does not affect runtime behavior. It is a plan-completion and repository-hygiene
deviation.

## Confirmed implementation details

### Fix-plan changes

The following requested changes are present:

- The dashboard headline derives freshness from successful listing data rather than
  attempted checks.
- A dashboard rendering exception no longer prevents already-collected data from being
  preserved.
- The workflow commit step executes after non-cancellation failures.
- Rupee values use Indian digit grouping.
- Fresh out-of-stock observations remain visible.
- Lifetime averages and 180-day medians receive distinct labels.
- The score element uses tabular figures.
- Unbuyable products retain outbound retailer/history links.
- The approved prototype was restored exactly from its designated historical commit.
- The handoff document accurately describes the hand-written canvas chart renderer.
- `pytest` was added to runtime requirements.
- The workflow runs the complete test suite after preserving tracking data.

### Requested products

At the audited state:

| Product | Listing ID | Last stored price | Retailer | Own CSV samples |
|---|---|---:|---|---:|
| Nelko P21 label maker | `amazon-in-b0chjr8nld` | ₹2,748.06 | Amazon India | 1 |
| Hasbro Original Jenga | `amazon-in-b08675psbt` | ₹660.00 | Amazon India | 1 |

Both listing records had successful provider attempts, `last_success_ts` values, current
in-stock state, scores, product-level recommendations, and provider-derived histories.

Generated chart artifacts contained:

```text
amazon-in-b0chjr8nld.json: 67 daily-low points
amazon-in-b08675psbt.json: 550 daily-low points
```

### Index visibility

The generated dashboard contained three product cards: the pre-existing Gillette
trimmer, the Nelko label maker, and Hasbro Jenga. Both requested additions included:

- product name;
- current stored price;
- score and status;
- Amazon freshness label;
- lazy chart path;
- range statistics;
- one Amazon offer row;
- retailer and provider-history links.

## Workflow verification

The workflow currently provides:

- scheduled and manual execution;
- a manual `force_all` option;
- serialized workflow runs;
- repository write permission;
- Python 3.12 setup and pip caching;
- dependency installation from `requirements.txt`;
- tracker execution with notification-related secrets passed through;
- data, docs, and watchlist commits;
- test execution after the commit-preservation step.

The latest audited live run was
[GitHub Actions run 30715385666](https://github.com/bhanu-thakur/price-sentinel/actions/runs/30715385666):

```text
Event:       schedule
Conclusion:  success
Created:     2026-08-01 19:43:20 UTC
Tracker:     0/3 products due
Tests:       30 passed, 5 subtests passed in 18.97s
```

## Test evidence

The complete suite could not be run in the local checkout because the repository's
declared Python dependencies were not installed. The required environment doctor
reported `price-sentinel` as missing its Python dependency setup.

Local verification produced:

- `python -m pytest`: unavailable because `pytest` was not installed;
- Python 3.12 `unittest` discovery: ten dependency-free tests passed, while four modules
  failed to import because `requests` was not installed.

These were treated as environment limitations, not application test failures.

The authoritative complete result came from the live Actions environment after it
installed `requirements.txt`:

```text
30 passed, 5 subtests passed
```

## Limitations

The audit did not:

- run the tracker locally or mutate tracking state;
- contact retailer pages to discover new counterparts;
- confirm that an equivalent Flipkart listing exists for either product;
- add, reject, or approve candidates;
- install dependencies;
- send notifications;
- perform fixes;
- stage, commit, or push files.

Accordingly, the report concludes that real Flipkart listings are absent; it does not
assert that a safe equivalent listing could have been automatically confirmed.

## Final conclusion

Luna's fix-plan work is technically present and its complete CI suite is green. The two
requested products are genuinely tracked and visible in the dashboard. The platform-
comparison architecture also exists and passes a synthetic Amazon/Flipkart test.

The delivered user-facing result is nevertheless incomplete because neither requested
product has more than one confirmed retailer listing. Until such listings are added,
the dashboard is monitoring two Amazon products, not comparing their prices across
Amazon and Flipkart.
