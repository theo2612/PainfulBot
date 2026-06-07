"""Idle-hacking jobs: hack catalog + start / resolve logic.

Design source of truth: TWITCHACK_IDLE_HACKING_SPEC.md (§3 jobs, §6 catalog).

A "hack" is a timed job. `!run <id>` starts one (consuming a job slot); it
resolves when its timer elapses, paying out cash + rep (or failing — losing the
time). Phase 1 resolves lazily: `resolve_due_jobs()` is called whenever the
player next interacts. The data model is ready for a background ticker later.

Pure module — no Twitch/async dependencies — so the whole loop is unit-testable.
"""
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import items
from game import hardware


# Cash dropped per successful *click* (clicker tier). The bootstrap rule
# (spec §8): clicking must pay some cash or you could never afford your first
# rig, since idle hacks require hardware. Clicks stay cash-light; hacks pay more.
CLICK_CASH = 4


@dataclass(frozen=True)
class HackDef:
    """One runnable hack. Adding a hack is a single new row in HACK_DEFS."""
    id: str
    name: str
    category: str           # network | password | malware | web | social | exfil
    base_duration: int      # seconds, before clock/category speed multipliers
    success: float          # 0..1 chance of a payout
    cash: tuple             # (lo, hi) cash on success
    rep: tuple              # (lo, hi) rep on success (rep == points → drives level)
    level_req: int = 0
    location: str | None = None          # None = runnable anywhere
    hw_req: dict = field(default_factory=dict)  # {"gpu_power": N} / {"storage": N}


# ---------------------------------------------------------------------------
# Catalog. Phase 1: the four Single-Board Computer starter hacks (spec §6.1).
# All location=anywhere, gpu 0, low storage → SBC-legal. Cash-heavy split.
# ---------------------------------------------------------------------------
HACK_DEFS: dict[str, HackDef] = {
    "portscan": HackDef(
        id="portscan", name="Port scan", category="network",
        base_duration=12, success=0.95, cash=(6, 10), rep=(2, 4),
    ),
    "servicescan": HackDef(
        id="servicescan", name="Service scan", category="network",
        base_duration=36, success=0.92, cash=(20, 30), rep=(8, 12),
    ),
    "spearphish": HackDef(
        id="spearphish", name="Spear-phishing", category="social",
        base_duration=48, success=0.90, cash=(24, 36), rep=(10, 14),
    ),
    "credstuff": HackDef(
        id="credstuff", name="Credential stuffing", category="web",
        base_duration=144, success=0.88, cash=(75, 105), rep=(25, 35),
    ),
    # Exfil: long, high-pay data heists gated by bandwidth (+ storage to hold
    # the loot). The SBC (bandwidth 1, 16 GB) can't touch these; the Laptop
    # (bandwidth 4, 256 GB) runs them and its fat pipe also makes them faster.
    "dbexfil": HackDef(
        id="dbexfil", name="Database exfiltration", category="exfil",
        base_duration=300, success=0.85, cash=(120, 180), rep=(40, 55),
        hw_req={"bandwidth": 3, "storage": 64},
    ),
    # The big score: exfiltrate ALL of EvilCorp. Gated to a fat pipe + huge disk
    # → only the Desktop (bandwidth 8, 1 TB) can pull it; the Laptop's bandwidth
    # 4 / 256 GB can't. Long, big pay, riskier — a failed heist burns the time.
    "corpheist": HackDef(
        id="corpheist", name="Corporate data heist", category="exfil",
        base_duration=1200, success=0.80, cash=(400, 650), rep=(110, 150),
        hw_req={"bandwidth": 6, "storage": 512},
    ),
}


def get_hack(hack_id: str) -> HackDef | None:
    return HACK_DEFS.get(hack_id)


# ---------------------------------------------------------------------------
# Time helpers — ISO-8601 (timezone-aware UTC) on the wire, datetimes in code.
# Matches the rest of the Player time fields, which store ISO strings.
# ---------------------------------------------------------------------------
def _now(now: datetime | None) -> datetime:
    return now or datetime.now(timezone.utc)


