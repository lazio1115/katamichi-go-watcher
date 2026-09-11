import watcher.notifiers.discord as discord_mod
from watcher.notifiers.discord import MAX_CONTENT, DiscordNotifier, _chunks


class _Res:
    def __init__(self, status_code=204, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise AssertionError(f"unexpected status {self.status_code}")


def test_short_message_is_not_split():
    assert _chunks("hello") == ["hello"]


def test_long_message_is_split_on_line_boundaries():
    listing = "\n".join(f"line {i}" for i in range(8))
    text = "\n\n".join([listing] * 40)
    chunks = _chunks(text)
    assert len(chunks) > 1
    assert all(len(c) <= MAX_CONTENT for c in chunks)
    assert "".join(chunks) == text


def test_every_chunk_is_posted(monkeypatch):
    posted = []
    monkeypatch.setattr(
        discord_mod.requests,
        "post",
        lambda url, json, timeout: posted.append(json["content"]) or _Res(),
    )
    body = "\n".join(f"行{i}" * 20 for i in range(200))
    DiscordNotifier("https://discord.test/hook").send("タイトル", body)
    assert len(posted) > 1
    assert posted[0].startswith("**タイトル**")


def test_rate_limited_request_is_retried(monkeypatch):
    calls = []
    slept = []

    def fake_post(url, json, timeout):
        calls.append(json["content"])
        return _Res(429, {"retry_after": 0.25}) if len(calls) == 1 else _Res()

    monkeypatch.setattr(discord_mod.requests, "post", fake_post)
    monkeypatch.setattr(discord_mod.time, "sleep", slept.append)

    DiscordNotifier("https://discord.test/hook").send("t", "short body")
    assert len(calls) == 2
    assert slept == [0.25]


def test_retry_after_is_capped(monkeypatch):
    slept = []
    monkeypatch.setattr(
        discord_mod.requests, "post", lambda url, json, timeout: _Res(429, {"retry_after": 9999})
    )
    monkeypatch.setattr(discord_mod.time, "sleep", slept.append)

    try:
        DiscordNotifier("https://discord.test/hook").send("t", "body")
    except RuntimeError:
        pass
    assert slept and all(s == 60.0 for s in slept)
