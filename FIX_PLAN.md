# Dashboard redesign — fix plan

Directive instructions. Apply in order. Do not improvise: every replacement below is
given in full. If a block you are told to replace does not match the file character for
character, **stop and report** rather than guessing — the file has drifted from this plan.

Delete this file once all phases are merged.

---

## 0. Environment setup — do this first, it will bite you otherwise

Two things about this machine will waste your time if you skip them:

**a) The default `python` has no `pip`.** Create a venv with `uv`:

```bash
cd /d/GitHub/price-sentinel && uv venv .venv-fix && uv pip install -q --python .venv-fix -r requirements.txt pytest
```

Use `./.venv-fix/Scripts/python.exe` for everything below. Add `.venv-fix/` to
`.gitignore` or delete it when done — do not commit it.

**b) Printing `₹` to the Windows console raises `UnicodeEncodeError` (cp1252).**
Prefix every command that prints prices:

```bash
PYTHONIOENCODING=utf-8 ./.venv-fix/Scripts/python.exe dashboard.py
```

**Baseline before you change anything** — confirm you start from green:

```bash
cd /d/GitHub/price-sentinel && PYTHONIOENCODING=utf-8 ./.venv-fix/Scripts/python.exe -m pytest tests -q
```

Expected: `30 passed, 5 subtests passed`. If not, stop and report.

---

# PHASE 1 — merge blockers

## Task 1.1 — The verdict line must report data freshness, not effort

**Why.** `_verdict_line` reads `last_checked_ts`, which `main.py` sets *before* any fetch
is attempted and never clears on failure. With every provider dead, the page headline
reads `checked Just now`. This is the project's documented failure mode — reporting
success while doing nothing — on the single most important line of the page.
`last_success_ts` is only ever written by `_record_success`, so it is trustworthy.

**File:** `dashboard.py`

Replace the entire `_verdict_line` function with:

```python
def _verdict_line(products, state, now):
    count = sum(1 for product in products if _status(state, product) == "buy")
    if count == 0:
        headline = "No products in the buy zone"
    elif count == 1:
        headline = "1 product in the buy zone"
    else:
        headline = f"{count} products in the buy zone"
    # Freshness must describe DATA, not effort. last_checked_ts is set before the
    # fetch is attempted and survives total failure; last_success_ts does not.
    listings_state = state.get("listings") or {}
    timestamps = []
    for product in products:
        for listing in product.get("listings", []):
            stamp = _parse_ts(listings_state.get(listing.get("id"), {}).get("last_success_ts"))
            if stamp:
                timestamps.append(stamp)
    latest = max(timestamps, default=None)
    if latest is None:
        detail = "no successful check yet"
    elif now - latest > timedelta(hours=24):
        detail = f"STALE · last good price {_relative(latest, now)}"
    else:
        detail = f"priced {_relative(latest, now)}"
    return headline, f"{len(products)} tracked · {detail}"
```

`timedelta` is already imported at the top of the file. Do not add an import.

**Verify.** Save this as `verify_1_1.py` in the repo root and run it:

```python
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import main, fetch as fetcher, notify, re
os.environ["FORCE_ALL"] = "1"
notify.dispatch = lambda alerts: None
fetcher.fetch_listing = lambda listing, providers, session=None, now=None: (
    None, providers, [{"provider": "pricehistory.app", "status": "error"}])
main.run()
h = open("docs/index.html", encoding="utf-8").read().split("</style></head><body>")[1]
print("VERDICT:", re.sub("<[^>]+>", " ", re.search(r'<div class="verdict">(.*?)</div>', h).group(1)))
```

```bash
cd /d/GitHub/price-sentinel && PYTHONIOENCODING=utf-8 ./.venv-fix/Scripts/python.exe verify_1_1.py
```

This simulates a total provider outage. **Required:** the printed line must NOT contain
`checked Just now`. It must contain `priced` followed by a real age (the last real
success is ~2h old in committed state), or `STALE`. Then:

```bash
cd /d/GitHub/price-sentinel && git checkout docs/index.html data/state.json && rm verify_1_1.py
```

This test mutates `data/state.json` and `docs/index.html` — the checkout above is
mandatory, do not skip it.

---

## Task 1.2 — A dashboard crash must not destroy the run's collected data

