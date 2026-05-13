"""TwitcHack jail, speed-penalty and bail/treasury logic.

Design source of truth: TWITCHACK_JAIL_RATELIMIT_SPEC.md

Two ways a player gets jailed:
  1. Speed violations  — three strikes accrued from attacking faster than the
     per-location threshold for their level. Strikes decay after 10 min idle.
  2. !steal failure    — direct-to-jail, no warning, no strikes.

Jail durations follow a squaring ladder (1, 2, 4, 16, 256 minutes). The
ladder advances each time a player is jailed and resets to offense #1 after
24h jail-free.

Bail (paid in full from the jailed player's wallet, initiated by another
player who pays nothing) sends 90 % to the treasury and 10 % to the bailer.

Time handling: every public function accepts a `now` parameter so tests can
inject deterministic timestamps. When omitted, UTC wall-clock is used.

Persistence: per-player jail state lives on the Player object (see
playerdata.py). The treasury balance lives in a sidecar JSON file because
it is a single global value mutated rarely.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional


# ---------------------------------------------------------------------------
# Tunables — confirmed by spec; revisit after one stream of telemetry.
# ---------------------------------------------------------------------------

# Speed threshold table: minimum gap (seconds) below which an attack counts
# as a speed violation. Indexed by location and level tier.
#
# Each row is sorted [(max_level_inclusive, threshold_seconds), ...].
# Use `None` for the open-ended top tier.
#
# Design intent (revised post-launch): ANY level should be safe at 10 clicks/sec
# or slower. So thresholds are uniformly 0.1s at every location and every level
# — only superhuman click rates (>10/sec, auto-clicker territory) generate
# strikes. The escalation against high-level abusers comes from the penalty
# size (PENALTY_MULTIPLIER * base_reward, which is already larger at harder
# locations), not from tighter thresholds.
SPEED_THRESHOLDS: dict[str, list[tuple[Optional[int], float]]] = {
    "email":       [(None, 0.1)],
    "website":     [(None, 0.1)],
    "server":      [(None, 0.1)],
    "network":     [(None, 0.1)],
    "database":    [(None, 0.1)],
    "/etc/shadow": [(None, 0.1)],
    "evilcorp":    [(None, 0.1)],
}

# Below the threshold, the reward is replaced with -1 * penalty_multiplier *
# would-be reward. 3.0 means "going too fast costs 3x what success would have
# paid." Negative pts are clamped to zero at the caller (matches existing
# attack code conventions).
PENALTY_MULTIPLIER = 3.0

# Strikes-to-jail (uniform across levels — the level scaling is in the
# threshold table).
STRIKES_TO_JAIL = 3

# Strike decay: this much idle time resets the strike counter to zero.
STRIKE_DECAY = timedelta(minutes=10)

# Jail ladder (minutes). Offense number is 1-indexed. Beyond the end of the
# list, every further offense keeps the last (max) duration.
JAIL_LADDER_MINUTES: list[int] = [1, 2, 4, 16, 256]

# 24 hours jail-free → ladder resets to offense #1.
LADDER_RESET = timedelta(hours=24)

# Bail formula: bail_cost = duration_min * level * BAIL_LEVEL_MULTIPLIER.
BAIL_LEVEL_MULTIPLIER = 5

# Bailer's cut of the bail payment (the rest goes to the treasury).
BAILER_SHARE = 0.10

# Burner Laptop fires this many automatic attacks and bypasses speed checks
# for all of them. Exposed here so the laptop implementation can read one
# value rather than hardcoding a literal.
BURNER_LAPTOP_SHOTS = 10

# After the burst, the Burner Laptop also grants this many minutes of
# unrestricted hacking — speed cap is bypassed and no strikes can land.
BURNER_LAPTOP_NO_CAP_MINUTES = 60


def grant_no_cap(player, minutes: int = BURNER_LAPTOP_NO_CAP_MINUTES,
                 now: Optional[datetime] = None) -> str:
    """Extend (or start) the player's no-cap window. Stacks additively from
    `now` or the existing window's end, whichever is later, so back-to-back
    laptops give more time. Returns the new ISO end timestamp."""
    n = _now(now)
    existing = _from_iso(getattr(player, 'no_cap_until', None))
    base = existing if existing and existing > n else n
    new_until = base + timedelta(minutes=minutes)
    player.no_cap_until = _to_iso(new_until)
    return player.no_cap_until


def no_cap_remaining_seconds(player, now: Optional[datetime] = None) -> int:
    """Seconds until the no-cap window expires. 0 if not active."""
    n = _now(now)
    end = _from_iso(getattr(player, 'no_cap_until', None))
    if not end or end <= n:
        return 0
    return int((end - n).total_seconds())


# ---------------------------------------------------------------------------
# Treasury storage — single global integer in a sidecar file.
# ---------------------------------------------------------------------------

_TREASURY_PATH = os.environ.get(
    "TWITCHACK_TREASURY_PATH",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "game_state.json"),
)


def set_treasury_path(path: str) -> None:
    """Override the treasury file location (used by tests)."""
    global _TREASURY_PATH
    _TREASURY_PATH = path


def get_treasury_balance() -> int:
    """Read the current treasury balance from disk. Missing file → 0."""
    try:
        with open(_TREASURY_PATH, "r") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return 0
    return int(data.get("treasury_balance", 0))


def _write_treasury(balance: int) -> None:
    """Replace the treasury file atomically-ish (best effort)."""
    payload = {"treasury_balance": int(balance)}
    tmp = _TREASURY_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(payload, f, indent=2)
    os.replace(tmp, _TREASURY_PATH)


def _credit_treasury(amount: int) -> int:
    """Add `amount` (≥ 0) to the treasury, returning the new balance."""
    if amount < 0:
        raise ValueError("Treasury credits must be non-negative")
    new_balance = get_treasury_balance() + amount
    _write_treasury(new_balance)
    return new_balance


# ---------------------------------------------------------------------------
# Per-attack telemetry — append-only JSONL for post-stream threshold tuning.
# One line per attack records the gap, the threshold it was compared to,
# whether it struck, and the resulting jail state. Set TWITCHACK_ATTACK_LOG=""
# to disable.
# ---------------------------------------------------------------------------

_ATTACK_LOG_PATH = os.environ.get(
    "TWITCHACK_ATTACK_LOG",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "attack_log.jsonl"),
)


def set_attack_log_path(path: str) -> None:
    """Override the attack-log location (used by tests)."""
    global _ATTACK_LOG_PATH
    _ATTACK_LOG_PATH = path


def _telemetry(player, location: str, base_reward: int, now: datetime, result) -> None:
    """Append one JSONL row describing this attack. Errors are swallowed so
    telemetry never breaks gameplay."""
    if not _ATTACK_LOG_PATH:
        return
    try:
        row = {
            "ts": _to_iso(now),
            "user": getattr(player, "username", "?"),
            "level": getattr(player, "level", 0),
            "location": location,
            "base_reward": base_reward,
            "gap": result.gap_seconds,
            "threshold": result.threshold,
            "violation": result.is_violation,
            "strikes_now": result.strikes_now,
            "jailed": result.jailed,
        }
        with open(_ATTACK_LOG_PATH, "a") as f:
            f.write(json.dumps(row) + "\n")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Time helpers — ISO-8601 strings as the wire format on Player, datetimes
# everywhere else. Player fields are JSON-serialized by the DB layer so we
# keep them as strings to avoid serialization bookkeeping there.
# ---------------------------------------------------------------------------

def _now(now: Optional[datetime]) -> datetime:
    return now if now is not None else datetime.now(timezone.utc)


def _to_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _from_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


# ---------------------------------------------------------------------------
# Threshold lookup — pure helper, exposed for tests.
# ---------------------------------------------------------------------------

def threshold_for(location: str, level: int) -> Optional[float]:
    """Return the speed threshold (seconds) for this location+level, or None
    if speed-limiting does not apply at this location (e.g. `home`).

    A return of None means "no rate limit here" — caller should skip the
    speed check entirely.
    """
    tiers = SPEED_THRESHOLDS.get(location)
    if tiers is None:
        return None
    for max_level, threshold in tiers:
        if max_level is None or level <= max_level:
            return threshold
    return tiers[-1][1]  # defensive; should be unreachable


# ---------------------------------------------------------------------------
# Result types — small dataclasses so callers can pattern-match cleanly.
# ---------------------------------------------------------------------------

@dataclass
class SpeedResult:
    """Outcome of recording an attack against the speed-penalty system.

    is_violation : the attack was too fast for the player's tier.
    strikes_now  : strike count after this attack.
    jailed       : True iff this attack pushed the player into jail.
    jail_minutes : duration of the new jail term (only when jailed is True).
    gap_seconds  : seconds since this player's previous attack at this location,
                   or None for first-ever. Used for telemetry / threshold tuning.
    threshold    : the threshold (seconds) the gap was measured against. None
                   when the location is not rate-limited.
    message      : optional user-facing copy describing what happened. The
                   caller composes the full chat reply; this is the jail-
                   specific fragment.
    """
    is_violation: bool
    strikes_now: int
    jailed: bool = False
    jail_minutes: int = 0
    gap_seconds: Optional[float] = None
    threshold: Optional[float] = None
    message: Optional[str] = None


@dataclass
class JailStatus:
    """Snapshot of a player's current jail state."""
    is_jailed: bool
    reason: Optional[str] = None
    offense_number: int = 0
    remaining_seconds: int = 0
    until_iso: Optional[str] = None


