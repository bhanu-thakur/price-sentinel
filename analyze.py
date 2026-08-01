"""Buy-zone decision engine keyed by retailer listing ID."""

import csv
import os
from datetime import datetime, timedelta, timezone

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def _get(value, key, default=None):
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def history_path(listing_id):
    return os.path.join(DATA_DIR, f"{listing_id}.csv")


def append_observation(listing_id, obs, ts=None):
    os.makedirs(DATA_DIR, exist_ok=True)
    path = history_path(listing_id)
    new = not os.path.exists(path)
    ts = ts or _get(obs, "fetched_ts") or datetime.now(timezone.utc)
    with open(path, "a", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        if new:
            writer.writerow(["ts", "price", "mrp", "in_stock", "seller", "shipper"])
        writer.writerow([
            ts.isoformat(timespec="seconds"),
            f"{_get(obs, 'price'):.2f}",
            f"{_get(obs, 'mrp'):.2f}" if _get(obs, "mrp") else "",
            int(bool(_get(obs, "in_stock", True))),
            _get(obs, "seller") or "",
            _get(obs, "shipper") or "",
        ])


def load_history(listing_id, days=None):
    path = history_path(listing_id)
    if not os.path.exists(path):
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(days=days) if days else None
    rows = []
    with open(path, encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            try:
                ts = datetime.fromisoformat(row["ts"])
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
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


LOOKBACK_DAYS = 180


def evaluate(listing_id, obs, product, min_samples=8):
    """Return a listing verdict without changing the established formulas."""
    price = _get(obs, "price")
    hist = load_history(listing_id, days=LOOKBACK_DAYS)
    prices = sorted(p for _, p in hist)
    n = len(prices)

    v = {
        "listing_id": listing_id,
        "product_id": product.get("id"),
        "name": product.get("name") or _get(obs, "title") or listing_id,
        "price": price,
        "mrp": _get(obs, "mrp"),
        "seller": _get(obs, "seller"),
        "retailer": _get(obs, "retailer"),
        "source": _get(obs, "source"),
        "in_stock": _get(obs, "in_stock", True),
        "url": _get(obs, "listing_url"),
        "samples": n,
        "alert": False,
        "reasons": [],
        "score": 0,
    }

    target = product.get("target")
    if target is not None and price <= target:
        v["alert"] = True
        v["reasons"].append(f"At or below your target of Rs {target:,.0f}")

    if n < min_samples:
        lo, avg, hi = _get(obs, "site_low"), _get(obs, "site_avg"), _get(obs, "site_high")
        if lo and hi and hi > lo:
            v.update({"min90": lo, "median": avg or (lo + hi) / 2, "max90": hi,
                      "basis": "lifetime stats from source site"})
            v["score"] = round(min(100, 100 * (hi - price) / (hi - lo)), 1)
            if price <= lo * 1.005:
                v["alert"] = True
                v["reasons"].append(f"At the lowest price ever recorded (Rs {lo:,.0f})")
            elif price <= lo * 1.03:
                v["alert"] = True
                v["reasons"].append(f"Within 3% of the all-time low (Rs {lo:,.0f})")
            elif avg and price <= avg * 0.93:
                v["alert"] = True
                v["reasons"].append(f"{(1 - price / avg) * 100:.1f}% below the lifetime average")
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

    rank = sum(1 for p in prices if p < price) / n * 100
    v["percentile"] = rank
    v["vs_median_pct"] = (price - median) / median * 100 if median else 0

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
            f"Steep drop: {abs(v['vs_median_pct']):.1f}% under {LOOKBACK_DAYS}-day median"
        )

    life_lo, life_avg, life_hi = (
        _get(obs, "site_low"), _get(obs, "site_avg"), _get(obs, "site_high")
    )
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
            v["reasons"].append(f"{(1 - price / life_avg) * 100:.1f}% below the lifetime average")
        if life_hi and life_hi > life_lo:
            v["score"] = round(min(100, 100 * (life_hi - price) / (life_hi - life_lo)), 1)

    if _get(obs, "mrp") and _get(obs, "mrp") > 0:
        disc = (_get(obs, "mrp") - price) / _get(obs, "mrp") * 100
        v["mrp_discount_pct"] = disc
        if disc > 60 and median > _get(obs, "mrp") * 0.55:
            v["reasons"].append("Caution: MRP looks inflated - judge against history, not MRP")

    seller = (_get(obs, "seller") or "").lower()
    if seller and "amazon" not in seller and (_get(obs, "shipper") or "").lower().find("amazon") < 0:
        v["reasons"].append(f"Caution: third-party seller ({_get(obs, 'seller')})")

    if not _get(obs, "in_stock", True):
        v["alert"] = False
        v["reasons"].append("Out of stock - suppressed")
    return v


def should_notify(v, state, cooldown_days=7):
    """Anti-spam: suppress the same product inside the cooldown unless >3% cheaper."""
    if not v["alert"]:
        return False
    listing_id = v["listing_id"]
    if isinstance(state, dict) and "listings" in state:
        product_id = v.get("product_id")
        previous = (
            state.get("products", {}).get(product_id, {})
            if product_id
            else state.get("listings", {}).get(listing_id, {})
        )
    else:
        previous = state.get(listing_id, {})
    last_ts = previous.get("last_alert_ts")
    last_price = previous.get("last_alert_price")
    if not last_ts:
        return True
    try:
        parsed = datetime.fromisoformat(last_ts)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - parsed
    except (TypeError, ValueError):
        return True
    if age > timedelta(days=cooldown_days):
        return True
    return bool(last_price and v["price"] < last_price * 0.97)
