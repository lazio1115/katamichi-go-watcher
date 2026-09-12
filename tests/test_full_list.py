"""cmd_run's notification branches, driven through a stub notifier."""

import pytest

from watcher import __main__ as m
from watcher.config import DEFAULTS
from watcher.scraper import Listing


class StubNotifier:
    def __init__(self):
        self.sent = []

    def send(self, title, body):
        self.sent.append((title, body))

    @property
    def titles(self):
        return [t for t, _ in self.sent]


def _cfg():
    return {**DEFAULTS, "filters": dict(DEFAULTS["filters"])}


def _listing(key, closed=False, **kw):
    return Listing(key=key, car_model=f"車{key}", is_closed=closed, **kw)


@pytest.fixture
def harness(monkeypatch, tmp_path):
    notifier = StubNotifier()
    saved = {}
    monkeypatch.setattr(m, "build", lambda cfg: notifier)
    monkeypatch.setattr(m.store, "save_snapshot", lambda html: None)
    monkeypatch.setattr(m.store, "load_muted", lambda: {})
    monkeypatch.setattr(m.store, "save_state", lambda merged: saved.update(merged))
    return notifier, saved


def _stub_scrape(monkeypatch, listings):
    monkeypatch.setattr(m, "_scrape", lambda cfg: (listings, 0, "<html></html>"))


def test_first_run_sends_one_digest(monkeypatch, harness):
    notifier, saved = harness
    _stub_scrape(monkeypatch, [_listing("a"), _listing("b", closed=True)])
    monkeypatch.setattr(m.store, "load_state", lambda: {})

    assert m.cmd_run(_cfg(), dry_run=False) == 0
    assert len(notifier.sent) == 1
    assert notifier.titles[0].startswith("監視を開始しました")
    assert all(l.notified for l in saved.values())


def test_steady_state_notifies_only_new_listings(monkeypatch, harness):
    notifier, saved = harness
    known = _listing("a", last_seen="2026-09-12T13:00:00+09:00", notified=True)
    _stub_scrape(monkeypatch, [_listing("a"), _listing("b")])
    monkeypatch.setattr(m.store, "load_state", lambda: {"a": known})

    assert m.cmd_run(_cfg(), dry_run=False) == 0
    assert len(notifier.sent) == 1
    assert notifier.titles[0].startswith("🚗 新規 1 件")


def test_nothing_new_sends_nothing(monkeypatch, harness):
    notifier, _ = harness
    known = _listing("a", last_seen="2026-09-12T13:00:00+09:00", notified=True)
    _stub_scrape(monkeypatch, [_listing("a")])
    monkeypatch.setattr(m.store, "load_state", lambda: {"a": known})

    assert m.cmd_run(_cfg(), dry_run=False) == 0
    assert notifier.sent == []


def test_full_list_sends_everything_bookable_on_demand(monkeypatch, harness):
    notifier, _ = harness
    known = {
        k: _listing(k, last_seen="2026-09-12T13:00:00+09:00", notified=True)
        for k in ("a", "b")
    }
    _stub_scrape(
        monkeypatch,
        [_listing("a"), _listing("b"), _listing("c", closed=True)],
    )
    monkeypatch.setattr(m.store, "load_state", lambda: known)

    assert m.cmd_run(_cfg(), dry_run=False, full_list=True) == 0
    assert len(notifier.sent) == 1
    title, body = notifier.sent[0]
    assert title == "いま予約できる車両（掲載中 2 件 / 全 3 件）"
    # The closed listing stays out of the list.
    assert body.count("🚗") == 2


def test_full_list_does_not_reset_the_baseline(monkeypatch, harness):
    """An on-demand list must not mark closed listings as already notified."""
    notifier, saved = harness
    known = {"a": _listing("a", last_seen="2026-09-12T13:00:00+09:00", notified=True)}
    _stub_scrape(monkeypatch, [_listing("a"), _listing("c", closed=True)])
    monkeypatch.setattr(m.store, "load_state", lambda: known)

    m.cmd_run(_cfg(), dry_run=False, full_list=True)
    assert saved["c"].notified is False


def test_full_list_marks_new_bookable_listings_it_showed(monkeypatch, harness):
    notifier, saved = harness
    known = {"a": _listing("a", last_seen="2026-09-12T13:00:00+09:00", notified=True)}
    _stub_scrape(monkeypatch, [_listing("a"), _listing("b")])
    monkeypatch.setattr(m.store, "load_state", lambda: known)

    m.cmd_run(_cfg(), dry_run=False, full_list=True)
    # "b" appeared in the list that was just sent, so it must not fire again.
    assert saved["b"].notified is True


def test_total_key_churn_is_refused_without_notifying(monkeypatch, harness):
    """A degraded page keeps the count but changes every key — never notify on that."""
    notifier, saved = harness
    known = {
        f"old{i}": _listing(f"old{i}", last_seen="2026-09-13T06:00:00+09:00", notified=True)
        for i in range(20)
    }
    _stub_scrape(monkeypatch, [_listing(f"new{i}") for i in range(20)])
    monkeypatch.setattr(m.store, "load_state", lambda: known)

    assert m.cmd_run(_cfg(), dry_run=False) == 1
    assert notifier.titles == ["⚠️ 構造変化の疑い"]
    assert saved == {}, "state must be kept as-is"


def test_normal_turnover_is_not_mistaken_for_churn(monkeypatch, harness):
    notifier, saved = harness
    known = {
        f"k{i}": _listing(f"k{i}", last_seen="2026-09-13T06:00:00+09:00", notified=True)
        for i in range(20)
    }
    # 16 of 20 survive, 4 drop off, 3 genuinely new — a busy but ordinary run.
    current = [_listing(f"k{i}") for i in range(16)] + [_listing(f"n{i}") for i in range(3)]
    _stub_scrape(monkeypatch, current)
    monkeypatch.setattr(m.store, "load_state", lambda: known)

    assert m.cmd_run(_cfg(), dry_run=False) == 0
    assert notifier.titles == ["🚗 新規 3 件"]


def test_churn_guard_ignores_tiny_samples(monkeypatch, harness):
    """With only a handful of listings a full turnover is plausible."""
    notifier, _ = harness
    known = {"a": _listing("a", last_seen="2026-09-13T06:00:00+09:00", notified=True)}
    _stub_scrape(monkeypatch, [_listing("b")])
    monkeypatch.setattr(m.store, "load_state", lambda: known)

    assert m.cmd_run(_cfg(), dry_run=False) == 0
    assert notifier.titles == ["🚗 新規 1 件"]


def test_cli_passes_the_flag_through(monkeypatch):
    seen = {}
    monkeypatch.setattr(m, "cmd_run", lambda cfg, dry_run, full_list: seen.update(
        dry_run=dry_run, full_list=full_list
    ) or 0)

    m.main(["run", "--dry-run", "--full-list"])
    assert seen == {"dry_run": True, "full_list": True}

    seen.clear()
    m.main(["run"])
    assert seen == {"dry_run": False, "full_list": False}
