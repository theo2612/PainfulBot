from gevent import monkey
monkey.patch_all()

import json
import logging
import os
import re
import secrets
import threading
import time as _time

from dotenv import load_dotenv
load_dotenv('/home/b7h30/PainfulBot/.env')

import requests as http_req
from urllib.parse import urlencode

from flask import Flask, render_template, request, jsonify, redirect, session, send_from_directory
from flask_socketio import SocketIO

from cf_access import CFAccessVerifier

logging.getLogger('engineio').setLevel(logging.CRITICAL)
logging.getLogger('engineio.server').setLevel(logging.CRITICAL)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# Command audit log
# ---------------------------------------------------------------------------

_log_dir = os.path.join(BASE_DIR, 'logs')
os.makedirs(_log_dir, exist_ok=True)

_cmd_logger = logging.getLogger('cmd_audit')
_cmd_logger.setLevel(logging.INFO)
_cmd_logger.propagate = False
_cmd_handler = logging.FileHandler(os.path.join(_log_dir, 'commands.log'))
_cmd_handler.setFormatter(logging.Formatter('%(asctime)s | %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
_cmd_logger.addHandler(_cmd_handler)
BOOT_TS = str(int(_time.time()))

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET", "painfulit-bossbattle-2026")
socketio = SocketIO(app, async_mode="gevent", cors_allowed_origins="*",
                    logger=False, engineio_logger=False,
                    ping_interval=10, ping_timeout=5)

# ---------------------------------------------------------------------------
# Cloudflare Access (operator auth for /todo/control)
# ---------------------------------------------------------------------------

CF_ACCESS_TEAM_DOMAIN = os.environ.get('CF_ACCESS_TEAM_DOMAIN', '').strip()
CF_ACCESS_AUD         = os.environ.get('CF_ACCESS_AUD', '').strip()

if CF_ACCESS_TEAM_DOMAIN and CF_ACCESS_AUD:
    cf_verifier = CFAccessVerifier(CF_ACCESS_TEAM_DOMAIN, CF_ACCESS_AUD)
    print(f'  [cf-access] enabled — team={CF_ACCESS_TEAM_DOMAIN}')
else:
    cf_verifier = None
    print('  [cf-access] DISABLED — set CF_ACCESS_TEAM_DOMAIN and CF_ACCESS_AUD in .env for prod')


def _request_came_through_cloudflare():
    return bool(request.headers.get('Cf-Ray') or request.headers.get('Cf-Connecting-Ip'))


def _identify_operator():
    """Return an identity string if this request is allowed to operate the
    todo control, or None if it must be rejected.

    - Requests that came through Cloudflare must present a valid CF Access JWT.
    - Requests that did NOT come through Cloudflare are assumed to be direct
      localhost dev access (cloudflared runs on the same host, so any tunnel
      traffic will carry Cf-* headers). They are allowed as 'localhost-dev'.
    """
    came_through_cf = _request_came_through_cloudflare()
    if came_through_cf:
        if not cf_verifier:
            return None  # fail-closed: configured to be public but no verifier
        token = (request.headers.get('Cf-Access-Jwt-Assertion')
                 or request.cookies.get('CF_Authorization', ''))
        claims = cf_verifier.verify(token)
        if not claims:
            return None
        return claims.get('email') or claims.get('common_name') or 'cf-authed'
    return 'localhost-dev'


# ---------------------------------------------------------------------------
# Twitch OAuth config
# ---------------------------------------------------------------------------

TWITCH_CLIENT_ID     = os.environ.get('OAUTH_CLIENT_ID', os.environ.get('CLIENT_ID', ''))
TWITCH_CLIENT_SECRET = os.environ.get('OAUTH_CLIENT_SECRET', os.environ.get('CLIENT_SECRET', ''))
REDIRECT_URI         = 'https://bossbattle.b7h30.com/twitchack/callback'
BOT_API              = os.environ.get('BOT_API', 'http://localhost:3004/command')

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
    "join_phase": False,
    "hack_used": [],          # list of usernames who've used their !hack nuke this battle
    "cooldown_until": 0,      # epoch ms; bossbattle Start button enables once Date.now() > this
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
            "join_phase": state["join_phase"],
            "hack_used": list(state["hack_used"]),
            "cooldown_until": state["cooldown_until"],
        }


# ---------------------------------------------------------------------------
# Game (TwitcHack) state
# ---------------------------------------------------------------------------

game_lock = threading.Lock()
MAX_EVENTS = 100

game = {
    "events":  [],  # [{username, command, result, type, ts}] newest first
    "players": {},  # {username: {level, points, health, items, location}} session-active
    "drops":   [],  # [{name, location, ts}] active item drops
    "treasury": 0,  # bot-pushed running treasury balance for the GUI widget
}

# SID → username for authenticated socket connections
_sid_username = {}


def _game_snapshot():
    with game_lock:
        return {
            "events":   list(game["events"]),
            "players":  dict(game["players"]),
            "drops":    list(game["drops"]),
            "treasury": int(game.get("treasury", 0)),
        }


# ---------------------------------------------------------------------------
# Stream Todo state
# ---------------------------------------------------------------------------

todo_lock = threading.Lock()

todo_state = {
    "show_title": "PainfulIT Live",
    "items": [],
    "current_index": -1,
    "running": False,
}

TODO_CONFIG_PATH = os.path.join(BASE_DIR, "todo_config.json")
DEFAULT_TODO_COLOR = "#E8A020"
_VALID_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _validate_color(c):
    """Return c if it is a safe 6-digit hex color, else the default. This is
    the only sanitization for the `color` field, which is interpolated into
    CSS on the display overlay."""
    if isinstance(c, str) and _VALID_COLOR_RE.match(c):
        return c
    return DEFAULT_TODO_COLOR


# Authorized control-page SIDs on the /todo namespace. A SID lands here only
# if its WebSocket upgrade carried a valid Cloudflare Access JWT (or came
# directly from localhost in dev). Public display clients connect to the same
# namespace but are not added — they can read state but cannot run cmd_*.
_todo_authorized = {}  # sid -> operator identity string


def _load_todo_config():
    with open(TODO_CONFIG_PATH, "r") as f:
        cfg = json.load(f)
    default_duration = cfg.get("default_duration", 300)
    items = []
    for item in cfg.get("items", []):
        items.append({
            "id": item.get("id", ""),
            "label": item.get("label", ""),
            "sublabel": item.get("sublabel", ""),
            "duration": item.get("duration", default_duration),
            "color": _validate_color(item.get("color")),
            "remaining": item.get("duration", default_duration),
            "status": "pending",
        })
    return cfg.get("show_title", "PainfulIT Live"), items


def _build_todo_payload():
    with todo_lock:
        return {
            "show_title": todo_state["show_title"],
            "items": [dict(i) for i in todo_state["items"]],
            "current_index": todo_state["current_index"],
            "running": todo_state["running"],
        }


def _todo_advance():
    """Mark current item complete and move to next. Must be called under todo_lock."""
    idx = todo_state["current_index"]
    if 0 <= idx < len(todo_state["items"]):
        todo_state["items"][idx]["status"] = "complete"
        todo_state["items"][idx]["remaining"] = 0
    next_idx = idx + 1
    if next_idx < len(todo_state["items"]):
        todo_state["current_index"] = next_idx
        todo_state["items"][next_idx]["status"] = "active"
        todo_state["items"][next_idx]["remaining"] = todo_state["items"][next_idx]["duration"]
    else:
        todo_state["current_index"] = len(todo_state["items"])
        todo_state["running"] = False


def _broadcast_todo():
    socketio.emit("state_update", _build_todo_payload(), namespace="/todo")


def _save_todo_config(show_title, items):
    """Atomically write todo config. Strips runtime-only fields."""
    try:
        with open(TODO_CONFIG_PATH, "r") as f:
            existing = json.load(f)
        default_duration = existing.get("default_duration", 300)
    except Exception:
        default_duration = 300

    serialized = []
    for it in items:
        entry = {
            "id": it["id"],
            "label": it["label"],
            "sublabel": it.get("sublabel", ""),
            "duration": int(it["duration"]),
        }
        color = _validate_color(it.get("color"))
        if color != DEFAULT_TODO_COLOR:
            entry["color"] = color
        serialized.append(entry)

    payload = {
        "show_title": show_title,
        "default_duration": default_duration,
        "items": serialized,
    }
    tmp_path = TODO_CONFIG_PATH + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")
    os.replace(tmp_path, TODO_CONFIG_PATH)


def _merge_todo_items(new_items):
    """Replace todo_state['items'] with new_items, preserving runtime progress
    for items whose id matches an existing one. Must be called under todo_lock."""
    old_by_id = {it["id"]: it for it in todo_state["items"] if it.get("id")}

    old_idx = todo_state["current_index"]
    old_active_id = None
    if 0 <= old_idx < len(todo_state["items"]):
        old_active_id = todo_state["items"][old_idx].get("id")

    merged = []
    for item in new_items:
        iid = item["id"]
        duration = int(item["duration"])
        old = old_by_id.get(iid)
        if old:
            remaining = min(old["remaining"], duration)
            color = _validate_color(item.get("color") or old.get("color"))
            merged.append({
                "id": iid,
                "label": item["label"],
                "sublabel": item.get("sublabel", ""),
                "duration": duration,
                "color": color,
                "remaining": remaining,
                "status": old["status"],
            })
        else:
            merged.append({
                "id": iid,
                "label": item["label"],
                "sublabel": item.get("sublabel", ""),
                "duration": duration,
                "color": _validate_color(item.get("color")),
                "remaining": duration,
                "status": "pending",
            })

    todo_state["items"] = merged

    if old_active_id is not None:
        new_active = next((i for i, it in enumerate(merged) if it["id"] == old_active_id), -1)
        if new_active >= 0:
            todo_state["current_index"] = new_active
        else:
            todo_state["running"] = False
            next_pending = next((i for i, it in enumerate(merged) if it["status"] == "pending"), len(merged))
            todo_state["current_index"] = next_pending
            if next_pending < len(merged):
                merged[next_pending]["status"] = "active"
                merged[next_pending]["remaining"] = merged[next_pending]["duration"]
    elif old_idx == -1:
        todo_state["current_index"] = -1
    else:
        todo_state["current_index"] = len(merged)


# ---------------------------------------------------------------------------
# Stream Todo background ticker
# ---------------------------------------------------------------------------

def _todo_ticker():
    while True:
        try:
            socketio.sleep(1)
            with todo_lock:
                if not todo_state["running"]:
                    continue
                idx = todo_state["current_index"]
                if idx < 0 or idx >= len(todo_state["items"]):
                    todo_state["running"] = False
                    continue
                item = todo_state["items"][idx]
                if item["remaining"] > 0:
                    item["remaining"] -= 1
                remaining = item["remaining"]

            socketio.emit("ticker", {
                "remaining": remaining,
                "current_index": idx,
            }, namespace="/todo")

            if remaining == 0:
                with todo_lock:
                    _todo_advance()
                _broadcast_todo()

        except Exception as e:
            print(f"[todo-ticker] error: {e}")


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
    return render_template(
        "spectator.html",
        v=BOOT_TS,
        username=session.get('twitch_username'),
    )


@app.route("/twitchack")
def twitchack():
    return render_template("twitchack.html", v=BOOT_TS)


@app.route("/todo")
def todo_display():
    return render_template("todo_display.html", v=BOOT_TS)


@app.route("/todo/control")
def todo_control():
    operator = _identify_operator()
    if not operator:
        return 'Unauthorized — sign in via Cloudflare Access.', 403
    return render_template("todo_control.html", v=BOOT_TS)


@app.route("/guide/bossbattle")
def guide_bossbattle():
    return send_from_directory(
        os.path.join(BASE_DIR, "..", "bossbattle-guide"), "index.html"
    )


@app.route("/guide/twitchack")
def guide_twitchack():
    return send_from_directory(
        os.path.join(BASE_DIR, "..", "twitchack-guide"), "index.html"
    )


# ── Twitch OAuth ─────────────────────────────────────────────────────────────

@app.route("/twitchack/login")
def twitchack_login():
    state_token = secrets.token_hex(16)
    session['oauth_state'] = state_token
    # Optional ?next=/path so callers (e.g. the spectator page at /) can be
    # bounced back to where they came from. Only same-origin paths are allowed.
    next_url = request.args.get('next', '/twitchack')
    if not next_url.startswith('/') or next_url.startswith('//'):
        next_url = '/twitchack'
    session['post_login_redirect'] = next_url
    params = {
        'client_id':     TWITCH_CLIENT_ID,
        'redirect_uri':  REDIRECT_URI,
        'response_type': 'code',
        'scope':         'user:read:email',
        'state':         state_token,
    }
    return redirect('https://id.twitch.tv/oauth2/authorize?' + urlencode(params))


@app.route("/twitchack/callback")
def twitchack_callback():
    if request.args.get('state') != session.pop('oauth_state', None):
        return 'Authentication error — state mismatch. Please try again.', 400

    code = request.args.get('code')
    if not code:
        return 'Authentication error — no code returned.', 400

    # Exchange code for access token
    try:
        token_resp = http_req.post('https://id.twitch.tv/oauth2/token', data={
            'client_id':     TWITCH_CLIENT_ID,
            'client_secret': TWITCH_CLIENT_SECRET,
            'code':          code,
            'grant_type':    'authorization_code',
            'redirect_uri':  REDIRECT_URI,
        }, timeout=5)
        access_token = token_resp.json()['access_token']
    except Exception:
        return 'Authentication error — token exchange failed.', 500

    # Fetch Twitch username
    try:
        user_resp = http_req.get('https://api.twitch.tv/helix/users',
            headers={
                'Authorization': f'Bearer {access_token}',
                'Client-Id':     TWITCH_CLIENT_ID,
            }, timeout=5)
        username = user_resp.json()['data'][0]['login'].lower()
    except Exception:
        return 'Authentication error — could not fetch user info.', 500

    session['twitch_username'] = username

    # Auto-register player (bot handles "already registered" gracefully)
    try:
        http_req.post(BOT_API, json={
            'username': username,
            'command':  'start',
        }, timeout=2)
    except Exception:
        pass  # Bot may be offline — player can register via chat later

    return redirect(session.pop('post_login_redirect', '/twitchack'))


# ── Game web command API ──────────────────────────────────────────────────────



@app.route("/api/game/me")
def api_me():
    username = session.get('twitch_username')
    if not username:
        return jsonify({'username': None})

    with game_lock:
        player_data = dict(game["players"].get(username, {}))
        drops = list(game["drops"])

    return jsonify({
        'username':    username,
        'player':      player_data,
        'drops':       drops,
    })


# ── Boss battle endpoints ────────────────────────────────────────────────────

@app.route("/api/push", methods=["POST"])
def api_push():
    """Bot pushes full battle state snapshot here."""
    data = request.get_json(force=True, silent=True) or {}
    with state_lock:
        for key in ("active", "boss_name", "boss_health", "boss_max_health",
                    "players", "result", "join_phase", "hack_used", "cooldown_until"):
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
    """Reset boss battle overlay to idle state.

    Preserves `cooldown_until` so the player overlay knows when the next battle
    can be started (the bot pushes the post-battle cooldown via the same field).
    """
    with state_lock:
        state["active"] = False
        state["boss_name"] = ""
        state["boss_health"] = 0
        state["boss_max_health"] = 0
        state["players"] = {}
        state["log"] = []
        state["result"] = None
        state["join_phase"] = False
        state["hack_used"] = []
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
            "level":        data.get("level", 1),
            "points":       data.get("points", 0),
            "cash":         data.get("cash", 0),
            "health":       data.get("health", 100),
            "max_health":   data.get("max_health", data.get("health", 100)),
            "items":        data.get("items", []),
            "location":     data.get("location", "home"),
            "founder_tier": data.get("founder_tier"),
            "jail":         data.get("jail"),
            "speed_strikes": data.get("speed_strikes", 0),
            "bail_request_for": data.get("bail_request_for"),
            "no_cap_until": data.get("no_cap_until"),
        }
        players_snapshot = dict(game["players"])
    socketio.emit("players_update", players_snapshot)
    return jsonify({"ok": True})


