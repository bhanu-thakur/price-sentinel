"""Sequential provider orchestration with bounded fallback and circuit breakers."""

import math
import random
import re
import time
from datetime import datetime, timedelta, timezone

import requests

from providers import buyhatke, pricehistory_app
from providers.base import Observation, SourceError


PROVIDER_PRIORITY = ("pricehistory.app", "buyhatke.com", "pricehistoryapp.com")
PROVIDER_ADAPTERS = {
    pricehistory_app.PROVIDER: pricehistory_app,
    buyhatke.PROVIDER: buyhatke,
}
_last_request_at = None


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


def _wait_for_request():
    """Enforce the 4–11 second inter-request gap without delaying the first call."""
    global _last_request_at
    now = time.monotonic()
    if _last_request_at is not None:
        wait = random.uniform(4, 11) - (now - _last_request_at)
        if wait > 0:
            time.sleep(wait)
    _last_request_at = time.monotonic()


def _status_from_error(error):
    match = re.search(r"\bHTTP\s+(\d{3})\b", error.message, re.I)
    return int(match.group(1)) if match else None


def _provider_record(provider_state, provider):
    return provider_state.setdefault(
        provider,
        {"consecutive_failures": 0, "disabled_until": None, "last_error": None},
    )


def _validate_observation(observation, listing, provider, source_url, now):
    if not isinstance(observation, Observation):
        raise SourceError(provider, "parse", "adapter returned an invalid observation")
    if observation.listing_id != listing.get("id"):
        raise SourceError(provider, "identity", "observation listing ID does not match")
    if observation.source != provider or observation.source_url != source_url:
        raise SourceError(provider, "identity", "observation source does not match requested source")
    if not math.isfinite(observation.price) or observation.price <= 0:
        raise SourceError(provider, "parse", "price must be finite and greater than zero")
    if observation.currency != "INR":
        raise SourceError(provider, "parse", "only INR observations are supported")
    expected_retailer = (listing.get("retailer") or "").lower().removeprefix("www.")
    if observation.retailer != expected_retailer:
        raise SourceError(provider, "identity", "observation retailer does not match listing")
    if observation.observed_ts and now - observation.observed_ts > timedelta(hours=48):
        raise SourceError(provider, "stale", "observation is more than 48 hours old")
    return observation


def _record_failure(provider_state, provider, error, now):
    record = _provider_record(provider_state, provider)
    status = _status_from_error(error)
    record["last_error"] = f"{error.kind}: {error.message}"
    if status in (403, 429) or error.kind == "blocked":
        record["disabled_until"] = _iso(now + timedelta(hours=6))
    elif status == 404:
        return "invalid_source"
    elif error.kind in {"network", "http", "parse", "identity", "stale"}:
        record["consecutive_failures"] = record.get("consecutive_failures", 0) + 1
        if record["consecutive_failures"] >= 3:
            record["disabled_until"] = _iso(now + timedelta(hours=3))
    return None


def fetch_listing(listing, provider_state, session=None, now=None):
    """Return ``(Observation | None, updated_provider_state, attempts_log)``."""
    session = session or requests.Session()
    now = now or datetime.now(timezone.utc)
    provider_state = provider_state if provider_state is not None else {}
    source_urls = listing.get("source_urls") or {}
    attempts = []

    for provider in PROVIDER_PRIORITY:
        source_url = source_urls.get(provider)
        if not source_url:
            continue
        adapter = PROVIDER_ADAPTERS.get(provider)
        if adapter is None:
            attempts.append({"provider": provider, "status": "skipped", "reason": "unsupported"})
            continue

        record = _provider_record(provider_state, provider)
        disabled_until = _parse_ts(record.get("disabled_until"))
        if disabled_until and disabled_until > now:
            attempts.append({
                "provider": provider,
                "status": "skipped",
                "reason": "disabled",
                "disabled_until": record["disabled_until"],
            })
            continue
        if disabled_until and disabled_until <= now:
            record["disabled_until"] = None

        _wait_for_request()
        try:
            observation = adapter.fetch(source_url, listing, session, now=now)
            observation = _validate_observation(observation, listing, provider, source_url, now)
        except SourceError as error:
            invalid = _record_failure(provider_state, provider, error, now)
            attempt = {
                "provider": provider,
                "status": "failed",
                "kind": error.kind,
                "message": error.message,
            }
            if invalid == "invalid_source":
                listing.setdefault("source_urls", {}).pop(provider, None)
                attempt["source_invalid"] = True
            attempts.append(attempt)
            continue
        except requests.RequestException as error:
            source_error = SourceError(provider, "network", str(error))
            _record_failure(provider_state, provider, source_error, now)
            attempts.append({
                "provider": provider,
                "status": "failed",
                "kind": "network",
                "message": str(error),
            })
            continue

        record["consecutive_failures"] = 0
        record["last_error"] = None
        if record.get("disabled_until") and _parse_ts(record["disabled_until"]) <= now:
            record["disabled_until"] = None
        attempts.append({"provider": provider, "status": "success"})
        return observation, provider_state, attempts

    return None, provider_state, attempts
