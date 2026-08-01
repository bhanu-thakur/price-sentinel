# Price Sentinel — handoff

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
- A dashboard redesign was prototyped and reviewed but not implemented (see below).

---

## Files

```
watchlist.json              what to track; ph_url is the primary source URL
fetch.py                    two fetchers: pricehistory.app (primary), Amazon (fallback)
analyze.py                  history storage + dual-window buy-zone engine
notify.py                   ntfy push + SMTP email; no-ops when secrets absent
dashboard.py                static dashboard generator
main.py                     orchestrator, adaptive tier scheduling
.github/workflows/track.yml 30-minute cron
data/*.csv                  price history, auto-committed
data/state.json             per-product tier, last check, lifetime stats
docs/index.html             generated dashboard
```

---

## Decisions that must not be silently reverted

**1. Primary source is pricehistory.app, not Amazon.**
Not because Amazon blocks us — see the Brotli bug below; that diagnosis was wrong.
The real reasons: it server-renders price, MRP and **lifetime low/avg/high** into one
meta tag, which is a far more stable parse target than Amazon's A/B-tested price
markup, and the lifetime figures make buy-zone logic work from the first run instead
of needing 180 days of accumulation. Amazon direct remains the automatic fallback.

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
2. **Dashboard redesign.** A prototype was built and reviewed, drawing on Apple
   Wallet (collapsed cards expanding to detail), Groww (range selector, dotted
   reference lines for all-time low and your target) and CRED (dark premium surface,
   score as hero) — but deliberately without CRED's gamified ornament. Key proposed
   change: a verdict line at the top ("1 product in the buy zone") so the page answers
   "should I act right now?" in under two seconds. Open concerns: the score meter may
   be weaker than a sparkline in the same space, and charts should render lazily on
   expand rather than shipping all products' data on page load. Not yet implemented.
3. **Add more products.** Resolve each `ph_url` by pasting the Amazon link into
   pricehistory.app and copying the resulting `/p/...` URL.
4. Consider a second source (buyhatke etc.) only after observing real failure data —
   speculative redundancy was already a wrong turn once.

---

## Working on this repo

Local clone at `D:\GitHub\price-sentinel`, authenticated through GitHub Desktop.
Do not use the GitHub web upload form — it silently dropped three commits during the
build by submitting before the React form registered the commit message. Always
verify HEAD after committing.
