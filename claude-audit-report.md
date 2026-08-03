# Audit — FIX_PLAN.md execution + cross-platform / new-product asks

Repo: `D:\GitHub\price-sentinel` · HEAD `7c8a222` (= `origin/main`) · audited 2026-08-02
Procedure, commands and limits: [`claude-audit-method.md`](claude-audit-method.md)
**No source file, data file or generated artifact in the repo was modified by this audit.**

---

## 1. Verdict

| Ask | Status |
|---|---|
| FIX_PLAN.md Phase 1 (3 tasks) | **Applied correctly, verified** |
| FIX_PLAN.md Phase 2 (4 tasks) | **Applied correctly, verified** |
| FIX_PLAN.md Phase 3 (2 tasks) | **Applied correctly, verified** |
| Track the 2 Amazon products | **Done and live** |
| Make them visible on index | **Done and live** |
| GitHub workflow updates | **Done, green in CI** |
| Compare listings across platforms (Flipkart vs Amazon) | **Not delivered.** No code written for it; zero non-Amazon listings exist; the page compares nothing. Plus a latent rendering bug that fires the moment a second retailer is added. |

Every instruction in FIX_PLAN.md was applied **verbatim** — each replacement block was diffed
against the plan text character-for-character. No improvisation, no silent drift. That part of
the work is clean.

The gap is the part that was *not* in FIX_PLAN.md: the cross-platform comparison.

---

## 2. FIX_PLAN.md — task by task

Change set: `7e91a11` → merged as `f111895` → data commit `7c8a222`.
Scope check (`git show --stat`): only the files the plan names were touched.

### Phase 1

**1.1 — verdict line reports data freshness, not effort** · `dashboard.py:157-181` · **APPLIED, VERIFIED**

Replacement matches the plan exactly. Re-verified by executing `_verdict_line` directly
(no file writes):

| scenario | output |
|---|---|
| total provider outage, no successful check ever | `1 tracked · no successful check yet` |
| outage, last good price 3h old | `1 tracked · priced 3 hr ago` |
| last good price 5 days old | `1 tracked · STALE · last good price 5d ago` |

The live page reads `3 tracked · priced Just now`. The word `checked` no longer appears.
The documented failure mode — reporting success while doing nothing — is closed. ✔

**1.2a — `main.py` guards `dashboard.build()`** · `main.py:222-229` · **APPLIED**

`import traceback` added alphabetically (`main.py:7`); `try/except Exception` with
`traceback.print_exc()` and the `[dashboard] BUILD FAILED — price data preserved, page left
stale` message, followed by the unchanged `[done]` line. Matches the plan exactly.
Assessed by code inspection — the plan's simulation writes `data/state.json` (see method §6.1).

**1.2b — `track.yml` commit step survives a `main.py` failure** · **APPLIED, VERIFIED IN CI**

`if: ${{ !cancelled() }}` added to `Commit history`; nothing else in the step changed.

**1.3 — en-IN currency grouping** · `dashboard.py:55-76` · **APPLIED, VERIFIED**

`_group_inr` + rewritten `_money`, verbatim. All seven plan cases pass — `MISMATCHES: []`:

```
3359 → ₹3,359      99999 → ₹99,999      124990 → ₹1,24,990      12499000 → ₹1,24,99,000
24990 → ₹24,990    100000 → ₹1,00,000   1249900 → ₹12,49,900
```

Beyond the plan: `None → —`, `0 → ₹0`, `2799.6 → ₹2,800`, `-1234567 → ₹-12,34,567`
(sign printed after the ₹ — cosmetic only; no card can reach a negative price).
Card and chart axis now agree above ₹99,999.

**Phase 1 gate** — `30 passed, 5 subtests passed`, re-run today. ✔

### Phase 2

**2.1 — out-of-stock fallback + delta ladder** · `dashboard.py:296-348` · **APPLIED**

Whole block matches the plan. The intended single-listing case reproduces:

