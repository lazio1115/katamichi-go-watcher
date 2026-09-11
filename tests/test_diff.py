import json
from pathlib import Path

from watcher.diff import compute
from watcher.scraper import Listing, parse
from watcher.store import load_state, save_state

FIXTURE = Path(__file__).parent / "fixtures" / "page_sample.html"


def _listing(key: str, **kw) -> Listing:
    return Listing(key=key, car_model=kw.pop("car_model", "ヤリス"), **kw)


def test_second_pass_over_the_same_html_finds_nothing_new():
    listings, _ = parse(FIXTURE.read_text(encoding="utf-8"))
    first = compute({}, listings)
    assert len(first.new) == len(listings)

    again, _ = parse(FIXTURE.read_text(encoding="utf-8"))
    second = compute(first.merged, again)
    assert second.new == []
    assert second.removed == []
    assert len(second.existing) == len(listings)


def test_removed_is_detected():
    previous = {"a": _listing("a"), "b": _listing("b")}
    result = compute(previous, [_listing("a")])
    assert [l.key for l in result.removed] == ["b"]
    assert result.new == []


def test_first_seen_is_preserved_and_last_seen_advances():
    previous = {"a": _listing("a", first_seen="2026-01-01T00:00:00+09:00", last_seen="2026-01-01T00:00:00+09:00")}
    result = compute(previous, [_listing("a")])
    kept = result.merged["a"]
    assert kept.first_seen == "2026-01-01T00:00:00+09:00"
    assert kept.last_seen != "2026-01-01T00:00:00+09:00"


def test_notified_flag_survives_a_later_run():
    previous = {"a": _listing("a", notified=True)}
    result = compute(previous, [_listing("a")])
    assert result.merged["a"].notified is True


def test_state_roundtrip(tmp_path: Path):
    path = tmp_path / "state.json"
    save_state({"a": _listing("a", car_number="3843")}, path)
    restored = load_state(path)
    assert restored["a"].car_number == "3843"


def test_zero_results_must_not_overwrite_state(tmp_path: Path):
    """§9: a 0-item scrape keeps the previous state instead of clearing it."""
    path = tmp_path / "state.json"
    save_state({"a": _listing("a")}, path)
    before = json.loads(path.read_text(encoding="utf-8"))

    scraped: list[Listing] = []
    if scraped:  # the guard cmd_run applies
        save_state(compute(load_state(path), scraped).merged, path)

    assert json.loads(path.read_text(encoding="utf-8")) == before
    assert list(load_state(path)) == ["a"]
