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
        p = make_player(cash=120, rig=["sbc"], jobs=[{"hack_id": "portscan",
                        "started_at": "x", "finishes_at": "y"}])
        restored = Player.from_dict("alice", p.to_dict())
        self.assertEqual(restored.cash, 120)
        self.assertEqual(restored.rig, ["sbc"])
        self.assertEqual(restored.jobs[0]["hack_id"], "portscan")

    def test_empty_fields_omitted_from_dict(self):
        d = make_player().to_dict()
        self.assertNotIn("cash", d)
        self.assertNotIn("rig", d)
        self.assertNotIn("jobs", d)


class RigStatsTests(unittest.TestCase):
    def test_no_rig_has_no_job_slots(self):
        self.assertEqual(hardware.job_slots(make_player()), 0)

    def test_sbc_yields_exactly_one_slot(self):
        # 2 GB RAM is the bottleneck: min(threads 4, floor(2/2)=1) = 1.
        self.assertEqual(hardware.job_slots(make_player(rig=["sbc"])), 1)

    def test_sbc_stats(self):
        stats = hardware.rig_stats(make_player(rig=["sbc"]))
        self.assertEqual(stats.threads, 4)
        self.assertEqual(stats.memory, 2)
        self.assertEqual(stats.gpu_power, 0)


class BuyTests(unittest.TestCase):
    def test_cannot_afford(self):
        p = make_player(cash=50)
        comp, reason = hardware.buy_component(p, "sbc")
        self.assertIsNone(comp)
        self.assertIn("costs", reason)
        self.assertEqual(p.rig, [])
        self.assertEqual(p.cash, 50)  # not deducted on failure

    def test_successful_purchase_deducts_and_installs(self):
        p = make_player(cash=250)
        comp, reason = hardware.buy_component(p, "sbc")
        self.assertIsNotNone(comp)
        self.assertEqual(p.cash, 50)        # 250 - 200
        self.assertEqual(p.rig, ["sbc"])

    def test_cannot_buy_duplicate(self):
        p = make_player(cash=500, rig=["sbc"])
        comp, reason = hardware.buy_component(p, "sbc")
        self.assertIsNone(comp)
        self.assertIn("already own", reason)
        self.assertEqual(p.cash, 500)

    def test_unknown_component(self):
        comp, reason = hardware.buy_component(make_player(cash=999), "quantum_rig")
        self.assertIsNone(comp)


class DurationTests(unittest.TestCase):
    def test_pi_clock_slows_jobs(self):
        # base 12s on the SBC's 0.8 clock → 15s (spec §6.1).
        stats = hardware.rig_stats(make_player(rig=["sbc"]))
        self.assertEqual(hacks.duration_for(hacks.HACK_DEFS["portscan"], stats), 15)
        self.assertEqual(hacks.duration_for(hacks.HACK_DEFS["credstuff"], stats), 180)


class LaptopTierTests(unittest.TestCase):
    def test_laptop_yields_three_slots(self):
        # 6 GB → min(threads 6, floor(6/2)=3) = 3 — real concurrency.
        self.assertEqual(hardware.job_slots(make_player(rig=["laptop"])), 3)

    def test_laptop_runs_jobs_at_base_speed(self):
        # clock 1.0 → portscan at its 12s base (vs the SBC's 15s).
        stats = hardware.rig_stats(make_player(rig=["laptop"]))
        self.assertEqual(hacks.duration_for(hacks.HACK_DEFS["portscan"], stats), 12)

    def test_buying_laptop_deducts_cost(self):
        p = make_player(cash=1300)
        comp, reason = hardware.buy_component(p, "laptop")
        self.assertIsNotNone(comp)
        self.assertEqual(p.cash, 100)        # 1300 - 1200
        self.assertEqual(p.rig, ["laptop"])

    def test_can_run_three_concurrent_on_laptop(self):
        p = make_player(rig=["laptop"])
        self.assertIsNotNone(hacks.start_hack(p, "portscan")[0])
        self.assertIsNotNone(hacks.start_hack(p, "servicescan")[0])
        self.assertIsNotNone(hacks.start_hack(p, "spearphish")[0])
        # 4th exceeds the 3 slots.
        job, reason = hacks.start_hack(p, "credstuff")
        self.assertIsNone(job)
        self.assertIn("busy", reason)


