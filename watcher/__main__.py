"""CLI entry point: run / list / mute / unmute / muted."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone

from . import config as config_mod
from . import store
from .diff import compute
from .notifiers import ConsoleNotifier, build
from .scraper import Listing, ScrapeError, fetch, parse

log = logging.getLogger("watcher")

# Guard against a silent site/HTML change wiping the whole state.
COLLAPSE_RATIO = 0.8


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m watcher")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="scrape, diff and notify")
    p_run.add_argument("--dry-run", action="store_true", help="print instead of notifying")
    p_run.add_argument(
        "--full-list",
        action="store_true",
        help="send every bookable listing, not just the new ones",
    )

    sub.add_parser("list", help="show the current listings with index numbers")
    p_mute = sub.add_parser("mute", help="hide a listing (e.g. it is fully booked)")
    p_mute.add_argument("target", help="index number from `list`, or a key prefix")
    p_mute.add_argument("--reason", default="満車")
    p_unmute = sub.add_parser("unmute", help="un-hide a listing")
    p_unmute.add_argument("target", help="key or key prefix")
    sub.add_parser("muted", help="show hidden listings")

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    cfg = config_mod.load()

    if args.command == "run":
        return cmd_run(cfg, dry_run=args.dry_run, full_list=args.full_list)
    if args.command == "list":
        return cmd_list(cfg)
    if args.command == "mute":
        return cmd_mute(cfg, args.target, args.reason)
    if args.command == "unmute":
        return cmd_unmute(args.target)
    if args.command == "muted":
        return cmd_muted()
    return 1


def _scrape(cfg: dict) -> tuple[list[Listing], int, str]:
    http = cfg["http"]
    html = fetch(
        cfg["target_url"],
        user_agent=http["user_agent"],
        timeout=http["timeout_sec"],
        retries=http["retries"],
        backoff=http["retry_backoff_sec"],
    )
    listings, skipped = parse(html)
    return listings, skipped, html


def _visible(cfg: dict, listings: list[Listing], muted: dict[str, dict]) -> list[Listing]:
    out = [l for l in listings if l.key not in muted]
    if cfg.get("skip_closed", True):
        out = [l for l in out if not l.is_closed]
    return [l for l in out if _passes_filters(cfg["filters"], l)]


def _passes_filters(f: dict, l: Listing) -> bool:
    prefs = f.get("depart_prefectures") or []
    if prefs and not any(p in l.depart_pref for p in prefs):
        return False
    companies = f.get("return_companies") or []
    if companies and l.return_company not in companies:
        return False
    models = f.get("car_models") or []
    if models and not any(m in l.car_model for m in models):
        return False
    if (pf := f.get("period_from")) and l.period_end and l.period_end < str(pf):
        return False
    if (pt := f.get("period_to")) and l.period_start and l.period_start > str(pt):
        return False
    return True


def cmd_run(cfg: dict, dry_run: bool, full_list: bool = False) -> int:
    notify_cfg = cfg["notify"]
    notifier = ConsoleNotifier() if dry_run else build(notify_cfg)

    try:
        listings, skipped, html = _scrape(cfg)
    except ScrapeError as exc:
        log.error("%s", exc)
        if not dry_run:
            notifier.send("⚠️ 取得失敗", str(exc))
        return 1

    if not dry_run:
        store.save_snapshot(html)
    if skipped:
        log.warning("skipped %d unparsable listing(s)", skipped)

    previous = store.load_state()
    muted = store.load_muted()

    if not listings:
        msg = "取得件数が0件でした。HTML構造の変更かサイト障害の可能性があります。state は維持します。"
        log.error(msg)
        notifier.send("⚠️ 0件検出", msg)
        return 1

    if previous and len(listings) <= len(previous) * (1 - COLLAPSE_RATIO):
        notifier.send(
            "⚠️ 件数が急減",
            f"前回 {len(previous)} 件 → 今回 {len(listings)} 件。HTML構造の変更を確認してください。",
        )

    result = compute(previous, listings)
    first_run = not previous
    gap = hours_since_last_run(previous)
    resumed = not first_run and gap is not None and gap >= cfg["reinit_after_hours"]

    # A listing that vanished from the site no longer needs a mute entry.
    removed_keys = {l.key for l in result.removed}
    if removed_keys & muted.keys():
        for key in removed_keys & muted.keys():
            muted.pop(key)
        if not dry_run:
            store.save_muted(muted)

    notify_targets = [
        l for l in _visible(cfg, result.new, muted) if not l.notified
    ]

    if first_run or resumed or full_list:
        # Every ON after an OFF is effectively a fresh start: send one digest of
        # what is bookable right now instead of replaying the whole backlog.
        if first_run:
            title = "監視を開始しました"
        elif resumed:
            title = "監視を再開しました"
        else:
            title = "いま予約できる車両"
        _send_digest(notifier, cfg, _visible(cfg, listings, muted), len(listings), title)
        # An on-demand full list is not a new baseline, so it only marks the
        # listings it actually showed.
        marked = result.merged.values() if (first_run or resumed) else notify_targets
        for listing in marked:
            listing.notified = True
    elif notify_targets:
        _send_new(notifier, notify_cfg, cfg["target_url"], notify_targets)
        for listing in notify_targets:
            listing.notified = True

    if notify_cfg.get("notify_removed") and result.removed and not (first_run or resumed or full_list):
        body = "\n".join(_one_line(l) for l in result.removed[:20])
        notifier.send(f"掲載終了 {len(result.removed)} 件", body)

    closed = sum(1 for l in listings if l.is_closed)
    print(
        f"取得 {len(listings)} 件（受付終了 {closed} / 掲載中 {len(listings) - closed}）"
        f" 新規 {len(result.new)} / 通知対象 {len(notify_targets)}"
        f" / 掲載終了 {len(result.removed)} / スキップ {skipped}"
    )

    if not dry_run:
        store.save_state(result.merged)
    return 0


def hours_since_last_run(previous: dict[str, Listing]) -> float | None:
    """Hours since the newest last_seen in the stored state, or None if unknown."""
    stamps = [l.last_seen for l in previous.values() if l.last_seen]
    if not stamps:
        return None
    try:
        last = datetime.fromisoformat(max(stamps))
    except ValueError:
        return None
    return (datetime.now(timezone.utc) - last).total_seconds() / 3600


def _send_digest(notifier, cfg: dict, visible: list[Listing], total: int, title: str) -> None:
    header = f"{title}（掲載中 {len(visible)} 件 / 全 {total} 件）"
    if not visible:
        notifier.send(header, f"いま予約できる車両はありません。\n{cfg['target_url']}")
        return

    visible = sorted(visible, key=lambda l: (l.period_start, l.depart_company, l.depart_shop))
    body = "\n\n".join(_format(l) for l in visible)
    notifier.send(header, f"{body}\n\n{cfg['target_url']}")


def _send_new(notifier, notify_cfg: dict, url: str, new: list[Listing]) -> None:
    max_messages = int(notify_cfg.get("max_messages_per_run") or 3)
    per_message = 10
    batches = [new[i : i + per_message] for i in range(0, len(new), per_message)]

    if len(batches) > max_messages:
        head = "\n\n".join(_format(l) for l in new[:per_message])
        notifier.send(
            f"🚗 新規 {len(new)} 件（多数）",
            f"{head}\n\n他 {len(new) - per_message} 件\n{url}",
        )
        return

    for idx, batch in enumerate(batches, start=1):
        suffix = f"（{idx}/{len(batches)}）" if len(batches) > 1 else ""
        body = "\n\n".join(_format(l) for l in batch)
        notifier.send(f"🚗 新規 {len(new)} 件{suffix}", f"{body}\n\n{url}")


def _format(l: Listing) -> str:
    number = f"（{l.car_number}）" if l.car_number else ""
    pref = f"（{l.depart_pref}）" if l.depart_pref else ""
    lines = [
        f"🚗 {l.car_model}{number}",
        f"出発: {l.depart_company} {l.depart_shop}{pref}".rstrip(),
        f"返却: {l.return_company} {l.return_shop}".rstrip(),
        f"期間: {l.period_start} 〜 {l.period_end}",
    ]
    if l.conditions:
        lines.append(f"条件: {l.conditions}")
    if l.tel:
        lines.append(f"TEL : {l.tel}（{l.tel_label}）" if l.tel_label else f"TEL : {l.tel}")
    return "\n".join(lines)


def _one_line(l: Listing) -> str:
    return (
        f"{l.car_model} {l.car_number} / {l.depart_company} {l.depart_shop}"
        f" / {l.period_start}〜{l.period_end}"
    )


def cmd_list(cfg: dict) -> int:
    try:
        listings, skipped, _ = _scrape(cfg)
    except ScrapeError as exc:
        log.error("%s", exc)
        return 1
    muted = store.load_muted()
    visible = _visible(cfg, listings, muted)
    visible.sort(key=lambda l: (l.period_start, l.depart_company, l.depart_shop))
    for idx, l in enumerate(visible, start=1):
        print(f"[{idx:3d}] {l.key[:8]} {_one_line(l)}")
    print(f"\n{len(visible)} 件表示 / 取得 {len(listings)} 件 / mute {len(muted)} 件 / skip {skipped}")
    return 0


def _resolve(cfg: dict, target: str) -> str | None:
    """Resolve a `list` index number or a key prefix to a full key."""
    try:
        listings, _, _ = _scrape(cfg)
    except ScrapeError as exc:
        log.error("%s", exc)
        return None
    visible = _visible(cfg, listings, store.load_muted())
    visible.sort(key=lambda l: (l.period_start, l.depart_company, l.depart_shop))

    if target.isdigit():
        idx = int(target)
        if not 1 <= idx <= len(visible):
            log.error("番号 %d は範囲外です（1〜%d）", idx, len(visible))
            return None
        return visible[idx - 1].key

    matches = [l.key for l in listings if l.key.startswith(target)]
    if not matches:
        log.error("該当する掲載がありません: %s", target)
        return None
    if len(matches) > 1:
        log.error("key の指定が曖昧です（%d件該当）: %s", len(matches), target)
        return None
    return matches[0]


def cmd_mute(cfg: dict, target: str, reason: str) -> int:
    key = _resolve(cfg, target)
    if not key:
        return 1
    muted = store.load_muted()
    muted[key] = {"key": key, "reason": reason, "muted_at": store.now_iso()}
    store.save_muted(muted)
    print(f"muted: {key}")
    return 0


def cmd_unmute(target: str) -> int:
    muted = store.load_muted()
    matches = [k for k in muted if k == target or k.startswith(target)]
    if not matches:
        log.error("該当する mute がありません: %s", target)
        return 1
    for key in matches:
        muted.pop(key)
    store.save_muted(muted)
    print(f"unmuted: {', '.join(matches)}")
    return 0


def cmd_muted() -> int:
    muted = store.load_muted()
    if not muted:
        print("mute しているものはありません。")
        return 0
    for entry in muted.values():
        print(f"{entry['key'][:8]} {entry.get('reason', '')} {entry.get('muted_at', '')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
