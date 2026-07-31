"""Fetch current price/availability for an Amazon.in product page.

Strategy: rotate realistic desktop+mobile headers, retry with backoff, and
parse several selector families because Amazon A/B-tests its price markup.
Returns None on a hard block so the caller can just skip this cycle -- with
48 cycles a day, missing a few is harmless.
"""
import random
import re
import time

import requests
from bs4 import BeautifulSoup

UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
]

PRICE_SELECTORS = [
    "#corePriceDisplay_desktop_feature_div .a-price .a-offscreen",
    "#corePrice_feature_div .a-price .a-offscreen",
    "#corePrice_desktop .a-price .a-offscreen",
    "#priceblock_ourprice",
    "#priceblock_dealprice",
    ".a-price .a-offscreen",
]

MRP_SELECTORS = [
    ".basisPrice .a-price .a-offscreen",
    "#corePriceDisplay_desktop_feature_div .a-text-price .a-offscreen",
    ".priceBlockStrikePriceString",
]


def _headers():
    return {
        "User-Agent": random.choice(UAS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-IN,en-GB;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "DNT": "1",
    }


def _money(text):
    if not text:
        return None
    m = re.search(r"([\d,]+(?:\.\d{1,2})?)", text.replace("₹", "").strip())
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def _first(soup, selectors):
    for sel in selectors:
        el = soup.select_one(sel)
        if el:
            val = _money(el.get_text())
            if val:
                return val
    return None


def fetch(asin, session=None, attempts=3):
    """Return a dict of observed fields, or None if blocked/unparseable."""
    sess = session or requests.Session()
    url = f"https://www.amazon.in/dp/{asin}?psc=1"

    for i in range(attempts):
        try:
            r = sess.get(url, headers=_headers(), timeout=25)
        except requests.RequestException:
            time.sleep(3 + i * 4)
            continue

        if r.status_code != 200 or "captcha" in r.text[:4000].lower():
            time.sleep(4 + i * 6 + random.random() * 3)
            continue

        soup = BeautifulSoup(r.text, "lxml")
        price = _first(soup, PRICE_SELECTORS)
        if price is None:
            time.sleep(3 + i * 4)
            continue

        title_el = soup.select_one("#productTitle")
        avail_el = soup.select_one("#availability")
        seller_el = soup.select_one("#sellerProfileTriggerId") or soup.select_one(
            "#merchant-info"
        )
        ship_el = soup.select_one("#fulfillerInfoFeature_feature_div .offer-display-feature-text-message")

        avail = (avail_el.get_text(strip=True) if avail_el else "").lower()

        return {
            "asin": asin,
            "price": price,
            "mrp": _first(soup, MRP_SELECTORS),
            "title": title_el.get_text(strip=True) if title_el else None,
            "in_stock": ("in stock" in avail) or (avail == ""),
            "availability": avail[:120],
            "seller": (seller_el.get_text(strip=True)[:80] if seller_el else None),
            "shipper": (ship_el.get_text(strip=True)[:60] if ship_el else None),
        }

    return None


# ---------------------------------------------------------------------------
# Price-history-site source (primary).
#
# Amazon blocks datacenter IPs, which is fatal for a GitHub Actions runner.
# pricehistory.app server-renders everything we need into one meta tag and does
# not block datacenter traffic, so we parse that instead. Bonus: it hands us the
# lifetime low/avg/high immediately, so buy-zone logic works from the first run
# instead of waiting for us to accumulate our own history.
# ---------------------------------------------------------------------------

PH_FIELDS = {
    "low": r"Lowest Price:\s*\u20b9\s*([\d,]+(?:\.\d+)?)",
    "avg": r"Average Price:\s*\u20b9\s*([\d,]+(?:\.\d+)?)",
    "high": r"Highest Price:\s*\u20b9\s*([\d,]+(?:\.\d+)?)",
    "mrp": r"MRP:\s*\u20b9\s*([\d,]+(?:\.\d+)?)",
    "price": r"Price in India on [^:]*:\s*\u20b9\s*([\d,]+(?:\.\d+)?)",
}


def _num(m):
    return float(m.group(1).replace(",", "")) if m else None


def fetch_pricehistory(ph_url, asin=None, session=None, attempts=3):
    """Parse a pricehistory.app product page. Returns obs dict or None."""
    sess = session or requests.Session()

    for i in range(attempts):
        try:
            r = sess.get(ph_url, headers=_headers(), timeout=25)
        except requests.RequestException as e:
            print(f"    [ph] attempt {i+1}: network error {e.__class__.__name__}: {e}")
            time.sleep(3 + i * 4)
            continue
        if r.status_code != 200:
            print(f"    [ph] attempt {i+1}: HTTP {r.status_code}, body starts: "
                  f"{r.text[:160]!r}")
            time.sleep(3 + i * 4)
            continue

        soup = BeautifulSoup(r.text, "lxml")
        meta = soup.find("meta", attrs={"name": "description"}) or soup.find(
            "meta", attrs={"property": "og:description"}
        )
        desc = meta.get("content", "") if meta else ""

        vals = {k: _num(re.search(p, desc)) for k, p in PH_FIELDS.items()}
        if not vals["price"]:
            print(f"    [ph] attempt {i+1}: HTTP 200 but price not parsed. "
                  f"len={len(r.text)} desc={desc[:200]!r}")
            time.sleep(3 + i * 4)
            continue

        title_el = soup.find("meta", attrs={"property": "og:title"})
        title = title_el.get("content", "").replace(" - Price History", "") if title_el else None

        # Site reports the last price it saw; absent an explicit stock signal we
        # assume in stock and let Amazon's own page correct it if ever consulted.
        return {
            "asin": asin,
            "price": vals["price"],
            "mrp": vals["mrp"],
            "title": title,
            "in_stock": True,
            "availability": "",
            "seller": None,
            "shipper": None,
            "site_low": vals["low"],
            "site_avg": vals["avg"],
            "site_high": vals["high"],
            "source": "pricehistory",
        }

    return None
