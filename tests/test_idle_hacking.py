"""Tests for Phase 1 idle hacking — rig stats, buying hardware, starting hacks,
job-slot limits, durations, and lazy job resolution.

Design source: TWITCHACK_IDLE_HACKING_SPEC.md (§3–§6).

Run from the repo root:
    python3 -m unittest tests.test_idle_hacking -v
"""
import os
import sys
import random
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from playerdata import Player
from game import hardware, hacks


def make_player(level=1, cash=0, rig=None, jobs=None):
    return Player(
        username="alice", level=level, health=50, items=[],
        location="home", points=0, started=0,
        cash=cash, rig=rig, jobs=jobs,
    )


class FakeRandom:
    """Deterministic stand-in for the random module used by resolve_due_jobs."""
    def __init__(self, roll, value):
        self._roll = roll      # what random() returns (success if < hack.success)
        self._value = value    # what randint() returns

    def random(self):
        return self._roll

    def randint(self, lo, hi):
        return self._value


class PersistenceTests(unittest.TestCase):
    def test_new_fields_default_empty(self):
        p = make_player()
        self.assertEqual(p.cash, 0)
        self.assertEqual(p.rig, [])
        self.assertEqual(p.jobs, [])

    def test_round_trip_through_dict(self):
        p = make_player(cash=120, rig=["rpi"], jobs=[{"hack_id": "portscan",
                        "started_at": "x", "finishes_at": "y"}])
        restored = Player.from_dict("alice", p.to_dict())
        self.assertEqual(restored.cash, 120)
        self.assertEqual(restored.rig, ["rpi"])
        self.assertEqual(restored.jobs[0]["hack_id"], "portscan")

    def test_empty_fields_omitted_from_dict(self):
        d = make_player().to_dict()
        self.assertNotIn("cash", d)
        self.assertNotIn("rig", d)
        self.assertNotIn("jobs", d)


class RigStatsTests(unittest.TestCase):
    def test_no_rig_has_no_job_slots(self):
        self.assertEqual(hardware.job_slots(make_player()), 0)

    def test_raspberry_pi_yields_exactly_one_slot(self):
        # 2 GB RAM is the bottleneck: min(threads 4, floor(2/2)=1) = 1.
        self.assertEqual(hardware.job_slots(make_player(rig=["rpi"])), 1)

    def test_raspberry_pi_stats(self):
        stats = hardware.rig_stats(make_player(rig=["rpi"]))
        self.assertEqual(stats.threads, 4)
        self.assertEqual(stats.memory, 2)
        self.assertEqual(stats.gpu_power, 0)


class BuyTests(unittest.TestCase):
    def test_cannot_afford(self):
        p = make_player(cash=50)
        comp, reason = hardware.buy_component(p, "rpi")
        self.assertIsNone(comp)
        self.assertIn("costs", reason)
        self.assertEqual(p.rig, [])
        self.assertEqual(p.cash, 50)  # not deducted on failure

    def test_successful_purchase_deducts_and_installs(self):
        p = make_player(cash=250)
        comp, reason = hardware.buy_component(p, "rpi")
        self.assertIsNotNone(comp)
        self.assertEqual(p.cash, 50)        # 250 - 200
        self.assertEqual(p.rig, ["rpi"])

    def test_cannot_buy_duplicate(self):
        p = make_player(cash=500, rig=["rpi"])
        comp, reason = hardware.buy_component(p, "rpi")
        self.assertIsNone(comp)
        self.assertIn("already own", reason)
        self.assertEqual(p.cash, 500)

    def test_unknown_component(self):
        comp, reason = hardware.buy_component(make_player(cash=999), "quantum_rig")
        self.assertIsNone(comp)


class DurationTests(unittest.TestCase):
    def test_pi_clock_slows_jobs(self):
        # base 12s on the Pi's 0.8 clock → 15s (spec §6.1).
        stats = hardware.rig_stats(make_player(rig=["rpi"]))
        self.assertEqual(hacks.duration_for(hacks.HACK_DEFS["portscan"], stats), 15)
        self.assertEqual(hacks.duration_for(hacks.HACK_DEFS["credstuff"], stats), 180)


class StartHackTests(unittest.TestCase):
    def test_cannot_run_without_a_rig(self):
        job, reason = hacks.start_hack(make_player(), "portscan")
        self.assertIsNone(job)
        self.assertIn("rig", reason)

    def test_start_appends_job_and_returns_eta(self):
        p = make_player(rig=["rpi"])
        now = datetime(2026, 5, 30, 12, 0, 0, tzinfo=timezone.utc)
        job, seconds = hacks.start_hack(p, "portscan", now=now)
        self.assertEqual(seconds, 15)
        self.assertEqual(len(p.jobs), 1)
        self.assertEqual(p.jobs[0]["hack_id"], "portscan")

    def test_one_slot_means_one_concurrent_job(self):
        p = make_player(rig=["rpi"])
        hacks.start_hack(p, "portscan")
        job, reason = hacks.start_hack(p, "servicescan")
        self.assertIsNone(job)
        self.assertIn("busy", reason)
        self.assertEqual(len(p.jobs), 1)

    def test_unknown_hack_rejected(self):
        job, reason = hacks.start_hack(make_player(rig=["rpi"]), "nope")
        self.assertIsNone(job)