@dataclass
class BailResult:
    ok: bool
    message: str
    bail_cost: int = 0
    treasury_share: int = 0
    bailer_share: int = 0


# ---------------------------------------------------------------------------
# Jail state — pure functions over the Player object.
# ---------------------------------------------------------------------------

def _release_if_expired(player, now: datetime) -> bool:
    """If the player's jail term is over, transition them out.

    Returns True if a release happened (so callers can emit a notification).
    """
    if not player.jail:
        return False
    until = _from_iso(player.jail.get("until"))
    if until is None or now < until:
        return False
    player.jail = None
    player.speed_strikes = 0
    player.last_strike_at = None
    player.last_jail_released_at = _to_iso(now)
    player.bail_request_for = None  # any open request goes stale on auto-release
    return True


def jail_status(player, now: Optional[datetime] = None) -> JailStatus:
    """Inspect a player's jail state (and quietly release if expired)."""
    n = _now(now)
    _release_if_expired(player, n)
    if not player.jail:
        return JailStatus(is_jailed=False)
    until = _from_iso(player.jail.get("until"))
    remaining = int((until - n).total_seconds()) if until else 0
    return JailStatus(
        is_jailed=True,
        reason=player.jail.get("reason"),
        offense_number=int(player.jail.get("offense_number", 1)),
        remaining_seconds=max(0, remaining),
        until_iso=player.jail.get("until"),
    )