**Why.** `dashboard.build()` is the last statement in `run()`, unguarded, and runs
*after* the CSV append, *after* `state.json` is written, and *after* the alert has been
pushed to the owner's phone. When it raises, `main.py` exits 1, the workflow's
"Commit history" step never runs, and the price sample is discarded with the runner.
`last_alert_ts` dies with it, so the cooldown resets and the same alert re-fires.
The dashboard is a *view*; it must degrade, not take down collection.

Both edits are required. Neither alone closes the hole.

### 1.2a — `main.py`

Add `import traceback` to the stdlib import block, keeping it alphabetical:

```python
import copy
import json
import os
import sys
import traceback
from datetime import datetime, timedelta, timezone
```

Replace:

```python
    # The dashboard is static and regenerated from committed watchlist/state.
    dashboard.build(products, state)
    print(f"[done] checked={checked} failed={failed} alerts={len(alerts)}")
```

with:

```python
    # The dashboard is a view over data that is already on disk but NOT yet
    # committed. A rendering bug must never cost us the price sample or the
    # alert-cooldown state, so it degrades to a stale page instead of exiting.
    try:
        dashboard.build(products, state)
    except Exception:
        traceback.print_exc()
        print("[dashboard] BUILD FAILED — price data preserved, page left stale")
    print(f"[done] checked={checked} failed={failed} alerts={len(alerts)}")
```

### 1.2b — `.github/workflows/track.yml`

Add an `if:` to the commit step so data survives any `main.py` failure. Replace:

```yaml
      - name: Commit history
        run: |
```

with:

```yaml
      - name: Commit history
        if: ${{ !cancelled() }}
        run: |
```

Change nothing else in that step. `!cancelled()` runs on success and failure but not on
cancellation. The job still goes red on failure — that is intended; we want to see it.

**Verify.**

```bash
cd /d/GitHub/price-sentinel && PYTHONIOENCODING=utf-8 ./.venv-fix/Scripts/python.exe -c "
import main, dashboard, notify, fetch as fetcher
notify.dispatch = lambda a: None
fetcher.fetch_listing = lambda l, p, session=None, now=None: (None, p, [])
def boom(*a, **k): raise ValueError('simulated rendering bug')
dashboard.build = boom
main.run(); print('EXIT REACHED — run() survived the crash')
"; echo "exit code: $?"
```

**Required:** exit code `0`, output ends with `EXIT REACHED`, and the traceback for
`simulated rendering bug` plus `BUILD FAILED` both appear above it. Then:

```bash
cd /d/GitHub/price-sentinel && git checkout data/state.json docs/index.html
```

---

## Task 1.3 — Currency must use en-IN grouping

**Why.** `_money` uses Python's `:,` (Western 3-digit) grouping while the chart JS uses
`toLocaleString("en-IN")` (lakh/crore). Above ₹99,999 the same card shows two different
numbers: card price `₹124,990`, chart axis directly below `₹1,24,990`. Invisible today
only because the one tracked product is ₹3,119.

**File:** `dashboard.py`

Replace the entire `_money` function with these two functions:

```python
def _group_inr(number):
    """Group digits en-IN: last three, then pairs. 1249900 -> 12,49,900."""
    digits = str(int(number))
    sign = ""
    if digits.startswith("-"):
        sign, digits = "-", digits[1:]
    if len(digits) <= 3:
        return sign + digits
    head, tail = digits[:-3], digits[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return sign + ",".join(parts) + "," + tail


def _money(value):
    if value is None:
        return "—"
    return f"₹{_group_inr(round(float(value)))}"
```

**Verify.**

```bash
cd /d/GitHub/price-sentinel && PYTHONIOENCODING=utf-8 ./.venv-fix/Scripts/python.exe -c "
import dashboard
expected = {3359:'₹3,359', 24990:'₹24,990', 99999:'₹99,999', 100000:'₹1,00,000',
            124990:'₹1,24,990', 1249900:'₹12,49,900', 12499000:'₹1,24,99,000'}
bad = [(v, dashboard._money(v), e) for v, e in expected.items() if dashboard._money(v) != e]
print('MISMATCHES:', bad)
assert not bad, bad
print('all en-IN groupings correct')
"
```

**Required:** `MISMATCHES: []`.

---

## Phase 1 gate

```bash
cd /d/GitHub/price-sentinel && PYTHONIOENCODING=utf-8 ./.venv-fix/Scripts/python.exe -m pytest tests -q && git status --porcelain
```

