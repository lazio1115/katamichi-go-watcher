from __future__ import annotations

import requests

MAX_CONTENT = 1900  # Discord's hard limit is 2000; leave room for the title line.


class DiscordNotifier:
    def __init__(self, webhook_url: str, timeout: int = 20) -> None:
        self._url = webhook_url
        self._timeout = timeout

    def send(self, title: str, body: str) -> None:
        content = f"**{title}**\n{body}" if title else body
        for chunk in _chunks(content):
            res = requests.post(self._url, json={"content": chunk}, timeout=self._timeout)
            res.raise_for_status()


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