def is_jailed(player, now: Optional[datetime] = None) -> bool:
    """Shortcut for callers that don't need the details."""
    return jail_status(player, now=now).is_jailed


def _next_offense_number(player, now: datetime) -> int:
    """Compute the offense # for a jail that's about to begin.

    Resets to 1 if the player has been jail-free for at least LADDER_RESET.
    """
    if player.offense_count == 0:
        return 1
    last_release = _from_iso(player.last_jail_released_at)
    if last_release is not None and now - last_release >= LADDER_RESET:
        return 1
    return min(player.offense_count + 1, len(JAIL_LADDER_MINUTES))


def _duration_for_offense(offense_number: int) -> int:
    """Minutes of jail time for the given offense rung (1-indexed)."""
    idx = max(1, offense_number) - 1
    if idx >= len(JAIL_LADDER_MINUTES):
        return JAIL_LADDER_MINUTES[-1]
    return JAIL_LADDER_MINUTES[idx]


def _send_to_jail(player, reason: str, now: datetime) -> tuple[int, int]:
    """Internal: actually flip a player into jail. Returns (duration_min, offense_no)."""
    offense_no = _next_offense_number(player, now)
    duration_min = _duration_for_offense(offense_no)
    until = now + timedelta(minutes=duration_min)
    player.jail = {
        "until": _to_iso(until),
        "reason": reason,
        "offense_number": offense_no,
    }
    player.offense_count = offense_no
    player.speed_strikes = 0
    player.last_strike_at = None
    return duration_min, offense_no


def jail_on_steal_fail(player, now: Optional[datetime] = None) -> JailStatus:
    """Send `player` straight to jail for a failed !steal — no strikes path."""
    n = _now(now)
    _release_if_expired(player, n)  # in case they were jailed and we somehow got here
    _send_to_jail(player, reason="steal_fail", now=n)
    return jail_status(player, now=n)


# ---------------------------------------------------------------------------
# Speed check — the main attack-time entry point.
# ---------------------------------------------------------------------------

