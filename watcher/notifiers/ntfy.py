from __future__ import annotations

import requests


class NtfyNotifier:
    """Publishes via ntfy's JSON endpoint.

    The header-based API requires ASCII-only headers, which mangles Japanese
    titles; the JSON body is UTF-8 clean.
    """

    def __init__(self, topic: str, server: str = "https://ntfy.sh", timeout: int = 20) -> None:
        self._server = server.rstrip("/")
        self._topic = topic
        self._timeout = timeout

    def send(self, title: str, body: str) -> None:
        res = requests.post(
            self._server,
            json={"topic": self._topic, "title": title, "message": body},
            timeout=self._timeout,
        )
        res.raise_for_status()
