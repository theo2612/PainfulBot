"""Chatter memory for Monday AI."""
import json
from pathlib import Path

_MEMORY_FILE = Path(__file__).parent.parent / "data" / "chatter_memory.json"
GLOBAL_KEY = "_global"

# Chatters whose notes have already been used this session (resets on bot restart)
_session_seen: set = set()


def should_inject_chatter_notes(username: str) -> bool:
    """Return True if this chatter's notes haven't been used yet this session."""
    return username.lower() not in _session_seen


def mark_chatter_seen(username: str):
    """Mark a chatter's notes as used for this session."""
    _session_seen.add(username.lower())


def _load() -> dict:
    if not _MEMORY_FILE.exists():
        return {}
    try:
        return json.loads(_MEMORY_FILE.read_text())
    except Exception:
        return {}


def _save(data: dict):
    _MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    _MEMORY_FILE.write_text(json.dumps(data, indent=2))


def add_note(key: str, note: str):
    data = _load()
    data.setdefault(key, []).append(note)
    _save(data)


def forget(key: str):
    data = _load()
    data.pop(key, None)
    _save(data)


def get_notes(key: str) -> list:
    return _load().get(key, [])
