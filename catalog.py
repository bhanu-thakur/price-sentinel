"""Catalog, URL normalization, identity matching, and migration helpers."""

import hashlib
import json
import re
import unicodedata
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


SCHEMA_VERSION = 2
TRACKING_QUERY_KEYS = {
    "camp",
    "creative",
    "creativeasin",
    "ref",
    "ref_",
    "referrer",
    "tag",
    "qid",
    "sprefix",
    "sr",
}
IDENTIFIER_KEYS = {"model", "part_number", "gtin", "ean", "upc", "isbn"}
VARIANT_KEYS = {
    "storage",
    "memory",
    "capacity",
    "size",
    "pack_count",
    "generation",
    "colour",
    "color",
}
MARKETING_WORDS = {
    "official",
    "original",
    "new",
    "best",
    "deal",
    "sale",
    "buy",
    "online",
}


def normalize_url(value):
    """Return a canonical HTTPS URL with tracking parameters removed."""
    if not isinstance(value, str):
        raise ValueError("URL must be a string")
    parsed = urlsplit(value.strip())
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("URL must be an http(s) URL")
    if parsed.username or parsed.password:
        raise ValueError("URL credentials are not supported")

    hostname = parsed.hostname.lower().removeprefix("www.")
    path = parsed.path or "/"
    query = []
    for key, item in parse_qsl(parsed.query, keep_blank_values=True):
        lowered = key.lower()
        if lowered.startswith("utm_") or lowered in TRACKING_QUERY_KEYS:
            continue
        query.append((key, item))
    query.sort()

    # Amazon exposes one ASIN through many title, /dp/, /gp/product/, and /ref=
    # paths. Canonicalize those forms to the retailer identity so intake cannot
    # propose or persist the same listing twice under different URLs.
    if hostname == "amazon.in":
        amazon = re.search(r"/(?:dp|gp/product)/([A-Za-z0-9]{10})(?:[/?]|$)", path)
        if amazon:
            path = f"/dp/{amazon.group(1).upper()}"
            query = []
    return urlunsplit(("https", hostname, path, urlencode(query), ""))


def retailer_hostname(url):
    return urlsplit(normalize_url(url)).hostname


def normalize_identity_text(value):
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    words = [word for word in text.split() if word not in MARKETING_WORDS]
    return " ".join(words)


def slugify_title(title):
    text = unicodedata.normalize("NFKC", str(title or "")).casefold()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "product"


def product_id_for(title, seed_url, existing_ids=()):
    """Create the stable product ID required by schema v2."""
    base = slugify_title(title)
    existing = set(existing_ids)
    if base in existing:
        digest = hashlib.sha256(normalize_url(seed_url).encode("utf-8")).hexdigest()[:8]
        base = f"{base}-{digest}"
    return base


def retailer_product_id(url):
    """Extract a retailer product identifier when the URL exposes one."""
    parsed = urlsplit(normalize_url(url))
    amazon = re.search(r"/(?:dp|gp/product)/([A-Za-z0-9]{10})(?:[/?]|$)", parsed.path)
    if amazon:
        return amazon.group(1).lower()
    query = dict(parse_qsl(parsed.query))
    if query.get("pid"):
        return query["pid"].lower()
    return None


def listing_id_for(url):
    normalized = normalize_url(url)
    host = retailer_hostname(normalized).replace(".", "-")
    provider_id = retailer_product_id(normalized)
    if provider_id:
        return f"{host}-{provider_id}"
    path_slug = slugify_title(urlsplit(normalized).path)[:80]
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:8]
    return f"{host}-{path_slug}-{digest}".strip("-")


def listing_identity(url):
    """Return a stable retailer-scoped identity suitable for deduplication."""
    normalized = normalize_url(url)
    return retailer_hostname(normalized), retailer_product_id(normalized) or normalized


def extract_attributes(title):
    """Extract conservative identity attributes from a provider title."""
    title = str(title or "").strip()
    attrs = {}
    words = re.findall(r"[A-Za-z][A-Za-z0-9+&'-]*", title)
    if words:
        attrs["brand"] = words[0]

    patterns = {
        "storage": r"\b\d+(?:\.\d+)?\s*(?:gb|tb|mb)\b",
        "memory": r"\b\d+(?:\.\d+)?\s*gb\s*(?:ram|memory)\b",
        "capacity": r"\b\d+(?:\.\d+)?\s*(?:mah|ml|l|kg|g|w)\b",
        "size": r"\b\d+(?:\.\d+)?\s*(?:inch|in|cm|mm)\b",
        "pack_count": r"\b(?:pack\s+of|set\s+of)\s*\d+\b",
        "generation": r"\b(?:\d+(?:st|nd|rd|th)\s+gen|generation\s*\d+)\b",
        "colour": r"\b(?:black|white|blue|red|green|grey|gray|silver|gold|pink|purple)\b",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, title, re.I)
        if match:
            attrs[key] = match.group(0)

    model_tokens = [
        token
        for token in re.findall(r"\b[A-Za-z0-9][A-Za-z0-9-]{2,}\b", title)
        if any(char.isdigit() for char in token)
    ]
    if model_tokens:
        attrs["model"] = model_tokens[0]
    return attrs