**Required:** `30 passed`, and `git status` shows only `dashboard.py`, `main.py`,
`.github/workflows/track.yml` modified. If `data/` or `docs/` appear as modified, you
skipped a `git checkout` above — run it now.

**Stop here and report if the user only asked for Phase 1.**

---

# PHASE 2 — correctness and UI

## Task 2.1 — Out-of-stock and the overloaded delta string

**Why.** *Correcting an error in the original audit: a successful out-of-stock fetch does
not render an enticing price — it renders **nothing at all**.* Verified against the real
pipeline: with the only listing out of stock, `main.py` filters it out of `fresh` offers,
so `recommended_listing_id` becomes `None`, `last_verdict` becomes `None`, and the card
renders `No fresh offer · No fresh offer / — / — / 100 / "No fresh verdict yet."`. The
word "stock" appears nowhere on the page. The tracker successfully fetched ₹2,799 at the
all-time low and the page claims it has no data — indistinguishable from a dead provider.
The full observation is sitting unused in `product_state["stale_offers"]`.

Separately, `"No fresh offer"` is the delta fallback for three unrelated conditions,
including *fresh* products with no lifetime high and products priced *above* their
all-time high — so a row can read `Fresh · 1 hr ago` and `No fresh offer` side by side.

**File:** `dashboard.py`

In `_card`, replace everything from the line `verdict = product_state.get("last_verdict") or {}`
down to and including the single-line `delta = ...` assignment, with:

```python
    verdict = product_state.get("last_verdict") or {}
    # No BUYABLE offer does not mean no data: an out-of-stock listing is filtered
    # out of `fresh` upstream and lands in stale_offers with its verdict intact.
    # Only accept a fallback that is still recent, never a days-old observation.
    stale_offers = product_state.get("stale_offers") or []
    fallback = next((offer for offer in stale_offers if offer.get("fresh")), {})
    out_of_stock = bool(fallback) and not fallback.get("in_stock", True)
    if not verdict and fallback:
        verdict = fallback
    recommended_id = product_state.get("recommended_listing_id")
    offer_items = _offer_data(product, state)
    recommended = next((item for item in offer_items if item["listing"]["id"] == recommended_id), None)
    chart_offer = recommended or (offer_items[0] if offer_items else None)
    recommended_listing = recommended["listing"] if recommended else None
    chart_listing = chart_offer["listing"] if chart_offer else None
    recommended_state = chart_offer["state"] if chart_offer else {}
    display_listing = recommended_listing or chart_listing
    price = _number(verdict.get("price"))
    score = _number(verdict.get("score"))
    high = _number(verdict.get("life_high") or recommended_state.get("site_high"))
    low = _number(verdict.get("life_low") or recommended_state.get("site_low"))
    if verdict.get("basis"):
        median = _number(verdict.get("median") or verdict.get("life_avg") or recommended_state.get("site_avg"))
        median_label = "Lifetime average"
    elif verdict.get("median") is not None:
        median = _number(verdict.get("median"))
        median_label = "180-day median"
    else:
        median = _number(verdict.get("life_avg") or recommended_state.get("site_avg"))
        median_label = "Lifetime average" if median is not None else "180-day median"
    below_peak = ((high - price) / high * 100) if high and price is not None and high >= price else None
    retailer = _retailer_label(display_listing.get("retailer")) if display_listing else "Not tracked"
    chart_retailer = _retailer_label(chart_listing.get("retailer")) if chart_listing else retailer
    freshness = _freshness(recommended_state, now) if display_listing else "No data"
    stock_note = " · Out of stock" if out_of_stock else ""
    color = "#3FB950" if status == "buy" else "#D29922" if status == "watch" else "#4B85D6"
    listing_id = chart_listing["id"] if chart_listing else (product.get("listings") or [{"id": ""}])[0]["id"]
    chart_path = chart_paths.get(listing_id, "")
    target = product.get("target")
    reasons = verdict.get("reasons") or ["No fresh verdict yet."]
    score_text = f"{score:.0f}" if score is not None else "—"
    fill = max(0, min(100, score or 0))
    if out_of_stock:
        delta = "Out of stock"
    elif price is None:
        delta = "No fresh offer"
    elif low is not None and price <= low:
        delta = "at all-time low"
    elif high is not None and price > high:
        delta = "above all-time high"
    elif below_peak is not None:
        delta = f"{below_peak:.0f}% below peak"
    else:
        delta = "No range data"
```