def _to_iso(dt: datetime) -> str:
    return dt.isoformat()


def _from_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


# Exfil's baseline bandwidth — the gate. Bandwidth above this speeds exfil up
# (e.g. bandwidth 6 with EXFIL_BW_BASE 3 → exfil runs 2x faster).
EXFIL_BW_BASE = 3


def _category_speed(category: str, stats) -> float:
    """Per-category speed multiplier on top of clock. Exfil scales with
    bandwidth (a fat pipe moves stolen data faster). Password/crypto will scale
    with GPU later; for now a GPU only *unlocks* it, no speed bonus yet."""
    if category == "exfil":
        return max(1.0, stats.bandwidth / EXFIL_BW_BASE)
    return 1.0


# Wear & tear: condition lost per second of a hack's base_duration. So a 12s
# portscan wears ~0.5%, a 300s exfil ~12% — machines degrade over dozens of runs.
WEAR_RATE = 0.04


def duration_for(hack: HackDef, stats, condition: float = hardware.FULL_CONDITION) -> int:
    """Effective duration (seconds) for this hack on this machine.

    base / (clock * category_speed * condition_factor). On the SBC (clock 0.8) a
    12s base → 15s at full condition; a worn machine runs slower still.
    """
    speed = stats.clock * _category_speed(hack.category, stats) * hardware.condition_factor(condition)
    if speed <= 0:
        speed = 1.0
    return max(1, round(hack.base_duration / speed))


def wear_for(hack: HackDef) -> float:
    """How much condition a completed run of this hack costs the machine."""
    return hack.base_duration * WEAR_RATE


def _machine_meets(hack: HackDef, machine_id: str) -> tuple[bool, str]:
    """Whether a single machine's hardware can run this hack. Returns
    (ok, reason)."""
    s = hardware.machine_stats(machine_id)
    name = hardware.get_component(machine_id)
    name = name.name if name else machine_id
    need_gpu = hack.hw_req.get("gpu_power", 0)
    if need_gpu > s.gpu_power:
        return False, f"{name} can't run {hack.name} — needs a GPU."
    need_storage = hack.hw_req.get("storage", 0)
    if need_storage > s.storage:
        return False, f"{name} can't run {hack.name} — needs {need_storage} GB storage."
    need_bw = hack.hw_req.get("bandwidth", 0)
    if need_bw > s.bandwidth:
        return False, f"{name} can't run {hack.name} — needs more bandwidth (≥ {need_bw})."
    return True, ""


def resolve_machine(player, hack: HackDef, machine_id: str | None):
    """Pick/validate which machine runs this hack. With an explicit machine_id,
    validate it (owned, capable, free). Without one, auto-pick the fastest owned
    machine that can run it and has a free slot. Returns (machine_id, "") or
    (None, reason)."""
    owned = hardware.machines(player)
    if not owned:
        return None, "you need a rig first — open the Shop (🛒) to buy one."

    if machine_id:
        if machine_id not in owned:
            return None, "you don't own that machine."
        ok, reason = _machine_meets(hack, machine_id)
        if not ok:
            return None, reason
        if hardware.machine_free(player, machine_id) <= 0:
            comp = hardware.get_component(machine_id)
            return None, f"{comp.name if comp else machine_id} is busy — all its slots are full."
        return machine_id, ""

    # Auto-pick: capable + free machines, fastest (highest clock) first.
    capable = [m for m in owned if _machine_meets(hack, m)[0]]
    if not capable:
        return None, f"none of your machines can run {hack.name} yet — upgrade in the Shop."
    free = [m for m in capable if hardware.machine_free(player, m) > 0]
    if not free:
        return None, f"all machines that can run {hack.name} are busy."
    best = max(free, key=lambda m: hardware.machine_stats(m).clock)
    return best, ""


