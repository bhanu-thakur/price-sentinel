# Price Sentinel decisions

This file records current decisions and explicitly supersedes older statements in
`HANDOFF.md` where noted.

## D-001 — Provider-neutral tracker

**Status:** accepted, implemented
**Date:** 2026-08-01

Price Sentinel is not Amazon-specific. A tracked product is a canonical item with
one or more retailer listings. Do not use ASIN as the product's primary identity.
Keep provider, retailer, listing URL, and provider-specific identifier as separate
fields.

## D-002 — Source order and direct-retailer fetching

**Status:** accepted, implemented
**Date:** 2026-08-01

Use source adapters in this order:

1. `pricehistory.app`
2. `buyhatke.com`
3. `pricehistoryapp.com`

Remove the direct Amazon fetcher from the runtime workflow. A fallback is queried
only when the preferred source fails or returns invalid/stale data; it is not an
instruction to hit all three sources every cycle. This supersedes the handoff's
decision to retain Amazon as the automatic fallback.

`pricehistory.app` publicly supports pasted marketplace links and currently enables
tracking for Amazon and Flipkart. Treat other retailers as best-effort until a source
adapter is verified against real fixtures.

## D-003 — Preserve the decision engine

**Status:** accepted

Preserve the 180-day recent window plus lifetime overlay, lifetime-range score,
seven-day notification cooldown with a further 3% drop override, and daily-low chart
downsampling. Provider normalization must feed the existing engine; it must not
silently change deal semantics.

## D-004 — Final dashboard direction

**Status:** accepted, implemented

`docs/prototype.html` is the approved visual design and becomes the generated main
dashboard in `docs/index.html`. Keep the verdict-first layout, collapsed rows,
status rail, tabular figures, range controls, reference lines, statistics, reasoning,
and retailer actions. Remove prototype-only sample data and non-functional controls.

Charts and other secondary detail are initialized only when a row is expanded.
Collapsed decision data remains immediately available.

## D-005 — Product intake and cross-store matching

**Status:** accepted, implemented

The user-facing intake is one pasted URL from any supported retailer, including an
Amazon or Flipkart link. Resolution happens once when adding the product, not during
every scheduled check.

The resolver may discover equivalent listings on other retailers and track their
prices, but a textual similarity match is never silently accepted. Exact model,
variant, storage/capacity, colour where price-relevant, pack size, and other defining
attributes must agree. Auto-accept only a high-confidence exact match; otherwise save
candidates for confirmation. This is necessary because aggregator “same product”
results can include nearby but non-equivalent variants.

The dashboard and eventual alert identify the cheapest confirmed retailer listing
and link directly to it. Per-retailer history remains separate so prices are not
merged into a misleading single series.

## D-006 — Load and failure discipline

**Status:** accepted, implemented

- Resolve and cache stable source URLs during product intake.
- Keep adaptive cadence and randomized spacing.
- Call fallbacks only after a primary failure or stale/invalid response.
- Use exponential backoff, per-provider circuit breakers, and last-known-good data.
- Do not perform cross-store discovery in the recurring tracking workflow.
- Record source health and freshness so a stale price cannot look current.
- Keep charts lazy. Prefer a provider's verified historical series when available;
  otherwise feed them with local `daily_low()` data. Keep the two histories separate.

The target is a polite low request rate and graceful partial results rather than
aggressive retries that cause provider blocking.

## D-007 — Alerts are postponed

**Status:** accepted

Do not configure secrets or include alert-delivery activation in Luna's work. Existing
notification code may remain compatible, but end-to-end alert testing is a separate
final phase after provider and dashboard changes stabilize.

## D-008 — Provider history remains distinct from tracker observations

**Status:** accepted, implemented
**Date:** 2026-08-01

When a verified provider exposes a historical chart series on its public product
page, validate and retain that series as listing-level `provider_history`. Prefer it
for dashboard charts because it predates this tracker's first observation. Do not
backfill it into the tracker CSV or treat provider points as observations made by
Price Sentinel.

If verified provider history is unavailable, fall back to the tracker's own daily
lows. Plot either source against real timestamps with straight chronological
segments; do not smooth sparse samples into invented intermediate price movement.
