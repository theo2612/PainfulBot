"""Tests for the unified HP model — current vs max, regen, battle entry gate,
battle exit outcomes, and migration from legacy persisted state.

Run from the repo root:
    python3 -m unittest tests.test_hp_model -v
"""
import os
import sys
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from playerdata import Player
from bot import helpers


def make_player(username="alice", health=50, max_health=None, last_regen_at=None):
    return Player(
        username=username,
        level=1,
        health=health,
        max_health=max_health,
        last_regen_at=last_regen_at,
        items=[],
        location="home",
        points=0,
        started=0,
    )


class PlayerModelTests(unittest.TestCase):
    def test_new_player_max_defaults_to_starting_health(self):
        p = make_player(health=50)
        self.assertEqual(p.max_health, 50)
        self.assertEqual(p.health, 50)

    def test_explicit_max_separates_from_current(self):
        p = make_player(health=20, max_health=80)
        self.assertEqual(p.max_health, 80)
        self.assertEqual(p.health, 20)

    def test_current_is_clamped_to_max_on_construction(self):
        # If a corrupt record arrives with current > max, current is clamped.
        p = make_player(health=200, max_health=100)
        self.assertEqual(p.max_health, 100)
        self.assertEqual(p.health, 100)

    def test_roundtrip_includes_both_fields(self):
        p = make_player(health=42, max_health=80, last_regen_at="2026-05-27T12:00:00")
        d = p.to_dict()
        self.assertEqual(d["health"], 42)
        self.assertEqual(d["max_health"], 80)
        self.assertEqual(d["last_regen_at"], "2026-05-27T12:00:00")

        restored = Player.from_dict("alice", d)
        self.assertEqual(restored.health, 42)
        self.assertEqual(restored.max_health, 80)
        self.assertEqual(restored.last_regen_at, "2026-05-27T12:00:00")

    def test_legacy_record_without_max_migrates_to_full(self):
        # Pre-split records had only `health` (functionally the max). On load
        # we synthesize max_health = health and keep them at full HP.
        legacy = {"level": 3, "health": 75, "items": [], "location": "home",
                  "points": 100, "started": 1}
        p = Player.from_dict("legacy_user", legacy)
        self.assertEqual(p.max_health, 75)
        self.assertEqual(p.health, 75)


class RegenTickTests(unittest.TestCase):
    def test_heals_one_hp_when_off_cooldown(self):
        p = make_player(health=20, max_health=50)
        now = datetime(2026, 5, 27, 12, 0, 0)
        healed = helpers.regen_tick(p, now=now)
        self.assertEqual(healed, 1)
        self.assertEqual(p.health, 21)
        self.assertEqual(p.last_regen_at, now.isoformat())

    def test_cooldown_blocks_second_tick_within_30s(self):
        now = datetime(2026, 5, 27, 12, 0, 0)
        p = make_player(health=20, max_health=50)
        helpers.regen_tick(p, now=now)
        # 29 seconds later — should NOT heal.
        healed = helpers.regen_tick(p, now=now + timedelta(seconds=29))
        self.assertEqual(healed, 0)
        self.assertEqual(p.health, 21)

    def test_cooldown_releases_after_30s(self):
        now = datetime(2026, 5, 27, 12, 0, 0)
        p = make_player(health=20, max_health=50)
        helpers.regen_tick(p, now=now)
        healed = helpers.regen_tick(p, now=now + timedelta(seconds=30))
        self.assertEqual(healed, 1)
        self.assertEqual(p.health, 22)

    def test_does_not_heal_above_max(self):
        p = make_player(health=50, max_health=50)
        healed = helpers.regen_tick(p)
        self.assertEqual(healed, 0)
        self.assertEqual(p.health, 50)

    def test_corrupt_last_regen_at_falls_through_to_tick(self):
        p = make_player(health=10, max_health=50, last_regen_at="not-a-timestamp")
        healed = helpers.regen_tick(p)
        self.assertEqual(healed, 1)
        self.assertEqual(p.health, 11)


class BattleEntryGateTests(unittest.TestCase):
    """50%-of-max entry floor (uses math.ceil so odd maxes round up)."""

    import math as _math

    def _floor(self, max_hp):
        return self._math.ceil(max_hp / 2)

    def test_full_hp_can_enter(self):
        p = make_player(health=50, max_health=50)
        self.assertGreaterEqual(p.health, self._floor(p.max_health))

    def test_exactly_half_can_enter(self):
        p = make_player(health=25, max_health=50)
        self.assertGreaterEqual(p.health, self._floor(p.max_health))

    def test_below_half_is_blocked(self):
        p = make_player(health=24, max_health=50)
        self.assertLess(p.health, self._floor(p.max_health))

    def test_odd_max_rounds_up(self):
        # 51 max requires 26, not 25 — ceil(51/2) = 26.
        p = make_player(health=25, max_health=51)
        self.assertLess(p.health, self._floor(p.max_health))
        p2 = make_player(health=26, max_health=51)
        self.assertGreaterEqual(p2.health, self._floor(p2.max_health))


class BattleOutcomeTests(unittest.TestCase):
    """Outcome semantics: win = full heal + max bump; loss = 1 HP for all."""

    def test_victory_full_heals_survivor_and_bumps_max(self):
        p = make_player(health=12, max_health=50)
        # Simulate the post-victory mutation in reward_team.
        p.max_health = min(p.max_health + 5, 1000)
        p.health = p.max_health
        self.assertEqual(p.max_health, 55)
        self.assertEqual(p.health, 55)

    def test_victory_max_bump_caps_at_1000(self):
        p = make_player(health=1000, max_health=1000)
        p.max_health = min(p.max_health + 5, 1000)
        p.health = p.max_health
        self.assertEqual(p.max_health, 1000)
        self.assertEqual(p.health, 1000)

    def test_defeat_sets_everyone_to_one(self):
        # Both survivors-via-USB and fallen go to 1 HP.
        p1 = make_player("alice", health=25, max_health=50)
        p2 = make_player("bob", health=0, max_health=80)
        for p in (p1, p2):
            p.health = 1
        self.assertEqual(p1.health, 1)
        self.assertEqual(p2.health, 1)
        # max_health is untouched on defeat.
        self.assertEqual(p1.max_health, 50)
        self.assertEqual(p2.max_health, 80)


if __name__ == "__main__":
    unittest.main()
