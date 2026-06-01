"""Regression test for the overlay's startup re-seed request.

The overlay holds the game roster/treasury/catalogs in memory only, so on its
own startup it must ask the bot to re-push them (POST to the bot's /resync).
This verifies the URL is derived from BOT_API and that the request loop posts
there and stops once the bot answers.

OVERLAY_DISABLE_RESEED is set before importing server so the real background
re-seed greenlet does not fire during the test (we drive _request_bot_reseed
directly instead).

Run from the boss_battle/ directory:
    .venv/bin/python -m pytest tests/test_overlay_reseed.py -v
or as a plain script:
    .venv/bin/python tests/test_overlay_reseed.py
"""
import os
import sys

os.environ["OVERLAY_DISABLE_RESEED"] = "1"
os.environ["BOT_API"] = "http://bot:3004/command"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server  # noqa: E402


def test_resync_url_derived_from_bot_api():
    assert server.BOT_RESYNC_URL == "http://bot:3004/resync"


class _Resp:
    def __init__(self, ok=True, payload=None):
        self.ok = ok
        self._payload = payload or {}

    def json(self):
        return self._payload


def test_reseed_posts_to_resync_and_stops_on_success():
    """One successful POST to BOT_RESYNC_URL should end the retry loop."""
    calls = []

    def fake_post(url, **kwargs):
        calls.append(url)
        return _Resp(ok=True, payload={"players": 40})

    orig_post = server.http_req.post
    orig_sleep = server.socketio.sleep
    server.http_req.post = fake_post
    server.socketio.sleep = lambda *_a, **_k: None  # never reached on first success
    try:
        server._request_bot_reseed()
    finally:
        server.http_req.post = orig_post
        server.socketio.sleep = orig_sleep

    assert calls == ["http://bot:3004/resync"], calls


def test_reseed_retries_until_the_bot_answers():
    """If the bot API isn't up yet, keep retrying; succeed once it responds."""
    attempts = {"n": 0}

    def fake_post(url, **kwargs):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise ConnectionError("bot API not up yet")
        return _Resp(ok=True, payload={"players": 40})

    orig_post = server.http_req.post
    orig_sleep = server.socketio.sleep
    server.http_req.post = fake_post
    server.socketio.sleep = lambda *_a, **_k: None  # don't actually wait
    try:
        server._request_bot_reseed()
    finally:
        server.http_req.post = orig_post
        server.socketio.sleep = orig_sleep

    assert attempts["n"] == 3, attempts


if __name__ == "__main__":
    test_resync_url_derived_from_bot_api()
    test_reseed_posts_to_resync_and_stops_on_success()
    test_reseed_retries_until_the_bot_answers()
    print("all tests passed")