@app.route("/api/game/drop", methods=["POST"])
def api_game_drop():
    """Bot announces a new item drop; web clients show grab button."""
    data = request.get_json(force=True, silent=True) or {}
    name = data.get("name", "").strip()
    location = data.get("location", "").strip()
    if not name:
        return jsonify({"ok": True})
    entry = {"name": name, "location": location, "ts": _time.time()}
    with game_lock:
        # Avoid duplicates
        if not any(d["name"].lower() == name.lower() for d in game["drops"]):
            game["drops"].append(entry)
        drops_snapshot = list(game["drops"])
    socketio.emit("drops_update", drops_snapshot)
    return jsonify({"ok": True})


@app.route("/api/game/drop_taken", methods=["POST"])
def api_game_drop_taken():
    """Bot notifies that an item was grabbed; removes it from the drop list."""
    data = request.get_json(force=True, silent=True) or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"ok": True})
    with game_lock:
        game["drops"] = [d for d in game["drops"] if d["name"].lower() != name.lower()]
        drops_snapshot = list(game["drops"])
    socketio.emit("drops_update", drops_snapshot)
    return jsonify({"ok": True})


@app.route("/api/game/treasury", methods=["POST"])
def api_game_treasury():
    """Bot pushes the current Treasury balance; we mirror to all clients."""
    data = request.get_json(force=True, silent=True) or {}
    try:
        balance = int(data.get("balance", 0))
    except (TypeError, ValueError):
        balance = 0
    with game_lock:
        game["treasury"] = balance
    socketio.emit("treasury_update", {"balance": balance})
    return jsonify({"ok": True})


