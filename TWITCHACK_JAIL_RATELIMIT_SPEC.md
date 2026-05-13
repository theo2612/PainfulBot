# TwitcHack: Speed Penalty, Jail, Treasury & Bail — Design Spec

Status: Approved, ready to implement
Designed: 2026-05
Drives two new features:
1. **Rate-limit / anti-auto-clicker** — economic speed penalty + jail
2. **Jail** — triggered by (a) repeated speed violations and (b) failed `!steal`

---

## 1. Speed Penalty (the "rate limit")

No GUI throttle. Buttons always clickable. The penalty is purely economic — players who attack too fast lose points instead of earning them.

### Mechanic

- Per `(player, location)`, track the timestamp of the last attack.
- On every new attack, compute `gap = now - last_attack_at` for that location.
- If `gap < threshold(level, location)` → **speed violation**:
  - Reward is replaced by a flat negative penalty (cliff curve, not linear).
  - Penalty magnitude = `abs(would-be reward) × penalty_multiplier`. Start with `penalty_multiplier = 3.0`, tune from telemetry.
  - Player accrues **1 strike**.
- If `gap >= threshold` → normal reward, no strike.

### Threshold table (gap in seconds)

Threshold is the *minimum* gap-since-last-attack that avoids a strike. Below it → penalty + strike.

| Location | Lvl 1–50 | Lvl 51–500 | Lvl 501–5000 | Lvl 5000+ |
|---|---|---|---|---|
| email / website | 0.1s | 0.5s | 1.5s | 3s |
| server / network | 0.2s | 1s | 3s | 6s |
| database | 0.3s | 2s | 5s | 8s |
| /etc/shadow | 0.3s | 2s | 5s | 8s |
| evilcorp | 0.5s | 3s | 8s | 15s |

Design intent: a frantic newbie clicking ~5/sec stays *above* their 0.1s threshold and is never punished. A high-level auto-clicker at 1/sec at evilcorp is wildly below the 15s threshold → strikes pile up fast → jail within seconds → "wtf just happened" → adjust the clicker.

### Strike accounting

- Strikes are global per player (not per-location). Going too fast anywhere counts.
- **3 strikes → jail** (see §2). Same threshold for all levels — the scaling lives in the speed threshold above.
- **Decay:** if a player has no new strike for **10 minutes**, strike count resets to 0.
- **Reset on jail release:** after serving any jail term, strikes reset to 0.

### `!steal` failure (separate path to jail)

- A failed `!steal` sends the attacker **directly to jail**. No strike accumulation, no warning.
- Jail duration follows the same exponential ladder as speed-violation jail (§2).

---

## 2. Jail

### Triggers

1. 3 strikes from speed violations
2. Failed `!steal` (instant, no strikes)

### Duration (squaring ladder)

| Offense # | Duration |
|---|---|
| 1 | 1 min |
| 2 | 2 min |
| 3 | 4 min |
| 4 | 16 min |
| 5+ | 256 min (~4h) |

- Offense counter is **per player**, persistent across sessions.
- **Ladder reset:** if a player goes **24h jail-free**, next jail starts back at offense #1.

### What jail blocks

Blocked while jailed:
- All attack commands (`!crack`, `!stealth`, `!bruteforce`, `!phish`, `!exploit`, `!backdoor`, `!sqli`, `!xss`, `!ddos`, `!scan`, `!root`, `!ransom`, `!revshell`, `!mvp`, etc.)
- `!steal`
- Item use (any consumable, including Burner Laptop)

Allowed while jailed:
- `!hack <location>` (movement)
- Read-only commands: `!status`, `!points`, `!leaderboard`, `!inventory`, `!treasury`
- Read-only GUI/overlay buttons
- Boss battle participation (jailed players are still summoned, still fight)

### UI feedback

- **Overlay player card:** 🚔 badge next to username when jailed. Optional: countdown timer showing remaining sentence.
- **Inline error on blocked actions:** when a jailed player tries a blocked command (chat or button), respond with a clear, themed message in chat + the same surfaced on the game overlay event log. Example: `@user 🚔 you're locked up — N min remaining. Someone has to !bail you out.`
- **Jail-start announcement:** broadcast in chat + overlay event when a player is jailed, with reason and duration.

---

## 3. Treasury (the bail vault)

A new location-like entity that accumulates bail money. **Not a hackable location** in v1 — players cannot `!hack treasury`, it doesn't appear in `!hack` autocomplete, no attacks target it.

### Behavior

- Public running balance.
- `!treasury` command shows current balance in chat.
- Overlay can display the balance as a watermark/widget (optional, not required for v1).
- Bail payments flow here (see §4).
- Future content hook: a "heist" mechanic could later make this hackable. Keep the data model open for that, but don't build it now.

### Data model

A single `treasury_balance: int` field stored alongside global game state (not per-player). All bail-derived points flow here. Initial value: 0.

---

## 4. Bail

### Formula

```
bail_cost = jail_duration_minutes × jailed_player_level × 5
```

Examples:
- loafageddon (lvl 5126), 4-min jail → **102,520 pts**
- newbie (lvl 3), 1-min jail → **15 pts**
- veteran (lvl 500), 16-min jail → **40,000 pts**

### Flow

