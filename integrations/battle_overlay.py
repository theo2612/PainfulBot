"""Fire-and-forget HTTP pushes to the boss battle spectator overlay.

All calls silently swallow errors — if the overlay server isn't running
it never affects the bot.
"""

import asyncio
import json
import urllib.request

OVERLAY_URL = "http://localhost:3003"
_TIMEOUT = 0.5  # tight so the bot never stalls waiting on this


def _post(path: str, payload: dict) -> None:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{OVERLAY_URL}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    urllib.request.urlopen(req, timeout=_TIMEOUT)


async def push(**kwargs) -> None:
    """Push full battle state snapshot to the overlay."""
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: _post("/api/push", kwargs))
    except Exception:
        pass


async def log(msg: str, entry_type: str = "info") -> None:
    """Append a single line to the overlay combat log."""
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, lambda: _post("/api/log", {"msg": msg, "type": entry_type})
        )
    except Exception:
        pass


async def clear() -> None:
    """Reset the overlay to idle state."""
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: _post("/api/clear", {}))
    except Exception:
        pass
