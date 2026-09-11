from watcher.__main__ import _visible
from watcher.config import DEFAULTS
from watcher.scraper import Listing


def _cfg(**over) -> dict:
    cfg = {**DEFAULTS, "filters": dict(DEFAULTS["filters"])}
    cfg.update(over)
    return cfg


OPEN = Listing(key="open", car_model="ヤリス", depart_pref="宮城県 仙台市")
CLOSED = Listing(key="closed", car_model="アクア", depart_pref="山形県 山形市", is_closed=True)


def test_muted_listing_disappears():
    assert [l.key for l in _visible(_cfg(), [OPEN, CLOSED], {})] == ["open"]
    assert _visible(_cfg(), [OPEN], {"open": {"key": "open"}}) == []


def test_closed_listings_are_hidden_by_default_and_can_be_shown():
    assert [l.key for l in _visible(_cfg(), [OPEN, CLOSED], {})] == ["open"]
    shown = _visible(_cfg(skip_closed=False), [OPEN, CLOSED], {})
    assert [l.key for l in shown] == ["open", "closed"]


def test_prefecture_filter():
    cfg = _cfg()
    cfg["filters"]["depart_prefectures"] = ["山形県"]
    assert [l.key for l in _visible(cfg, [OPEN, CLOSED], {})] == []
    cfg["skip_closed"] = False
    assert [l.key for l in _visible(cfg, [OPEN, CLOSED], {})] == ["closed"]


def test_period_filter():
    cfg = _cfg()
    cfg["filters"]["period_from"] = "2026-09-10"
    early = Listing(key="early", period_start="2026-09-01", period_end="2026-09-05")
    late = Listing(key="late", period_start="2026-09-11", period_end="2026-09-15")
    assert [l.key for l in _visible(cfg, [early, late], {})] == ["late"]