@app.route("/api/game/clear", methods=["POST"])
def api_game_clear():
    """Reset TwitcHack session data (call on bot restart)."""
    with game_lock:
        game["events"] = []
        game["players"] = {}
        game["drops"] = []
    socketio.emit("game_state", _game_snapshot())
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Socket events
# ---------------------------------------------------------------------------

@socketio.on("connect")
def on_connect():
    username = session.get('twitch_username')
    if username:
        _sid_username[request.sid] = username
    # Send both boss battle state and game state on connect
    socketio.emit("state_update", _snapshot(), to=request.sid)
    socketio.emit("game_state", _game_snapshot(), to=request.sid)


@socketio.on("disconnect")
def on_disconnect():
    _sid_username.pop(request.sid, None)


@socketio.on("web_command")
def on_web_command(data):
    # Primary lookup: SID map set at connect time.
    # Fallback: re-read Flask session in case the server restarted and _sid_username was cleared.
    username = _sid_username.get(request.sid) or session.get('twitch_username')
    if username and request.sid not in _sid_username:
        _sid_username[request.sid] = username  # re-populate so future calls are fast
    if not username:
        socketio.emit("web_result", {"result": "Not authenticated — please sign in."}, to=request.sid)
        return

    cmd  = (data.get("command") or "").strip()
    # `args` is usually a string from sendCmd(), but accept list-of-strings too
    # (web clients have been seen sending arrays — defensive normalization).
    args_raw = data.get("args") or ""
    if isinstance(args_raw, list):
        args = " ".join(str(a) for a in args_raw if a is not None).strip()
    else:
        args = str(args_raw).strip()
    ip   = request.environ.get("HTTP_X_FORWARDED_FOR",
           request.environ.get("REMOTE_ADDR", "?")).split(",")[0].strip()

    try:
        resp   = http_req.post(BOT_API, json={"username": username, "command": cmd, "args": args}, timeout=5)
        result = resp.json().get("result", "")
    except Exception:
        result = "Command failed — bot may be offline."

    _cmd_logger.info("%s | %s | %s | %s | %s", ip, username, cmd, args, (result or "")[:120].replace("\n", " "))
    socketio.emit("web_result", {"result": result, "command": cmd}, to=request.sid)


