# Price Sentinel

Always-on Amazon.in price tracker. Runs on GitHub Actions every 30 minutes — free,
forever, whether or not your laptop is on. Alerts by phone push (ntfy) and email.

The point isn't "tell me the price." It's **judging whether a price is actually good**,
by scoring it against that product's own 90-day history instead of a threshold you guessed.

---

## Setup (~10 minutes, one time)

### 1. Create the repo

Make a **public** repo on GitHub named `price-sentinel` and push these files.

> Public matters: public repos get unlimited free Actions minutes. A private repo
> burns your 2,000 free minutes/month and a 30-min cadence will exhaust them.
> Nothing sensitive lives in the repo — only product links and price history.
> Your credentials go in encrypted Secrets, which stay private either way.

```bash
cd price-sentinel
git init && git add -A && git commit -m "init"
git branch -M main
git remote add origin https://github.com/<you>/price-sentinel.git
git push -u origin main
```

### 2. Phone push via ntfy (free, no account)

1. Install **ntfy** from the Play Store.
2. Pick a private topic name — treat it like a password, since anyone who knows it
   can read your alerts. Example: `bhanu-deals-7fk29x`
3. In the app: **+ → Subscribe to topic →** enter that name.

### 3. Email via Gmail

Gmail needs an **App Password**, not your login password:
Google Account → Security → 2-Step Verification (must be on) → App passwords →
generate one, copy the 16 characters.

### 4. Add repo secrets

Repo → **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Value |
|---|---|
| `NTFY_TOPIC` | `bhanu-deals-7fk29x` |
| `SMTP_HOST` | `smtp.gmail.com` |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | `bhanu.aichat@gmail.com` |
| `SMTP_PASS` | your 16-char app password |
| `MAIL_TO` | `bhanu.aichat@gmail.com` |

Either channel works alone — leave secrets out to disable that channel.

### 5. Turn on the dashboard

Repo → **Settings → Pages → Source: Deploy from branch → `main` / `/docs`**.
Live at `https://<you>.github.io/price-sentinel/`.

### 6. First run

Repo → **Actions → Price Sentinel → Run workflow** (tick *force_all*).
Check the log shows a price. Then it's on its own.

---

## Adding products

Edit `watchlist.json`, commit, push:

```json
{
  "asin": "B0GSVFV3R4",
  "name": "Gillette Series 5 Trimmer",
  "url": "https://www.amazon.in/dp/B0GSVFV3R4",
  "target": 2850,
  "tier": "hot"
}
```

The ASIN is the code after `/dp/` in any Amazon URL.
`target` is optional — a hard floor that always alerts. The statistical engine works without it.
`tier` is just a starting hint (`hot` / `warm` / `cold`); the system auto-promotes
anything scoring 60+ to `hot` on its own.

---

## How the decision engine works

Every check appends to `data/<ASIN>.csv`, committed to the repo — so your price
history is yours, permanently, not locked in someone's app.

An alert fires when **any** of these holds:

- Price is at or below your `target`
- Price is the **lowest in 90 days**
- Price is in the **bottom 10%** of the 90-day range *and* ≥5% under the median
- Price is in the bottom 25% *and* ≥7% under the median (a sharp sudden drop)

Then these **suppress** it:

- Out of stock
- Already alerted for this product in the last 7 days, unless it dropped a further 3%

And these get flagged **in** the alert, not hidden:

- Third-party seller rather than Amazon-fulfilled
- MRP looks inflated relative to real trading history (fake-discount detection)

`score` (0–100) blends how cheap the price is within its range with how volatile
that product is — a 5% dip on a rock-steady product outranks a 5% dip on one that
swings 20% monthly.

**Worth knowing:** statistical rules stay idle for the first ~8 observations of a new
product (roughly a day). Only `target` fires during that window. That's deliberate —
it prevents confident nonsense from a 3-point history.

---

## Cadence and cost

| Tier | Frequency |
|---|---|
| hot | every ~30 min |
| warm | every 3 hours |
| cold | every 12 hours |

For 50 products with a typical spread, that's ~350 requests/day. Randomised 4–11s
gaps and rotating headers keep the traffic unremarkable. Running cost: **₹0**.

---

## The one real limitation

GitHub Actions runners use Azure datacenter IPs, and Amazon sometimes serves those a
CAPTCHA. Expect a portion of checks to come back blocked — the log prints
`blocked/unparsed` and simply moves on.

This is fine in practice: at 48 attempts a day, a multi-day price window gets caught
even at a 40% success rate. Your ₹2,799 dip lasted about four days — roughly 190
attempts. You would not have missed it.

If you later see sustained failure streaks, add a scraper API as fallback for hot
items only (ScraperAPI / ScrapingBee free tiers ≈ 200 Amazon calls/month; paid ≈ ₹4,200/mo
— only worth it if you scale well past 50 products).

---

## Files

```
watchlist.json              what to track
fetch.py            page fetch + price extraction
analyze.py          history storage + buy-zone engine
notify.py           ntfy push + SMTP email
dashboard.py        static dashboard generator
main.py             orchestrator, adaptive scheduling
.github/workflows/track.yml the 30-minute heartbeat
data/                       price history (auto-committed)
docs/index.html             dashboard (auto-generated)
```

Personal-use tool: low request volume, no account access, no resale of data.
