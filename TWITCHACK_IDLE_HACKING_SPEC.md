# TwitcHack Idle Hacking — Design Spec

**Status:** Draft / planning. Nothing here is built yet.
**Owner:** Theo
**Origin:** Loaf's suggestion to turn the points game from a *clicker* into an
*idle game* — "hacks take time, harder hack == more points == more time, run
multiple hacks at once because we're asynchronous multiprocessors, buy
hardware/software to increase computing power and cut hack time."

This doc is the source of truth for the design. We build it in **phases**, each
phase shippable and playable on its own. Numbers in here are starting points for
playtesting, not final — anything tagged `(tune)` is expected to move.

---

## 1. Vision & pillars

We are **not** replacing the clicker. We are adding an idle layer *on top* of it
and turning the clicker into the beginner on-ramp. The whole game becomes a
progression ladder:

```
   Tier 0   CLICKING        no hardware. Manual !phish/!spoof/etc at a location.
            (what exists)   Small, instant, hands-on. How everyone starts.
              │
              ▼  buy your first machine
   Tier 1   RASPBERRY PI    your first "rig". Unlocks idle hacks: start a timer,
                            it resolves later for points. 1 job at a time.
              │
              ▼  upgrade
   Tier 2   LAPTOP (Dell)   prebuilt, stronger. More job slots, faster, more
                            storage. Still no assembly required.
              │
              ▼  go custom
   Tier 3   CUSTOM TOWER    buy a case + motherboard + CPU + RAM + storage + GPU.
                            Build your own rig. Scales the highest. GPU unlocks
                            crypto/password cracking hacks.
```

**Design pillars**

1. **Clicking stays, as the tutorial.** It's instant-gratification, requires no
   purchase, and teaches the locations/commands. It stays small so it's an
   on-ramp, not the endgame.
2. **Idle = parallel timers.** A "hack" is a job with a duration. Harder hacks
   take longer and pay more. You can run several at once — that's the whole
   "asynchronous multiprocessor" fantasy. Concurrency is the core resource.
3. **Hardware is the upgrade tree.** You spend points on parts. Parts increase
   (a) how many jobs you can run at once and (b) how fast they finish, and some
   parts (c) unlock whole categories of hack (GPU → password cracking).
4. **Points get a sink.** Today points only feed leveling. Hardware gives points
   a place to go: earn → buy faster/wider rig → earn more. That loop *is* the
   idle genre.
5. **One file per variant.** Per CLAUDE.md: a new hack, a new component, a new
   prebuilt should be a single data row in a registry — never a new 40-line
   handler and never a central `if` ladder to edit.

---

## 2. What exists today (so we know what we're changing)

- **Clicker attacks**: ~20 near-identical command handlers in `PainfulBot.py`
  (`!phish`, `!spoof`, `!bruteforce`, `!sniff`, …). Each: check registration →
  check location → check level → `_jail_speed_gate(base_reward=N)` → roll
  success → `player.points += random.randint(...)`. Each already carries a
  `base_reward` and a level gate.
- **Locations**: `home`, `email`, `website`, `/etc/shadow`, `database`,
  `server`, `network`, `evilcorp`. `!hack <location>` moves you.
- **Anti-clicker system**: `game/jail.py` (speed strikes, jail, bail, treasury)
  exists *to stop auto-clickers spamming the instant attacks*.
- **Items**: `items.py` + `HACK_ITEMS` in `PainfulBot.py`. Items give attack
  bonuses (`get_item_bonus`) and map to boss-battle attacks.
- **Player model**: `playerdata.py` — `level, health, max_health, items,
  location, points, …` persisted to Postgres (JSONB) per the March 2026 refactor.

**Implications for this design**

