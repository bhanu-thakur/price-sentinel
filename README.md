# Price Sentinel

Always-on Amazon.in price tracker. Runs on GitHub Actions every 30 minutes — free,
forever, whether or not your laptop is on. Alerts by phone push (ntfy) and email.

The point isn't "tell me the price." It's **judging whether a price is actually good**,
by scoring it against that product's own history rather than a threshold you guessed.

**Live dashboard:** https://bhanu-thakur.github.io/price-sentinel/

---

## How it gets prices

Primary source is **pricehistory.app**, not Amazon directly. Two reasons:

1. It server-renders the current price, MRP, and the product's **lifetime low / average /
   high** into a single meta tag — a far more stable parse target than Amazon's
   A/B-tested price markup.
2. Those lifetime figures mean buy-zone logic works on the **first run**, instead of
   waiting to accumulate its own history.

Amazon.in direct is kept as an automatic fallback if the primary source fails.

Each product needs a `ph_url`, resolved once when you add it (see below). At runtime
there's no search step — just a direct fetch of a stable URL.

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

1. Paste the Amazon link into the search box at https://pricehistory.app/
2. Copy the resulting `/p/...` URL.
3. Add an entry to `watchlist.json` and commit:

```json
{
  "asin": "B0GSVFV3R4",
  "name": "Gillette Series 5 Trimmer",
  "url": "https://www.amazon.in/dp/B0GSVFV3R4",
  "ph_url": "https://pricehistory.app/p/gillette-series-5-all-one-beard-body-5vQqMKIm",
  "target": 2850,
  "tier": "hot"
}
```

`target` is optional — a hard floor that always alerts. The statistical engine works
without it. `tier` (`hot`/`warm`/`cold`) is only a starting hint; anything scoring 60+
is auto-promoted to `hot`.

---

## How the decision engine works

Every check appends to `data/<ASIN>.csv`, committed to the repo — your price history
is yours permanently, not locked inside someone's app.

**Once it has 8+ of its own samples**, an alert fires when any of these hold:

- Price at or below your `target`
- **Lowest in 90 days**
- Bottom 10% of the 90-day range *and* ≥5% under the median
- Bottom 25% *and* ≥7% under the median (a sharp sudden drop)

**Before that**, it uses the source site's lifetime figures:

- At the lowest price ever recorded
- Within 3% of the all-time low
- ≥7% below the lifetime average

Then these **suppress** the alert:

- Out of stock
- Already alerted for this product within 7 days, unless it dropped a further 3%

And these are **surfaced inside** the alert rather than hidden:

- Third-party seller rather than Amazon-fulfilled
- MRP inflated relative to real trading history (fake-discount detection)

`score` (0–100) blends how cheap the price is within its range with how volatile the
product is, so a 5% dip on a rock-steady product outranks 5% on one that swings 20%
monthly.

---

## Cadence

| Tier | Frequency |
|---|---|
| hot | ~30 min |
| warm | 3 hours |
| cold | 12 hours |

For 50 products that's roughly 350 requests/day, with randomised 4–11s gaps and
rotating headers. Running cost: **₹0**.

---

## Notes for future debugging

Two bugs during build, both of which failed *silently* — worth knowing the shape of them:

- **Unset secrets arrive as empty strings**, not missing keys. `os.environ.get("X", default)`
  returns `""`, not the default. Use `os.environ.get("X") or default`.
- **Don't advertise `Accept-Encoding: br`** unless `brotli` is installed. `requests`
  cannot decode Brotli on its own and hands back binary garbage with HTTP 200, which
  looks exactly like an IP block. This cost a long detour — the fetcher now requests
  only `gzip, deflate`, and `brotli` is pinned in requirements as a safety net.

The fetcher logs the HTTP status and a body snippet on every failed parse, so the next
failure is diagnosable from the Actions log alone.

---

## Files

```
watchlist.json              what to track
fetch.py                    price-history + Amazon fetchers, price extraction
analyze.py                  history storage + buy-zone engine
notify.py                   ntfy push + SMTP email
dashboard.py                static dashboard generator
main.py                     orchestrator, adaptive scheduling
.github/workflows/track.yml the 30-minute heartbeat
data/                       price history (auto-committed)
docs/index.html             dashboard (auto-generated)
```

Personal-use tool: low request volume, no account access, no resale of data.
