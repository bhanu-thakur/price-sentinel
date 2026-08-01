"""Interactive one-link product intake for schema-v2 watchlists."""

import argparse
import json
import os
import sys

import requests

import catalog
from providers import SourceError
from providers import buyhatke, pricehistory_app


ROOT = os.path.dirname(os.path.abspath(__file__))
WATCHLIST_PATH = os.path.join(ROOT, "watchlist.json")
ADAPTERS = (pricehistory_app, buyhatke)


def _load_watchlist():
    try:
        with open(WATCHLIST_PATH, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {"schema_version": 2, "products": []}
    catalog.validate_watchlist(data)
    return data


def _resolve_sources(retailer_url, session):
    resolved = []
    for adapter in ADAPTERS:
        try:
            source_url = adapter.resolve(retailer_url, session)
        except SourceError as exc:
            print(f"  [{adapter.PROVIDER}] resolve {exc.kind}: {exc.message}")
            continue
        if source_url:
            resolved.append((adapter, source_url))
    return resolved


def _seed_listing(retailer_url, title):
    return {
        "id": catalog.listing_id_for(retailer_url),
        "retailer": catalog.retailer_hostname(retailer_url),
        "url": retailer_url,
        "confirmed_by": "seed",
        "attributes": catalog.extract_attributes(title),
        "source_urls": {},
    }


def build_product(retailer_url, target, tier, session=None, confirm=input):
    """Build a proposed product without writing it to disk."""
    session = session or requests.Session()
    retailer_url = catalog.normalize_url(retailer_url)
    resolved = _resolve_sources(retailer_url, session)
    if not resolved:
        raise RuntimeError("no working provider resolved the retailer URL")

    provisional = _seed_listing(retailer_url, "")
    seed_obs = None
    for adapter, source_url in resolved:
        try:
            observation = adapter.fetch(source_url, provisional, session)
        except SourceError as exc:
            print(f"  [{adapter.PROVIDER}] fetch {exc.kind}: {exc.message}")
            continue
        provisional["source_urls"][adapter.PROVIDER] = source_url
        if seed_obs is None:
            seed_obs = observation
    if seed_obs is None:
        raise RuntimeError("resolved providers returned no valid seed observation")

    title = seed_obs.title or retailer_url
    provisional["attributes"] = catalog.extract_attributes(title)
    data = _load_watchlist()
    product_id = catalog.product_id_for(title, retailer_url, (p["id"] for p in data["products"]))
    product = {
        "id": product_id,
        "name": title,
        "target": target,
        "tier": tier,
        "notes": "",
        "rejected_candidate_urls": [],
        "listings": [provisional],
    }

    confirmed_urls = {provisional["url"]}
    rejected_urls = set()
    for adapter, source_url in resolved:
        try:
            candidates = adapter.discover(source_url, session)
        except SourceError as exc:
            print(f"  [{adapter.PROVIDER}] discover {exc.kind}: {exc.message}")
            continue
        for candidate in candidates:
            try:
                candidate_url = catalog.normalize_url(candidate["url"])
            except (KeyError, ValueError):
                continue
            if candidate_url in confirmed_urls or candidate_url in rejected_urls:
                continue
            candidate_listing = {
                "id": catalog.listing_id_for(candidate_url),
                "retailer": catalog.retailer_hostname(candidate_url),
                "url": candidate_url,
                "confirmed_by": "pending",
                "attributes": {},
                "source_urls": {},
            }
            candidate_title = candidate.get("title") or ""
            for candidate_adapter in ADAPTERS:
                try:
                    candidate_source = candidate_adapter.resolve(candidate_url, session)
                    if not candidate_source:
                        continue
                    candidate_observation = candidate_adapter.fetch(
                        candidate_source, candidate_listing, session
                    )
                except SourceError as exc:
                    print(
                        f"  [{candidate_adapter.PROVIDER}] candidate {exc.kind}: "
                        f"{exc.message}"
                    )
                    continue
                candidate_listing["source_urls"][candidate_adapter.PROVIDER] = candidate_source
                if not candidate_title and candidate_observation.title:
                    candidate_title = candidate_observation.title
            if not candidate_listing["source_urls"]:
                continue

            candidate_attrs = {
                **catalog.extract_attributes(candidate_title),
                **(candidate.get("attributes") or {}),
            }
            candidate_listing["attributes"] = candidate_attrs
            decision = catalog.match_candidate(provisional["attributes"], candidate_attrs)
            if decision == "reject":
                rejected_urls.add(candidate_url)
                continue
            if decision == "confirm":
                print("\nCandidate counterpart:")
                print(f"  Retailer: {candidate_listing['retailer']}")
                print(f"  Title: {candidate_title or 'Unknown'}")
                print(f"  URL: {candidate_url}")
                print(
                    "  Attributes: "
                    + json.dumps(candidate_attrs, ensure_ascii=False, sort_keys=True)
                )
                if confirm("Add this as the same product? [y/N] ").strip().lower() != "y":
                    rejected_urls.add(candidate_url)
                    continue

            candidate_listing["confirmed_by"] = "auto" if decision == "accept" else "user"
            product["listings"].append(candidate_listing)
            confirmed_urls.add(candidate_url)

    product["rejected_candidate_urls"] = sorted(rejected_urls)
    proposed = {"schema_version": 2, "products": [product]}
    print(json.dumps(proposed, indent=2, ensure_ascii=False))
    return proposed


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("retailer_url")
    parser.add_argument("--target", type=float)
    parser.add_argument("--tier", choices=("hot", "warm", "cold"), default="warm")
    args = parser.parse_args(argv)
    try:
        proposed = build_product(args.retailer_url, args.target, args.tier)
        if input("Write this change to watchlist.json? [y/N] ").strip().lower() != "y":
            print("No changes written.")
            return 0
        data = _load_watchlist()
        data["products"].extend(proposed["products"])
        catalog.write_watchlist(WATCHLIST_PATH, data)
        print(f"Wrote {proposed['products'][0]['id']} to {WATCHLIST_PATH}")
        return 0
    except (KeyboardInterrupt, EOFError):
        print("\nNo changes written.")
        return 1
    except (RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
