"""Idle-hacking hardware: component catalog + rig stat aggregation.

Design source of truth: TWITCHACK_IDLE_HACKING_SPEC.md (§4 rig model, §5 catalog).

A player owns a `rig` — a list of installed component ids. Components aggregate
into a single `RigStats` profile that the job system (game/hacks.py) reads. The
whole game reads the aggregate; nothing branches on which component you own.

Phase 1 ships exactly one component: the Single-Board Computer prebuilt. The
aggregation already handles the general (parts-build) case so later phases add a
row, not a code path.

Hardware is brand-neutral by design: the `id` is an internal/command handle and
the `name` is a separate display layer, so a name can be swapped (e.g. for a
sponsor) without touching logic or persisted data — only `id` is stored on a
player's rig.
"""
from dataclasses import dataclass, field, replace

# GB of RAM each concurrent job consumes (spec §4.2). This is the knob that makes
# you need BOTH compute and memory: job_slots is gated by min(threads, mem/2).
MEM_PER_JOB = 2


@dataclass(frozen=True)
class RigStats:
    """Aggregate capability profile the job system reads."""
    threads: int = 0
    memory: int = 0      # "GB"
    storage: int = 0     # "GB"
    gpu_power: int = 0   # crypto/cracking acceleration; 0 = no GPU
    clock: float = 1.0   # general speed multiplier (higher = faster)
    bandwidth: int = 0   # network throughput; gates + speeds exfil hacks

    def job_slots(self) -> int:
        """Max concurrent jobs. Needs both compute (threads) and memory.

        `min(threads, floor(memory / MEM_PER_JOB))` — a 16-thread CPU with 2 GB
        RAM still runs only 1 job, which is why you buy RAM *and* a CPU.
        """
        if self.threads <= 0 or self.memory < MEM_PER_JOB:
            return 0
        return max(0, min(self.threads, self.memory // MEM_PER_JOB))


@dataclass(frozen=True)
class Component:
    """A buyable piece of hardware. Adding one is a single new row here."""
    id: str
    name: str
    kind: str            # cpu | ram | storage | gpu | motherboard | case | psu | prebuilt
    cost: int            # cash
    level_req: int = 0
    stats: RigStats = field(default_factory=RigStats)
    desc: str = ""       # short "what it does" line for the shop


# ---------------------------------------------------------------------------
# Catalog of prebuilt rigs. Brand-neutral names. See spec §5.1.
#
# Tuning note: stats aren't shown to players, so prebuilt threads/memory are
# chosen to hit a target job-slot count via min(threads, memory//2), not for
# spec-sheet realism. Progression: SBC 1 slot → Laptop 3 slots → (future)
# custom tower scaling higher.
# ---------------------------------------------------------------------------
COMPONENTS: dict[str, Component] = {
    "sbc": Component(
        id="sbc",
        name="Single-Board Computer",
        kind="prebuilt",
        cost=200,
        level_req=1,
        # 2 GB → exactly 1 job slot (min(4, 2//2)=1). RAM is soldered on these
        # boards, so it can't be expanded — you graduate to a bigger machine for
        # concurrency. clock 0.8 = jobs run 1.25x slower than base. 16 GB card
        # and gpu 0 lock it out of malware/exfil and crypto/cracking.
        stats=RigStats(threads=4, memory=2, storage=16, gpu_power=0, clock=0.8,
                       bandwidth=1),
        desc="Your first rig. Runs 1 hack at a time.",
    ),
    "laptop": Component(
        id="laptop",
        name="Laptop",
        kind="prebuilt",
        cost=1200,
        level_req=1,
        # 6 GB → 3 job slots (min(6, 6//2)=3): real concurrency, a 3x jump from
        # the SBC. clock 1.0 = jobs at base speed (~20% faster than the SBC's
        # 0.8). 256 GB storage opens room for future storage-gated hacks; a
        # token iGPU (gpu_power 1) is a toe-hold for entry-level cracking later.
        stats=RigStats(threads=6, memory=6, storage=256, gpu_power=1, clock=1.0,
                       bandwidth=4),
        desc="3 hacks at once, ~20% faster, lots of storage. Fat pipe → unlocks data exfil.",
    ),
    "desktop": Component(
        id="desktop",
        name="Desktop",
        kind="prebuilt",
        cost=6000,
        level_req=1,
        # 12 GB → 6 job slots (min(8, 12//2)=6): heavy parallelism. clock 1.3 =
        # ~30% faster than base; bandwidth 8 makes exfil rip; 1 TB storage and a
        # real GPU (4) set up future malware/cracking content.
        stats=RigStats(threads=8, memory=12, storage=1000, gpu_power=4, clock=1.3,
                       bandwidth=8),
        desc="6 hacks at once, fast clock, fat pipe + 1 TB disk. The heavy iron.",
    ),
}


def get_component(component_id: str) -> Component | None:
    return COMPONENTS.get(component_id)


def rig_stats(player) -> RigStats:
    """Aggregate a player's installed components into one RigStats.

    A prebuilt defines the whole rig (no mixing). Parts (Phase 3) sum their
    contributions. No rig at all → empty stats (clicker-only, 0 job slots).
    """
    rig = getattr(player, "rig", None) or []
    owned = [COMPONENTS[c] for c in rig if c in COMPONENTS]
    if not owned:
        return RigStats()

    prebuilts = [c for c in owned if c.kind == "prebuilt"]
    if prebuilts:
        # The strongest prebuilt (by slots, then storage) is your machine.
        best = max(prebuilts, key=lambda c: (c.stats.job_slots(), c.stats.storage))
        return best.stats

    # Parts build (Phase 3). Sum capacity; take the best clock. Provisional —
    # real part interactions (PSU draw, sockets) are a later phase.
    return RigStats(
        threads=sum(c.stats.threads for c in owned),
        memory=sum(c.stats.memory for c in owned),
        storage=sum(c.stats.storage for c in owned),
        gpu_power=sum(c.stats.gpu_power for c in owned),
        clock=max((c.stats.clock for c in owned), default=1.0),
    )


# ---------------------------------------------------------------------------
# Per-machine model (spec §4 / DEV_BACKLOG). Each owned machine is its own
# workstation with its own slots AND its own clock speed. A hack runs on one
# machine; total concurrency is the sum across machines. (For now every owned
# component is a standalone prebuilt machine; later, custom-tower parts will
# assemble into a single 'tower' machine.)
# ---------------------------------------------------------------------------
def machines(player) -> list[str]:
    """Owned component ids that are standalone machines (prebuilts)."""
    rig = getattr(player, "rig", None) or []
    return [c for c in rig if c in COMPONENTS and COMPONENTS[c].kind == "prebuilt"]


def machine_stats(machine_id: str) -> RigStats:
    """The RigStats of a single machine (a prebuilt's own stats)."""
    comp = COMPONENTS.get(machine_id)
    return comp.stats if comp else RigStats()


def machine_slots(machine_id: str) -> int:
    """How many concurrent jobs this one machine can run."""
    return machine_stats(machine_id).job_slots()


def jobs_on(player, machine_id: str) -> int:
    """How many of the player's running jobs are assigned to this machine."""
    return sum(1 for j in (getattr(player, "jobs", None) or [])
               if j.get("machine") == machine_id)


def machine_free(player, machine_id: str) -> int:
    """Free job slots remaining on this machine (never negative)."""
    return max(0, machine_slots(machine_id) - jobs_on(player, machine_id))


def total_slots(player) -> int:
    """Total concurrent jobs across all owned machines (the sum)."""
    return sum(machine_slots(m) for m in machines(player))


def job_slots(player) -> int:
    """Total concurrent-job capacity across all owned machines."""
    return total_slots(player)


# ---------------------------------------------------------------------------
# Wear & tear (DEV_BACKLOG). Each owned machine has a condition (100 → 0) that
# drops as it runs hacks. Low condition → slower hacks (the gentle consequence).
# Repairs restore it but get pricier each time (soft obsolescence). All numbers
# are tunable.
# ---------------------------------------------------------------------------
FULL_CONDITION = 100.0
MIN_CONDITION_SPEED = 0.5     # a fully-worn machine runs at half speed
REPAIR_COST_FRACTION = 0.1    # full repair (0→100) costs 10% of machine value…
REPAIR_ESCALATION = 0.5       # …+50% per prior repair on that machine


def condition_of(player, machine_id: str) -> float:
    """A machine's current condition (defaults to full for machines never worn)."""
    return float((getattr(player, "conditions", None) or {}).get(machine_id, FULL_CONDITION))


def condition_factor(condition: float) -> float:
    """Speed multiplier from condition: 1.0 at full, MIN_CONDITION_SPEED at 0."""
    c = max(0.0, min(FULL_CONDITION, condition))
    return MIN_CONDITION_SPEED + (1.0 - MIN_CONDITION_SPEED) * (c / FULL_CONDITION)


def apply_wear(player, machine_id: str, amount: float) -> float:
    """Reduce a machine's condition by `amount` (floored at 0). Returns the new
    condition. No-op for unknown machines."""
    if machine_id not in COMPONENTS or amount <= 0:
        return condition_of(player, machine_id)
    if player.conditions is None:
        player.conditions = {}
    new = max(0.0, condition_of(player, machine_id) - amount)
    player.conditions[machine_id] = new
    return new


def repair_cost(player, machine_id: str) -> int:
    """Cash to fully repair a machine: scales with its value, the damage to
    restore, and how many times it's already been repaired (pricier each time)."""
    comp = COMPONENTS.get(machine_id)
    if not comp:
        return 0
    damage = FULL_CONDITION - condition_of(player, machine_id)
    if damage <= 0:
        return 0
    prior = int((getattr(player, "repairs", None) or {}).get(machine_id, 0))
    base = comp.cost * REPAIR_COST_FRACTION * (damage / FULL_CONDITION)
    return max(1, round(base * (1 + prior * REPAIR_ESCALATION)))


def repair(player, machine_id: str):
    """Repair a machine to full condition for cash. Returns (cost, "") on success
    (cash deducted, condition restored, repair count bumped) or (None, reason)."""
    comp = COMPONENTS.get(machine_id)
    if not comp or machine_id not in machines(player):
        return None, "you don't own that machine."
    if condition_of(player, machine_id) >= FULL_CONDITION:
        return None, f"{comp.name} is already in perfect condition."
    cost = repair_cost(player, machine_id)
    cash = getattr(player, "cash", 0)
    if cash < cost:
        return None, f"repairing {comp.name} costs {cost} cash — you have {cash}."
    player.cash = cash - cost
    if player.conditions is None:
        player.conditions = {}
    if player.repairs is None:
        player.repairs = {}
    player.conditions[machine_id] = FULL_CONDITION
    player.repairs[machine_id] = int(player.repairs.get(machine_id, 0)) + 1
    return cost, ""


# ---------------------------------------------------------------------------
# AIO cooling + overclock (DEV_BACKLOG). Cooling is a per-machine part; with it
# installed you can overclock that machine: hacks run faster but it wears faster
# (more heat). A risk/reward that feeds the repair sink. All numbers tunable.
# ---------------------------------------------------------------------------
COOLING_COST_FRACTION = 0.15  # cooling costs 15% of the machine's value
OC_CLOCK_MULT = 1.5           # overclock → 1.5x clock (faster hacks)
OC_WEAR_MULT = 2.5            # …but wears 2.5x faster while overclocked


def has_cooling(player, machine_id: str) -> bool:
    return machine_id in (getattr(player, "cooling", None) or [])


def overclock_active(player, machine_id: str) -> bool:
    """Overclock only counts when cooling is also installed (defensive)."""
    return (machine_id in (getattr(player, "overclock", None) or [])
            and has_cooling(player, machine_id))


def cooling_cost(machine_id: str) -> int:
    comp = COMPONENTS.get(machine_id)
    return max(1, round(comp.cost * COOLING_COST_FRACTION)) if comp else 0


def effective_stats(player, machine_id: str) -> RigStats:
    """A machine's stats with overclock applied (boosted clock). Used for hack
    timing; gating still uses the base machine_stats."""
    s = machine_stats(machine_id)
    if overclock_active(player, machine_id):
        s = replace(s, clock=round(s.clock * OC_CLOCK_MULT, 3))
    return s


def install_cooling(player, machine_id: str):
    """Install AIO cooling on an owned machine for cash. Returns (cost, "") or
    (None, reason)."""
    comp = COMPONENTS.get(machine_id)
    if not comp or machine_id not in machines(player):
        return None, "you don't own that machine."
    if has_cooling(player, machine_id):
        return None, f"{comp.name} already has cooling."
    cost = cooling_cost(machine_id)
    cash = getattr(player, "cash", 0)
    if cash < cost:
        return None, f"AIO cooling for {comp.name} costs {cost} cash — you have {cash}."
    player.cash = cash - cost
    if player.cooling is None:
        player.cooling = []
    player.cooling.append(machine_id)
    return cost, ""


def set_overclock(player, machine_id: str, on: bool):
    """Turn overclock on/off for a machine (requires cooling). Returns
    (new_state_bool, "") or (None, reason)."""
    comp = COMPONENTS.get(machine_id)
    if not comp or machine_id not in machines(player):
        return None, "you don't own that machine."
    if on and not has_cooling(player, machine_id):
        return None, f"{comp.name} needs AIO cooling before you can overclock it."
    if player.overclock is None:
        player.overclock = []
    if on and machine_id not in player.overclock:
        player.overclock.append(machine_id)
    elif not on and machine_id in player.overclock:
        player.overclock.remove(machine_id)
    return (machine_id in player.overclock), ""


def buy_component(player, component_id: str):
    """Purchase a component with the player's cash. Returns (component, "") on
    success (cash deducted, id appended to rig) or (None, reason) on failure.
    `reason` is a player-facing string. Kept here (not in a command) so the
    purchase rules are unit-testable and live with the catalog."""
    comp = COMPONENTS.get(component_id)
    if not comp:
        return None, f"no such hardware '{component_id}'. Try !buy to see the shop."
    if component_id in (getattr(player, "rig", None) or []):
        return None, f"you already own a {comp.name}."
    if player.level < comp.level_req:
        return None, f"{comp.name} needs level {comp.level_req}."
    cash = getattr(player, "cash", 0)
    if cash < comp.cost:
        return None, f"{comp.name} costs {comp.cost} cash — you have {cash}."
    player.cash = cash - comp.cost
    if player.rig is None:
        player.rig = []
    player.rig.append(component_id)
    return comp, ""