This block also supplies `median_label` (Task 2.2) and `display_listing` (Task 2.4).

## Task 2.2 — Stop mislabelling a lifetime average as a 180-day median

**Why.** When own history is under 8 samples, `analyze.evaluate` puts the provider's
*lifetime average* in `median` and records `basis: "lifetime stats from source site"`.
The dashboard labels it "180-day median" regardless and ignores `basis`. Every newly
added product mislabels this tile until it accumulates 8 samples.

`median_label` is already computed by Task 2.1. Now use it — in `_card`, replace:

```python
        f'<div class="st"><div class="stl">180-day median</div><div class="stv num">{_escape(_money(median))}</div></div>'
```

with:

```python
        f'<div class="st"><div class="stl">{_escape(median_label)}</div><div class="stv num">{_escape(_money(median))}</div></div>'
```

## Task 2.3 — `tabular-nums` on the score

**Why.** Spec item 4 calls tabular figures non-negotiable. Every numeric element carries
`.num` except `.mlabel`, which holds the score — the exact digit that changes between
refreshes, and the element the spec calls score-as-hero.

In `_card`, replace `<div class="mlabel">` with `<div class="mlabel num">`.
There is exactly one occurrence in the Python source. Do not touch the `.mlabel` CSS rule.

## Task 2.4 — Surface the stock note, and keep links on unbuyable products

In `_card`, replace:

```python
        f'<div><div class="nm">{_escape(product.get("name"))}</div><div class="sub2">{_escape(retailer)} · {_escape(freshness)}</div></div>'
```

with:

```python
        f'<div><div class="nm">{_escape(product.get("name"))}</div><div class="sub2">{_escape(retailer)} · {_escape(freshness)}{_escape(stock_note)}</div></div>'
```

Then, still in `_card`, the actions block currently keys off `recommended_listing`, so an
out-of-stock product loses its "Open on …" link entirely. Replace these three lines:

```python
    if recommended_listing:
        primary_url = recommended_listing.get("url")
```

with:

```python
    if display_listing:
        primary_url = display_listing.get("url")
```

and, a few lines below, replace:

```python
            or recommended_listing.get("source_urls", {}).get(source_name)
            or next(iter(recommended_listing.get("source_urls", {}).values()), None)
```

with:

```python
            or display_listing.get("source_urls", {}).get(source_name)
            or next(iter(display_listing.get("source_urls", {}).values()), None)
```

**Verify Phase 2.** Save as `verify_2.py` in the repo root:

```python
import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import main, fetch as fetcher, notify
from datetime import datetime, timezone
from providers.base import Observation
os.environ["FORCE_ALL"] = "1"
notify.dispatch = lambda a: None
fetcher.fetch_listing = lambda l, p, session=None, now=None: (Observation(
    listing_id=l["id"], price=2799.0, mrp=3999.0, currency="INR", in_stock=False,
    seller="Amazon", retailer="amazon.in", source="pricehistory.app",
    source_url="https://pricehistory.app/p/x", listing_url=l["url"], title="t",
    site_low=2799.0, site_avg=3301.0, site_high=3999.0, history=None,
    fetched_ts=datetime.now(timezone.utc), observed_ts=None), p, [])
main.run()
b = open("docs/index.html", encoding="utf-8").read().split("</style></head><body>")[1]
for name, pat in [("SUBLINE", r'class="sub2">(.*?)</div>'), ("PRICE", r'class="price num">(.*?)</div>'),
                  ("DELTA", r'class="delta num">(.*?)</div>'), ("SCORE", r'class="mlabel num">(.*?)</div>')]:
    m = re.search(pat, b)
    print(f"  {name:8}:", m.group(1) if m else "!! NOT FOUND !!")
print("  has 'Out of stock':", "Out of stock" in b)
print("  has 'Open on'     :", "Open on" in b)
```

```bash
cd /d/GitHub/price-sentinel && PYTHONIOENCODING=utf-8 ./.venv-fix/Scripts/python.exe verify_2.py
```

**Required:** `SUBLINE` ends with `· Out of stock`; `PRICE` is `₹2,799` (not `—`);
`DELTA` is `Out of stock`; `SCORE` is found (proving `mlabel num` applied) and is not `—`;
both booleans `True`. Then clean up — mandatory:

```bash
cd /d/GitHub/price-sentinel && git checkout docs/index.html data/state.json && rm verify_2.py
```

