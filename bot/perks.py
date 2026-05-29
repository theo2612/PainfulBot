"""Player perk helpers (Cardboard Box steal-immunity, Konami cooldown, etc.).

Centralizes the timer/state logic so commands stay focused on game flow.
"""
from datetime import datetime, timedelta

CARDBOARD_BOX = "Snake's Cardboard Box"
CARDBOARD_BOX_HOURS = 1
KONAMI_COOLDOWN_HOURS = 24


def _parse(ts):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None


def is_box_active(player) -> bool:
    """True if the Cardboard Box steal-immunity perk is currently active."""
    expiry = _parse(getattr(player, 'cardboard_box_until', None))
    return bool(expiry and expiry > datetime.now())


def box_remaining_seconds(player) -> int:
    expiry = _parse(getattr(player, 'cardboard_box_until', None))
    if not expiry:
        return 0
    return max(0, int((expiry - datetime.now()).total_seconds()))


def box_remaining_label(player) -> str | None:
    """Short human-readable remaining time, or None if not active."""
    secs = box_remaining_seconds(player)
    if secs <= 0:
        return None
    if secs < 60:
        return f"{secs}s left"
    mins = secs // 60
    if mins < 60:
        return f"{mins}m left"
    return f"{mins // 60}h{mins % 60:02d}m left"


def prune_box(player) -> bool:
    """Remove an expired Cardboard Box from items. Returns True if pruned."""
    if is_box_active(player):
        return False
    if CARDBOARD_BOX in (player.items or []):
        player.items = [i for i in player.items if i != CARDBOARD_BOX]
        return True
    return False


def grant_box(player) -> str:
    """Activate (or refresh) the Cardboard Box for CARDBOARD_BOX_HOURS.

    Returns the ISO expiry timestamp written to the player.
    """
    expiry = datetime.now() + timedelta(hours=CARDBOARD_BOX_HOURS)
    player.cardboard_box_until = expiry.isoformat(timespec='seconds')
    if CARDBOARD_BOX not in (player.items or []):
        player.items = (player.items or []) + [CARDBOARD_BOX]
    return player.cardboard_box_until


def konami_cooldown_remaining_seconds(player) -> int:
    last = _parse(getattr(player, 'konami_last_at', None))
    if not last:
        return 0
    elapsed = (datetime.now() - last).total_seconds()
    return max(0, int(KONAMI_COOLDOWN_HOURS * 3600 - elapsed))


def konami_cooldown_label(player) -> str | None:
    """Short label like '14h32m' until the next Konami can fire, else None."""
    secs = konami_cooldown_remaining_seconds(player)
    if secs <= 0:
        return None
    hrs = secs // 3600
    mins = (secs % 3600) // 60
    if hrs > 0:
        return f"{hrs}h{mins:02d}m"
    return f"{mins}m"


def mark_konami_used(player) -> None:
    player.konami_last_at = datetime.now().isoformat(timespec='seconds')
