"""Tests for game/jail.py — speed penalty, jail, bail and treasury.

Run from the repo root:
    python3 -m unittest tests.test_jail -v
"""
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

# Make repo root importable when running from anywhere.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game import jail
from playerdata import Player


T0 = datetime(2026, 5, 9, 12, 0, 0, tzinfo=timezone.utc)


def make_player(username="alice", level=10, points=10_000) -> Player:
    return Player(
        username=username,
        level=level,
        health=10,
        items=[],
        location="email",
        points=points,
        started=0,
    )


class JailTestBase(unittest.TestCase):
    """Each test gets its own temp treasury file and a disabled attack log."""

    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        )
        self._tmp.write("{}")
        self._tmp.close()
        jail.set_treasury_path(self._tmp.name)
        jail.set_attack_log_path("")  # disable telemetry during tests

    def tearDown(self):
        try:
            os.unlink(self._tmp.name)
        except FileNotFoundError:
            pass


# ---------------------------------------------------------------------------
# Threshold table
# ---------------------------------------------------------------------------

class ThresholdLookupTests(JailTestBase):
    def test_threshold_is_uniform_across_levels(self):
        # Revised design: any level can click 10/sec manually without a strike.
        # Threshold = 0.1s at every level for every supported location.
        for loc in ["email", "website", "server", "network",
                    "database", "/etc/shadow", "evilcorp"]:
            for level in (1, 50, 500, 5000, 50_000):
                self.assertEqual(
                    jail.threshold_for(loc, level), 0.1,
                    f"{loc} @ lvl {level} should be 0.1s",
                )

    def test_unknown_location_returns_none(self):
        self.assertIsNone(jail.threshold_for("home", 100))
        self.assertIsNone(jail.threshold_for("unknown_zone", 100))


# ---------------------------------------------------------------------------
# Speed check / strike accumulation
# ---------------------------------------------------------------------------

class SpeedCheckTests(JailTestBase):
    def test_first_attack_never_a_violation(self):
        p = make_player(level=5000)
        r = jail.record_attack(p, "evilcorp", base_reward=100, now=T0)
        self.assertFalse(r.is_violation)
        self.assertEqual(r.strikes_now, 0)

    def test_attack_above_threshold_is_clean(self):
        p = make_player(level=5000)
        jail.record_attack(p, "evilcorp", 100, now=T0)
        # Threshold is 0.1s for everyone; 1s later is comfortably above.
        r = jail.record_attack(p, "evilcorp", 100, now=T0 + timedelta(seconds=1))
        self.assertFalse(r.is_violation)
        self.assertEqual(r.strikes_now, 0)

    def test_attack_below_threshold_is_a_strike(self):
        p = make_player(level=5000)
        jail.record_attack(p, "evilcorp", 100, now=T0)
        # 50ms = 20 clicks/sec = auto-clicker speed → strike
        r = jail.record_attack(p, "evilcorp", 100, now=T0 + timedelta(seconds=0.05))
        self.assertTrue(r.is_violation)
        self.assertEqual(r.strikes_now, 1)
        self.assertFalse(r.jailed)

    def test_manual_10cps_is_safe_at_any_level(self):
        """10 clicks/sec (0.1s gaps) is the design floor: never a strike, any level."""
        for lvl in (1, 50, 500, 5000, 50_000):
            for loc in ("email", "/etc/shadow", "evilcorp"):
                p = make_player(level=lvl)
                now = T0
                for i in range(10):
                    r = jail.record_attack(p, loc, 100, now=now)
                    self.assertFalse(
                        r.is_violation,
                        f"manual click at lvl {lvl} @ {loc} (#{i}) should not strike",
                    )
                    now += timedelta(seconds=0.1)

    def test_at_exactly_threshold_is_not_a_strike(self):
        p = make_player(level=5000)
        jail.record_attack(p, "evilcorp", 100, now=T0)
        # gap == threshold (0.1s) should be allowed (>= check in record_attack)
        r = jail.record_attack(p, "evilcorp", 100, now=T0 + timedelta(seconds=0.1))
        self.assertFalse(r.is_violation)

    def test_bypass_speed_check_records_but_skips_strike(self):
        p = make_player(level=5000)
        jail.record_attack(p, "evilcorp", 100, now=T0)
        r = jail.record_attack(
            p, "evilcorp", 100,
            now=T0 + timedelta(seconds=0.1),
            bypass_speed_check=True,
        )
        self.assertFalse(r.is_violation)
        self.assertEqual(r.strikes_now, 0)
        # timestamp updated so the next attack is measured against this one
        self.assertEqual(
            p.last_attack_at["evilcorp"],
            (T0 + timedelta(seconds=0.1)).isoformat(),
        )