class ResolveTests(unittest.TestCase):
    def test_unfinished_job_is_left_running(self):
        p = make_player(rig=["rpi"])
        now = datetime(2026, 5, 30, 12, 0, 0, tzinfo=timezone.utc)
        hacks.start_hack(p, "credstuff", now=now)  # 180s
        results = hacks.resolve_due_jobs(p, now=now + timedelta(seconds=30))
        self.assertEqual(results, [])
        self.assertEqual(len(p.jobs), 1)

    def test_finished_job_success_pays_cash_and_rep(self):
        p = make_player(rig=["rpi"])
        now = datetime(2026, 5, 30, 12, 0, 0, tzinfo=timezone.utc)
        hacks.start_hack(p, "portscan", now=now)
        # roll 0.0 < success → win; randint pegged to 7
        rng = FakeRandom(roll=0.0, value=7)
        results = hacks.resolve_due_jobs(p, now=now + timedelta(seconds=20), rng=rng)
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["success"])
        self.assertEqual(p.cash, 7)
        self.assertEqual(p.points, 7)
        self.assertEqual(p.jobs, [])  # slot freed

    def test_finished_job_failure_pays_nothing(self):
        p = make_player(rig=["rpi"])
        now = datetime(2026, 5, 30, 12, 0, 0, tzinfo=timezone.utc)
        hacks.start_hack(p, "portscan", now=now)
        rng = FakeRandom(roll=0.999, value=7)  # roll >= success → fail
        results = hacks.resolve_due_jobs(p, now=now + timedelta(seconds=20), rng=rng)
        self.assertFalse(results[0]["success"])
        self.assertEqual(p.cash, 0)
        self.assertEqual(p.points, 0)
        self.assertEqual(p.jobs, [])  # still consumed the time

    def test_past_due_job_resolves_with_realtime_now(self):
        # The background ticker calls resolve_due_jobs() with no `now`, relying
        # on datetime.now(timezone.utc) comparing cleanly against the job's
        # timezone-aware finishes_at. Simulate a job that already finished.
        p = make_player(rig=["rpi"])
        past = datetime.now(timezone.utc) - timedelta(seconds=30)
        hacks.start_hack(p, "portscan", now=past)  # finished ~15s ago
        results = hacks.resolve_due_jobs(p, rng=FakeRandom(0.0, 7))  # no now arg
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["success"])
        self.assertEqual(p.jobs, [])

    def test_resolution_frees_the_slot_for_a_new_hack(self):
        p = make_player(rig=["rpi"])
        now = datetime(2026, 5, 30, 12, 0, 0, tzinfo=timezone.utc)
        hacks.start_hack(p, "portscan", now=now)
        hacks.resolve_due_jobs(p, now=now + timedelta(seconds=20),
                               rng=FakeRandom(0.0, 7))
        job, reason = hacks.start_hack(p, "servicescan", now=now + timedelta(seconds=21))
        self.assertIsNotNone(job)


class CommandNameCollisionRegression(unittest.TestCase):
    """Regression: a command METHOD named `run` shadowed twitchio's Bot.run()
    — the blocking entry point called at module load — so `bot.run()` invoked
    the Command instead of starting the bot, crash-looping on boot.

    Bot.run() internally calls self.connect()/self.close() (NOT self.start(),
    which is why the long-standing `!start` command is harmless). Any command
    method sharing a name in that startup chain breaks boot. Guard against it by
    parsing the source — no heavyweight import of PainfulBot required.
    """
    # twitchio Bot.run()'s call chain. Shadowing any of these with a command
    # method name prevents the bot from starting. `start` is intentionally NOT
    # here: run() never calls it, so the existing !start command is safe.
    RESERVED = {"run", "connect", "close"}

    def _command_method_names(self):
        import re
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "PainfulBot.py")
        with open(path, encoding="utf-8") as f:
            src = f.read()
        # @commands.command(...) immediately followed by `async def <name>(`.
        return re.findall(r"@commands\.command\([^)]*\)\s+async def (\w+)\s*\(", src)

    def test_no_command_shadows_bot_startup_methods(self):
        names = self._command_method_names()
        self.assertIn("run_hack", names, "expected the renamed !run handler to be present")
        collisions = sorted(set(names) & self.RESERVED)
        self.assertEqual(
            collisions, [],
            f"command method(s) {collisions} shadow twitchio Bot.run()'s startup "
            f"chain and will crash-loop the bot on boot. Rename the method (keep "
            f"the user-facing name via the decorator's name=).",
        )


if __name__ == "__main__":
    unittest.main()
