"""Adapter for the public pricehistory.app product pages."""

import base64
import binascii
import html
import json
import math
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from .base import Observation, SourceError


PROVIDER = "pricehistory.app"
BASE_URL = "https://pricehistory.app"
_MONEY = r"(?:₹|Rs\.?|INR)?\s*([\d,]+(?:\.\d+)?)"
_RETAILER_HOSTS = {
    "amazon.in",
    "flipkart.com",
    "myntra.com",
    "tatacliq.com",
    "croma.com",
    "ajio.com",
    "snapdeal.com",
}
_RETAILER_ALIASES = {
    "amazon": "amazon.in",
    "amazon india": "amazon.in",
    "flipkart": "flipkart.com",
    "myntra": "myntra.com",
    "tata cliq": "tatacliq.com",
    "croma": "croma.com",
    "ajio": "ajio.com",
    "snapdeal": "snapdeal.com",
}


def _response_text(response):
    return getattr(response, "text", "") or ""


def _number(patterns, *texts):
    for text in texts:
        if not text:
            continue
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                try:
                    value = float(match.group(1).replace(",", ""))
                except (TypeError, ValueError):
                    continue
                if math.isfinite(value) and value > 0:
                    return value
    return None


def _meta(soup, name=None, prop=None):
    attrs = {"name": name} if name else {"property": prop}
    tag = soup.find("meta", attrs=attrs)
    return (tag.get("content") or "").strip() if tag else ""


def _retailer_from_page(text):
    match = re.search(r"Store\s+Name\s*\|\s*([a-z0-9.-]+)", text, re.I)
    if match:
        value = match.group(1).lower().removeprefix("www.")
        return _RETAILER_ALIASES.get(value, value)
    match = re.search(r"\b([a-z0-9.-]+)\s+Price in India on\b", text, re.I)
    if match:
        value = match.group(1).lower().removeprefix("www.")
        return _RETAILER_ALIASES.get(value, value)
    return None


def _listing_retailer(listing):
    return (listing.get("retailer") or "").lower().removeprefix("www.")


def _retailer_product_id(listing):
    url = listing.get("url") or ""
    parsed = urlparse(url)
    match = re.search(r"/(?:dp|gp/product)/([A-Za-z0-9]{10})(?:[/?]|$)", parsed.path)
    return match.group(1).upper() if match else None


def _page_product_id(text):
    match = re.search(
        r"Store\s+Product\s+Code\s*(?:\||:)?\s*([A-Za-z0-9-]+)",
        text,
        re.I,
    )
    return match.group(1).upper() if match else None


def _valid_lifetime(low, average, high):
    if low is not None and high is not None and low <= high:
        pass
    elif low is not None or high is not None:
        low = None
        high = None
    if average is not None and (not math.isfinite(average) or average <= 0):
        average = None
    return low, average, high