@socketio.on("request_state")
def on_request_state():
    socketio.emit("state_update", _snapshot(), to=request.sid)


@socketio.on("request_game_state")
def on_request_game_state():
    socketio.emit("game_state", _game_snapshot(), to=request.sid)


# ---------------------------------------------------------------------------
# Stream Todo socket events (/todo namespace)
# ---------------------------------------------------------------------------

@socketio.on("connect", namespace="/todo")
def on_todo_connect():
    # Public display clients are allowed to connect (they only read state),
    # but only operators who passed Cloudflare Access (or local dev) land in
    # the authorized set and can fire cmd_* events.
    operator = _identify_operator()
    if operator:
        _todo_authorized[request.sid] = operator
        _cmd_logger.info("todo authorize | %s | sid=%s", operator, request.sid)
    socketio.emit("state_update", _build_todo_payload(),
                  to=request.sid, namespace="/todo")


@socketio.on("disconnect", namespace="/todo")
def on_todo_disconnect():
    _todo_authorized.pop(request.sid, None)


def _require_todo_operator(cmd_name):
    """Guard for /todo cmd_* events. Returns operator identity or None.
    On rejection, emits an auth_error to the requesting SID and logs the
    attempt for auditing."""
    operator = _todo_authorized.get(request.sid)
    if not operator:
        ip = (request.headers.get('Cf-Connecting-Ip')
              or request.environ.get('HTTP_X_FORWARDED_FOR',
                 request.environ.get('REMOTE_ADDR', '?')).split(',')[0].strip())
        _cmd_logger.warning("todo REJECT %s | sid=%s | ip=%s", cmd_name, request.sid, ip)
        socketio.emit("auth_error",
                      {"message": "Not authorized — operator login required."},
                      to=request.sid, namespace="/todo")
        return None
    _cmd_logger.info("todo %s | %s", cmd_name, operator)
    return operator