# ---------------------------------------------------------------------------
# Strike decay (10 min idle resets)
# ---------------------------------------------------------------------------

class StrikeDecayTests(JailTestBase):
    def test_strike_persists_within_decay_window(self):
        p = make_player(level=5000)
        jail.record_attack(p, "evilcorp", 100, now=T0)
        jail.record_attack(p, "evilcorp", 100, now=T0 + timedelta(seconds=0.05))
        self.assertEqual(p.speed_strikes, 1)

        # 9 minutes later — still within decay window
        r = jail.record_attack(p, "evilcorp", 100, now=T0 + timedelta(minutes=9))
        # Above threshold → not a strike, but counter not yet decayed
        self.assertFalse(r.is_violation)
        self.assertEqual(p.speed_strikes, 1)

    def test_strike_decays_after_10_min(self):
        p = make_player(level=5000)
        jail.record_attack(p, "evilcorp", 100, now=T0)
        jail.record_attack(p, "evilcorp", 100, now=T0 + timedelta(seconds=0.05))
        self.assertEqual(p.speed_strikes, 1)

        # 11 minutes since the strike — decayed
        jail.record_attack(p, "evilcorp", 100, now=T0 + timedelta(minutes=11))
        self.assertEqual(p.speed_strikes, 0)


# ---------------------------------------------------------------------------
# Jail entry / ladder / exit
# ---------------------------------------------------------------------------

class JailLadderTests(JailTestBase):
    def test_three_strikes_jails(self):
        p = make_player(level=5000)
        # Fire 4 rapid-fire attacks → first sets baseline, next 3 each strike
        # Gaps of 0.05s (20 cps) are below the 0.1s threshold.
        for i in range(4):
            r = jail.record_attack(p, "evilcorp", 100, now=T0 + timedelta(seconds=i * 0.05))
        self.assertTrue(jail.is_jailed(p, now=T0 + timedelta(seconds=1)))
        # First offense → 1 minute
        self.assertEqual(r.jail_minutes, 1)

    def test_jail_ladder_squaring(self):
        """Five back-to-back jails produce 1, 2, 4, 16, 256 minutes."""
        p = make_player(level=1000)
        expected = [1, 2, 4, 16, 256]
        for i, expected_min in enumerate(expected):
            t = T0 + timedelta(hours=i * 12)  # well within 24h reset window
            duration, offense_no = jail._send_to_jail(p, "speed", t)
            self.assertEqual(
                duration, expected_min,
                f"offense #{i + 1} should be {expected_min} min, got {duration}",
            )
            self.assertEqual(offense_no, i + 1)
            # Manually release between jails so the ladder advances
            p.jail = None
            p.last_jail_released_at = (t + timedelta(minutes=expected_min)).isoformat()

    def test_offense_caps_at_256(self):
        """6th offense (and beyond) stays at the 256-min top rung."""
        p = make_player(level=1000)
        p.offense_count = 5
        p.last_jail_released_at = T0.isoformat()
        duration, offense_no = jail._send_to_jail(p, "speed", T0 + timedelta(hours=1))
        self.assertEqual(duration, 256)
        self.assertEqual(offense_no, 5)  # capped at the top rung

    def test_ladder_resets_after_24h_jail_free(self):
        p = make_player(level=1000)
        p.offense_count = 3
        p.last_jail_released_at = T0.isoformat()
        # 25 hours later → reset
        duration, offense_no = jail._send_to_jail(p, "speed", T0 + timedelta(hours=25))
        self.assertEqual(duration, 1)
        self.assertEqual(offense_no, 1)

    def test_expired_jail_releases_on_status_check(self):
        p = make_player(level=1000)
        jail._send_to_jail(p, "speed", T0)
        # 2 minutes later (first offense = 1 min) → expired
        status = jail.jail_status(p, now=T0 + timedelta(minutes=2))
        self.assertFalse(status.is_jailed)
        self.assertEqual(p.speed_strikes, 0)
        self.assertIsNotNone(p.last_jail_released_at)