```
SUB2  : Amazon · Fresh · 1 hr ago · Out of stock
PRICE : ₹2,799        DELTA : Out of stock        SCORE : 100 / 100
```

The plan's stated goal is met — a successful out-of-stock fetch is no longer rendered as
"no data". But the implementation carries a defect at more than one listing: **Finding A**.

**2.2 — `median_label`** · `dashboard.py:316-324, 378` · **APPLIED, VERIFIED**

Verdict carrying `basis` (own history under 8 samples) → tile reads `Lifetime average`.
Verdict carrying a real 180-day `median` → tile reads `180-day median`. Both branches
confirmed by probe. Both new products currently render `Lifetime average`, correctly —
they are at 1 sample each.

**2.3 — `tabular-nums` on the score** · `dashboard.py:415` · **APPLIED, VERIFIED**

Exactly one occurrence changed; the `.mlabel` CSS rule untouched; `class="mlabel num"` is
present in the generated `docs/index.html`.

**2.4 — stock note + links on unbuyable products** · `dashboard.py:390-396, 414` · **APPLIED**

`recommended_listing` → `display_listing` in all three prescribed places. An out-of-stock
product keeps its `Open on …` and `View price history` buttons (probe: `HAS_OPEN_ON: True`).

### Phase 3

**3.1 — restore the design reference, de-fabricate the spec** · **APPLIED, VERIFIED**

`docs/prototype.html` is **byte-identical** to `9120a8a:docs/prototype.html` (`diff` clean —
not an eyeball check). `HANDOFF.md`'s "Implementation note" and the two "Known concerns"
bullets now carry the exact replacement text: the Chart.js fabrication is gone, the
hand-rolled canvas renderer is documented as a deliberate deviation, and the range-window
behaviour is recorded as `Unresolved`. The "score meter is the weakest element" bullet was
left untouched, as instructed.

**3.2 — run the tests in CI** · **APPLIED, VERIFIED IN CI**

`pytest>=8.0.0` appended to `requirements.txt`. `Run tests` added **after** `Commit history`
as the final step. CI run **30715385666**, on the audited SHA `7c8a222`:

```
4 success  pip install -r requirements.txt
5 success  Run tracker
6 success  Commit history
7 success  Run tests          ← new step, correct position, green
```

Ordering is right: a failing test turns the run red without ever gating the price commit.

### Final gate — independently re-checked

1. Gillette card price `₹3,119`, real product name — not sample data ✔
2. Verdict sub-line says `priced …`, never `checked …` ✔
3. `class="mlabel num"` present ✔
4. `docs/chart-data/amazon-in-b0gsvfv3r4.json` = **32** daily points ✔;
   `docs/index.html` contains **0** occurrences of `"price"` — charts stayed lazy ✔
5. Working tree clean of `data/` and `docs/` drift; no `verify_*.py` left behind ✔
6. `.venv-fix/` was not committed ✔ — but see Finding E for *why*

---

## 3. Findings

### A — HIGH · False "Out of stock" the moment a second retailer is added

`dashboard.py:299-301`

```python
stale_offers = product_state.get("stale_offers") or []
fallback = next((offer for offer in stale_offers if offer.get("fresh")), {})
out_of_stock = bool(fallback) and not fallback.get("in_stock", True)
```

`out_of_stock` is computed from the first fresh entry in `stale_offers` **unconditionally** —
it never checks whether a real, buyable recommended verdict already exists two lines below.
In `main.py`, `_offers_for_product` (`main.py:136`) filters `fresh` down to
*fresh **and** in-stock*, so **every** offer that is out of stock lands in `stale` — including
a sibling retailer on a product whose primary offer is perfectly buyable.

Reproduced by executing the real `_card()` against a two-listing state: Amazon **in stock at
₹3,119** (recommended) plus a Flipkart listing that is fresh but out of stock →

```
SUB2  : Amazon · Fresh · 1 hr ago · Out of stock     ← wrong
PRICE : ₹3,119
DELTA : Out of stock                                  ← wrong
```

