"""Shared provider contracts."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


SOURCE_ERROR_KINDS = {
    "network",
    "blocked",
    "http",
    "parse",
    "identity",
    "stale",
    "unsupported",
}


class SourceError(Exception):
    """A deterministic provider failure that the orchestrator can classify."""

    def __init__(self, provider: str, kind: str, message: str):
        if kind not in SOURCE_ERROR_KINDS:
            raise ValueError(f"unsupported source error kind: {kind}")
        self.provider = provider
        self.kind = kind
        self.message = message
        super().__init__(f"{provider} [{kind}]: {message}")


@dataclass(frozen=True)
class Observation:
    """One validated price observation from one provider listing."""

    listing_id: str
    price: float
    mrp: Optional[float]
    currency: str
    in_stock: bool
    title: Optional[str]
    seller: Optional[str]
    retailer: str
    listing_url: str
    source: str
    source_url: str
    fetched_ts: datetime
    observed_ts: Optional[datetime]
    site_low: Optional[float]
    site_avg: Optional[float]
    site_high: Optional[float]
    history: Optional[tuple] = None
