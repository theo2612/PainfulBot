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
# State
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
    """Bot appends a single combat log entry."""
    data = request.get_json(force=True, silent=True) or {}
    msg = data.get("msg", "").strip()
    entry_type = data.get("type", "info")
    if msg:
        with state_lock:
            state["log"].insert(0, {"msg": msg, "type": entry_type})
            if len(state["log"]) > MAX_LOG:
                state["log"] = state["log"][:MAX_LOG]
        socketio.emit("log_entry", {"msg": msg, "type": entry_type})
    return jsonify({"ok": True})


@app.route("/api/clear", methods=["POST"])
def api_clear():
    """Reset overlay to idle state."""
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


# ---------------------------------------------------------------------------
# Socket events
# ---------------------------------------------------------------------------

@socketio.on("connect")
def on_connect():
    socketio.emit("state_update", _snapshot(), to=request.sid)


@socketio.on("request_state")
def on_request_state():
    socketio.emit("state_update", _snapshot(), to=request.sid)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print()
    print("  Boss Battle Spectator: http://localhost:3003/")
    print()
    socketio.run(app, host="0.0.0.0", port=3003, debug=False)
