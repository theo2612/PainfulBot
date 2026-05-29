import json
import logging
import os
import threading

import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, request, make_response
from flask_socketio import SocketIO

# Suppress "Invalid session" and "unsupported version" noise from engineio
logging.getLogger('engineio').setLevel(logging.CRITICAL)
logging.getLogger('engineio.server').setLevel(logging.CRITICAL)

import time as _time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
BOOT_TS = str(int(_time.time()))  # cache buster — changes every server restart

app = Flask(__name__)
app.config["SECRET_KEY"] = "painfulit-stream-overlay"
socketio = SocketIO(app, async_mode="eventlet", cors_allowed_origins="*",
                   logger=False, engineio_logger=False)

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

state_lock = threading.Lock()

state = {
    "show_title": "PainfulIT Live",
    "items": [],          # list of item dicts with runtime fields
    "current_index": -1,  # -1 = not started
    "running": False,
}


def _load_config():
    with open(CONFIG_PATH, "r") as f:
        cfg = json.load(f)
    default_duration = cfg.get("default_duration", 300)
    items = []
    for item in cfg.get("items", []):
        items.append({
            "id": item.get("id", ""),
            "label": item.get("label", ""),
            "sublabel": item.get("sublabel", ""),
            "duration": item.get("duration", default_duration),
            "color": item.get("color", "#E8A020"),
            "remaining": item.get("duration", default_duration),
            "status": "pending",  # pending | active | complete
        })
    return cfg.get("show_title", "PainfulIT Live"), items


def _build_state_payload():
    """Return a serialisable snapshot of the current state."""
    with state_lock:
        return {
            "show_title": state["show_title"],
            "items": [dict(i) for i in state["items"]],
            "current_index": state["current_index"],
            "running": state["running"],
        }


def _advance():
    """Mark current item complete and move to next. Must be called under state_lock."""
    idx = state["current_index"]
    if 0 <= idx < len(state["items"]):
        state["items"][idx]["status"] = "complete"
        state["items"][idx]["remaining"] = 0

    next_idx = idx + 1
    if next_idx < len(state["items"]):
        state["current_index"] = next_idx
        state["items"][next_idx]["status"] = "active"
        state["items"][next_idx]["remaining"] = state["items"][next_idx]["duration"]
    else:
        # Show finished
        state["current_index"] = len(state["items"])  # past-the-end sentinel
        state["running"] = False


def _broadcast_state():
    """Send current state to all connected clients."""
    socketio.emit("state_update", _build_state_payload())


# ---------------------------------------------------------------------------
# Background ticker thread
# ---------------------------------------------------------------------------

def _ticker():
    while True:
        try:
            eventlet.sleep(1)
            with state_lock:
                if not state["running"]:
                    continue
                idx = state["current_index"]
                if idx < 0 or idx >= len(state["items"]):
                    state["running"] = False
                    continue

                item = state["items"][idx]
                if item["remaining"] > 0:
                    item["remaining"] -= 1

                remaining = item["remaining"]

            # Emit lightweight ticker update
            socketio.emit("ticker", {
                "remaining": remaining,
                "current_index": idx,
            })

            if remaining == 0:
                with state_lock:
                    _advance()
                _broadcast_state()

        except Exception as e:
            print(f"[ticker] error: {e}")


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
def display():
    return render_template("display.html", v=BOOT_TS)


@app.route("/control")
def control():
    return render_template("control.html", v=BOOT_TS)


# ---------------------------------------------------------------------------
# Socket events
# ---------------------------------------------------------------------------

@socketio.on("connect")
def on_connect():
    sid = request.sid
    print(f"[socket] + connected: {sid}")
    socketio.emit("state_update", _build_state_payload(), to=sid)


@socketio.on("disconnect")
def on_disconnect():
    print(f"[socket] - disconnected: {request.sid}")


@socketio.on("request_state")
def on_request_state():
    """Client can explicitly ask for current state (reconnect safety net)."""
    sid = request.sid
    socketio.emit("state_update", _build_state_payload(), to=sid)


@socketio.on("cmd_start_pause")
def on_start_pause(_data=None):
    with state_lock:
        if state["current_index"] == -1:
            # First start: begin from item 0
            if state["items"]:
                state["current_index"] = 0
                state["items"][0]["status"] = "active"
                state["running"] = True
        elif state["running"]:
            state["running"] = False
        else:
            # Resume — only if show isn't finished
            if state["current_index"] < len(state["items"]):
                state["running"] = True

    _broadcast_state()


@socketio.on("cmd_skip")
def on_skip(_data=None):
    with state_lock:
        if state["current_index"] < 0:
            return
        _advance()
        if state["current_index"] < len(state["items"]):
            state["running"] = True

    _broadcast_state()


@socketio.on("cmd_restart_item")
def on_restart_item(_data=None):
    with state_lock:
        idx = state["current_index"]
        if 0 <= idx < len(state["items"]):
            state["items"][idx]["remaining"] = state["items"][idx]["duration"]

    _broadcast_state()


@socketio.on("cmd_restart_show")
def on_restart_show(_data=None):
    try:
        show_title, items = _load_config()
    except Exception as e:
        print(f"[restart_show] failed to load config: {e}")
        return
    with state_lock:
        state["show_title"] = show_title
        state["items"] = items
        state["current_index"] = -1
        state["running"] = False

    _broadcast_state()


@socketio.on("cmd_jump")
def on_jump(data):
    target = data.get("index", 0)
    with state_lock:
        if target < 0 or target >= len(state["items"]):
            return
        # Mark everything before target as complete
        for i in range(target):
            state["items"][i]["status"] = "complete"
            state["items"][i]["remaining"] = 0
        # Mark target as active
        state["current_index"] = target
        state["items"][target]["status"] = "active"
        state["items"][target]["remaining"] = state["items"][target]["duration"]
        # Mark everything after target as pending
        for i in range(target + 1, len(state["items"])):
            state["items"][i]["status"] = "pending"
            state["items"][i]["remaining"] = state["items"][i]["duration"]
        state["running"] = True

    _broadcast_state()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    show_title, items = _load_config()
    with state_lock:
        state["show_title"] = show_title
        state["items"] = items

    eventlet.spawn(_ticker)

    print()
    print("  OBS Source:    http://localhost:3000/")
    print("  Control Panel: http://localhost:3000/control")
    print()

    socketio.run(app, host="0.0.0.0", port=3000, debug=False)
