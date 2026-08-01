"""Adapter for BuyHatke's public, server-rendered product pages."""

import html
import math
import re
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

from .base import Observation, SourceError


PROVIDER = "buyhatke.com"
BASE_URL = "https://www.buyhatke.com"
FETCH_TIMEOUT = 60
_RETAILER_NAMES = {
    "amazon": "amazon.in",
    "flipkart": "flipkart.com",
    "myntra": "myntra.com",
    "vijay sales": "vijaysales.com",
    "reliance digital": "reliancedigital.in",
}
_EXCLUDED_HOSTS = {
    "buyhatke.com",
    "redirect.buyhatke.com",
    "compare.buyhatke.com",
}


def _number(value):
    if value is None:
        return None
    try:
        parsed = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) and parsed > 0 else None


def _field(fragment, name):
    quoted = re.search(
        rf"\b{re.escape(name)}\s*:\s*\"((?:\\.|[^\"\\])*)\"",
        fragment,
    )
    if quoted:
        return html.unescape(quoted.group(1))
    match = re.search(rf"\b{re.escape(name)}\s*:\s*([^,}}]+)", fragment)
    if not match:
        return None
    value = match.group(1).strip()
    if value.startswith(("\"", "'")) and value[-1:] == value[0]:
        return html.unescape(value[1:-1])
    return value


def _product_fragment(body):
    match = re.search(r"productData:\{(?P<fragment>.*?)\},predictedData:", body, re.S)
    return match.group("fragment") if match else None


def _retailer_from_name(name):
    if not name:
        return None
    lowered = name.strip().lower()
    return _RETAILER_NAMES.get(lowered, lowered.removeprefix("www."))


def _listing_retailer(listing):
    return (listing.get("retailer") or "").lower().removeprefix("www.")


def _retailer_product_id(listing):
    parsed = urlparse(listing.get("url") or "")
    path_match = re.search(r"/(?:dp|gp/product)/([A-Za-z0-9]{10})(?:[/?]|$)", parsed.path)
    if path_match:
        return path_match.group(1).upper()
    query_id = parse_qs(parsed.query).get("pid", [None])[0]
    return query_id.upper() if query_id else None


def _canonical(soup):
    tag = soup.find("link", rel=lambda value: value and "canonical" in value)
    if tag and tag.get("href"):
        return tag["href"].strip()
    for attrs in ({"property": "og:url"}, {"name": "og:url"}):
        tag = soup.find("meta", attrs=attrs)
        if tag and tag.get("content"):
            return tag["content"].strip()
    return None


def _parse(source_url, listing, body, now):
    soup = BeautifulSoup(body, "lxml")
    fragment = _product_fragment(body)
    if not fragment:
        raise SourceError(PROVIDER, "parse", "server-rendered product data is missing")

    price = _number(_field(fragment, "cur_price"))
    if price is None:
        raise SourceError(PROVIDER, "parse", "current price is missing")

    retailer = _retailer_from_name(_field(fragment, "site_name"))
    expected_retailer = _listing_retailer(listing)
    if not retailer or retailer != expected_retailer:
        raise SourceError(
            PROVIDER,
            "identity",
            f"page retailer {retailer!r} does not match listing retailer {expected_retailer!r}",
        )

    page_id = (_field(fragment, "pid") or "").upper() or None
    expected_id = _retailer_product_id(listing)
    if expected_id and page_id != expected_id:
        raise SourceError(
            PROVIDER,
            "identity",
            f"page product ID {page_id!r} does not match listing product ID {expected_id!r}",
        )

    in_stock = _field(fragment, "inStock")
    title = _field(fragment, "name")
    low = _number(_field(fragment, "min"))
    average = _number(_field(fragment, "avg"))
    high = _number(_field(fragment, "maxall"))
    if low is not None and high is not None and low > high:
        low = high = None

    return Observation(
        listing_id=listing["id"],
        price=price,
        mrp=_number(_field(fragment, "mrpFloat")),
        currency="INR",
        in_stock=in_stock not in {None, "0", "false", "False"},
        title=title.strip() if title else None,
        seller=None,
        retailer=retailer,
        listing_url=listing["url"],
        source=PROVIDER,
        source_url=source_url,
        fetched_ts=now,
        observed_ts=None,
        site_low=low,
        site_avg=average,
        site_high=high,
    )


def fetch(source_url, listing, session, now=None):
    """Fetch and validate one BuyHatke product page."""
    now = now or datetime.now(timezone.utc)
    try:
        response = session.get(source_url, timeout=FETCH_TIMEOUT)
    except requests.RequestException as exc:
        raise SourceError(PROVIDER, "network", str(exc)) from exc
    if response.status_code != 200:
        kind = "blocked" if response.status_code in (403, 429) else "http"
        raise SourceError(PROVIDER, kind, f"HTTP {response.status_code}")
    return _parse(source_url, listing, getattr(response, "text", "") or "", now)


def resolve(retailer_url, session):
    """Resolve a retailer URL using BuyHatke's documented public prefix flow."""
    parsed = urlparse(retailer_url)
    if parsed.scheme != "https" or not parsed.netloc:
        return None
    host = parsed.netloc.removeprefix("www.")
    prefixed = urlunparse(("https", host, parsed.path, parsed.params, parsed.query, ""))
    request_url = f"{BASE_URL}/{urlunparse(urlparse(prefixed)).removeprefix('https://')}"
    try:
        response = session.get(request_url, timeout=25)
    except requests.RequestException as exc:
        raise SourceError(PROVIDER, "network", str(exc)) from exc
    if response.status_code != 200:
        kind = "blocked" if response.status_code in (403, 429) else "http"
        raise SourceError(PROVIDER, kind, f"HTTP {response.status_code}")
    canonical = _canonical(BeautifulSoup(getattr(response, "text", "") or "", "lxml"))
    if not canonical:
        return None
    parsed_canonical = urlparse(canonical)
    if parsed_canonical.netloc.lower().removeprefix("www.") != "buyhatke.com":
        return None
    if parsed_canonical.path in {"", "/"}:
        return None
    return canonical


def discover(source_url, session):
    """Return direct retailer links present in the public comparison data."""
    try:
        response = session.get(source_url, timeout=25)
    except requests.RequestException as exc:
        raise SourceError(PROVIDER, "network", str(exc)) from exc
    if response.status_code != 200:
        kind = "blocked" if response.status_code in (403, 429) else "http"
        raise SourceError(PROVIDER, kind, f"HTTP {response.status_code}")

    body = html.unescape(getattr(response, "text", "") or "")
    candidates = []
    seen = set()
    for match in re.finditer(r"\blink:\s*\"(https?://[^\"]+)\"", body):
        url = match.group(1)
        parsed = urlparse(url)
        host = parsed.netloc.lower().removeprefix("www.")
        if not host or host in _EXCLUDED_HOSTS or url in seen:
            continue
        seen.add(url)
        candidates.append({"url": url, "retailer": host})
    return candidates
