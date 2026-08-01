# Price Sentinel

Always-on multi-retailer price tracker. Runs on GitHub Actions every 30 minutes —
free, forever, whether or not your laptop is on. Alert delivery remains postponed
until provider and dashboard work stabilizes.

The point isn't "tell me the price." It's **judging whether a price is actually good**,
by scoring it against that product's own history rather than a threshold you guessed.

**Live dashboard:** https://bhanu-thakur.github.io/price-sentinel/

---

## How it gets prices

The tracker never requests retailer pages during scheduled runs. It uses verified
provider product pages in this order:

1. **pricehistory.app** — primary source for current price and lifetime statistics.
2. **buyhatke.com** — fallback when the primary source fails or is circuit-broken.
3. **pricehistoryapp.com** — reserved in the source order but currently disabled,
   because its public resolver could not be verified without a signed request.

The pricehistoryapp.com adapter is not enabled until its public URL resolver can
be verified without using its signed client API. Fallbacks are failure-driven,
sequential, and circuit-broken; providers are not queried for comparison every
cycle.

Each product stores stable provider URLs resolved once during intake. At runtime
there is no retailer search step.

---

## Setup

### 1. Repo

Public repo, so Actions minutes are unlimited and free. A private repo burns your
2,000 free minutes/month and a 30-minute cadence would exhaust them. Nothing sensitive
lives in the repo — only product links and price history. Credentials go in encrypted
Secrets, which stay private either way.

### 2. Workflow permissions

Settings → Actions → General → Workflow permissions → **Read and write**.

Required. GitHub defaults new repos to read-only, and the workflow commits price
history back to the repo. Without this every run appears to succeed while silently
saving nothing.

### 3. Phone push via ntfy (free, no account)

1. Install **ntfy** from the Play Store.
2. Choose a private topic name — treat it like a password, since anyone who knows it
   can read your alerts. e.g. `bhanu-deals-7fk29x`
3. In the app: **+ → Subscribe to topic**.

### 4. Email via Gmail

Needs an **App Password**, not your login password:
Google Account → Security → 2-Step Verification (must be on) → App passwords.

### 5. Secrets

Settings → Secrets and variables → Actions:

| Secret | Value |
|---|---|
| `NTFY_TOPIC` | your ntfy topic |
| `SMTP_HOST` | `smtp.gmail.com` |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | your Gmail address |
| `SMTP_PASS` | 16-character app password |
| `MAIL_TO` | where alerts go |

Either channel works alone. Leave secrets unset to disable that channel — the tracker
still runs, stores history and updates the dashboard, it just doesn't notify.

### 6. Dashboard

Settings → Pages → Source: **Deploy from branch** → `main` / `/docs`.

---

## Adding products

Run the interactive intake with one real product URL:

```powershell
python add_product.py "https://www.amazon.in/dp/B0GSVFV3R4" --target 2850 --tier hot
```

The intake resolves the URL through the verified public providers, shows the
discovered listings and lifetime statistics, and asks for confirmation before
writing watchlist.json. The resulting schema-v2 entry has a stable product ID,
listing IDs, provider source URLs, and optional target/tier values. The current
working adapters are pricehistory.app and buyhatke.com; pricehistoryapp.com remains
disabled until its public resolver can be verified without a signed client API.

For non-interactive setup, write the same schema-v2 shape directly:

