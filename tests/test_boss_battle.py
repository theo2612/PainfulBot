"""Tests for boss battle setup.

Run from the repo root:
    python3 -m unittest tests.test_boss_battle -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game.battle import BossBattle, BOSS_MAX_HEALTH


class BossStartHealthTests(unittest.TestCase):
    def test_boss_starts_at_full_boss_health(self):
        # Regression: the boss HP used to be min(boss_player.max_health, 1500).
        # Since b7h30 is stored as an ordinary player record (max_health 50),
        # that capped the boss at 50 HP every fight. The boss must always start
        # at the full BOSS_MAX_HEALTH, never derived from a player record.
        battle = BossBattle(boss_name="b7h30")
        self.assertEqual(battle.boss_health, BOSS_MAX_HEALTH)
        self.assertEqual(battle.boss_max_health, BOSS_MAX_HEALTH)

    def test_boss_max_health_is_1500(self):
        self.assertEqual(BOSS_MAX_HEALTH, 1500)


if __name__ == "__main__":
    unittest.main()
