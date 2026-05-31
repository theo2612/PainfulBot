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

from game.hardware import rig_stats


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


def _category_speed(category: str, stats) -> float:
    """Per-category speed multiplier. Only crypto/password is GPU-accelerated;
    everything else runs at clock speed. GPU scaling lands with the GPU tier
    (Phase 3) — for now a GPU just unlocks `password`, no speed bonus yet."""
    return 1.0


def duration_for(hack: HackDef, stats) -> int:
    """Effective duration (seconds) for this hack on this rig.

    base / (clock * category_speed). On the SBC (clock 0.8) a 12s base → 15s.
    """
    speed = stats.clock * _category_speed(hack.category, stats)
    if speed <= 0:
        speed = 1.0
    return max(1, round(hack.base_duration / speed))


def can_run(player, hack_id: str) -> tuple[bool, str]:
    """Return (ok, reason). `reason` is a player-facing string on failure."""
    hack = HACK_DEFS.get(hack_id)
    if not hack:
        return False, f"unknown hack '{hack_id}'. Try !run to list hacks."

    stats = rig_stats(player)
    slots = stats.job_slots()
    if slots <= 0:
        return False, "you need a rig first — !buy sbc to get a Single-Board Computer."
    if player.level < hack.level_req:
        return False, f"{hack.name} needs level {hack.level_req}."
    need_gpu = hack.hw_req.get("gpu_power", 0)
    if need_gpu > stats.gpu_power:
        return False, f"{hack.name} needs a GPU (gpu_power ≥ {need_gpu})."
    need_storage = hack.hw_req.get("storage", 0)
    if need_storage > stats.storage:
        return False, f"{hack.name} needs more storage (≥ {need_storage} GB)."
    if hack.location and player.location != hack.location:
        return False, f"{hack.name} must be run from {hack.location}."
    if len(player.jobs or []) >= slots:
        return False, f"all {slots} job slot(s) busy — wait or check !jobs."
    return True, ""


def start_hack(player, hack_id: str, now: datetime | None = None):
    """Start a hack if allowed. Returns (job_dict, seconds) on success, or
    (None, reason) on failure. Mutates player.jobs."""
    ok, reason = can_run(player, hack_id)
    if not ok:
        return None, reason
    now = _now(now)
    hack = HACK_DEFS[hack_id]
    seconds = duration_for(hack, rig_stats(player))
    job = {
        "hack_id": hack_id,
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
    cash = rng.randint(*hack.cash)
    rep = rng.randint(*hack.rep)
    player.cash = getattr(player, "cash", 0) + cash
    player.points += rep  # rep is points → caller runs check_level_up
    return {"hack_id": hack.id, "name": hack.name,
            "success": True, "cash": cash, "rep": rep}


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