# ---------------------------------------------------------------------------
# Steal-fail direct-to-jail path
# ---------------------------------------------------------------------------

class StealFailJailTests(JailTestBase):
    def test_steal_fail_jails_immediately(self):
        p = make_player()
        status = jail.jail_on_steal_fail(p, now=T0)
        self.assertTrue(status.is_jailed)
        self.assertEqual(status.reason, "steal_fail")

    def test_steal_fail_does_not_require_strikes(self):
        p = make_player()
        self.assertEqual(p.speed_strikes, 0)
        jail.jail_on_steal_fail(p, now=T0)
        self.assertTrue(p.jail is not None)
        # No strikes accumulated, just direct
        self.assertEqual(p.speed_strikes, 0)

    def test_steal_fail_advances_ladder(self):
        p = make_player()
        jail.jail_on_steal_fail(p, now=T0)
        # Release them by force, then steal-fail again — should be offense #2 (2 min)
        p.jail = None
        p.last_jail_released_at = (T0 + timedelta(minutes=1)).isoformat()
        jail.jail_on_steal_fail(p, now=T0 + timedelta(minutes=5))
        self.assertEqual(p.offense_count, 2)
        duration_min = jail._duration_for_offense(p.offense_count)
        self.assertEqual(duration_min, 2)


# ---------------------------------------------------------------------------
# Bail math + treasury
# ---------------------------------------------------------------------------

