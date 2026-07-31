"""Orchestrator. Run by GitHub Actions every 30 minutes.

Adaptive cadence keeps request volume low (and your IP unremarkable):
  hot  -> every cycle (~30 min)   items near their buy zone
  warm -> every 3 hours
  cold -> every 12 hours
Tiers auto-promote: anything scoring >=60 becomes hot without you touching it.
"""
import json
import os
import random
import sys
import time
from datetime import datetime, timedelta, timezone

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze  # noqa: E402
import dashboard  # noqa: E402
import fetch as fetcher  # noqa: E402
import notify  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(ROOT, "data", "state.json")
WATCHLIST = os.path.join(ROOT, "watchlist.json")

INTERVALS = {"hot": timedelta(minutes=25), "warm": timedelta(hours=3), "cold": timedelta(hours=12)}


def load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def due(product, state):
    if os.environ.get("FORCE_ALL") == "1":
        return True
    rec = state.get(product["asin"], {})
    last = rec.get("last_checked_ts")
    if not last:
        return True
    tier = rec.get("auto_tier") or product.get("tier", "warm")
    try:
        elapsed = datetime.now(timezone.utc) - datetime.fromisoformat(last)
    except ValueError:
        return True
    return elapsed >= INTERVALS.get(tier, INTERVALS["warm"])


def main():
    wl = load_json(WATCHLIST, {"products": []})
    products = wl.get("products", [])
    state = load_json(STATE_PATH, {})
    session = requests.Session()

    pending = [p for p in products if due(p, state)]
    print(f"[run] {len(pending)}/{len(products)} products due at {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC")

    alerts, checked, blocked = [], 0, 0

    for i, product in enumerate(pending):
        asin = product["asin"]
        if i:
            time.sleep(random.uniform(4, 11))  # be a polite, boring client

        ph_url = product.get("ph_url")
        obs = fetcher.fetch_pricehistory(ph_url, asin, session=session) if ph_url else None
        if not obs:
            obs = fetcher.fetch(asin, session=session)
        rec = state.setdefault(asin, {})

        if not obs:
            blocked += 1
            rec["consecutive_failures"] = rec.get("consecutive_failures", 0) + 1
            print(f"  {asin}: blocked/unparsed (fail streak {rec['consecutive_failures']})")
            continue

        checked += 1
        rec["consecutive_failures"] = 0
        rec["last_checked_ts"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        rec["last_price"] = obs["price"]

        analyze.append_observation(asin, obs)
        v = analyze.evaluate(asin, obs, product)
        rec["last_score"] = v["score"]
        rec["auto_tier"] = "hot" if v["score"] >= 60 else product.get("tier", "warm")

        flag = "ALERT" if v["alert"] else "     "
        print(f"  {flag} {asin}: Rs {obs['price']:,.0f} score {v['score']} via {obs.get('source', 'amazon')}")

        if analyze.should_notify(v, state):
            alerts.append(v)
            rec["last_alert_ts"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            rec["last_alert_price"] = v["price"]

    notify.dispatch(alerts)

    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2, sort_keys=True)

    dashboard.build(products, state)
    print(f"[done] checked={checked} blocked={blocked} alerts={len(alerts)}")


if __name__ == "__main__":
    main()
