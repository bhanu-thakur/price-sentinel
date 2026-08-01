# Changelog

All notable project changes are recorded here. Runtime-generated price samples and
dashboard refreshes are excluded.

## Unreleased

### Changed

- Added an identity-verified Hasbro Classic Jenga listing from Flipkart and a verified
  BuyHatke fallback for the Nelko Amazon listing.
- Made scheduled runs true no-ops when no product is due, preventing relative-time-only
  dashboard commits and unnecessary Pages rebuilds.
- Canonicalized retailer listing identities and routed heuristic brand mismatches to
  human confirmation instead of silently rejecting cross-retailer candidates.
- Increased the BuyHatke fetch timeout for verified server-rendered pages that can
  exceed the former 25-second limit.
- Brought the generated GitHub Pages dashboard to prototype fidelity with polished
  responsive cards, verdict-first hierarchy, accessible expansion and range states,
  retailer actions, and mobile layouts.
- Replaced the Chart.js CDN dependency with a lazy native-canvas price chart so the
  published dashboard remains self-contained and resilient.

### Fixed

- Record alert cooldowns only after at least one delivery channel succeeds; cleared
  cooldowns previously created while both delivery channels were disabled.
- Bound fallback price, retailer, stock state, link, freshness, and chart rendering to
  the same listing; fresh sibling failures can no longer mark a buyable offer out of
  stock.
- Recomputed fallback freshness at render time and made the headline report stale or
  missing products explicitly.
- Surfaced current cross-retailer savings in each collapsed dashboard row.
- Parsed and persisted PriceHistory's verified embedded chart series, preferred it
  over sparse local observations, and plotted points on a true chronological axis.
- Accepted the current separator-free `Store Product Code` label while retaining
  exact retailer-product identity validation.

### Documentation

- Added `DECISIONS.md` as the durable record of architectural choices.
- Added `LUNA_IMPLEMENTATION_PLAN.md` for the provider-neutral tracker and final
  dashboard rollout.
- Deferred alert-secret setup and end-to-end delivery testing until after that work.

## 2026-08-01

### Added

- Added the generated verdict-first dashboard with expandable rows and lazy charts.
- Added lifetime price statistics from `pricehistory.app` so scoring works during
  cold start.
- Added ntfy and SMTP notification adapters that safely no-op without secrets.
- Added adaptive hot, warm, and cold scheduling.

### Changed

- Replaced direct retailer fetching with sequential provider adapters and bounded
  fallback state.
- Added schema-v2 catalog intake, exact listing matching, and one-time history
  migration.
- Changed scoring to use the lifetime price range while retaining both recent and
  lifetime alert windows.
- Downsampled dashboard charts to daily lows.
- Forced LF line endings and enabled workflow write permissions.

### Fixed

- Normalized provider retailer labels such as `Amazon` to canonical retailer hosts.
- Added the verified BuyHatke fallback URL for the migrated Gillette listing.
- Fixed lazy charts reading their data path from the wrong dashboard element.
- Required successful provider parsing before intake stores a source URL.
- Added visible candidate identity details before manual counterpart confirmation.
- Preserved cooldown state at canonical-product level across retailer changes.
- Staged runtime `watchlist.json` source invalidations in the tracking workflow.
- Corrected the product-intake command and schema-v2 example in the README.
- Prevented empty secret values from breaking SMTP port parsing.
- Removed Brotli advertising from request headers and pinned Brotli as a safety net.
- Added failed-parse response logging to avoid silent source failures.