class BailTests(JailTestBase):
    def test_bail_formula_matches_design_spec(self):
        """Loafageddon at lvl 5126, 4-min jail → 102,520 pts (per spec §4)."""
        p = make_player(username="loafageddon", level=5126, points=200_000)
        jail._send_to_jail(p, "speed", T0)
        # Force offense #3 to land on the 4-minute rung
        p.offense_count = 0  # rewind
        jail.JAIL_LADDER_MINUTES  # ensure not accidentally mutated
        # Manually set a 4-min term to match the spec example
        p.jail = {
            "until": (T0 + timedelta(minutes=4)).isoformat(),
            "reason": "speed",
            "offense_number": 3,
        }
        cost = jail.bail_cost_for(p, now=T0)
        self.assertEqual(cost, 4 * 5126 * 5)
        self.assertEqual(cost, 102_520)

    def test_successful_bail_splits_90_10(self):
        bailer = make_player(username="bailer", level=10, points=1_000)
        jailed = make_player(username="jailed", level=10, points=10_000)
        jailed.jail = {
            "until": (T0 + timedelta(minutes=4)).isoformat(),
            "reason": "speed",
            "offense_number": 3,
        }
        jailed.offense_count = 3
        ok, _ = jail.request_bail(jailed, "bailer", now=T0)
        self.assertTrue(ok)
        result = jail.post_bail(bailer, jailed, now=T0)
        self.assertTrue(result.ok)
        cost = 4 * 10 * 5  # 200
        self.assertEqual(result.bail_cost, cost)
        self.assertEqual(result.bailer_share, 20)  # 10% of 200
        self.assertEqual(result.treasury_share, 180)
        self.assertEqual(jailed.points, 10_000 - 200)
        self.assertEqual(bailer.points, 1_000 + 20)
        self.assertEqual(jail.get_treasury_balance(), 180)
        # Jail ended, consent consumed
        self.assertIsNone(jailed.jail)
        self.assertIsNone(jailed.bail_request_for)
        self.assertEqual(jailed.speed_strikes, 0)
        # offense_count preserved (ladder doesn't reset on bail)
        self.assertEqual(jailed.offense_count, 3)

    def test_bail_fails_when_jailed_is_broke(self):
        bailer = make_player(username="bailer", points=1_000)
        jailed = make_player(username="jailed", level=10, points=50)  # too poor
        jailed.jail = {
            "until": (T0 + timedelta(minutes=4)).isoformat(),
            "reason": "speed",
            "offense_number": 3,
        }
        jail.request_bail(jailed, "bailer", now=T0)
        result = jail.post_bail(bailer, jailed, now=T0)
        self.assertFalse(result.ok)
        self.assertEqual(jailed.points, 50)  # unchanged
        self.assertEqual(bailer.points, 1_000)  # unchanged
        self.assertEqual(jail.get_treasury_balance(), 0)
        self.assertIsNotNone(jailed.jail)  # still in

    def test_bail_fails_when_not_jailed(self):
        bailer = make_player(username="bailer", points=1_000)
        free = make_player(username="free", points=10_000)
        result = jail.post_bail(bailer, free, now=T0)
        self.assertFalse(result.ok)

    def test_cannot_bail_yourself(self):
        # Two refs to the same player would not exist in practice, but the
        # check defends against client misuse.
        p = make_player(username="self", points=10_000)
        p.jail = {
            "until": (T0 + timedelta(minutes=1)).isoformat(),
            "reason": "speed",
            "offense_number": 1,
        }
        result = jail.post_bail(p, p, now=T0)
        self.assertFalse(result.ok)

    def test_bail_cost_decays_as_time_passes(self):
        p = make_player(username="late", level=10, points=10_000)
        p.jail = {
            "until": (T0 + timedelta(minutes=4)).isoformat(),
            "reason": "speed",
            "offense_number": 3,
        }
        # Full 4 min remaining
        self.assertEqual(jail.bail_cost_for(p, now=T0), 4 * 10 * 5)
        # 2 min remaining
        self.assertEqual(jail.bail_cost_for(p, now=T0 + timedelta(minutes=2)), 2 * 10 * 5)