@socketio.on("request_state", namespace="/todo")
def on_todo_request_state():
    socketio.emit("state_update", _build_todo_payload(),
                  to=request.sid, namespace="/todo")


@socketio.on("cmd_start_pause", namespace="/todo")
def on_todo_start_pause(_data=None):
    if not _require_todo_operator("cmd_start_pause"):
        return
    with todo_lock:
        if todo_state["current_index"] == -1:
            if todo_state["items"]:
                todo_state["current_index"] = 0
                todo_state["items"][0]["status"] = "active"
                todo_state["running"] = True
        elif todo_state["running"]:
            todo_state["running"] = False
        else:
            if todo_state["current_index"] < len(todo_state["items"]):
                todo_state["running"] = True
    _broadcast_todo()


@socketio.on("cmd_skip", namespace="/todo")
def on_todo_skip(_data=None):
    if not _require_todo_operator("cmd_skip"):
        return
    with todo_lock:
        if todo_state["current_index"] < 0:
            return
        _todo_advance()
        if todo_state["current_index"] < len(todo_state["items"]):
            todo_state["running"] = True
    _broadcast_todo()


@socketio.on("cmd_restart_item", namespace="/todo")
def on_todo_restart_item(_data=None):
    if not _require_todo_operator("cmd_restart_item"):
        return
    with todo_lock:
        idx = todo_state["current_index"]
        if 0 <= idx < len(todo_state["items"]):
            todo_state["items"][idx]["remaining"] = todo_state["items"][idx]["duration"]
    _broadcast_todo()


