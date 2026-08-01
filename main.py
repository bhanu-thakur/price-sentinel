"""Scheduled provider-only orchestrator for schema-v2 products."""

import copy
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze  # noqa: E402
import catalog  # noqa: E402
import dashboard  # noqa: E402
import fetch as fetcher  # noqa: E402
import notify  # noqa: E402


ROOT = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(ROOT, "data", "state.json")
WATCHLIST = os.path.join(ROOT, "watchlist.json")

INTERVALS = {
    "hot": timedelta(minutes=25),
    "warm": timedelta(hours=3),
    "cold": timedelta(hours=12),
}


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return default


def _parse_ts(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _iso(value):
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


def _new_state(state):
    if state.get("schema_version") != 2:
        return {"schema_version": 2, "providers": {}, "products": {}, "listings": {}}
    state.setdefault("providers", {})
    state.setdefault("products", {})
    state.setdefault("listings", {})
    return state


def due(product, state, now=None):
    """Return whether this product's configured/automatic cadence has elapsed."""
    if os.environ.get("FORCE_ALL") == "1":
        return True
    now = now or datetime.now(timezone.utc)
    product_state = state.get("products", {}).get(product["id"], {})
    last = _parse_ts(product_state.get("last_checked_ts"))
    if not last:
        return True
    tier = product_state.get("auto_tier") or product.get("tier", "warm")
    return now - last >= INTERVALS.get(tier, INTERVALS["warm"])


def _listing_state(state, listing_id):
    return state.setdefault("listings", {}).setdefault(listing_id, {})


def _record_success(record, observation, verdict, now, attempts):
    success_ts = observation.fetched_ts or now
    record.update({
        "consecutive_failures": 0,
        "last_checked_ts": _iso(now),
        "last_success_ts": _iso(success_ts),
        "last_price": observation.price,
        "last_in_stock": observation.in_stock,
        "last_score": verdict["score"],
        "last_source": observation.source,
        "last_source_url": observation.source_url,
        "last_retailer": observation.retailer,
        "site_avg": observation.site_avg,
        "site_high": observation.site_high,
        "site_low": observation.site_low,
        "last_verdict": verdict,
        "last_attempts": attempts,
    })
    if observation.history:
        record["provider_history"] = [
            {"date": day, "price": price} for day, price in observation.history
        ]
        record["provider_history_source"] = observation.source


def _record_failure(record, now, attempts):
    # Do not update last_checked_ts or last_success_ts: a failed request is not
    # a newly checked price and must not make last-known-good data look current.
    record["last_attempt_ts"] = _iso(now)
    record["last_attempts"] = attempts


def _stored_offer(listing, record, now):
    verdict = record.get("last_verdict")
    success_ts = _parse_ts(record.get("last_success_ts"))
    if not verdict or not success_ts:
        return None
    offer = copy.deepcopy(verdict)
    offer["listing_id"] = listing["id"]
    offer["retailer"] = listing.get("retailer")
    offer["listing_url"] = listing.get("url")
    offer["last_success_ts"] = _iso(success_ts)
    offer["fresh"] = now - success_ts <= timedelta(hours=24)
    return offer


def _offers_for_product(product, state, current_offers, now):
    by_listing = {offer["listing_id"]: offer for offer in current_offers}
    all_offers = []
    for listing in product.get("listings", []):
        if listing["id"] in by_listing:
            all_offers.append(by_listing[listing["id"]])
            continue
        record = _listing_state(state, listing["id"])
        stored = _stored_offer(listing, record, now)
        if stored:
            all_offers.append(stored)
    fresh = [offer for offer in all_offers if offer.get("fresh") and offer.get("in_stock")]
    stale = [offer for offer in all_offers if offer not in fresh]
    return fresh, stale


def _update_product_verdict(product, state, current_offers, now):
    product_state = state.setdefault("products", {}).setdefault(product["id"], {})
    fresh, stale = _offers_for_product(product, state, current_offers, now)
    recommended = min(fresh, key=lambda offer: (offer["price"], offer.get("retailer", ""))) if fresh else None
    product_state["last_verdict"] = copy.deepcopy(recommended) if recommended else None
    product_state["stale_offers"] = stale
    product_state["recommended_listing_id"] = recommended["listing_id"] if recommended else None
    if recommended:
        if recommended.get("alert"):
            product_state["status"] = "buy"
        elif recommended.get("score", 0) >= 60:
            product_state["status"] = "watch"
        else:
            product_state["status"] = "idle"
        product_state["auto_tier"] = "hot" if recommended.get("score", 0) >= 60 else product.get("tier", "warm")
    else:
        product_state["status"] = "idle"
        product_state["auto_tier"] = product.get("tier", "warm")
    return recommended


def run(now=None, session=None):
    now = now or datetime.now(timezone.utc)
    session = session or requests.Session()
    watchlist = load_json(WATCHLIST, {"schema_version": 2, "products": []})
    catalog.validate_watchlist(watchlist)
    state = _new_state(load_json(STATE_PATH, {}))
    products = watchlist.get("products", [])
    original_watchlist = json.dumps(watchlist, sort_keys=True)

    due_products = [product for product in products if due(product, state, now=now)]
    print(f"[run] {len(due_products)}/{len(products)} products due at {now:%Y-%m-%d %H:%M} UTC")

    alerts = []
    checked = 0
    failed = 0
    for product in due_products:
        product_state = state.setdefault("products", {}).setdefault(product["id"], {})
        product_state["last_checked_ts"] = _iso(now)
        current_offers = []
        for listing in product.get("listings", []):
            observation, state["providers"], attempts = fetcher.fetch_listing(
                listing, state["providers"], session=session, now=now
            )
            record = _listing_state(state, listing["id"])
            if observation is None:
                _record_failure(record, now, attempts)
                failed += 1
                continue

            checked += 1
            analyze.append_observation(listing["id"], observation, ts=observation.fetched_ts)
            verdict = analyze.evaluate(listing["id"], observation, product)
            _record_success(record, observation, verdict, now, attempts)
            current_offers.append({
                **verdict,
                "listing_id": listing["id"],
                "retailer": listing.get("retailer"),
                "listing_url": listing.get("url"),
                "last_success_ts": _iso(observation.fetched_ts),
                "fresh": True,
            })
            print(
                f"  {listing['id']}: Rs {observation.price:,.0f} "
                f"score {verdict['score']} via {observation.source}"
            )

        recommended = _update_product_verdict(product, state, current_offers, now)
        if recommended and analyze.should_notify(recommended, state):
            product_state["last_alert_ts"] = _iso(now)
            product_state["last_alert_price"] = recommended["price"]
            alerts.append(recommended)

    if json.dumps(watchlist, sort_keys=True) != original_watchlist:
        catalog.write_watchlist(WATCHLIST, watchlist)

    notify.dispatch(alerts)
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(state, handle, indent=2, sort_keys=True)

    # The dashboard is static and regenerated from committed watchlist/state.
    dashboard.build(products, state)
    print(f"[done] checked={checked} failed={failed} alerts={len(alerts)}")
    return state


def main():
    run()


if __name__ == "__main__":
    main()