class BailConsentTests(JailTestBase):
    def _jailed(self, username="jailed", level=10, points=10_000):
        p = make_player(username=username, level=level, points=points)
        p.jail = {
            "until": (T0 + timedelta(minutes=4)).isoformat(),
            "reason": "speed",
            "offense_number": 3,
        }
        return p

    def test_bail_refused_without_request(self):
        bailer = make_player(username="bailer", points=1_000)
        jailed = self._jailed()
        result = jail.post_bail(bailer, jailed, now=T0)
        self.assertFalse(result.ok)
        self.assertIn("hasn't requested bail", result.message)
        # Money didn't move
        self.assertEqual(jailed.points, 10_000)
        self.assertEqual(bailer.points, 1_000)
        self.assertEqual(jail.get_treasury_balance(), 0)
        # Still jailed
        self.assertIsNotNone(jailed.jail)

    def test_bail_refused_when_requested_from_someone_else(self):
        loaf  = make_player(username="loaf",  points=1_000)
        derb  = self._jailed(username="derboki")
        other = make_player(username="other", points=0)
        jail.request_bail(derb, "other", now=T0)  # derb asked other, not loaf
        result = jail.post_bail(loaf, derb, now=T0)
        self.assertFalse(result.ok)
        self.assertIn("not you", result.message.lower())
        self.assertIsNotNone(derb.jail)
        self.assertEqual(derb.points, 10_000)

    def test_request_bail_rejects_self_and_empty(self):
        p = self._jailed(username="alone")
        ok, msg = jail.request_bail(p, "alone", now=T0)
        self.assertFalse(ok)
        ok, msg = jail.request_bail(p, "", now=T0)
        self.assertFalse(ok)
        ok, msg = jail.request_bail(p, "   ", now=T0)
        self.assertFalse(ok)

    def test_request_bail_strips_at_and_lowercases(self):
        p = self._jailed(username="loaf")
        ok, _ = jail.request_bail(p, "@DerBOKI", now=T0)
        self.assertTrue(ok)
        self.assertEqual(p.bail_request_for, "derboki")

    def test_request_bail_requires_jailed_state(self):
        p = make_player(username="free")
        ok, msg = jail.request_bail(p, "buddy", now=T0)
        self.assertFalse(ok)
        self.assertIn("not in jail", msg)

    def test_auto_release_clears_pending_request(self):
        p = self._jailed(username="ghosted")
        jail.request_bail(p, "buddy", now=T0)
        self.assertEqual(p.bail_request_for, "buddy")
        # 5 minutes later — past the 4-min jail term
        jail.jail_status(p, now=T0 + timedelta(minutes=5))
        self.assertIsNone(p.bail_request_for)

    def test_successful_bail_clears_request(self):
        bailer = make_player(username="b", points=0)
        jailed = self._jailed(username="j", level=10, points=10_000)
        jail.request_bail(jailed, "b", now=T0)
        result = jail.post_bail(bailer, jailed, now=T0)
        self.assertTrue(result.ok)
        self.assertIsNone(jailed.bail_request_for)

    def test_bail_request_persists_on_dict_round_trip(self):
        p = self._jailed(username="round")
        jail.request_bail(p, "trip", now=T0)
        d = p.to_dict()
        self.assertEqual(d["bail_request_for"], "trip")
        from playerdata import Player
        p2 = Player.from_dict("round", d)
        self.assertEqual(p2.bail_request_for, "trip")


# ---------------------------------------------------------------------------
# Command gating
# ---------------------------------------------------------------------------

class CommandGatingTests(JailTestBase):
    def test_free_player_can_use_any_command(self):
        p = make_player()
        self.assertIsNone(jail.block_if_jailed(p, now=T0))

    def test_jailed_player_is_blocked(self):
        p = make_player()
        jail._send_to_jail(p, "speed", T0)
        msg = jail.block_if_jailed(p, now=T0)
        self.assertIsNotNone(msg)
        self.assertIn("jail", msg.lower())

    def test_after_jail_expires_player_is_unblocked(self):
        p = make_player()
        jail._send_to_jail(p, "speed", T0)
        # 1-minute first offense → 2 minutes later they're free
        self.assertIsNone(jail.block_if_jailed(p, now=T0 + timedelta(minutes=2)))


# ---------------------------------------------------------------------------
# Integration scenario: an auto-clicker pipeline
# ---------------------------------------------------------------------------