def _embedded_history(body):
    """Decode the chart series publicly embedded in a PriceHistory product page."""
    data_match = re.search(r'PagePriceHistoryDataSet\s*=\s*["\']([^"\']+)', body)
    key_match = re.search(r'CachedKey\s*=\s*["\']([^"\']+)', body)
    if not data_match or not key_match:
        return None
    try:
        encrypted = base64.b64decode(data_match.group(1), validate=True)
        key = key_match.group(1).encode("utf-8")
        payload = json.loads(bytes(value ^ key[index % len(key)] for index, value in enumerate(encrypted)))
    except (ValueError, TypeError, UnicodeError, binascii.Error, json.JSONDecodeError):
        return None

    raw_points = (payload.get("History") or {}).get("Price")
    if not isinstance(raw_points, list):
        return None
    by_date = {}
    for point in raw_points:
        if not isinstance(point, dict):
            continue
        date_value = point.get("x")
        price_value = point.get("y")
        try:
            day = datetime.fromisoformat(str(date_value)[:10]).date().isoformat()
            price = float(price_value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(price) and price > 0:
            by_date[day] = price
    return tuple((day, by_date[day]) for day in sorted(by_date)) or None


def _parse(source_url, listing, body, now):
    soup = BeautifulSoup(body, "lxml")
    description = html.unescape(_meta(soup, name="description"))
    page_text = html.unescape(soup.get_text(" ", strip=True))
    combined = " ".join(part for part in (description, page_text) if part)

    price = _number(
        [r"Price in India on [^:|]+:\s*" + _MONEY, r"Current Price\s*[:|]\s*" + _MONEY],
        description,
        page_text,
    )
    if price is None:
        raise SourceError(PROVIDER, "parse", "current price is missing")

    retailer = _retailer_from_page(combined)
    expected_retailer = _listing_retailer(listing)
    if not retailer or retailer != expected_retailer:
        raise SourceError(
            PROVIDER,
            "identity",
            f"page retailer {retailer!r} does not match listing retailer {expected_retailer!r}",
        )

    page_id = _page_product_id(combined)
    expected_id = _retailer_product_id(listing)
    if expected_id and page_id and page_id != expected_id:
        raise SourceError(
            PROVIDER,
            "identity",
            f"page product code {page_id!r} does not match listing product code {expected_id!r}",
        )
    if expected_id and not page_id:
        raise SourceError(PROVIDER, "identity", "page product code is missing")

    mrp = _number([r"MRP\s*[:|]\s*" + _MONEY], description, page_text)
    low = _number([r"Lowest(?: Ever)?(?: Price)?\s*[:|]\s*" + _MONEY], description, page_text)
    average = _number([r"Average(?: Price)?\s*[:|]\s*" + _MONEY], description, page_text)
    high = _number([r"Highest(?: Ever)?(?: Price)?\s*[:|]\s*" + _MONEY], description, page_text)
    low, average, high = _valid_lifetime(low, average, high)

    title = _meta(soup, prop="og:title") or (soup.title.get_text(strip=True) if soup.title else None)
    if title:
        title = re.sub(r"\s+-\s+Price History\s*$", "", title).strip()

    return Observation(
        listing_id=listing["id"],
        price=price,
        mrp=mrp,
        currency="INR",
        in_stock=True,
        title=title or None,
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
        history=_embedded_history(body),
    )


def fetch(source_url, listing, session, now=None):
    """Fetch and validate one pricehistory.app product page."""
    now = now or datetime.now(timezone.utc)
    try:
        response = session.get(source_url, timeout=25)
    except requests.RequestException as exc:
        raise SourceError(PROVIDER, "network", str(exc)) from exc
    if response.status_code != 200:
        kind = "blocked" if response.status_code in (403, 429) else "http"
        raise SourceError(PROVIDER, kind, f"HTTP {response.status_code}")
    return _parse(source_url, listing, _response_text(response), now)


def resolve(retailer_url, session):
    """Resolve a retailer URL through pricehistory.app's public search form."""
    try:
        response = session.post(
            f"{BASE_URL}/api/search",
            json={"url": retailer_url},
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            timeout=25,
        )
    except requests.RequestException as exc:
        raise SourceError(PROVIDER, "network", str(exc)) from exc
    if response.status_code != 200:
        kind = "blocked" if response.status_code in (403, 429) else "http"
        raise SourceError(PROVIDER, kind, f"HTTP {response.status_code}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise SourceError(PROVIDER, "parse", "resolver returned invalid JSON") from exc
    code = payload.get("code") if payload.get("status") else None
    if not isinstance(code, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", code):
        return None
    return f"{BASE_URL}/p/{code}"


def discover(source_url, session):
    """Return only direct retailer links visibly exposed on the product page."""
    try:
        response = session.get(source_url, timeout=25)
    except requests.RequestException as exc:
        raise SourceError(PROVIDER, "network", str(exc)) from exc
    if response.status_code != 200:
        kind = "blocked" if response.status_code in (403, 429) else "http"
        raise SourceError(PROVIDER, kind, f"HTTP {response.status_code}")

    soup = BeautifulSoup(_response_text(response), "lxml")
    candidates = []
    seen = set()
    for anchor in soup.find_all("a", href=True):
        parsed = urlparse(anchor["href"])
        host = parsed.netloc.lower().removeprefix("www.")
        if host not in _RETAILER_HOSTS:
            continue
        url = anchor["href"]
        if url not in seen:
            seen.add(url)
            candidates.append({"url": url, "retailer": host})
    return candidates
