"""Fetch and parse the 片道GO! listing page."""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass

import requests
from bs4 import BeautifulSoup

from .normalize import (
    make_key,
    normalize,
    parse_period,
    split_car,
    split_shop,
    strip_parens,
)

log = logging.getLogger(__name__)


@dataclass
class Listing:
    depart_company: str = ""
    depart_shop: str = ""
    depart_pref: str = ""
    return_company: str = ""
    return_shop: str = ""
    car_model: str = ""
    car_number: str = ""
    conditions: str = ""
    period_start: str = ""
    period_end: str = ""
    tel_label: str = ""
    tel: str = ""
    # The site marks closed listings with a CSS overlay reading 受付終了.
    is_closed: bool = False
    key: str = ""
    first_seen: str = ""
    last_seen: str = ""
    notified: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Listing":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})


class ScrapeError(RuntimeError):
    pass


def fetch(url: str, user_agent: str, timeout: int, retries: int, backoff: int) -> str:
    last: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            res = requests.get(url, headers={"User-Agent": user_agent}, timeout=timeout)
            res.raise_for_status()
            res.encoding = res.apparent_encoding or "utf-8"
            return res.text
        except Exception as exc:  # noqa: BLE001 - retried and re-raised below
            last = exc
            log.warning("fetch attempt %d/%d failed: %s", attempt, retries, exc)
            if attempt < retries:
                time.sleep(backoff * (2 ** (attempt - 1)))
    raise ScrapeError(f"failed to fetch {url} after {retries} attempts: {last}")


def _value_p(container) -> str:
    """Return the text of the value <p>, skipping the mobile-only label <p>."""
    if container is None:
        return ""
    for p in container.find_all("p"):
        if "label-sp" in (p.get("class") or []):
            continue
        return p.get_text(" ", strip=True)
    return container.get_text(" ", strip=True)


def _shop_parts(container) -> tuple[str, str]:
    """Split a shop block into (main text, parenthesised note)."""
    if container is None:
        return "", ""
    note = ""
    for p in container.find_all("p"):
        if "label-sp" in (p.get("class") or []):
            continue
        small = p.find("small")
        if small:
            note = strip_parens(small.get_text(" ", strip=True))
            small.extract()
        return p.get_text(" ", strip=True), note
    return "", ""


def parse(html: str) -> tuple[list[Listing], int]:
    """Parse every listing and dedupe by key.

    The page renders two <ul> lists (``#service-items-shop-type-start`` and
    ``#service-items-shop-type-return``) holding the same listings in different
    order, so every listing appears exactly twice.

    Returns (deduped listings, number of unparsable rows skipped).
    """
    soup = BeautifulSoup(html, "lxml")
    by_key: dict[str, Listing] = {}
    skipped = 0

    for li in soup.select("li.service-item"):
        if "no-data" in (li.get("class") or []):
            continue
        try:
            listing = _parse_item(li)
        except Exception as exc:  # noqa: BLE001 - one bad row must not kill the run
            skipped += 1
            log.warning("skipped unparsable listing: %s", exc)
            continue
        if not listing.key:
            skipped += 1
            continue
        by_key.setdefault(listing.key, listing)

    return list(by_key.values()), skipped


def _parse_item(li) -> Listing:
    body = li.select_one(".service-item__body")
    is_closed = bool(body) and "show-entry-end" in (body.get("class") or [])

    depart_text, depart_pref = _shop_parts(li.select_one(".service-item__shop-start"))
    return_text, _ = _shop_parts(li.select_one(".service-item__shop-return"))

    depart_company, depart_shop = split_shop(depart_text)
    return_company, return_shop = split_shop(return_text)

    period_start, period_end = parse_period(_value_p(li.select_one(".service-item__date")))
    car_model, car_number = split_car(_value_p(li.select_one(".service-item__info__car-type")))

    conditions = normalize(_value_p(li.select_one(".service-item__info__condition")))
    tel_label = normalize(_text(li.select_one(".service-item__reserve-shop")))
    tel = normalize(_text(li.select_one(".service-item__reserve-tel")))

    listing = Listing(
        depart_company=depart_company,
        depart_shop=depart_shop,
        depart_pref=depart_pref,
        return_company=return_company,
        return_shop=return_shop,
        car_model=car_model,
        car_number=car_number,
        conditions=conditions,
        period_start=period_start,
        period_end=period_end,
        tel_label=tel_label,
        tel=tel,
        is_closed=is_closed,
    )
    listing.key = make_key(
        listing.depart_company,
        listing.depart_shop,
        listing.return_company,
        listing.car_model,
        listing.car_number,
        listing.period_start,
        listing.period_end,
    )
    return listing


def _text(node) -> str:
    return node.get_text(" ", strip=True) if node else ""