@socketio.on("cmd_restart_show", namespace="/todo")
def on_todo_restart_show(_data=None):
    if not _require_todo_operator("cmd_restart_show"):
        return
    try:
        show_title, items = _load_todo_config()
    except Exception as e:
        print(f"[todo-restart] failed to load config: {e}")
        return
    with todo_lock:
        todo_state["show_title"] = show_title
        todo_state["items"] = items
        todo_state["current_index"] = -1
        todo_state["running"] = False
    _broadcast_todo()


@socketio.on("cmd_save_rundown", namespace="/todo")
def on_todo_save_rundown(data):
    if not _require_todo_operator("cmd_save_rundown"):
        return
    sid = request.sid

    def err(msg):
        socketio.emit("save_error", {"message": msg}, to=sid, namespace="/todo")

    if not isinstance(data, dict):
        return err("Invalid payload")

    show_title = data.get("show_title", "")
    if not isinstance(show_title, str) or not show_title.strip():
        return err("Show title cannot be empty")

    incoming = data.get("items", [])
    if not isinstance(incoming, list) or not incoming:
        return err("Rundown must have at least one item")

    seen_ids = set()
    normalized = []
    for i, it in enumerate(incoming):
        if not isinstance(it, dict):
            return err(f"Item {i+1} is malformed")
        iid = it.get("id")
        if not isinstance(iid, str) or not iid.strip():
            return err(f"Item {i+1} is missing an id")
        iid = iid.strip()
        if iid in seen_ids:
            return err(f"Duplicate id: {iid}")
        seen_ids.add(iid)

        label = it.get("label", "")
        if not isinstance(label, str) or not label.strip():
            return err(f"Item {i+1} needs a label")

        try:
            dur = int(it.get("duration", 0))
        except (TypeError, ValueError):
            return err(f"Item {i+1} has invalid duration")
        if dur <= 0:
            return err(f"Item {i+1} duration must be greater than zero")

        sublabel = it.get("sublabel", "")
        if not isinstance(sublabel, str):
            sublabel = ""

        normalized.append({
            "id": iid,
            "label": label.strip(),
            "sublabel": sublabel,
            "duration": dur,
            "color": _validate_color(it.get("color")),
        })

    try:
        _save_todo_config(show_title.strip(), normalized)
    except Exception as e:
        print(f"[todo-save] write failed: {e}")
        return err(f"Failed to write config: {e}")

    with todo_lock:
        todo_state["show_title"] = show_title.strip()
        _merge_todo_items(normalized)

    _broadcast_todo()
    socketio.emit("save_ok", {}, to=sid, namespace="/todo")


