# Price Sentinel — handoff

> **Update, 1 Aug 2026:** `DECISIONS.md` and `LUNA_IMPLEMENTATION_PLAN.md` record the
> approved provider-neutral direction now implemented in this worktree. Alerts remain
> postponed, and `pricehistoryapp.com` remains disabled pending a verifiable public
> resolver.

Context for whoever picks this up next. Written 1 Aug 2026 at the end of the build
session. Read this before changing anything in `analyze.py` or `fetch.py` — several
decisions here look arbitrary and are not.

---

## What it is

Always-on Amazon.in price tracker. GitHub Actions runs every 30 minutes, fetches
prices, appends history to the repo, scores each price against two statistical
windows, and alerts by phone push + email when something enters a buy zone.

**Origin problem:** the owner kept missing short price dips. A Gillette trimmer traded
at ₹2,799 for ~4 days in July 2026 and he saw it at ₹3,359. Consumer trackers only
solve alerting; they don't judge whether a price is genuinely good, and they don't
run when your laptop is shut.

- Repo: https://github.com/bhanu-thakur/price-sentinel (public)
- Dashboard: https://bhanu-thakur.github.io/price-sentinel/
- Local clone: `D:\GitHub\price-sentinel`

---

## Current state

**Working and verified in production:**

- Scheduled runs firing unattended (confirmed commits at 23:30, 01:07, 04:51 UTC)
- Price fetch → history CSV → buy-zone scoring → commit back to repo
- Dashboard auto-generated and served via GitHub Pages
- Real captured data: `3359.00` on 2026-07-31, matching the live Amazon page

**Not yet done:**

