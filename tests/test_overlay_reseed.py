"""Regression test for the overlay re-seed wiring.

The overlay (boss_battle/server.py) keeps the game roster, treasury, and
catalogs in memory only. Restarting the overlay by itself used to blank the
roster: the full list is seeded by the bot, and before this change the bot only
seeded it once, in event_ready (i.e. on a *bot* restart). So an overlay-only
restart showed just the handful of players who happened to act next.

The fix: the bot exposes a /resync endpoint that re-pushes everything, the seed
logic lives in one reusable place (_reseed_overlay) used by both event_ready and
/resync, and the overlay calls /resync on its own startup.

PainfulBot imports aiohttp, which isn't installed outside the bot container, so
(like tests/test_idle_hacking.py) this guards the wiring by parsing the source
rather than importing the module.

Run from the repo root:
    python3 -m unittest tests.test_overlay_reseed -v
"""
import os
import re
import unittest


def _read(path):
    full = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), path)
    with open(full, encoding="utf-8") as f:
        return f.read()


class BotReseedWiringTests(unittest.TestCase):
    def setUp(self):
        self.src = _read("PainfulBot.py")

    def test_reseed_method_exists(self):
        self.assertIn(
            "async def _reseed_overlay(self):", self.src,
            "the shared overlay re-seed method must exist",
        )

    def test_reseed_pushes_every_player(self):
        """The seed must loop over the whole roster, not a single player."""
        body = self._method_body("_reseed_overlay")
        self.assertRegex(
            body, r"for\s+\w+,\s*\w+\s+in\s+list\(self\.player_data\.items\(\)\)",
            "_reseed_overlay must iterate the full player_data, re-pushing each",
        )
        self.assertIn("game_overlay.clear()", body)
        self.assertIn("game_overlay.player(", body)
        self.assertIn("game_overlay.treasury(", body)
        self.assertIn("_push_idle_catalog()", body)

    def test_event_ready_uses_the_shared_seed(self):
        """event_ready must delegate to _reseed_overlay (not inline its own copy),
        so the bot-startup seed and the /resync seed can never drift apart."""
        body = self._method_body("event_ready")
        self.assertIn("self._reseed_overlay()", body)

    def test_resync_route_registered(self):
        self.assertRegex(
            self.src,
            r"add_post\(\s*['\"]/resync['\"]\s*,\s*self\._internal_resync_handler\s*\)",
            "the /resync route must be registered on the internal API",
        )

    def test_resync_handler_calls_the_shared_seed(self):
        body = self._method_body("_internal_resync_handler")
        self.assertIn("self._reseed_overlay()", body)

    # ── helper ────────────────────────────────────────────────────────────────
    def _method_body(self, name):
        """Return the source of `async def <name>` up to the next def/method at
        the same (4-space) indentation. Crude but adequate for these guards."""
        m = re.search(rf"\n    async def {re.escape(name)}\(", self.src)
        self.assertIsNotNone(m, f"method {name} not found")
        start = m.start()
        rest = self.src[start + 1:]
        nxt = re.search(r"\n    (?:async def|def) ", rest)
        return rest[: nxt.start()] if nxt else rest


if __name__ == "__main__":
    unittest.main()