@socketio.on("cmd_jump", namespace="/todo")
def on_todo_jump(data):
    if not _require_todo_operator("cmd_jump"):
        return
    target = data.get("index", 0)
    with todo_lock:
        if target < 0 or target >= len(todo_state["items"]):
            return
        for i in range(target):
            todo_state["items"][i]["status"] = "complete"
            todo_state["items"][i]["remaining"] = 0
        todo_state["current_index"] = target
        todo_state["items"][target]["status"] = "active"
        todo_state["items"][target]["remaining"] = todo_state["items"][target]["duration"]
        for i in range(target + 1, len(todo_state["items"])):
            todo_state["items"][i]["status"] = "pending"
            todo_state["items"][i]["remaining"] = todo_state["items"][i]["duration"]
        todo_state["running"] = True
    _broadcast_todo()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Startup — runs on module import (so gunicorn picks it up too)
# ---------------------------------------------------------------------------

try:
    _show_title, _items = _load_todo_config()
    with todo_lock:
        todo_state["show_title"] = _show_title
        todo_state["items"] = _items
    print("  [todo] Config loaded OK")
except FileNotFoundError:
    print("  [todo] No todo_config.json found — todo overlay disabled")

socketio.start_background_task(_todo_ticker)

print()
print("  Boss Battle Spectator: http://localhost:3003/")
print("  TwitcHack Live Feed:   http://localhost:3003/twitchack")
print("  Stream Todo Display:   http://localhost:3003/todo")
print("  Stream Todo Control:   http://localhost:3003/todo/control")
print("  Boss Battle Guide:     http://localhost:3003/guide/bossbattle")
print("  TwitcHack Guide:       http://localhost:3003/guide/twitchack")
print()


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=3003, debug=False)
