"""Fire-and-forget HTTP pushes to the TwitcHack live game feed overlay.

All calls silently swallow errors — if the overlay server isn't running
it never affects the bot.
"""

import asyncio
import json
import os
import urllib.request

from game import hardware  # for job_slots() in the player push (no import cycle)

OVERLAY_URL = os.environ.get("OVERLAY_URL", "http://localhost:3003")
_TIMEOUT = 2.0


def _post(path: str, payload: dict) -> None:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{OVERLAY_URL}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    urllib.request.urlopen(req, timeout=_TIMEOUT)


async def event(username: str, command: str, result: str,
                event_type: str = "attack-success") -> None:
    """Push a game event to the TwitcHack feed."""
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: _post("/api/game/event", {
            "username": username,
            "command":  command,
            "result":   result,
            "type":     event_type,
        }))
    except Exception:
        pass


async def player(username: str, player_obj) -> None:
    """Update a player's stats in the session player list.

    The `jail` field, if present, lets the overlay render a 🚔 badge and
    countdown. Shape: {until: iso8601, reason: str, offense_number: int}.
    """
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: _post("/api/game/player", {
            "username":     username,
            "level":        getattr(player_obj, "level", 1),
            "points":       getattr(player_obj, "points", 0),
            "cash":         getattr(player_obj, "cash", 0),
            "health":       getattr(player_obj, "health", 100),
            "max_health":   getattr(player_obj, "max_health", getattr(player_obj, "health", 100)),
            "items":        getattr(player_obj, "items", []),
            "location":     getattr(player_obj, "location", "home"),
            "founder_tier": getattr(player_obj, "founder_tier", None),
            "jail":         getattr(player_obj, "jail", None),
            "speed_strikes": getattr(player_obj, "speed_strikes", 0),
            "bail_request_for": getattr(player_obj, "bail_request_for", None),
            "no_cap_until": getattr(player_obj, "no_cap_until", None),
            "rig":          getattr(player_obj, "rig", []),
            "jobs":         getattr(player_obj, "jobs", []),
            "job_slots":    hardware.job_slots(player_obj),
        }))
    except Exception:
        pass


async def catalog(hardware_list, hack_list) -> None:
    """Push the idle-hacking catalogs (hardware + hacks) so the GUI can render
    buy/run buttons from the real source of truth. Sent once on bot startup."""
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: _post("/api/game/catalog", {
            "hardware": hardware_list,
            "hacks":    hack_list,
        }))
    except Exception:
        pass


async def treasury(balance: int) -> None:
    """Push the current treasury balance to the overlay so the GUI widget
    can render a live total."""
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: _post("/api/game/treasury", {
            "balance": int(balance),
        }))
    except Exception:
        pass


async def drop(item_name: str, location: str) -> None:
    """Announce a new item drop to the overlay (structured, for web grab buttons)."""
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: _post("/api/game/drop", {
            "name": item_name,
            "location": location,
        }))
    except Exception:
        pass


async def drop_taken(item_name: str) -> None:
    """Notify the overlay that an item was grabbed."""
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: _post("/api/game/drop_taken", {
            "name": item_name,
        }))
    except Exception:
        pass


async def clear() -> None:
    """Reset TwitcHack session data on the overlay (call on bot restart)."""
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: _post("/api/game/clear", {}))
    except Exception:
        pass