The card advertises a buyable price and simultaneously tells you it is out of stock. This is
invisible today only because all three products have exactly one listing — i.e. it surfaces on
day one of the cross-platform feature. `out_of_stock` needs to be gated on `not verdict`, or
read from the recommended offer, rather than from any sibling.

### B — MEDIUM · Cross-platform comparison was never implemented

Nothing in `7e91a11` addresses it. The `watchlist.json` diff is +52 lines = the two Amazon
products and nothing else. Current live state:

- `docs/index.html` contains **0** occurrences of "Flipkart".
- Every product's Offers table renders **exactly one row** (Amazon, marked "Best").
- All three products have exactly one `amazon.in` listing.

The plumbing that *would* carry the feature is real but **pre-existing** (commit `25950e1`,
before the fix plan): schema-v2 multi-listing products, `_offers_for_product` selecting the
cheapest fresh in-stock offer across retailers, the Offers comparison table in `_card`,
`RETAILER_LABELS` already covering Flipkart / Myntra / Croma / Tata CLiQ / AJIO / Snapdeal /
Reliance Digital / Vijay Sales, and `add_product.py` counterpart discovery. None of it was
exercised. Four concrete obstacles:

1. **Nelko has no BuyHatke source URL** (`watchlist.json:47-49` — `pricehistory.app` only).
   `buyhatke.discover()` (`providers/buyhatke.py:188`) is the only genuine cross-*site*
   discovery in the codebase — it reads the comparison `link:` fields.
   `pricehistory_app.discover()` (`providers/pricehistory_app.py:245`) only scrapes retailer
   anchors already present on that single product page. So for Nelko, cross-platform discovery
   is effectively switched off.
2. **Jenga's `rejected_candidate_urls` are four Amazon URLs** (`watchlist.json:60-63`) — all
   variants of the same game. No Flipkart candidate ever surfaced at all.
3. **Brand matching is fragile across retailers.** `catalog.extract_attributes` sets
   `brand` = the literal **first word of the title** (`catalog.py:123-125`), and
   `match_candidate` hard-**rejects** on any brand mismatch (`catalog.py:167-170`). A Flipkart
   title that does not lead with the brand word is discarded before a human is ever asked.
4. **No comparison is surfaced in the UI even when the data exists.** There is no
   "₹220 cheaper on Flipkart" line on the collapsed row. The only comparison surface is the
   Offers table, which sits inside the collapsed body — invisible while scanning, which is the
   page's stated primary job.

In fairness to the executor: FIX_PLAN.md never mentions cross-platform comparison, and its
"Explicitly out of scope" list is detailed. This reads as the requirement being lost between
the instruction and the plan, not the plan being disobeyed.

### C — MEDIUM · The verdict line hides per-product staleness at N > 1

`dashboard.py:174` takes `max()` of every listing's `last_success_ts`. With one product that
was exact. With three, one healthy product masks two dead ones — the headline can read
`3 tracked · priced Just now` while two products have not been priced in a week. Per-card
`Fresh` / `Stale` still tells the truth, so this is a headline-honesty regression at scale
rather than a data bug — and it arrived the day the two products were added. A minimum, or an
explicit "2 of 3 stale", would restore the property Task 1.1 was written to protect.

### D — LOW · The "never a days-old observation" guarantee is not enforced at render time

The comment at `dashboard.py:298` promises the fallback is recent, but `fresh` is a **stored
boolean**, written by `main._stored_offer` (`main.py:121`) when the product was last *due*.
`dashboard.py` trusts the flag instead of recomputing it from `last_success_ts` against `now`,
which it has. For a `warm` product (3h cadence) the flag can be ~3h out of date, `cold` ~12h —
so a fallback up to ~36h old can render as fresh. Bounded and low-impact, but the code does not
do what its comment claims.

### E — LOW · Housekeeping the plan asked for and did not get

