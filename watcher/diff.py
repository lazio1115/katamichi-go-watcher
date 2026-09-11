"""Difference detection between the previous state and the current scrape."""

from __future__ import annotations

from dataclasses import dataclass

from .scraper import Listing
from .store import now_iso


@dataclass
class DiffResult:
    new: list[Listing]
    removed: list[Listing]
    existing: list[Listing]
    merged: dict[str, Listing]


def compute(previous: dict[str, Listing], current: list[Listing]) -> DiffResult:
    stamp = now_iso()
    new: list[Listing] = []
    existing: list[Listing] = []
    merged: dict[str, Listing] = {}

    for listing in current:
        before = previous.get(listing.key)
        if before is None:
            listing.first_seen = stamp
            listing.last_seen = stamp
            new.append(listing)
        else:
            listing.first_seen = before.first_seen or stamp
            listing.last_seen = stamp
            listing.notified = before.notified
            existing.append(listing)
        merged[listing.key] = listing

    removed = [v for k, v in previous.items() if k not in merged]
    return DiffResult(new=new, removed=removed, existing=existing, merged=merged)