```json
{
  "schema_version": 2,
  "products": [
    {
      "id": "gillette-series-5-trimmer",
      "name": "Gillette Series 5 Trimmer",
      "target": 2850,
      "tier": "hot",
      "notes": "",
      "rejected_candidate_urls": [],
      "listings": [
        {
          "id": "amazon-in-b0gsvfv3r4",
          "retailer": "amazon.in",
          "url": "https://www.amazon.in/dp/B0GSVFV3R4",
          "confirmed_by": "seed",
          "attributes": {
            "brand": "Gillette",
            "model": "Series 5"
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

`target` is optional — a hard floor that always alerts. The statistical engine works
without it. `tier` (`hot`/`warm`/`cold`) is only a starting hint; anything scoring 60+
is auto-promoted to `hot`.

---

## How the decision engine works

Every check appends to `data/<listing-id>.csv`, committed to the repo — your price history
is yours permanently, not locked inside someone's app.

It judges every price against **two windows at once**, and alerts if *either* fires.

**Recent (180 days)** — "is this cheap versus how it has been trading lately?"
Adapts to price drift, so a product that launched at ₹4,500 and now sits at ₹3,300
doesn't look like a permanent bargain.

- Price at or below your `target`
- **Lowest in 180 days**
- Bottom 10% of the 180-day range *and* ≥5% under the median
- Bottom 25% *and* ≥7% under the median (a sharp sudden drop)

**Lifetime (max available)** — "is this a festival-grade low?"
Big Billion Days and the Great Indian Festival run once a year, so any window
shorter than a year is structurally blind to the biggest drop of the year. These
figures come from the source site, so they work from the very first run.

- At the lowest price ever recorded
- Within 3% of the all-time low
- ≥7% below the lifetime average

Both are needed. Lifetime-only would hide ordinary good deals behind an unbeatable
annual floor; recent-only would miss the annual sale entirely.

Then these **suppress** the alert:

- Out of stock
- Already alerted for this product within 7 days, unless it dropped a further 3%

And these are **surfaced inside** the alert rather than hidden:

- Third-party seller rather than Amazon-fulfilled
- MRP inflated relative to real trading history (fake-discount detection)

`score` (0–100) is measured against the **lifetime** range, not the recent one. The
180-day span is narrow enough that any new low saturates it, which would rate a modest
dip identically to a festival-grade one. On the Gillette trimmer (lifetime ₹2,799–₹3,999)
that gives ₹3,359 → 53, ₹3,250 → 62, ₹2,899 → 92, ₹2,799 → 100.

---

## Cadence

| Tier | Frequency |
|---|---|
| hot | ~30 min |
| warm | 3 hours |
| cold | 12 hours |

For 50 products that's roughly 350 primary requests/day, with randomised 4–11s gaps.
Fallbacks add requests only when an earlier provider fails. Running cost: **₹0**.

---

## How many products can this track?

GitHub is not the limit. On a **public** repo Actions minutes are unlimited, so the
binding constraint is how long one cycle takes when every product happens to be due
at once (~9s each: fetch plus a randomised 4–11s gap).

| Products | Worst-case cycle | Verdict |
|---|---|---|
| 25 | ~4 min | comfortable |
| 50 | ~8 min | comfortable |
| 75 | ~11 min | fine |
| 100 | ~15 min | near the 20-min job timeout |
| 130+ | >20 min | would be cut off |

**Practical ceiling: ~75 products.** To go higher, either drop the inter-product sleep
in `main.py`, raise `timeout-minutes` in the workflow, or split the watchlist across
parallel matrix jobs.

Two caveats that matter more than the raw number:

- **Keep the repo public.** On a private repo the 2,000 free minutes/month cap binds
  first, and at 48 runs/day you exhaust them regardless of how few products you track.
- **Be a good citizen.** At 50 products the tracker makes roughly 400 requests/day to
  pricehistory.app (~17/hour) — considerate for a free community site. At several
  hundred products you would be a noticeable load; raise the tier intervals if you
  scale up that far.

Repo growth is a non-issue: price history appends ~60 bytes per product per check,
so 50 products is roughly 50 MB/year before git compression, against GitHub's ~1 GB
guidance.

---

## Notes for future debugging

Two bugs during build, both of which failed *silently* — worth knowing the shape of them:

- **Unset secrets arrive as empty strings**, not missing keys. `os.environ.get("X", default)`
  returns `""`, not the default. Use `os.environ.get("X") or default`.
- **The dashboard downsamples to one point per day** (`daily_low`). Charting every
  30-minute sample meant ~156 KB of committed HTML per product, rewritten 48×/day.
  Daily lows are what matter for a price tracker and are 41× smaller.
- **Don't advertise `Accept-Encoding: br`** unless `brotli` is installed. `requests`
  cannot decode Brotli on its own and hands back binary garbage with HTTP 200, which
  looks exactly like an IP block. This cost a long detour — the fetcher now requests
  only `gzip, deflate`, and `brotli` is pinned in requirements as a safety net.

The fetcher records provider, failure kind, HTTP status when available, breaker state,
and the latest attempts in `data/state.json` for diagnosis from Actions logs and state.

---

## Files

```
watchlist.json              what to track
catalog.py                  URL normalization, identity, schema, and migration helpers
add_product.py              confirmed one-link intake through verified providers
providers/                  provider adapters and the Observation contract
fetch.py                    sequential provider fetch orchestration and breakers
analyze.py                  history storage + dual-window buy-zone engine
notify.py                   ntfy push + SMTP email
dashboard.py                static dashboard generator
main.py                     orchestrator, adaptive scheduling
.github/workflows/track.yml the 30-minute heartbeat
data/                       listing price history (auto-committed)
data/state.json             schema-v2 provider, product, and listing state
docs/index.html             dashboard (auto-generated)
docs/chart-data/            lazy chart JSON (auto-generated)
```

Personal-use tool: low request volume, no account access, no resale of data.