def _decay_strikes(player, now: datetime) -> None:
    """Reset strikes to zero if the player has been idle long enough."""
    if player.speed_strikes <= 0:
        return
    last = _from_iso(player.last_strike_at)
    if last is None or now - last >= STRIKE_DECAY:
        player.speed_strikes = 0
        player.last_strike_at = None


def record_attack(
    player,
    location: str,
    base_reward: int,
    *,
    now: Optional[datetime] = None,
    bypass_speed_check: bool = False,
) -> SpeedResult:
    """Register an attack at `location` for the speed-penalty system.

    Call this once per attack attempt, *before* applying any point changes,
    so the caller can use the result to decide whether to award rewards or
    flip them into a penalty.

    `base_reward` is the would-be reward this attack would have paid out on
    success (always non-negative); when below the speed threshold we use it
    to size the penalty (see PENALTY_MULTIPLIER).

    `bypass_speed_check=True` is for items like Burner Laptop that fire
    auto-attacks: we still record the timestamp (so the next manual click
    is measured against this one) but skip the strike/penalty machinery.

    Returns a SpeedResult; on jail-flip the caller should suppress the
    normal reward path and use the result's message.
    """
    n = _now(now)
    _release_if_expired(player, n)
    _decay_strikes(player, n)

    threshold = threshold_for(location, player.level)
    last_attack = _from_iso((player.last_attack_at or {}).get(location))
    gap = (n - last_attack).total_seconds() if last_attack else None

    # Burner Laptop's lingering "no-cap" window: while active, attacks
    # bypass the speed-penalty check entirely (no strikes, no penalty).
    no_cap_until = _from_iso(getattr(player, 'no_cap_until', None))
    in_no_cap = no_cap_until is not None and n < no_cap_until

    # Record this attack's timestamp regardless of outcome — strikes are
    # measured by the *next* attack, not this one.
    if player.last_attack_at is None:
        player.last_attack_at = {}
    player.last_attack_at[location] = _to_iso(n)

    if bypass_speed_check or in_no_cap or threshold is None or last_attack is None:
        result = SpeedResult(
            is_violation=False,
            strikes_now=player.speed_strikes,
            gap_seconds=gap,
            threshold=threshold,
        )
        _telemetry(player, location, base_reward, n, result)
        return result

    if gap >= threshold:
        result = SpeedResult(
            is_violation=False,
            strikes_now=player.speed_strikes,
            gap_seconds=gap,
            threshold=threshold,
        )
        _telemetry(player, location, base_reward, n, result)
        return result

    # Violation. Add a strike.
    player.speed_strikes += 1
    player.last_strike_at = _to_iso(n)
    strikes = player.speed_strikes

    if strikes >= STRIKES_TO_JAIL:
        duration_min, offense_no = _send_to_jail(player, reason="speed", now=n)
        result = SpeedResult(
            is_violation=True,
            strikes_now=0,  # reset by _send_to_jail
            jailed=True,
            jail_minutes=duration_min,
            gap_seconds=gap,
            threshold=threshold,
            message=(
                f"🚔 Too fast — strike {STRIKES_TO_JAIL}/{STRIKES_TO_JAIL}. "
                f"You're in jail for {duration_min} min (offense #{offense_no}). "
                f"Someone has to !bail you out."
            ),
        )
        _telemetry(player, location, base_reward, n, result)
        return result

    result = SpeedResult(
        is_violation=True,
        strikes_now=strikes,
        gap_seconds=gap,
        threshold=threshold,
        message=(
            f"⚠️ Too fast at {location}. Strike {strikes}/{STRIKES_TO_JAIL}. "
            f"One more and you're going to jail."
        ),
    )
    _telemetry(player, location, base_reward, n, result)
    return result


def speed_penalty(base_reward: int) -> int:
    """Convert a base reward into the punitive penalty applied on violation.

    Returns a *positive* magnitude — caller subtracts. Computed as
    `base_reward * PENALTY_MULTIPLIER`, rounded to int.
    """
    return int(max(0, base_reward) * PENALTY_MULTIPLIER)


# ---------------------------------------------------------------------------
# Bail / treasury — money flow.
# ---------------------------------------------------------------------------

