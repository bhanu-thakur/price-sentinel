"""Buy-zone decision engine.

The whole point: a static threshold is a guess. This scores the current price
against its own history, so 'good deal' is defined by the product, not by you.
"""
import csv
import os
from datetime import datetime, timedelta, timezone

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def history_path(asin):
    return os.path.join(DATA_DIR, f"{asin}.csv")


def append_observation(asin, obs, ts=None):
    os.makedirs(DATA_DIR, exist_ok=True)
    path = history_path(asin)
    new = not os.path.exists(path)
    ts = ts or datetime.now(timezone.utc)
    with open(path, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["ts", "price", "mrp", "in_stock", "seller", "shipper"])
        w.writerow([
            ts.isoformat(timespec="seconds"),
            f"{obs['price']:.2f}",
            f"{obs['mrp']:.2f}" if obs.get("mrp") else "",
            int(bool(obs.get("in_stock"))),
            obs.get("seller") or "",
            obs.get("shipper") or "",
        ])


def load_history(asin, days=None):
    path = history_path(asin)
    if not os.path.exists(path):
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(days=days) if days else None
    rows = []
    with open(path) as f:
        for row in csv.DictReader(f):
            try:
                ts = datetime.fromisoformat(row["ts"])
                price = float(row["price"])
            except (ValueError, KeyError):
                continue
            if cutoff and ts < cutoff:
                continue
            rows.append((ts, price))
    return rows