def normalize_attributes(attributes):
    result = {}
    for key, value in (attributes or {}).items():
        if value is None or value == "":
            continue
        if isinstance(value, (int, float)):
            value = str(value)
        result[str(key).lower()] = normalize_identity_text(value)
    return result


def match_candidate(seed_attributes, candidate_attributes):
    """Return ``accept``, ``reject``, or ``confirm`` using exact identity rules."""
    seed = normalize_attributes(seed_attributes)
    candidate = normalize_attributes(candidate_attributes)

    shared_identifiers = IDENTIFIER_KEYS & seed.keys() & candidate.keys()
    for key in shared_identifiers:
        if seed[key] != candidate[key]:
            return "reject"

    # The extractor's brand is deliberately heuristic (often the title's first
    # word). A cross-retailer title may lead with "Original" or a category name,
    # so a brand mismatch requires human confirmation rather than silent rejection.
    if not seed.get("brand") or not candidate.get("brand"):
        return "confirm"
    if seed["brand"] != candidate["brand"]:
        return "confirm"
    if not shared_identifiers:
        return "confirm"

    if any(key in seed.keys() ^ candidate.keys() for key in IDENTIFIER_KEYS):
        return "confirm"

    for key in VARIANT_KEYS:
        left, right = seed.get(key), candidate.get(key)
        if left and right and left != right:
            return "reject"
        if bool(left) != bool(right):
            return "confirm"
    return "accept"


def validate_watchlist(data):
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("watchlist must use schema version 2")
    if not isinstance(data.get("products"), list):
        raise ValueError("watchlist products must be a list")
    listing_ids = set()
    listing_identities = set()
    for product in data["products"]:
        for key in ("id", "name", "rejected_candidate_urls", "listings"):
            if key not in product:
                raise ValueError(f"product missing {key}")
        for listing in product["listings"]:
            for key in ("id", "retailer", "url", "confirmed_by", "attributes", "source_urls"):
                if key not in listing:
                    raise ValueError(f"listing missing {key}")
            if not re.fullmatch(r"[a-z0-9-]+", listing["id"]):
                raise ValueError(f"invalid listing ID: {listing['id']}")
            normalized = normalize_url(listing["url"])
            if listing["retailer"] != retailer_hostname(normalized):
                raise ValueError(f"listing retailer does not match URL: {listing['id']}")
            if listing["id"] != listing_id_for(normalized):
                raise ValueError(f"listing ID does not match URL identity: {listing['id']}")
            identity = listing_identity(normalized)
            if listing["id"] in listing_ids or identity in listing_identities:
                raise ValueError(f"duplicate retailer listing: {listing['id']}")
            listing_ids.add(listing["id"])
            listing_identities.add(identity)
        rejected = {listing_identity(url) for url in product["rejected_candidate_urls"]}
        confirmed = {listing_identity(listing["url"]) for listing in product["listings"]}
        if rejected & confirmed:
            raise ValueError(f"confirmed listing is also rejected: {product['id']}")
    return data


def write_watchlist(path, data):
    validate_watchlist(data)
    Path(path).write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def migrate_legacy_state(old_state, product_id, listing_id, auto_tier="warm"):
    """Convert the legacy single-ASIN state record once, preserving its values."""
    legacy = old_state.get("B0GSVFV3R4", {})
    listing = {
        "consecutive_failures": legacy.get("consecutive_failures", 0),
        "last_checked_ts": legacy.get("last_checked_ts"),
        "last_success_ts": legacy.get("last_success_ts") or legacy.get("last_checked_ts"),
        "last_price": legacy.get("last_price"),
        "last_score": legacy.get("last_score"),
        "site_avg": legacy.get("site_avg"),
        "site_high": legacy.get("site_high"),
        "site_low": legacy.get("site_low"),
        "last_source": legacy.get("last_source", "pricehistory.app"),
    }
    product = {
        "auto_tier": legacy.get("auto_tier", auto_tier),
        "last_verdict": None,
    }
    if legacy.get("last_alert_ts"):
        product["last_alert_ts"] = legacy["last_alert_ts"]
    if legacy.get("last_alert_price") is not None:
        product["last_alert_price"] = legacy["last_alert_price"]
    return {
        "schema_version": SCHEMA_VERSION,
        "providers": {},
        "products": {product_id: product},
        "listings": {listing_id: listing},
    }
