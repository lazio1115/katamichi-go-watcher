"""Pluggable notification backends."""

from __future__ import annotations

import os
from typing import Protocol


class Notifier(Protocol):
    def send(self, title: str, body: str) -> None: ...


class ConsoleNotifier:
    """Used by --dry-run so a run can be inspected without sending anything."""

    def send(self, title: str, body: str) -> None:
        print(f"--- {title} ---")
        print(body)


def build(notify_cfg: dict) -> Notifier:
    kind = (notify_cfg.get("type") or "discord").lower()
    if kind == "discord":
        from .discord import DiscordNotifier

        url = os.environ.get(notify_cfg.get("webhook_url_env") or "DISCORD_WEBHOOK_URL", "")
        if not url:
            raise RuntimeError(
                f"environment variable {notify_cfg.get('webhook_url_env')} is not set"
            )
        return DiscordNotifier(url)
    if kind == "ntfy":
        from .ntfy import NtfyNotifier

        topic = notify_cfg.get("ntfy_topic")
        if not topic:
            raise RuntimeError("notify.ntfy_topic is not set in config.yaml")
        return NtfyNotifier(topic)
    raise RuntimeError(f"unknown notifier type: {kind}")