class DesktopTierTests(unittest.TestCase):
    def test_desktop_yields_six_slots(self):
        # 12 GB → min(threads 8, floor(12/2)=6) = 6.
        self.assertEqual(hardware.machine_slots("desktop"), 6)

    def test_desktop_stats(self):
        s = hardware.machine_stats("desktop")
        self.assertEqual(s.bandwidth, 8)
        self.assertEqual(s.storage, 1000)
        self.assertEqual(s.clock, 1.3)

    def test_buying_desktop_deducts_cost(self):
        p = make_player(cash=6500)
        comp, reason = hardware.buy_component(p, "desktop")
        self.assertIsNotNone(comp)
        self.assertEqual(p.cash, 500)        # 6500 - 6000
        self.assertEqual(p.rig, ["desktop"])

    def test_three_tiers_sum_to_ten_slots(self):
        p = make_player(rig=["sbc", "laptop", "desktop"])
        self.assertEqual(hardware.total_slots(p), 10)   # 1 + 3 + 6

    def test_desktop_runs_exfil_fast(self):
        # bandwidth 8 → exfil factor 8/3; with clock 1.3 the 300s dbexfil
        # finishes much quicker than on the laptop.
        stats = hardware.machine_stats("desktop")
        secs = hacks.duration_for(hacks.HACK_DEFS["dbexfil"], stats)
        self.assertLess(secs, 120)


class PerMachineTests(unittest.TestCase):
    """Per-machine rigs: each owned machine has its own slots + speed; total
    concurrency is the sum; a job is tagged to the machine it runs on."""

    def test_total_slots_is_the_sum_of_owned_machines(self):
        p = make_player(rig=["sbc", "laptop"])
        self.assertEqual(hardware.total_slots(p), 4)   # sbc 1 + laptop 3
        self.assertEqual(hardware.job_slots(p), 4)
        self.assertEqual(hardware.machine_slots("sbc"), 1)
        self.assertEqual(hardware.machine_slots("laptop"), 3)

    def test_job_records_its_machine(self):
        p = make_player(rig=["sbc", "laptop"])
        job, _ = hacks.start_hack(p, "portscan", machine_id="sbc")
        self.assertEqual(job["machine"], "sbc")
        self.assertEqual(hardware.jobs_on(p, "sbc"), 1)
        self.assertEqual(hardware.jobs_on(p, "laptop"), 0)

    def test_speed_depends_on_the_chosen_machine(self):
        p = make_player(rig=["sbc", "laptop"])
        _, sbc_secs = hacks.start_hack(p, "portscan", machine_id="sbc")
        _, lap_secs = hacks.start_hack(p, "portscan", machine_id="laptop")
        self.assertEqual(sbc_secs, 15)   # sbc clock 0.8
        self.assertEqual(lap_secs, 12)   # laptop clock 1.0

    def test_auto_pick_chooses_the_fastest_free_machine(self):
        # No machine specified → fastest (laptop, clock 1.0) over the sbc (0.8).
        p = make_player(rig=["sbc", "laptop"])
        job, _ = hacks.start_hack(p, "portscan")
        self.assertEqual(job["machine"], "laptop")

    def test_can_fill_each_machine_independently(self):
        p = make_player(rig=["sbc", "laptop"])
        # 1 on the sbc + 3 on the laptop = 4 concurrent; a 5th has nowhere to go.
        self.assertIsNotNone(hacks.start_hack(p, "portscan", machine_id="sbc")[0])
        for _ in range(3):
            self.assertIsNotNone(hacks.start_hack(p, "portscan", machine_id="laptop")[0])
        self.assertEqual(len(p.jobs), 4)
        job, reason = hacks.start_hack(p, "portscan")
        self.assertIsNone(job)
        self.assertIn("busy", reason)

    def test_explicit_busy_machine_rejected_even_if_another_is_free(self):
        p = make_player(rig=["sbc", "laptop"])
        hacks.start_hack(p, "portscan", machine_id="sbc")  # fills the sbc (1 slot)
        job, reason = hacks.start_hack(p, "portscan", machine_id="sbc")
        self.assertIsNone(job)
        self.assertIn("busy", reason)

    def test_cannot_run_on_a_machine_you_do_not_own(self):
        p = make_player(rig=["sbc"])
        job, reason = hacks.start_hack(p, "portscan", machine_id="laptop")
        self.assertIsNone(job)
        self.assertIn("don't own", reason)