def bail_cost_for(player, now: Optional[datetime] = None) -> int:
    """How much it would cost (right now) to bail `player` out.

    Based on the *currently remaining* jail duration, so bailing early is
    cheaper than bailing the moment they go in. (Matches the IRL bail vibe.)

    Returns 0 if the player is not jailed.
    """
    status = jail_status(player, now=now)
    if not status.is_jailed:
        return 0
    minutes_remaining = max(1, (status.remaining_seconds + 59) // 60)
    return minutes_remaining * max(1, player.level) * BAIL_LEVEL_MULTIPLIER


def request_bail(player, bailer_username: str, now: Optional[datetime] = None) -> tuple[bool, str]:
    """Jailed player nominates a specific player as their bailer.

    Per design: bail requires consent. Only the nominated bailer can post.
    If the jailed player wants someone else, they call this again with a
    different target.

    Returns (ok, message). The message is chat-ready.
    """
    n = _now(now)
    status = jail_status(player, now=n)
    if not status.is_jailed:
        return False, f"@{player.username} you're not in jail — no bail to request."
    target = (bailer_username or "").strip().lstrip('@').lower()
    if not target:
        return False, f"@{player.username} usage: !requestbail <username>"
    if target == player.username.lower():
        return False, f"@{player.username} you can't post your own bail."
    player.bail_request_for = target
    return True, (
        f"🆘 @{player.username} has requested bail from @{target}. "
        f"@{target}: type !bail @{player.username} to spring them."
    )


def post_bail(bailer, jailed, now: Optional[datetime] = None) -> BailResult:
    """Bailer posts bail for `jailed`. Bailer pays nothing personally; the
    bail amount is drained from `jailed`'s wallet. Per the consent flow,
    the jailed player must have nominated *this specific bailer* via
    `request_bail()` first."""
    n = _now(now)
    status = jail_status(jailed, now=n)
    if not status.is_jailed:
        return BailResult(ok=False, message="That player isn't in jail.")
    if bailer.username.lower() == jailed.username.lower():
        return BailResult(ok=False, message="You can't bail yourself out.")

    requested_bailer = (getattr(jailed, 'bail_request_for', None) or '').lower()
    if not requested_bailer:
        return BailResult(
            ok=False,
            message=(
                f"@{jailed.username} hasn't requested bail. "
                f"They need to run !requestbail @<you> first."
            ),
        )
    if requested_bailer != bailer.username.lower():
        return BailResult(
            ok=False,
            message=(
                f"@{jailed.username} requested bail from @{requested_bailer}, not you. "
                f"Hands off."
            ),
        )

    cost = bail_cost_for(jailed, now=n)
    if jailed.points < cost:
        return BailResult(
            ok=False,
            message=(
                f"@{jailed.username} can't afford bail "
                f"({jailed.points}/{cost} pts). They sit it out."
            ),
            bail_cost=cost,
        )

    bailer_share = int(round(cost * BAILER_SHARE))
    treasury_share = cost - bailer_share

    jailed.points = max(0, jailed.points - cost)
    bailer.points += bailer_share
    _credit_treasury(treasury_share)

    # Spring them. Strikes already zeroed by _release_if_expired pattern;
    # do it explicitly here too.
    jailed.jail = None
    jailed.speed_strikes = 0
    jailed.last_strike_at = None
    jailed.last_jail_released_at = _to_iso(n)
    jailed.bail_request_for = None  # consume the request
    # offense_count intentionally preserved — getting bailed doesn't reset
    # the escalation ladder (only 24h jail-free does).

    return BailResult(
        ok=True,
        message=(
            f"@{bailer.username} bailed @{jailed.username} for {cost} pts. "
            f"Treasury +{treasury_share}, bailer +{bailer_share}."
        ),
        bail_cost=cost,
        treasury_share=treasury_share,
        bailer_share=bailer_share,
    )


# ---------------------------------------------------------------------------
# Command gating — call this from any handler that should be blocked while
# jailed (attacks, !steal, item use). Handlers that stay open while jailed
# (!hack movement, !status, etc.) simply don't call it. Per CLAUDE.md
# modularity: the gating choice lives on the command itself.
# ---------------------------------------------------------------------------

def block_if_jailed(player, now: Optional[datetime] = None) -> Optional[str]:
    """Returns a chat-ready denial message if `player` is currently jailed,
    or None if they're free. Callers short-circuit on a non-None return."""
    status = jail_status(player, now=now)
    if not status.is_jailed:
        return None
    minutes_remaining = max(1, (status.remaining_seconds + 59) // 60)
    return (
        f"🚔 @{player.username} you're in jail for {minutes_remaining} more min "
        f"(offense #{status.offense_number}). Someone has to !bail you out."
    )