Then re-run the suite: `PYTHONIOENCODING=utf-8 ./.venv-fix/Scripts/python.exe -m pytest tests -q`
→ **30 passed**. If any test fails, report the failure verbatim; do not edit the tests to
make them pass.

---

# PHASE 3 — documentation and CI

## Task 3.1 — Restore the design reference and de-fabricate the spec

**Why.** The redesign commit deleted `docs/prototype.html` (the approved design
reference) and rewrote HANDOFF.md's "Dashboard redesign **spec**" section into
"Dashboard redesign **implementation**" in past tense, deleting the three unresolved
"Known concerns" and replacing them with statements that they were resolved. The
replacement text also claims "lazy **Chart.js** loading" and "the existing Chart.js CDN"
— there is no Chart.js in the codebase at all; it was replaced with a hand-rolled canvas
renderer. The next person reads a spec that says it was followed.

Restore the deleted prototype:

```bash
cd /d/GitHub/price-sentinel && git show 9120a8a:docs/prototype.html > docs/prototype.html
```

Then in `HANDOFF.md`, replace the paragraph under `### Implementation note` — currently
beginning "`dashboard.py` now emits the verdict-first expandable rows" — with:

```
`dashboard.py` emits the verdict-first expandable rows, status rails, range controls,
and lazy chart loading. Chart data is written to `docs/chart-data/*.json` from
`daily_low()` and fetched only when a row expands — do not revert to raw samples, and
do not inline the series into the page.

Chart.js was dropped in favour of a hand-rolled canvas renderer (~40 lines in `SCRIPT`).
This is a deliberate deviation from the original spec and should not be reverted: it
removes the CDN dependency, stops leaking the owner's watchlist to a third party on
every page view, and works offline. The generator remains dependency-free.
```

And under `### Known concerns`, replace the two bullets that begin "Charts are
lazy-rendered" and "Dashboard data is generated from committed" with:

```
- Charts are lazy-rendered from separate daily-low JSON files, verified by execution.
  The page sorts buy, watch and idle without non-functional filter chips.
- Chart range windows (1M/3M/6M/1Y/All) are measured back from the newest data point,
  not from today, so a stale product shows an old window under a current-sounding label.
  Unresolved.
```

Leave the "score meter is the weakest element" bullet exactly as it is — it is still
unresolved and was never tested.

## Task 3.2 — Run the tests in CI

**Why.** 30 tests exist and none of them run in CI; `track.yml` only runs `python main.py`.
They will rot silently.

In `requirements.txt`, append a line: `pytest>=8.0.0`

In `.github/workflows/track.yml`, add this step **after** the existing "Commit history"
step, as the last step in the job:

```yaml
      - name: Run tests
        if: ${{ !cancelled() }}
        run: python -m pytest tests -q
```

It must come **after** the commit step, not before. A failing test must never block price
data from being committed — that is the same mistake as Task 1.2. Running it last still
turns the run red, which is all we need.

---

# Final gate — run all of this before reporting done

```bash
cd /d/GitHub/price-sentinel && PYTHONIOENCODING=utf-8 ./.venv-fix/Scripts/python.exe -m pytest tests -q && PYTHONIOENCODING=utf-8 ./.venv-fix/Scripts/python.exe dashboard.py && git diff --stat
```

Then confirm each of these by eye in `docs/index.html`:

1. Product name is `Gillette Series 5 All-in-One Trimmer (Braun)`, price `₹3,119` — real
   data, not sample data.
2. The verdict sub-line says `priced …`, never `checked …`.
3. `class="mlabel num"` is present.
4. `docs/chart-data/amazon-in-b0gsvfv3r4.json` still has 32 daily points, and the HTML
   body contains no `"price"` key (charts stay lazy).

Regenerating the dashboard is expected to modify `docs/index.html` — commit it.

Report: which tasks you applied, the verification output for each, and anything you had
to stop on. Do not report success for a task whose verification you did not run.

## Explicitly out of scope — do not do these

- Do not "fix" the range-window behaviour (Task 3.1 documents it as a known issue).
- Do not add a URL scheme allowlist to `href` outputs — hardening, tracked separately.
- Do not touch `analyze.py` scoring formulas or `LOOKBACK_DAYS`.
- Do not edit any file under `tests/` to make a test pass.
- Do not commit `.venv-fix/`.
