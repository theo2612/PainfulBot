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
from dataclasses import dataclass, field

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
        stats=RigStats(threads=4, memory=2, storage=16, gpu_power=0, clock=0.8),
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
        stats=RigStats(threads=6, memory=6, storage=256, gpu_power=1, clock=1.0),
        desc="3 hacks at once, ~20% faster, lots of storage.",
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


def job_slots(player) -> int:
    """Convenience: this player's max concurrent jobs."""
    return rig_stats(player).job_slots()


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
