"""Persistence for state.json / muted.json and HTML snapshots."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .scraper import Listing

ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = ROOT / "state.json"
MUTED_PATH = ROOT / "muted.json"
SNAPSHOT_DIR = ROOT / "snapshots"
SNAPSHOT_KEEP = 3


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _write_atomic(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def load_state(path: Path = STATE_PATH) -> dict[str, Listing]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {k: Listing.from_dict(v) for k, v in raw.get("listings", {}).items()}


def save_state(listings: dict[str, Listing], path: Path = STATE_PATH) -> None:
    _write_atomic(
        path,
        {
            "updated_at": now_iso(),
            "listings": {k: v.to_dict() for k, v in listings.items()},
        },
    )


def load_muted(path: Path = MUTED_PATH) -> dict[str, dict]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {entry["key"]: entry for entry in raw.get("muted", [])}


def save_muted(muted: dict[str, dict], path: Path = MUTED_PATH) -> None:
    _write_atomic(path, {"muted": list(muted.values())})


def save_snapshot(html: str, directory: Path = SNAPSHOT_DIR, keep: int = SNAPSHOT_KEEP) -> None:
    directory.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (directory / f"page-{stamp}.html").write_text(html, encoding="utf-8")
    for old in sorted(directory.glob("page-*.html"), reverse=True)[keep:]:
        old.unlink()