class NoCapWindowTests(JailTestBase):
    def test_grant_no_cap_sets_player_field(self):
        p = make_player()
        end = jail.grant_no_cap(p, minutes=60, now=T0)
        self.assertEqual(end, (T0 + timedelta(minutes=60)).isoformat())
        self.assertEqual(p.no_cap_until, end)

    def test_attack_in_no_cap_window_skips_strike(self):
        p = make_player(level=5000)
        jail.grant_no_cap(p, minutes=60, now=T0)
        jail.record_attack(p, "evilcorp", 100, now=T0)
        # Fire 5 attacks at 50ms gaps (would normally hit jail after 3 strikes)
        for i in range(1, 6):
            r = jail.record_attack(p, "evilcorp", 100, now=T0 + timedelta(seconds=i * 0.05))
            self.assertFalse(r.is_violation, f"shot #{i} in no-cap should not strike")
        self.assertEqual(p.speed_strikes, 0)
        self.assertIsNone(p.jail)

    def test_no_cap_expires_and_strikes_resume(self):
        p = make_player(level=5000)
        jail.grant_no_cap(p, minutes=60, now=T0)
        # Just past 60 min — window closed
        past = T0 + timedelta(minutes=61)
        jail.record_attack(p, "evilcorp", 100, now=past)
        r = jail.record_attack(p, "evilcorp", 100, now=past + timedelta(seconds=0.05))
        self.assertTrue(r.is_violation)
        self.assertEqual(r.strikes_now, 1)

    def test_grant_no_cap_stacks_additively(self):
        p = make_player()
        jail.grant_no_cap(p, minutes=60, now=T0)
        # 10 min later, another laptop — should extend to T0+60+60 = T0+120
        jail.grant_no_cap(p, minutes=60, now=T0 + timedelta(minutes=10))
        self.assertEqual(p.no_cap_until, (T0 + timedelta(minutes=120)).isoformat())

    def test_grant_no_cap_after_expiry_starts_fresh(self):
        p = make_player()
        jail.grant_no_cap(p, minutes=60, now=T0)
        # 2h later, original window long expired — new window starts from now
        later = T0 + timedelta(hours=2)
        jail.grant_no_cap(p, minutes=60, now=later)
        self.assertEqual(p.no_cap_until, (later + timedelta(minutes=60)).isoformat())

    def test_no_cap_remaining_seconds(self):
        p = make_player()
        jail.grant_no_cap(p, minutes=60, now=T0)
        self.assertEqual(jail.no_cap_remaining_seconds(p, now=T0), 3600)
        self.assertEqual(jail.no_cap_remaining_seconds(p, now=T0 + timedelta(minutes=30)), 1800)
        self.assertEqual(jail.no_cap_remaining_seconds(p, now=T0 + timedelta(minutes=61)), 0)


class TelemetryTests(JailTestBase):
    def test_telemetry_writes_jsonl_when_path_set(self):
        path = tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False).name
        try:
            jail.set_attack_log_path(path)
            p = make_player(level=5000)
            jail.record_attack(p, "evilcorp", 100, now=T0)
            jail.record_attack(p, "evilcorp", 100, now=T0 + timedelta(seconds=0.05))
            with open(path) as f:
                lines = [line for line in f.read().splitlines() if line]
            self.assertEqual(len(lines), 2)
            import json as _json
            first = _json.loads(lines[0])
            second = _json.loads(lines[1])
            self.assertEqual(first["user"], "alice")
            self.assertEqual(first["location"], "evilcorp")
            self.assertIsNone(first["gap"])  # first attack
            self.assertAlmostEqual(second["gap"], 0.05, places=3)
            self.assertTrue(second["violation"])
        finally:
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass
            jail.set_attack_log_path("")


class AutoclickerScenarioTests(JailTestBase):
    def test_autoclicker_jails_within_milliseconds(self):
        """A 20-clicks/sec auto-clicker (0.05s gaps) racks 3 strikes in 0.2s → jail.
        Matches the "wtf moment" design intent under the uniform 0.1s threshold."""
        p = make_player(username="loafageddon", level=5126)
        now = T0
        jailed_by_attack = None
        for i in range(5):
            r = jail.record_attack(p, "evilcorp", 100, now=now)
            if r.jailed:
                jailed_by_attack = i
                break
            now += timedelta(seconds=0.05)
        self.assertIsNotNone(jailed_by_attack, "should have hit jail in the loop")
        self.assertLessEqual(jailed_by_attack, 3)  # 1 baseline + 3 strikes
        self.assertTrue(jail.is_jailed(p, now=now))


if __name__ == "__main__":
    unittest.main(verbosity=2)
