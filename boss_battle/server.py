import logging
import os
import threading

import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO

logging.getLogger('engineio').setLevel(logging.CRITICAL)
logging.getLogger('engineio.server').setLevel(logging.CRITICAL)

import time as _time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BOOT_TS = str(int(_time.time()))

app = Flask(__name__)
app.config["SECRET_KEY"] = "painfulit-bossbattle"
socketio = SocketIO(app, async_mode="eventlet", cors_allowed_origins="*",
                    logger=False, engineio_logger=False)

# ---------------------------------------------------------------------------
# Boss battle state
# ---------------------------------------------------------------------------

state_lock = threading.Lock()
MAX_LOG = 60

state = {
    "active": False,
    "boss_name": "",
    "boss_health": 0,
    "boss_max_health": 0,
    "players": {},   # {username: {health, max_health, items: [], alive: bool}}
    "log": [],       # [{msg, type}] — newest first
    "result": None,  # None | "victory" | "defeat"
}


def _snapshot():
    with state_lock:
        return {
            "active": state["active"],
            "boss_name": state["boss_name"],
            "boss_health": state["boss_health"],
            "boss_max_health": state["boss_max_health"],
            "players": dict(state["players"]),
            "log": list(state["log"]),
            "result": state["result"],
        }


# ---------------------------------------------------------------------------
# Game (TwitcHack) state
# ---------------------------------------------------------------------------

game_lock = threading.Lock()
MAX_EVENTS = 100

game = {
    "events":  [],  # [{username, command, result, type, ts}] newest first
    "players": {},  # {username: {level, points, health, items}} session-active
}


def _game_snapshot():
    with game_lock:
        return {
            "events":  list(game["events"]),
            "players": dict(game["players"]),
        }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.after_request
def no_cache(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.route("/")
def spectator():
    return render_template("spectator.html", v=BOOT_TS)


@app.route("/twitchack")
def twitchack():
    return render_template("twitchack.html", v=BOOT_TS)


# ── Boss battle endpoints ────────────────────────────────────────────────────

@app.route("/api/push", methods=["POST"])
def api_push():
    """Bot pushes full battle state snapshot here."""
    data = request.get_json(force=True, silent=True) or {}
    with state_lock:
        for key in ("active", "boss_name", "boss_health", "boss_max_health",
                    "players", "result"):
            if key in data:
                state[key] = data[key]
    socketio.emit("state_update", _snapshot())
    return jsonify({"ok": True})


@app.route("/api/log", methods=["POST"])
def api_log():
    """Bot appends a single combat log entry; also fans out to TwitcHack feed."""
    data = request.get_json(force=True, silent=True) or {}
    msg = data.get("msg", "").strip()
    entry_type = data.get("type", "info")
    if msg:
        with state_lock:
            state["log"].insert(0, {"msg": msg, "type": entry_type})
            if len(state["log"]) > MAX_LOG:
                state["log"] = state["log"][:MAX_LOG]
        socketio.emit("log_entry", {"msg": msg, "type": entry_type})

        # Fan out to TwitcHack feed as a boss event
        game_entry = {
            "username": "",
            "command": "boss battle",
            "result": msg,
            "type": "boss",
            "ts": _time.time(),
        }
        with game_lock:
            game["events"].insert(0, game_entry)
            if len(game["events"]) > MAX_EVENTS:
                game["events"] = game["events"][:MAX_EVENTS]
        socketio.emit("game_event", game_entry)

    return jsonify({"ok": True})


@app.route("/api/clear", methods=["POST"])
def api_clear():
    """Reset boss battle overlay to idle state."""
    with state_lock:
        state["active"] = False
        state["boss_name"] = ""
        state["boss_health"] = 0
        state["boss_max_health"] = 0
        state["players"] = {}
        state["log"] = []
        state["result"] = None
    socketio.emit("state_update", _snapshot())
    return jsonify({"ok": True})


# ── Game (TwitcHack) endpoints ───────────────────────────────────────────────

@app.route("/api/game/event", methods=["POST"])
def api_game_event():
    """Bot pushes a single game event to the TwitcHack feed."""
    data = request.get_json(force=True, silent=True) or {}
    msg = data.get("result", "").strip()
    if not msg:
        return jsonify({"ok": True})
    entry = {
        "username": data.get("username", ""),
        "command":  data.get("command", ""),
        "result":   msg,
        "type":     data.get("type", "attack-success"),
        "ts":       _time.time(),
    }
    with game_lock:
        game["events"].insert(0, entry)
        if len(game["events"]) > MAX_EVENTS:
            game["events"] = game["events"][:MAX_EVENTS]
    socketio.emit("game_event", entry)
    return jsonify({"ok": True})


@app.route("/api/game/player", methods=["POST"])
def api_game_player():
    """Bot updates a single player's stats in the session player list."""
    data = request.get_json(force=True, silent=True) or {}
    username = data.get("username", "").strip()
    if not username:
        return jsonify({"ok": True})
    with game_lock:
        game["players"][username] = {
            "level":  data.get("level", 1),
            "points": data.get("points", 0),
            "health": data.get("health", 100),
            "items":  data.get("items", []),
        }
        players_snapshot = dict(game["players"])
    socketio.emit("players_update", players_snapshot)
    return jsonify({"ok": True})


@app.route("/api/game/clear", methods=["POST"])
def api_game_clear():
    """Reset TwitcHack session data (call on bot restart)."""
    with game_lock:
        game["events"] = []
        game["players"] = {}
    socketio.emit("game_state", _game_snapshot())
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Socket events
# ---------------------------------------------------------------------------

@socketio.on("connect")
def on_connect():
    # Send both boss battle state and game state on connect
    socketio.emit("state_update", _snapshot(), to=request.sid)
    socketio.emit("game_state", _game_snapshot(), to=request.sid)


@socketio.on("request_state")
def on_request_state():
    socketio.emit("state_update", _snapshot(), to=request.sid)


@socketio.on("request_game_state")
def on_request_game_state():
    socketio.emit("game_state", _game_snapshot(), to=request.sid)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print()
    print("  Boss Battle Spectator: http://localhost:3003/")
    print("  TwitcHack Live Feed:   http://localhost:3003/twitchack")
    print()
    socketio.run(app, host="0.0.0.0", port=3003, debug=False)
