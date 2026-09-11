"""config.yaml loading."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.yaml"

DEFAULTS: dict = {
    "target_url": "https://cp.toyota.jp/rentacar/",
    "skip_closed": True,
    "reinit_after_hours": 24,
    "filters": {
        "depart_prefectures": [],
        "return_companies": [],
        "car_models": [],
        "period_from": None,
        "period_to": None,
    },
    "notify": {
        "type": "discord",
        "webhook_url_env": "DISCORD_WEBHOOK_URL",
        "ntfy_topic": None,
        "notify_removed": False,
        "max_messages_per_run": 3,
    },
    "http": {
        "user_agent": "katamichi-go-watcher/1.0 (personal use)",
        "timeout_sec": 20,
        "retries": 3,
        "retry_backoff_sec": 5,
    },
}


def _merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in (override or {}).items():
        out[k] = _merge(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return out


def load(path: Path = CONFIG_PATH) -> dict:
    if not path.exists():
        return DEFAULTS
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return _merge(DEFAULTS, loaded)
