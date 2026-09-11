from pathlib import Path

import pytest

from watcher.scraper import parse

FIXTURE = Path(__file__).parent / "fixtures" / "page_sample.html"

# The fixture holds 276 <li>, i.e. 138 listings rendered twice (出発 list + 返却 list).
EXPECTED_UNIQUE = 138
EXPECTED_CLOSED = 105


@pytest.fixture(scope="module")
def parsed():
    return parse(FIXTURE.read_text(encoding="utf-8"))


def test_dedupes_the_two_rendered_lists(parsed):
    listings, skipped = parsed
    assert len(listings) == EXPECTED_UNIQUE
    assert skipped == 0


def test_keys_are_unique(parsed):
    listings, _ = parsed
    assert len({l.key for l in listings}) == len(listings)


def test_detects_entry_end_overlay(parsed):
    listings, _ = parsed
    assert sum(1 for l in listings if l.is_closed) == EXPECTED_CLOSED


def test_every_listing_has_the_core_fields(parsed):
    listings, _ = parsed
    for l in listings:
        # e.g. トヨタレンタリース宮城 / トヨタS&Dレンタシェア西東京
        assert l.depart_company.startswith("トヨタ")
        assert l.depart_pref
        assert l.return_company
        assert l.period_start and l.period_end
        assert l.period_start <= l.period_end
        assert l.tel
        assert l.car_model


def test_full_width_spaces_are_gone(parsed):
    listings, _ = parsed
    assert not any("　" in l.car_model for l in listings)


def test_parses_a_known_listing(parsed):
    listings, _ = parsed
    match = [
        l
        for l in listings
        if l.depart_shop == "山形駅前店" and l.car_number == "3878"
    ]
    assert len(match) == 1
    l = match[0]
    assert l.car_model == "ヤリス"
    assert l.depart_company == "トヨタレンタリース山形"
    assert l.depart_pref == "山形県 山形市"
    assert l.return_company == "トヨタレンタリース福島"
    assert l.period_start == "2026-09-07"
    assert l.period_end == "2026-09-09"
    assert l.tel == "023-625-0100"
    assert l.tel_label == "山形駅前店"
    assert l.is_closed is True


def test_empty_html_yields_nothing():
    listings, skipped = parse("<html><body></body></html>")
    assert listings == []
    assert skipped == 0