- The idle model makes spamming pointless (a 90s timer can't be "clicked
  faster"), so `jail.py` stops being load-bearing for idle hacks. We **keep**
  the clicker's speed-gate for the clicker tier, but idle jobs don't need it.
- The 20 copy-paste handlers are the natural thing to collapse into one
  data-driven path as we go (see Phase 2). The attacks aren't thrown away — each
  becomes a **row in a registry**.

---

## 3. Core model — Jobs (a "hack" is a timer)

A **job** is one running hack. Definition (a registry row, data only):

```
HackDef:
  id            : str         # "wpa2_crack", "sql_dump", ...
  name          : str         # "Crack WPA2 handshake"
  category      : str         # network | password | malware | web | social | exfil
  location      : str | None  # where you must be, or None = anywhere
  level_req     : int         # min player level
  base_duration : int (sec)   # before speed multipliers
  reward        : (lo, hi)    # points on success, before bonuses
  hw_req        : dict        # {"gpu_power": >=N} / {"storage": >=N} / {} = none
  effect        : dict | None # reuse existing effect vocabulary where it fits
```

**Runtime job state** (lives on the Player):

```
Job:
  hack_id      : str
  started_at   : iso
  finishes_at  : iso          # started_at + duration_after_multipliers
  # resolved lazily; no background thread required for v1
```

**Lifecycle**

```
!run <hack_id>      → if a free job slot AND level/hw/location ok:
                      compute duration, push a Job with finishes_at, reply ETA.
!jobs               → list running jobs + live countdowns.
(any interaction)   → resolve_due_jobs(player): for each job past finishes_at,
                      roll reward, bank points, emit ticker event, free the slot.
```

**Reward scales with time.** Rule of thumb: `reward ≈ k * base_duration`
`(tune)`, so a 5s micro-hack pays a little and a 6-minute heist pays a lot.
Keep a spread:

- **Short jobs (5–20s)** — dopamine + chat noise, keeps the stream alive.
- **Long jobs (2–10 min)** — the AFK/idle layer; start them and wander off.

The active decision is *what to queue next with the slots you have*, not staring
at one timer.

---

## 4. Core model — Rig & components (the capability system)

A player owns a **rig**: a set of installed components. Components aggregate into
a `RigStats` profile that the job system reads. This is the one piece of real
architecture — get it right and everything else is data.

### 4.1 RigStats (the aggregate the game actually reads)

```
RigStats:
  threads      : int   # raw concurrency from compute (CPU)
  memory       : int   # "GB" RAM; each running job consumes some
  storage      : int   # "GB"; gates data-heavy hacks (malware/exfil)
  gpu_power    : int    # crypto/cracking acceleration; 0 = no GPU
  clock        : float # general speed multiplier (CPU clock / quality)
```

### 4.2 Derived numbers (formulas, all `(tune)`)

- **Job slots** = `min(threads, floor(memory / MEM_PER_JOB))`
  - `MEM_PER_JOB = 2` (GB). This is the key depth knob: a 16-thread CPU with
    2 GB RAM still only runs 1 job. You need **both** compute and memory —
    which is exactly why you'd buy RAM *and* a CPU. Naturally teaches PC
    building.
- **Duration** = `base_duration / (clock * category_speed)`
  - `category_speed` = `gpu_power`-derived for `password`/crypto categories,
    else `1.0`. This is what makes a GPU *feel* like a GPU: "crack hashes 5×
    faster," and useless for phishing.
- **Unlocks**: a hack with `hw_req {"gpu_power": >=5}` simply can't be started
  until the rig meets it. Same for `storage`. No special-casing — the job
  system checks `hw_req` against `RigStats` uniformly.

### 4.3 Component definition (a registry row)

```
Component:
  id           : str
  name         : str        # "ASUS ROG B650", "AMD Ryzen 7", "Corsair 4000D"
  kind         : str        # cpu | ram | storage | gpu | motherboard | case
                            #  | psu | prebuilt
  cost         : int        # points
  level_req    : int
  stats        : dict       # contribution to RigStats (threads/memory/…)
  slots        : dict       # (motherboard/case only) sockets it provides
  draw         : int        # (optional) watts consumed; PSU must cover sum
```

A **prebuilt** (`kind: prebuilt`) is a single component that hardcodes a whole
`RigStats` and provides no expansion — Raspberry Pi, Dell laptop. A **custom
build** is `motherboard + case` providing sockets, into which you install
`cpu/ram/gpu/storage`. The case + motherboard cap how much you can install; the
PSU (later phase) caps total `draw`.

**Adding hardware later = one row.** No dispatcher edits. The aggregation walks
whatever components the player owns and sums/min's their stats.

---

## 5. Hardware catalog (first pass — all stats `(tune)`)

This is the fun, fillable part — Theo's list plus room to grow. Treat the
numbers as placeholders to balance during playtest.

**Brand-neutral by design (decided 2026-05-31).** Hardware uses generic names,
not brands — so the game stays neutral and a **sponsor can be slotted into a
tier later**. The architecture already supports this for free: a component's
`id` (internal/command handle) is decoupled from its `name` (display), and only
`id` is persisted on a player's rig, so a name is a swappable display layer with
zero migration. (Theo's original brand list below is kept as *inspiration* for
stats/role; the shipped names are generic.)

### 5.1 Prebuilts (no assembly — the early/mid game)

| id | name | cost | threads | memory | storage | gpu | clock | notes |
|----|------|------|---------|--------|---------|-----|-------|-------|
| `sbc` | Single-Board Computer | ~200 cash | 4 | 2 | 16 | 0 | 0.8 | **first rig. ✅ SHIPPED.** 2 GB → exactly 1 job slot (`min(4, floor(2/2))=1`). RAM is **soldered** (real SBCs) so it can't be expanded — you graduate to the next machine for concurrency. clock 0.8 = jobs run 1.25× slower than base. 16 GB card → locked out of malware/exfil; gpu 0 → locked out of crypto/cracking. (Was the branded "Raspberry Pi"; renamed brand-neutral 2026-05-31, id `rpi`→`sbc` with a one-row DB migration.) |
| `laptop` | Laptop (portable rig) | mid | 8 | 16 | 256 | 1 | 1.0 | ~2–3 slots; tiny iGPU. Next tier (Phase 2). Brand-neutral name. |

**Why the SBC's weakness is the point:** every weak stat previews an upgrade
reason *before* you leave it — more RAM = more slots (but SBC RAM is soldered,
so: buy a bigger machine), more storage = malware/exfil hacks, a GPU = cracking.
The SBC runs the whole Phase-1 starter set and nothing heavier.

### 5.2 Parts (the custom tower — mid/endgame)

| id | name | kind | stats (contribution) | notes |
|----|------|------|----------------------|-------|
| `asus_b650` | ASUS Motherboard | motherboard | slots: {cpu:1, ram:4, gpu:2, storage:4} | the chassis of capability |
| `corsair_4000d` | Corsair Case | case | bays/airflow caps | limits parts + (later) thermals |
| `intel_cpu` | Intel CPU | cpu | threads +N, clock +x | general speed + slots |
| `amd_cpu` | AMD CPU | cpu | threads +N, clock +x | more threads, theme rivalry |
| `ram_16gb` | 16 GB RAM | ram | memory +16 | stack multiple → more job slots |
| `hdd_1tb` | 1 TB Hard Drive | storage | storage +1000 | unlocks malware/exfil hacks |
| `gpu_*` | GPU (tiers) | gpu | gpu_power +N | unlocks + speeds crypto/cracking |
| `psu_*` | Power Supply | psu | watt budget | (Phase 3) caps total draw |

**Room to grow (note, don't build yet):** SSD vs HDD (speed vs capacity),
cooling (overclock = more clock but needs cooling), multi-GPU rigs, compatibility
flavor (Intel CPU needs Intel-socket board, AMD needs AM5) as optional Phase 3+
depth, branded/rare drops as loot.

---

## 6. Hacks catalog by category (first pass)

Categories map to hardware so each purchase *unlocks something visible*. Many of
these are the **existing clicker attacks reframed as timed jobs** — same name,
now with a duration. Existing clicker versions stay as the Tier-0 instant
variants.

| category | example hacks | gated by | flavor |
|----------|---------------|----------|--------|
| `social` | phish, spoof | none (clicker too) | the on-ramp; overlaps Tier 0 |
| `network` | recon scan, packet sniff, DDoS | any rig | bread-and-butter idle |
| `web` | SQL dump, XSS, session hijack | any rig | medium jobs |
| `malware` | ransomware payload, botnet | `storage >= N` | needs disk |
| `exfil` | data heist, db exfiltration | `storage >= N` (big) | long, high pay |
| `password` | brute force, **WPA2 / hash crack** | `gpu_power >= N` | GPU shines here |

**Duration/reward tiers** `(tune)`:

| tier | base_duration | reward | who runs it |
|------|---------------|--------|-------------|
| micro | 5–20 s | small | everyone, incl. Pi |
| standard | 30–120 s | medium | laptop+ |
| heavy | 3–10 min | large | tower; storage/GPU-gated |

### 6.1 Phase-1 starter hacks (the Raspberry Pi set)

The four hacks Phase 1 ships with. All `location: anywhere` (run from home — we
location-gate hacks in a later phase) and all Pi-legal (`gpu_power: 0`, low
`storage`). Times shown are **Pi-effective** (`base ÷ clock 0.8`); a faster
machine shrinks them. Cash-heavy split (cash ≈ 2–3× rep) — opposite of clicking
— so hacks fund the climb to the Dell laptop. Failure = lose the time, **no
payout**; **no trace/jail at this tier** (that's reserved for high-tier hacks).

Idle hacks are invoked `!run <id>`, namespaced under the `run` command — they are
**not** top-level Twitch commands, so a hack id can never shadow a clicker
command (e.g. the clicker's `!phish`). Names are still kept distinct for player
clarity.

| hack | id | category | base_dur | Pi time | success | cash / rep | role |
|------|-----|----------|----------|---------|---------|-----------|------|
| Port scan | `portscan` | network | 12 s | 15 s | 95% | 8 / 3 | the "hello world" micro-hack |
| Service scan | `servicescan` | network | 36 s | 45 s | 92% | 25 / 10 | short, bread-and-butter |
| Spear-phishing | `spearphish` | social | 48 s | 60 s | 90% | 30 / 12 | reuses phish flavor, renamed to avoid clicker `!phish` |
| Credential stuffing | `credstuff` | web | 144 s | 3 min | 88% | 90 / 30 | first "start it and walk away" job |

> **Credential stuffing ≠ password cracking.** Stuffing *replays known* creds, so
> it needs no GPU and is Pi-legal. Hash/brute-force *cracking* stays
> `gpu_power`-gated — that's what keeps the GPU purchase meaningful later.

All numbers `(tune)` — per Theo, we won't really know until we game-test it.

---

## 7. The ticker-tape OBS overlay

A horizontal scrolling marquee (like a stock ticker / news crawl) as an OBS
browser source — separate from the boss overlay, runs all the time during a
stream showing live hacking activity.

**What scrolls:** `theo2612 started Brute force @ database (ETA 2m)` ·
`cypherenigma CRACKED WPA2 handshake +340` · `loaf bought an AMD CPU` ·
`new high score: …`. Big events (heist completes, rig upgrades, level-ups) get
emphasis.

**Architecture — copy the patterns already in the repo:**

- New self-contained folder `ticker/` (mirror `stream_todo/` and `boss_battle/`):
  Flask + Flask-SocketIO + eventlet, own `.venv`, `start.sh`.
- OBS source `http://localhost:3004/` (3000 todo, 3001 guide, 3002 twitchack,
  3003 boss → **3004 ticker**).
- The bot pushes events fire-and-forget over HTTP via a new
  `integrations/ticker.py`, mirroring `integrations/battle_overlay.py`
  (`POST /api/event`, server re-broadcasts over WebSocket to the page).
- The page is a CSS marquee fed by `socket.on('event', …)`, appending to a
  scrolling queue. Color/emphasis by event type, same spirit as the boss
  combat-log colors.

This is largely **independent** of the game logic — it can be built and tested by
hand-posting events before the idle system exists.

---

## 8. Economy & point sinks

**DECIDED — two currencies (dual-drop, no conversion):**

- **Rep** = the *existing* `points` field, kept as-is. It is a monotonic odometer
  that drives levels via `level_for_points()` (`bot/leveling.py`). Never spent,
  never decreases. Everyone keeps their current level; the curve and founder
  tiers are untouched. (UI-rename "points" → "rep"; the stored field can stay
  named `points` to avoid migration.)
- **Cash** = a *new* spendable wallet field on Player, starts at 0. The only
  thing hardware costs. Spending cash never touches rep, so **buying a rig can
  never de-level you** — which is the whole reason for the split: level is read
  off the points balance, so a single shared pool would drop your level when you
  shop. There is **no rep→cash conversion** (it would reintroduce the de-level
  bug or just confuse).
- **Both drop together:** every completed hack (and every Tier-0 click) pays a
  little **rep** (progression) and some **cash** (to spend). Tune the two rates
  independently.

- Hardware is the sink. Price the ladder so a fresh player can afford a
  Raspberry Pi after a session of clicking, a laptop after a few, a full tower as
  a long-term goal `(tune)`.
- Retune cash/minute: time-gating changes the earn rate vs. today's clicker. A
  maxed rig should feel powerful but not trivialize the cash economy.

**Consequences of the split (decided with Option A, 2026-05-30):**

- **Theft targets CASH, not rep.** The existing steal mechanic
  (`attacker.points += stolen` in `PainfulBot.py`) must be repointed at cash —
  you rob a wallet, not a reputation. Stealing rep would de-level the victim
  (the exact bug the split exists to prevent). This is a required change when we
  touch stealing, and it's *more* thematically sound.
- **Veterans start broke.** Existing players keep their large rep (and thus their
  level) but begin with **cash = 0**. Accepted: it gives established players a
  fresh grind rather than letting them instakit a top-tier rig. (Revisit if it
  feels punishing — a one-time starter grant is an option.)
- **Earn mix is a lever, not a fixed ratio.** Rep and cash need not drop at the
  same rate from the same source. Planned use: **clicking pays mostly rep**
  (level up early, the on-ramp) while **idle hacks pay mostly cash** (get rich,
  fund the rig). This is also the clicker-ceiling knob (open-Q #5).
- **Bootstrap rule — clicking must pay *some* cash.** Your first Pi is bought
  with cash, and pre-Pi you can only click. So clicking is cash-*light* but never
  cash-*zero*, or the game can't start. Starting point `(tune)`: **click ≈ 4
  cash / 5 rep**, so a ~200-cash Pi ≈ 50 clicks (≈ one session). The earn-mix
  lever still holds — clicks are cash-poor *relative* to hacks.
- **Naming `(tune)`:** "rep" and "cash" are working names; hacker-flavored
  options on the table — rep as cred/notoriety, cash as credits/BTC/crypto/bytes.
  Decide at UI time; does not affect the data model.

---

## 9. Data model & code changes

**Player (`playerdata.py`)** — new fields (all optional, back-compat like the
existing `to_dict` pattern that omits falsy keys):

- `rig: list[str]` — installed component ids (prebuilt or parts).
- `jobs: list[dict]` — running jobs `{hack_id, started_at, finishes_at}`.

**New registries (one row per variant, auto-aggregated):**

- `game/hacks.py` — `HACK_DEFS` table (§3) + `resolve_due_jobs()`.
- `game/hardware.py` — `COMPONENTS` table (§4.3) + `rig_stats(player)`
  aggregator + derived `job_slots()` / `duration_for()`.

**Commands (data-driven, not per-hack handlers):**

- `!run <hack>` / `!jobs` / `!rig` / `!shop` / `!buy <component>`.

**Reuse:** item-bonus vocabulary (`get_item_bonus`), effect dicts, the Postgres
JSONB persistence, the overlay HTTP-push pattern.

**Retire/repurpose:** `jail.py` speed-gate stays for Tier-0 clicking only; idle
jobs skip it. (Open decision: keep jail as flavor for failed high-tier hacks?)

---

## 10. Phased rollout (build order — each phase ships on its own)

> Principle: every phase is playable and testable before the next starts. Write
> a test per feature, a regression test per bug (CLAUDE.md).

- [ ] **Phase 0 — keep clicking.** No code. Confirm Tier-0 clicker stays as the
      beginner experience. ✅ already exists.
- [x] **Phase 1 — minimal idle loop.** ✅ BUILT 2026-05-30. One prebuilt
      (Raspberry Pi), `cash`/`rig`/`jobs` on Player (`playerdata.py`),
      `game/hardware.py` (RigStats aggregation + `buy_component`) and
      `game/hacks.py` (4 starter hacks + lazy `resolve_due_jobs`). Commands
      `!buy` / `!run` / `!jobs` wired feed-only (WebCtx, never Twitch chat);
      click→cash bootstrap in `_attack_result`; cash shown in `!status`/`!points`.
      **1 job slot, no concurrency yet.** 20 unit tests in
      `tests/test_idle_hacking.py` (incl. a regression for the `run` vs
      `Bot.run()` startup-shadow crash hit during bring-up). ✅ Live-tested on
      the running bot (buy → run → jobs cycle confirmed in the feed) and
      committed (`0157c94`).
- [ ] **Phase 2 — concurrency + collapse the clicker.** RigStats aggregation,
      `job_slots` formula, second prebuilt (laptop) for 2–3 slots. Reframe the
      existing clicker attacks as `HackDef` rows (Tier-0 instant variants),
      retiring the copy-paste handlers.
- [ ] **Phase 3 — custom tower.** Parts catalog (mobo/case/cpu/ram/storage/gpu),
      `!shop`/`!buy`/`!rig`, slot limits, GPU-gated `password` hacks, storage-
      gated `malware`/`exfil`. PSU/thermals/compatibility optional depth.
- [ ] **Phase 4 — ticker overlay.** `ticker/` app + `integrations/ticker.py`,
      wire events from Phases 1–3. (Can be prototyped earlier in isolation.)
- [ ] **Phase 5 — balance pass.** Tune all `(tune)` numbers from telemetry
      (reuse the `attack_log.jsonl` telemetry habit). Decide jail's fate.

---

## 11. Decisions

**Resolved (2026-05-29):**

1. ✅ **Currencies — split, dual-drop.** Rep (existing `points`, drives levels,
   never spent) + Cash (new wallet, spent on hardware). No conversion. See §8.
2. ✅ **Failure model — hacks CAN fail.** A finished job rolls success/failure
   (lose the time, partial or zero payout). A failed high-tier hack may later
   "trace" you → cooldown (candidate repurpose for `jail.py`). Tune fail rates
   per tier `(tune)`.
3. ✅ **Resolution — background ticker, feed-only.** BUILT 2026-05-30:
   `Bot.idle_ticker_loop()` (launched in `event_ready`, `IDLE_TICK_SECONDS=5`)
   scans players with running jobs and settles + announces finished hacks on the
   feed the moment they complete — no need to poke `!jobs`. It reuses the lazy
   per-player resolver (`_resolve_idle_jobs`), which the command handlers still
   call too for instant settlement between ticks. Resolution logic lives in one
   place; `resolve_due_jobs` is synchronous so ticker/command calls can't
   double-resolve.
4. ✅ **Output channel — TwitcHack feed, NEVER Twitch chat.** Hack starts,
   results, payouts, purchases all surface in the on-screen TwitcHack feed /
   ticker overlay. **No `ctx.send()` to Twitch chat for idle-hacking events.**
   (This is a hard constraint — see note below; it also informs whether the
   existing clicker's chat replies get migrated to the feed.)

**Still open:**

5. **Clicker ceiling:** how small do we keep Tier-0 so it stays an on-ramp and
   doesn't compete with idle income?
6. **Concurrency cap:** hard ceiling on job slots regardless of rig? (Prevents a
   whale from running 50 jobs and flooding the feed/ticker.)
7. **Existing clicker chat replies:** the current clicker attacks reply in Twitch
   chat. Per decision #4, do we migrate those to the feed too, or leave Tier-0
   as the one chatty tier? (Affects whether `_attack_result` keeps sending.)

> **Output constraint (#4) restated for implementers:** idle-hacking code emits
> to the TwitcHack feed/overlay via the `integrations/` HTTP-push pattern, not to
> Twitch chat. Keep the two paths separate so the feed is the home for game
> activity and chat stays clean.
```