def can_run(player, hack_id: str, machine_id: str | None = None):
    """Return (ok, reason, machine_id). On success machine_id is the resolved
    machine the hack will run on; on failure it is None and reason is a
    player-facing string."""
    hack = HACK_DEFS.get(hack_id)
    if not hack:
        return False, f"unknown hack '{hack_id}'.", None
    if player.level < hack.level_req:
        return False, f"{hack.name} needs level {hack.level_req}.", None
    if hack.location and player.location != hack.location:
        return False, f"{hack.name} must be run from {hack.location}.", None
    resolved, reason = resolve_machine(player, hack, machine_id)
    if not resolved:
        return False, reason, None
    return True, "", resolved


def start_hack(player, hack_id: str, machine_id: str | None = None,
               now: datetime | None = None):
    """Start a hack on a machine. With no machine_id, auto-picks the fastest
    capable free machine. Returns (job_dict, seconds) on success, or
    (None, reason) on failure. The job records which machine it runs on and
    uses that machine's clock for its duration. Mutates player.jobs."""
    ok, reason, resolved = can_run(player, hack_id, machine_id)
    if not ok:
        return None, reason
    now = _now(now)
    hack = HACK_DEFS[hack_id]
    seconds = duration_for(hack, hardware.machine_stats(resolved),
                           hardware.condition_of(player, resolved))
    job = {
        "hack_id": hack_id,
        "machine": resolved,
        "started_at": _to_iso(now),
        "finishes_at": _to_iso(now + timedelta(seconds=seconds)),
    }
    if player.jobs is None:
        player.jobs = []
    player.jobs.append(job)
    return job, seconds


def _resolve_one(player, job: dict, rng) -> dict:
    """Resolve a single finished job, mutating player cash/points. Returns a
    result dict for the caller to surface on the feed."""
    hack = HACK_DEFS.get(job.get("hack_id"))
    if not hack:
        return {"hack_id": job.get("hack_id"), "name": job.get("hack_id"),
                "success": False, "cash": 0, "rep": 0}
    success = rng.random() < hack.success
    if not success:
        return {"hack_id": hack.id, "name": hack.name,
                "success": False, "cash": 0, "rep": 0}
    gross = rng.randint(*hack.cash)
    rep = rng.randint(*hack.rep)
    # Malicious "evil twin" items (e.g. Mnap) divert a slice of the payout to
    # the treasury. The caller credits the treasury with `skimmed` so this pure
    # module stays free of treasury/IO knowledge.
    net, skimmed = items.apply_cash_skim(player, gross)
    player.cash = getattr(player, "cash", 0) + net
    player.points += rep  # rep is points → caller runs check_level_up
    return {"hack_id": hack.id, "name": hack.name, "success": True,
            "cash": net, "gross_cash": gross, "skimmed": skimmed, "rep": rep}


def resolve_due_jobs(player, now: datetime | None = None, rng=random) -> list[dict]:
    """Resolve every job whose timer has elapsed. Mutates player (cash, points,
    jobs). Returns one result dict per resolved job (for the feed). Jobs still
    running are left in place. Banking rep does not level the player here — the
    caller runs helpers.check_level_up so leveling stays in one place."""
    now = _now(now)
    results: list[dict] = []
    remaining: list[dict] = []
    for job in player.jobs or []:
        finishes = _from_iso(job.get("finishes_at"))
        if finishes is not None and finishes <= now:
            results.append(_resolve_one(player, job, rng))
            # Running the job wears the machine that ran it (win or lose).
            hk = HACK_DEFS.get(job.get("hack_id"))
            if hk and job.get("machine"):
                hardware.apply_wear(player, job["machine"], wear_for(hk))
        else:
            remaining.append(job)
    player.jobs = remaining
    return results


def time_left(job: dict, now: datetime | None = None) -> int:
    """Seconds remaining on a job (never negative)."""
    now = _now(now)
    finishes = _from_iso(job.get("finishes_at"))
    if finishes is None:
        return 0
    return max(0, int((finishes - now).total_seconds()))
