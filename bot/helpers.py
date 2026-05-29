"""Helper methods for PainfulBot."""
import json
from datetime import datetime
from playerdata import Player
from bot.leveling import level_for_points


def log_to_file(message):
    """Helper method to log messages to file."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open('bot.log', 'a') as f:
        f.write(f"[{timestamp}] {message}\n")


def clamp_chat_message(message, limit=480):
    """
    Clamp outgoing chat messages to avoid Twitch's 500-char limit.
    Returns (text, was_clamped).
    """
    if len(message) <= limit:
        return message, False
    return message[: max(0, limit - 3)] + "...", True


def load_player_data():
    """Returns an empty player dict.

    The bot fills it from Postgres in event_ready via db.init(); this stub
    exists so the synchronous Bot.__init__ has something to assign before
    the async loop is up. Do not put JSON-loading logic here — the DB layer
    handles one-time migration from player_data.json on first boot.
    """
    return {}


def save_player_data(player_data):
    """Marks the player dict dirty; the DB flusher batches the write.

    The argument is unused — db.attach_dict() registered the live dict on
    startup and the flush task serializes it directly. Callers do not need
    to change.
    """
    # Lazy import so tests that don't need a DB connection can import this
    # module without pulling in the asyncpg dependency chain.
    from bot import db
    db.mark_dirty()


REGEN_COOLDOWN_SECONDS = 30
REGEN_AMOUNT = 1


def regen_tick(player, now=None):
    """Heal +1 HP if the player is below max and off cooldown.

    Returns the amount healed (0 or 1). The cooldown deliberately throttles
    HP recovery so that taking persistent damage forces a real wait before
    the next boss-battle attempt (entry gate is 50% of max). Mutates
    `player.health` and `player.last_regen_at` in place — caller is
    responsible for `save_player_data`.
    """
    if player is None or player.health >= player.max_health:
        return 0
    now = now or datetime.now()
    last = player.last_regen_at
    if last:
        try:
            last_dt = datetime.fromisoformat(last)
            if (now - last_dt).total_seconds() < REGEN_COOLDOWN_SECONDS:
                return 0
        except (TypeError, ValueError):
            pass  # corrupt timestamp — fall through and tick anyway
    healed = min(REGEN_AMOUNT, player.max_health - player.health)
    player.health += healed
    player.last_regen_at = now.isoformat()
    return healed


def check_level_up(player_data, username):
    """Ensure points stay non-negative and recompute level via the S2 curve.

    Levels never decrease (so losing points to !steal etc. doesn't pull a
    player backwards), but they are advanced when total points cross the
    next quadratic threshold.
    """
    player = player_data[username]
    player.points = max(0, player.points)
    current_level = player.level
    new_level = max(current_level, level_for_points(player.points))

    if new_level != current_level:
        player.level = new_level
        save_player_data(player_data)
        return True
    return False


def load_session_flags():
    """Load per-stream hidden command flags; reset daily."""
    today = datetime.now().date().isoformat()
    default = {
        "date": today,
        "konami": [],
        "coffee": [],
        "browns": [],
        "mvp_awarded": False,
    }
    try:
        with open("session_flags.json", "r") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {k: (set(v) if isinstance(v, list) else v) for k, v in default.items()}

    if data.get("date") != today:
        return {k: (set(v) if isinstance(v, list) else v) for k, v in default.items()}

    normalized = {}
    for k, v in data.items():
        normalized[k] = set(v) if isinstance(v, list) else v
    # Ensure keys exist
    for key in ("konami", "coffee", "browns"):
        normalized.setdefault(key, set())
        if not isinstance(normalized[key], set):
            normalized[key] = set(normalized[key])
    normalized.setdefault("mvp_awarded", False)
    normalized["date"] = today
    return normalized


def save_session_flags(session_flags):
    """Save session flags to JSON."""
    payload = {
        "date": session_flags.get("date", datetime.now().date().isoformat()),
        "konami": list(session_flags.get("konami", set())),
        "coffee": list(session_flags.get("coffee", set())),
        "browns": list(session_flags.get("browns", set())),
        "mvp_awarded": bool(session_flags.get("mvp_awarded", False)),
    }
    with open("session_flags.json", "w") as f:
        json.dump(payload, f, indent=2)


def load_audio_triggers():
    """Load audio trigger definitions from audio_triggers.json; fall back to defaults."""
    default = [
        {"clip": "!htp", "keywords": ["hack the planet", "hacking", "hacks", "hacker", "hackers"]},
        {"clip": "!kelso", "keywords": ["trying", "try hard", "study", "studying", "job", "career", "interview", "grind", "practice", "school", "exam", "cert"]},
        {"clip": "!begin", "keywords": ["starting", "begin", "kick off", "first step", "getting started", "new to", "learn", "learning"]},
        {"clip": "!here", "keywords": ["how long have you been", "where were you", "you been here", "here the whole time", "where have you been"]},
        {"clip": "!theobaby", "keywords": ["complain", "whine", "whining", "rigged", "unfair", "this sucks", "crying"]},
        {"clip": "!hallwaycats", "keywords": ["cav", "leon", "dog", "dogs", "cat", "cats", "hallway"]},
        {"clip": "!donttell", "keywords": ["dont tell jess"], "first_message_user": "britejess"},
        {"clip": "!gb", "keywords": ["got the job", "promotion", "finished", "completed", "shipped", "won", "beat it", "passed", "accomplished", "success"]},
        {"clip": "!looking", "keywords": ["hard", "difficult", "stuck", "struggling", "no luck", "can't find", "cant find", "tough", "not easy"]},
        {"clip": "!hal", "keywords": ["ai", "gpt", "chatgpt", "llm", "model", "openai"]},
        {"clip": "!daddy", "keywords": ["daddy, dad, father"], "cooldown_minutes": 30},
    ]

    try:
        with open("audio_triggers.json", "r") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
    except FileNotFoundError:
        log_to_file("audio_triggers.json not found, using defaults.")
    except json.JSONDecodeError as e:
        log_to_file(f"audio_triggers.json parse error: {e}. Using defaults.")
    except Exception as e:
        log_to_file(f"audio_triggers.json load error: {e}. Using defaults.")
    return default