- Any player can post bail by running `!bail @username`.
- Bailer pays **nothing** out of pocket — they just initiate.
- Bail amount is drained from the **jailed player's wallet**.
- If the jailed player has `< bail_cost` points → bail **fails**, jailed stays in. Bailer gets a "they're broke, can't post bail" message.
- On successful bail:
  - 90% of bail goes to **treasury** (`treasury_balance += 0.9 × bail_cost`)
  - 10% goes to the **bailer** (`bailer.points += 0.1 × bail_cost`) as a finder's fee
  - Jail ends **immediately** for the jailed player
  - Strikes reset, offense counter does *not* reset (jail tier still escalates next time)
  - Announce in chat + overlay: `@bailer just bailed @jailed for X pts. Treasury: Y pts.`

### Constraints (v1)

- One bailer per jailing. No split bail, no auctioning.
- No `!refusebail` from the jailed side — anyone with the bail amount can spring them.
- Payroll mechanic explicitly **dropped** — we discussed and chose IRL-faithful bail instead.

---

## 5. Burner Laptop (new item drop)

A consumable item that lets a player blow through their next batch of attacks.

### Mechanic

- One-shot consumable. Player runs `!useburner` (or similar) at a location.
- Fires **10 attacks automatically** at the current location, using the **strongest unlocked attack** at that location.
- Each shot rolls success/failure as normal, paying out rewards/penalties as normal.
- **Bypasses** the speed-penalty check entirely — these 10 shots do not generate strikes regardless of timing.
- After the 10th shot, the item is consumed and vanishes from inventory.
- Cannot be used while jailed (item-use is blocked — see §2).

### Acquisition

- New drop. Loot table needs an entry — defer specifics to implementation (probably ground drop + boss battle drop), but flavor it as a rare-ish find.

---

## 6. Data model changes

Per-player additions to `player_data.json`:

```jsonc
{
  "last_attack_at": {           // per-location timestamps for speed check
    "email": "2026-05-09T14:23:01.123Z",
    "server": "..."
  },
  "speed_strikes": 0,           // current strike count (0–3)
  "last_strike_at": null,       // for 10-min decay
  "jail": {                     // null when not jailed
    "until": "2026-05-09T14:30:00Z",
    "reason": "speed" | "steal_fail",
    "offense_number": 3         // current rung on the squaring ladder
  },
  "last_jail_released_at": null, // for 24h ladder reset
  "offense_count": 0            // persistent ladder position
}
```

Global state additions:

```jsonc
{
  "treasury_balance": 0
}
```

---

## 7. Implementation surface (where this touches)

Best-guess file map — confirm during implementation:

- **`PainfulBot.py`** — attack command handlers (`crack`, `stealth`, `bruteforce`, `phish`, etc.) need the speed-check wrapper. `!steal` needs the jail-on-fail branch. New commands: `!bail`, `!treasury`, `!useburner`.
- **`playerdata.py`** — extend player model with the fields in §6. Persist treasury balance somewhere global (likely a new `game_state.json` or a top-level key in `player_data.json`).
- **`game/`** — natural home for a new `jail.py` module: speed-check logic, strike accounting, jail enter/exit, bail math. Type-owned dispatch (per CLAUDE.md modularity rule): attacks call `jail.check_speed(player, location)` → returns penalty/strike result; commands call `jail.is_jailed(player)` to gate themselves.
- **`integrations/game_overlay.py`** and **`integrations/battle_overlay.py`** — emit jail events, 🚔 badge state.
- **`boss_battle/templates/`** + **overlay templates** — render the 🚔 badge on player cards, show treasury widget.
- **Loot tables** (wherever items.py lives) — register Burner Laptop.
- **Telemetry:** add per-attack timestamp logging (currently absent) so we can re-tune thresholds from real data after a stream. CSV or append-only JSONL, one line per attack with `(user, location, gap, was_strike, penalty)`.

### Modularity (per project CLAUDE.md)

- A new attack/location should not require editing the jail module. Speed thresholds are config-driven (the table in §1) — adding evilcorp2 means one new row, no code change.
- Jail-blocked vs. jail-allowed command status should be a property of the command (e.g., a decorator `@jail_blocks` or a list in command metadata), not a hardcoded ladder of `if jailed and cmd in [...]` inside the jail module.

---

## 8. Test plan

Per project CLAUDE.md ("every feature gets a test"):

- Speed check: at threshold = no strike; just below = strike + penalty; at level boundary = correct threshold tier picked.
- Strike decay: 10 min idle resets to 0.
- Jail enter/exit: state transitions, blocks correct commands, allows movement + read-only.
- Squaring ladder: 5 offenses produce 1, 2, 4, 16, 256.
- 24h ladder reset.
- Bail math: 90/10 split, treasury credited, broke jailed → bail fails.
- `!steal` fail → direct jail (no strike path).
- Burner Laptop: 10 shots, bypasses speed check, vanishes.
- Boss battle eligibility while jailed.

---

## 9. Explicitly out of scope (v1)

- Hacking the treasury (future heist mechanic — data model leaves room)
- Multi-bailer / bail auctions / `!refusebail`
- Payroll bail variant (discussed, dropped)
- Per-attack GUI cooldowns / greyed buttons (discussed, dropped — by design)
- Auto-jail integration with Twitch's `/timeout` mod action (in-game lock only)

---

## 10. Open tuning knobs (revisit after one stream)

- Speed threshold table values
- Penalty multiplier (start: 3.0)
- Strike decay window (start: 10 min)
- Jail ladder reset window (start: 24h)
- Bail formula constant (start: × 5)
- Burner Laptop attack count (start: 10) and drop rate