class ExfilBandwidthTests(unittest.TestCase):
    """bandwidth stat gates + speeds the exfil category."""

    def test_machines_have_bandwidth(self):
        self.assertEqual(hardware.machine_stats("sbc").bandwidth, 1)
        self.assertEqual(hardware.machine_stats("laptop").bandwidth, 4)

    def test_sbc_cannot_run_exfil(self):
        # SBC: bandwidth 1 (< 3) and 16 GB (< 64) — doubly gated out.
        job, reason = hacks.start_hack(make_player(rig=["sbc"]), "dbexfil", machine_id="sbc")
        self.assertIsNone(job)
        self.assertTrue("bandwidth" in reason or "storage" in reason)

    def test_laptop_can_run_exfil(self):
        job, secs = hacks.start_hack(make_player(rig=["laptop"]), "dbexfil", machine_id="laptop")
        self.assertIsNotNone(job)
        self.assertEqual(job["machine"], "laptop")

    def test_exfil_auto_picks_the_capable_machine(self):
        # Owning both, only the laptop can run exfil → auto-pick must choose it.
        p = make_player(rig=["sbc", "laptop"])
        job, _ = hacks.start_hack(p, "dbexfil")
        self.assertEqual(job["machine"], "laptop")

    def test_bandwidth_speeds_exfil(self):
        # base 300 / (clock 1.0 * bandwidth 4/3) = 225s on the laptop.
        stats = hardware.machine_stats("laptop")
        self.assertEqual(hacks.duration_for(hacks.HACK_DEFS["dbexfil"], stats), 225)

    def test_non_exfil_unaffected_by_bandwidth(self):
        # A network hack ignores bandwidth — laptop clock 1.0 → portscan 12s.
        stats = hardware.machine_stats("laptop")
        self.assertEqual(hacks.duration_for(hacks.HACK_DEFS["portscan"], stats), 12)