- **Alert secrets are not set.** `notify.py` degrades cleanly to no-ops, so nothing
  breaks — but no alert has ever actually been delivered. This path is UNTESTED end
  to end. Needs `NTFY_TOPIC`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`,
  `MAIL_TO` in repo Settings → Secrets and variables → Actions.
- Only one product in `watchlist.json`.
- Provider-neutral intake and scheduled tracking are implemented for the verified
  pricehistory.app and BuyHatke adapters. pricehistoryapp.com remains disabled
  until its public URL resolver can be verified without reproducing its signed
  client API.

---

## Files

```
watchlist.json              schema-v2 products, listings, and provider source URLs
catalog.py                  URL normalization, identity, schema, and migration helpers
add_product.py              confirmed one-link intake through verified providers
providers/                  provider adapters and the Observation contract
fetch.py                    sequential provider fetch orchestration and breakers
analyze.py                  history storage + dual-window buy-zone engine
notify.py                   ntfy push + SMTP email; no-ops when secrets absent
dashboard.py                static dashboard generator
main.py                     orchestrator, adaptive tier scheduling
.github/workflows/track.yml 30-minute cron
data/*.csv                  listing price history, auto-committed
data/state.json             schema-v2 provider, product, and listing state
docs/index.html             generated dashboard
```

---

## Decisions that must not be silently reverted

**1. Providers are external comparison/history services, not direct retailer pages.**
Not because Amazon blocks us — see the Brotli bug below; that diagnosis was wrong.
The real reasons: it server-renders price, MRP and **lifetime low/avg/high** into one
meta tag, which is a far more stable parse target than Amazon's A/B-tested price
markup, and the lifetime figures make buy-zone logic work from the first run instead
of needing 180 days of accumulation. Buyhatke is the verified fallback.

**2. Two windows, not one.**
`LOOKBACK_DAYS = 180` for recent trading, plus a lifetime overlay from the source
site. Alerts fire on either.

- Recent-only would miss Big Billion Days / Great Indian Festival, which are annual
  and therefore invisible to any sub-year window.
- Lifetime-only would hide ordinary good deals behind an unbeatable annual floor. On
  a product whose price has drifted down over years, everything looks cheap against
  an old high, so you'd stop getting useful alerts.

**3. Score is computed against the LIFETIME range, not the recent one.**
The 180-day span is narrow enough that any new low saturates it. With recent-range
scoring, ₹3,250 and ₹2,650 both scored 100/100. Lifetime scoring gives 62 vs 100.
If you change this, re-check that a modest dip and a festival-grade low still rank
differently.

**4. Anti-spam cooldown: 7 days, unless a further 3% drop.**
Without it a multi-day dip fires an alert every 30 minutes and trains the owner to
ignore notifications, which defeats the entire system.

**5. Dashboard charts downsample to daily lows (`daily_low`).**
At 48 samples/day a 180-day chart is 8,640 points per product ≈ 156 KB of committed
HTML each, rewritten 48×/day. Daily lows are 181 points, 3.8 KB — 97.6% smaller —
and the daily minimum is the price you could actually have bought at.

---

## Bugs already fixed — all three failed SILENTLY

Each of these looked like success. Watch for the pattern.

**Unset secrets arrive as empty strings, not missing keys.**
`os.environ.get("SMTP_PORT", "587")` returned `""`, and `int("")` crashed the whole
run on import. Use `os.environ.get("X") or default`.

**Never advertise `Accept-Encoding: br` without the `brotli` package.**
`requests` cannot decode Brotli alone and returns binary garbage with HTTP 200. This
looks exactly like an IP block and cost a long detour — it produced a confident but
wrong "Amazon is blocking datacenter IPs" diagnosis, which in turn caused a
needless migration to a different data source. The fetcher now requests only
`gzip, deflate`, and `brotli` is pinned in requirements as a safety net.
**Lesson: log the response body before concluding anything about blocking.**

**GitHub repo workflow permissions default to read-only.**
The workflow declares `contents: write`, but the repo-level setting is a ceiling.
Every run reported success while committing nothing. Now set to Read and write.

**Line endings.** A Windows clone showed all 11 files modified with 1,092
insertions/deletions — pure CRLF churn. `.gitattributes` now forces LF. This matters
beyond noise: CRLF in `.github/workflows/*.yml` can break Actions parsing.

---

## Scaling

GitHub is not the binding limit; job runtime is (~9s per product when everything is
due at once, against a 20-minute timeout).

| Products | Worst-case cycle | Verdict |
|---|---|---|
| 50 | ~8 min | comfortable |
| 75 | ~11 min | practical ceiling |
| 100 | ~15 min | near timeout |

Keep the repo **public** — private burns the 2,000 free minutes/month regardless of
product count. At 50 products the tracker makes ~400 requests/day to pricehistory.app;
be considerate, it's a free community site.

---

## Open items

1. **Set the alert secrets and verify a real alert lands.** Highest priority — the
   notification path has never been exercised end to end. Suggest temporarily setting
   a `target` above the current price to force one alert, then reverting.
2. **Add more products.** Run `python add_product.py "<retailer-url>"`, review the
   discovered listings, and confirm before the schema-v2 watchlist is written.
3. Consider additional providers only after a real public response can be verified;
   speculative redundancy was already a wrong turn once.

---

## Dashboard redesign implementation

The approved verdict-first design is generated into docs/index.html by
dashboard.py. Chart data is written separately under docs/chart-data/ and loaded
only when a product row expands.

The page is generated from the schema-v2 watchlist and committed state; it contains
no sample products or embedded chart price arrays.

### The problem it solves

The current dashboard is a wall of equal-weight cards. To find out whether anything
is worth acting on you must read every one. The dashboard's actual job is answering
**"is there anything I should buy right now?"** in under two seconds.

### What to port

**1. Verdict line at the top — the highest-value change.**
"1 product in the buy zone · 4 tracked · checked 6 min ago". State the answer before
the data. If nothing qualifies, say so plainly so the page can be dismissed at a glance.

**2. Collapsed rows that expand on tap** (Apple Wallet / Revolut pattern).
Collapsed shows only: status rail, name, seller, score, price, and distance from peak.
Expanded reveals chart, range selector, stats grid, buy-zone reasoning, and actions.
A watchlist is a scanning surface first and a detail surface second.

**3. Reference lines on the chart** (Groww pattern).
Dotted horizontal lines for the all-time low and the user's target, each labelled
inline. This is what converts the chart from decoration into a decision aid — you see
the gap you are waiting on. Range selector: 1M / 3M / 6M / 1Y / All.

**4. Status as a coloured left rail, not a badge.**
Three states: buy zone (green), watch (amber), idle (grey). Quieter than a badge and
scans better down a column.

**5. Tabular figures — non-negotiable.**
`font-variant-numeric: tabular-nums`. Without it ₹3,359 and ₹24,990 shift horizontally
between refreshes, which reads as instability on a page whose entire purpose is numbers.

### What was deliberately NOT taken

CRED's influence is limited to the dark premium surface and score-as-hero. Its retro
serif headings, 3D icons and gamification were rejected: a page you check for a price
drop should not feel like a game, and ornament competes with the numbers.

### Known concerns — resolve before or during implementation

- **The score meter is the weakest element.** It is a number pretending to be a gauge.
  A sparkline in the same space may inform more. Worth testing both.
- Charts are lazy-rendered and use separate daily-low JSON files. The page sorts
  buy, watch, and idle products without non-functional filter chips.
- Dashboard data is generated from committed product/listing state; no illustrative
  product data is included.

### Implementation note

`dashboard.py` now emits the verdict-first expandable rows, status rails, range
controls, and lazy Chart.js loading. Chart data is stored separately under
`docs/chart-data/` and generated from `daily_low()`; keep the generator dependency-free
apart from the existing Chart.js CDN and do not revert to raw samples.

---

## Working on this repo

Local clone at `D:\GitHub\price-sentinel`, authenticated through GitHub Desktop.
Do not use the GitHub web upload form — it silently dropped three commits during the
build by submitting before the React form registered the commit message. Always
verify HEAD after committing.