def percentile(sorted_vals, p):
    if not sorted_vals:
        return None
    k = (len(sorted_vals) - 1) * (p / 100.0)
    lo, hi = int(k), min(int(k) + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


# Two windows on purpose.
#
# RECENT (180d) answers "is this cheap versus how it has been trading lately?"
# It adapts to price drift - a product that launched at 4,500 and now sits at
# 3,300 should not look like a permanent bargain.
#
# LIFETIME (from the source site, effectively max-available) answers "is this a
# festival-grade low?" Big Billion Days / Great Indian Festival happen once a
# year, so any window shorter than a year is structurally blind to them.
#
# An alert fires on EITHER. Using only the long window would hide ordinary good
# deals behind an unbeatable annual floor; using only the short one would miss
# the biggest drop of the year entirely.
LOOKBACK_DAYS = 180


def evaluate(asin, obs, product, min_samples=8):
    """Return a verdict dict. 'alert' True means it is worth waking you up."""
    price = obs["price"]
    hist = load_history(asin, days=LOOKBACK_DAYS)
    prices = sorted(p for _, p in hist)
    n = len(prices)

    v = {
        "asin": asin,
        "name": product.get("name") or obs.get("title") or asin,
        "price": price,
        "mrp": obs.get("mrp"),
        "seller": obs.get("seller"),
        "in_stock": obs.get("in_stock", True),
        "samples": n,
        "alert": False,
        "reasons": [],
        "score": 0,
        "url": product.get("url") or f"https://www.amazon.in/dp/{asin}",
    }

    # Hard target always wins, even with no history.
    target = product.get("target")
    if target and price <= target:
        v["alert"] = True
        v["reasons"].append(f"At or below your target of Rs {target:,.0f}")

    if n < min_samples:
        # Cold start: fall back on the lifetime low/avg/high the source site
        # publishes, so buy-zone logic is useful from the very first run.
        lo, avg, hi = obs.get("site_low"), obs.get("site_avg"), obs.get("site_high")
        if lo and hi and hi > lo:
            v.update({"min90": lo, "median": avg or (lo + hi) / 2, "max90": hi,
                      "basis": "lifetime stats from source site"})
            v["score"] = round(min(100, 100 * (hi - price) / (hi - lo)), 1)
            if price <= lo * 1.005:
                v["alert"] = True
                v["reasons"].append(f"At the lowest price ever recorded (Rs {lo:,.0f})")
            elif price <= lo * 1.03:
                v["alert"] = True
                v["reasons"].append(
                    f"Within 3% of the all-time low (Rs {lo:,.0f})")
            elif avg and price <= avg * 0.93:
                v["alert"] = True
                v["reasons"].append(
                    f"{(1 - price / avg) * 100:.1f}% below the lifetime average")
            v["reasons"].append(f"Own history still building ({n} samples)")
        else:
            v["reasons"].append(f"Building history ({n} samples) - statistical rules idle")
            v["score"] = 100 if v["alert"] else 0
        return v

    p10 = percentile(prices, 10)
    p25 = percentile(prices, 25)
    median = percentile(prices, 50)
    lo, hi = prices[0], prices[-1]
    v.update({"p10": p10, "p25": p25, "median": median, "min90": lo, "max90": hi})

    # Where does today sit in its own 90-day distribution? 0 = cheapest ever seen.
    rank = sum(1 for p in prices if p < price) / n * 100
    v["percentile"] = rank
    v["vs_median_pct"] = (price - median) / median * 100 if median else 0

    # Score 0-100: cheapness within range, weighted by how wide that range is.
    span = hi - lo
    cheapness = 100 * (hi - price) / span if span > 0 else 0
    volatility_bonus = min(25, (span / median * 100)) if median else 0
    v["score"] = round(min(100, cheapness * 0.8 + volatility_bonus), 1)

    if price <= lo:
        v["alert"] = True
        v["reasons"].append(f"Lowest price in {LOOKBACK_DAYS} days")
    elif rank <= 10 and price <= median * 0.95:
        v["alert"] = True
        v["reasons"].append(
            f"Bottom {rank:.0f}% of {LOOKBACK_DAYS}-day range, "
            f"{abs(v['vs_median_pct']):.1f}% under median"
        )
    elif rank <= 25 and price <= median * 0.93:
        v["alert"] = True
        v["reasons"].append(
            f"Steep drop: {abs(v['vs_median_pct']):.1f}% under {LOOKBACK_DAYS}-day median")

    # Lifetime overlay - this is what catches the annual sale events.
    life_lo, life_avg = obs.get("site_low"), obs.get("site_avg")
    life_hi = obs.get("site_high")
    if life_lo:
        v["life_low"], v["life_avg"], v["life_high"] = life_lo, life_avg, life_hi
        if price <= life_lo * 1.005:
            v["alert"] = True
            v["reasons"].append(f"Lowest price EVER recorded (Rs {life_lo:,.0f})")
        elif price <= life_lo * 1.03:
            v["alert"] = True
            v["reasons"].append(f"Within 3% of the all-time low (Rs {life_lo:,.0f})")
        elif life_avg and price <= life_avg * 0.93:
            v["alert"] = True
            v["reasons"].append(
                f"{(1 - price / life_avg) * 100:.1f}% below the lifetime average")
        # Score against the LIFETIME range, not the recent one. The 180-day span
        # is narrow enough that any new low saturates it, which would rate a
        # modest dip the same as a festival-grade one. The lifetime range is the
        # meaningful absolute scale.
        if life_hi and life_hi > life_lo:
            v["score"] = round(min(100, 100 * (life_hi - price) / (life_hi - life_lo)), 1)

    # Trap detection - stops you celebrating a fake discount.
    if obs.get("mrp") and obs["mrp"] > 0:
        disc = (obs["mrp"] - price) / obs["mrp"] * 100
        v["mrp_discount_pct"] = disc
        if disc > 60 and median > obs["mrp"] * 0.55:
            v["reasons"].append("Caution: MRP looks inflated - judge against history, not MRP")

    seller = (obs.get("seller") or "").lower()
    if seller and "amazon" not in seller and (obs.get("shipper") or "").lower().find("amazon") < 0:
        v["reasons"].append(f"Caution: third-party seller ({obs.get('seller')})")

    if not obs.get("in_stock", True):
        v["alert"] = False
        v["reasons"].append("Out of stock - suppressed")

    return v


def should_notify(v, state, cooldown_days=7):
    """Anti-spam: don't re-alert the same price band inside the cooldown."""
    if not v["alert"]:
        return False
    prev = state.get(v["asin"], {})
    last_ts = prev.get("last_alert_ts")
    last_price = prev.get("last_alert_price")
    if not last_ts:
        return True
    try:
        age = datetime.now(timezone.utc) - datetime.fromisoformat(last_ts)
    except ValueError:
        return True
    if age > timedelta(days=cooldown_days):
        return True
    # Re-alert early only if it got meaningfully cheaper (>3%).
    return bool(last_price and v["price"] < last_price * 0.97)
