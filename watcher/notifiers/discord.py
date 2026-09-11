from __future__ import annotations

import logging
import time

import requests

MAX_CONTENT = 1900  # Discord's hard limit is 2000; leave room for the title line.
RATE_LIMIT_RETRIES = 5

log = logging.getLogger(__name__)


class DiscordNotifier:
    def __init__(self, webhook_url: str, timeout: int = 20) -> None:
        self._url = webhook_url
        self._timeout = timeout

    def send(self, title: str, body: str) -> None:
        content = f"**{title}**\n{body}" if title else body
        for chunk in _chunks(content):
            self._post(chunk)

    def _post(self, chunk: str) -> None:
        """Post one chunk, waiting out Discord's per-webhook rate limit.

        A full listing digest spans several messages, which is exactly the burst
        that trips the 5-requests-per-2-seconds webhook limit.
        """
        for _ in range(RATE_LIMIT_RETRIES):
            res = requests.post(self._url, json={"content": chunk}, timeout=self._timeout)
            if res.status_code != 429:
                res.raise_for_status()
                return
            wait = _retry_after(res)
            log.warning("rate limited by Discord, retrying in %.1fs", wait)
            time.sleep(wait)
        raise RuntimeError("Discord rate limit did not clear after several retries")


def _retry_after(res: requests.Response) -> float:
    try:
        return min(float(res.json()["retry_after"]), 60.0)
    except Exception:  # noqa: BLE001 - fall back to a fixed pause
        return 2.0


def _chunks(text: str) -> list[str]:
    if len(text) <= MAX_CONTENT:
        return [text]
    out: list[str] = []
    buf = ""
    for line in text.splitlines(keepends=True):
        if len(buf) + len(line) > MAX_CONTENT and buf:
            out.append(buf)
            buf = ""
        buf += line
    if buf:
        out.append(buf)
    return out