- **`FIX_PLAN.md` is still in the repo** and committed. Its line 7: *"Delete this file once all
  phases are merged."* All phases are merged.
- **`.venv-fix/` is still on disk.** Plan §0: *"Add `.venv-fix/` to `.gitignore` or delete it
  when done."* Neither happened. It escaped being committed only because `uv` writes its own
  `.gitignore` **inside** the venv (`git check-ignore -v` → `.venv-fix/.gitignore:1:*`), not
  because of any repo rule. There is **no root `.gitignore` in this repo at all**, and
  `__pycache__/`, `providers/__pycache__/`, `tests/__pycache__/` are untracked and unignored —
  one `git add .` commits them. CI is safe (`git add data docs watchlist.json`); local commits
  are not.

### F — LOW/INFO · Zero tests were added for three phases of behaviour change

The suite is still the same **30** tests, and `tests/test_dashboard.py` still contains exactly
**one** test (`test_ordering_escaping_offer_table_and_lazy_chart_files`). Nothing covers en-IN
grouping, the out-of-stock card path, the freshness verdict line, or the `build()` crash guard
— all newly written, each verified once by hand and then left unguarded. Task 3.2's own
rationale was that untested code "will rot silently"; the same argument applies to the code it
protects. The plan did not request new tests, so this is a gap in the plan as much as in the
execution.

### G — INFO · Side effects of adding the two products

- **All three products now read "buy zone" simultaneously**, so the headline is permanently
  `3 products in the buy zone` and the page loses the dismiss-at-a-glance property it was
  redesigned for. Cause is `analyze.evaluate`'s `n < min_samples` branch (`analyze.py:100-119`):
  on sample #1 both new products alerted off *"X% below the lifetime average"* — Nelko 8.1%
  (score 83.5), Jenga 14.0% (score 74.1). Pre-existing and explicitly out of scope for the
  plan; flagged because you now feel it on the page.
- **The 7-day alert cooldown has been burned on both new products.**
  `last_alert_ts = 2026-08-01T19:38:35Z` for each, while `notify.py` is still a no-op because
  no secrets are set. Neither alert was ever delivered, and neither product can alert again
  until ~8 Aug unless it drops a further 3%. Worth clearing if you set the secrets this week.
- **URL hygiene is inconsistent.** Gillette keeps `https://www.amazon.in/dp/…` (with `www.`)
  while the two new listings are normalised bare-host; the Jenga URL retains its
  `/ref=ox_sc_saved_title_5` tracking path segment, because `catalog.normalize_url`
  (`catalog.py:47`) strips tracking *query* params but not *path* refs. Listing IDs are correct
  in all three cases, so this is cosmetic.

---

## 4. Recommended order of work

No code was written for any of these.

1. **Fix Finding A before adding any Flipkart listing.** It is a small change and it is the
   difference between the cross-platform feature reading correctly and reading broken on its
   first day.
2. **Then actually add a second platform.** Realistic path: resolve a BuyHatke URL for Nelko so
   `discover()` has something cross-site to read; if discovery still returns nothing, run
   `add_product.py` against the Flipkart URLs directly and hand-confirm the counterpart
   listings into `watchlist.json`. Loosen the first-word brand rule (B.3) or you will keep
   getting silent rejects with no log line explaining them.
3. **Surface the comparison on the collapsed row** — e.g. "cheapest of 2 · ₹220 less on
   Flipkart". Without it the feature exists in the data and not on the page.
4. Finding C (per-product staleness in the headline), then D, then F.
5. **Workflow: no further change is needed for cross-platform.** Cadence and the 20-minute
   timeout have ample headroom — 3 products × 2 listings at the 4–11s inter-request gap is well
   under a minute, against the ~9s/product model in HANDOFF.md. The only thing worth revisiting
   is that `Run tests` now executes on all 48 cron runs a day; a `push` / `pull_request` trigger
   would be cheaper, but the current arrangement works and the cost is small.
6. Delete `FIX_PLAN.md`; add a root `.gitignore`.
