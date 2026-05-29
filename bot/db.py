"""Postgres-backed player storage with write coalescing.

Player data is held in a process-local dict (`self.player_data` on the bot)
exactly as before — `save_player_data` is now a "mark dirty" call that a
background flush task drains every FLUSH_INTERVAL seconds, batching all
changes into a single transaction.

This collapses N rapid command writes (e.g. autoclickers) into one DB write,
without changing any command handler signatures.
"""
import asyncio
import json
import os
from typing import Optional

import asyncpg

from playerdata import Player

FLUSH_INTERVAL = 0.5  # seconds; coalesces bursts within this window into one write
LEGACY_JSON_PATH = "player_data.json"

_pool: Optional[asyncpg.Pool] = None
_player_data_ref: Optional[dict] = None
_dirty = False
_flush_task: Optional[asyncio.Task] = None
_dsn: Optional[str] = None


def _resolve_dsn() -> str:
    dsn = os.environ.get("DATABASE_URL")
    if dsn:
        return dsn
    user = os.environ.get("POSTGRES_USER", "painful")
    password = os.environ.get("POSTGRES_PASSWORD", "painful")
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ.get("POSTGRES_DB", "painfulbot")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


async def init() -> dict:
    """Connect, ensure schema, migrate JSON if needed, and return the player dict.

    The returned dict is the working set the bot mutates. Pass it to
    `attach_dict()` so the flush task knows what to serialize.
    """
    global _pool, _dsn
    _dsn = _resolve_dsn()
    _pool = await asyncpg.create_pool(_dsn, min_size=2, max_size=10, command_timeout=10)

    async with _pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS players (
                username   TEXT PRIMARY KEY,
                data       JSONB NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        row_count = await conn.fetchval("SELECT COUNT(*) FROM players")

    if row_count == 0 and os.path.exists(LEGACY_JSON_PATH):
        await _migrate_from_json()

    return await _load_all()


async def _migrate_from_json() -> None:
    """One-time import of player_data.json into Postgres on empty-DB first boot."""
    try:
        with open(LEGACY_JSON_PATH, "r") as f:
            raw = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return
    if not raw:
        return

    rows = [(username, json.dumps(data)) for username, data in raw.items()]
    async with _pool.acquire() as conn:
        async with conn.transaction():
            await conn.executemany(
                "INSERT INTO players (username, data) VALUES ($1, $2::jsonb) "
                "ON CONFLICT (username) DO NOTHING",
                rows,
            )
    print(f"[db] Migrated {len(rows)} players from {LEGACY_JSON_PATH}")


async def _load_all() -> dict:
    rows = await _pool.fetch("SELECT username, data FROM players")
    out = {}
    for row in rows:
        data = row["data"]
        if isinstance(data, str):
            data = json.loads(data)
        out[row["username"]] = Player.from_dict(row["username"], data)
    return out


def attach_dict(player_data: dict) -> None:
    """Register the live player dict so the flush task can serialize it."""
    global _player_data_ref
    _player_data_ref = player_data


def mark_dirty() -> None:
    """Called by helpers.save_player_data — flags that a flush is needed."""
    global _dirty
    _dirty = True


async def flush() -> None:
    """Write all current players to Postgres in one transaction."""
    global _dirty
    if not _dirty or _player_data_ref is None or _pool is None:
        return
    _dirty = False  # reset before write — concurrent saves during flush re-mark

    rows = [(name, json.dumps(p.to_dict())) for name, p in _player_data_ref.items()]
    if not rows:
        return

    async with _pool.acquire() as conn:
        async with conn.transaction():
            await conn.executemany(
                "INSERT INTO players (username, data, updated_at) "
                "VALUES ($1, $2::jsonb, NOW()) "
                "ON CONFLICT (username) DO UPDATE "
                "SET data = EXCLUDED.data, updated_at = NOW()",
                rows,
            )


async def _flush_loop() -> None:
    while True:
        try:
            await asyncio.sleep(FLUSH_INTERVAL)
            await flush()
        except asyncio.CancelledError:
            await flush()
            raise
        except Exception as e:
            print(f"[db.flush] error: {e}")


async def start_flusher() -> None:
    global _flush_task
    if _flush_task is None or _flush_task.done():
        _flush_task = asyncio.create_task(_flush_loop())


async def close() -> None:
    global _flush_task, _pool
    if _flush_task is not None:
        _flush_task.cancel()
        try:
            await _flush_task
        except (asyncio.CancelledError, Exception):
            pass
        _flush_task = None
    if _pool is not None:
        await _pool.close()
        _pool = None