class WearAndRepairTests(unittest.TestCase):
    """Machines wear with use (→ slower) and are repaired with cash (pricier
    each time)."""

    def test_condition_defaults_to_full(self):
        self.assertEqual(hardware.condition_of(make_player(rig=["sbc"]), "sbc"), 100.0)

    def test_condition_factor_curve(self):
        self.assertEqual(hardware.condition_factor(100), 1.0)
        self.assertEqual(hardware.condition_factor(0), 0.5)
        self.assertEqual(hardware.condition_factor(50), 0.75)

    def test_running_a_hack_wears_its_machine(self):
        p = make_player(rig=["laptop"])
        now = datetime(2026, 6, 7, 12, 0, 0, tzinfo=timezone.utc)
        hacks.start_hack(p, "portscan", machine_id="laptop", now=now)
        hacks.resolve_due_jobs(p, now=now + timedelta(seconds=60), rng=FakeRandom(0.0, 7))
        # portscan wear = 12 * 0.04 = 0.48
        self.assertAlmostEqual(hardware.condition_of(p, "laptop"), 99.52, places=2)

    def test_low_condition_slows_hacks(self):
        stats = hardware.machine_stats("laptop")
        full = hacks.duration_for(hacks.HACK_DEFS["portscan"], stats, 100)
        worn = hacks.duration_for(hacks.HACK_DEFS["portscan"], stats, 50)
        self.assertEqual(full, 12)
        self.assertEqual(worn, 16)   # 12 / 0.75
        self.assertGreater(worn, full)

    def test_repair_cost_scales_and_escalates(self):
        p = make_player(rig=["laptop"], cash=10000)
        p.conditions = {"laptop": 50.0}           # 50 damage
        self.assertEqual(hardware.repair_cost(p, "laptop"), 60)   # 1200*0.1*0.5
        hardware.repair(p, "laptop")              # repairs_done → 1, condition → 100
        self.assertEqual(hardware.condition_of(p, "laptop"), 100.0)
        p.conditions = {"laptop": 50.0}           # damage it again
        self.assertEqual(hardware.repair_cost(p, "laptop"), 90)   # 60 * 1.5

    def test_repair_deducts_cash_and_restores(self):
        p = make_player(rig=["laptop"], cash=100)
        p.conditions = {"laptop": 50.0}
        cost, reason = hardware.repair(p, "laptop")
        self.assertEqual(cost, 60)
        self.assertEqual(p.cash, 40)
        self.assertEqual(hardware.condition_of(p, "laptop"), 100.0)

    def test_repair_blocked_when_broke(self):
        p = make_player(rig=["laptop"], cash=10)
        p.conditions = {"laptop": 50.0}
        cost, reason = hardware.repair(p, "laptop")
        self.assertIsNone(cost)
        self.assertIn("costs", reason)
        self.assertEqual(p.cash, 10)              # not deducted

    def test_repair_at_full_is_rejected(self):
        p = make_player(rig=["laptop"], cash=100)
        cost, reason = hardware.repair(p, "laptop")
        self.assertIsNone(cost)
        self.assertIn("perfect", reason)


class StartHackTests(unittest.TestCase):
    def test_cannot_run_without_a_rig(self):
        job, reason = hacks.start_hack(make_player(), "portscan")
        self.assertIsNone(job)
        self.assertIn("rig", reason)

    def test_start_appends_job_and_returns_eta(self):
        p = make_player(rig=["sbc"])
        now = datetime(2026, 5, 30, 12, 0, 0, tzinfo=timezone.utc)
        job, seconds = hacks.start_hack(p, "portscan", now=now)
        self.assertEqual(seconds, 15)
        self.assertEqual(len(p.jobs), 1)
        self.assertEqual(p.jobs[0]["hack_id"], "portscan")

    def test_one_slot_means_one_concurrent_job(self):
        p = make_player(rig=["sbc"])
        hacks.start_hack(p, "portscan")
        job, reason = hacks.start_hack(p, "servicescan")
        self.assertIsNone(job)
        self.assertIn("busy", reason)
        self.assertEqual(len(p.jobs), 1)

    def test_unknown_hack_rejected(self):
        job, reason = hacks.start_hack(make_player(rig=["sbc"]), "nope")
        self.assertIsNone(job)


class ResolveTests(unittest.TestCase):
    def test_unfinished_job_is_left_running(self):
        p = make_player(rig=["sbc"])
        now = datetime(2026, 5, 30, 12, 0, 0, tzinfo=timezone.utc)
        hacks.start_hack(p, "credstuff", now=now)  # 180s
        results = hacks.resolve_due_jobs(p, now=now + timedelta(seconds=30))
        self.assertEqual(results, [])
        self.assertEqual(len(p.jobs), 1)

    def test_finished_job_success_pays_cash_and_rep(self):
        p = make_player(rig=["sbc"])
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
        p = make_player(rig=["sbc"])
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
        p = make_player(rig=["sbc"])
        past = datetime.now(timezone.utc) - timedelta(seconds=30)
        hacks.start_hack(p, "portscan", now=past)  # finished ~15s ago
        results = hacks.resolve_due_jobs(p, rng=FakeRandom(0.0, 7))  # no now arg
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["success"])
        self.assertEqual(p.jobs, [])

    def test_resolution_frees_the_slot_for_a_new_hack(self):
        p = make_player(rig=["sbc"])
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
