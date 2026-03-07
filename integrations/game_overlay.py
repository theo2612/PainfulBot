"""Fire-and-forget HTTP pushes to the TwitcHack live game feed overlay.

All calls silently swallow errors — if the overlay server isn't running
it never affects the bot.
"""

import asyncio
import json
import urllib.request

OVERLAY_URL = "http://localhost:3003"
_TIMEOUT = 0.5


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
    """Update a player's stats in the session player list."""
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: _post("/api/game/player", {
            "username": username,
            "level":    getattr(player_obj, "level", 1),
            "points":   getattr(player_obj, "points", 0),
            "health":   getattr(player_obj, "health", 100),
            "items":    getattr(player_obj, "items", []),
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
