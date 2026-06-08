# TwitcHack — Dev Backlog

The living list of what we want to build/fix next. Plain-English on purpose.
Design *details* live in the spec (`TWITCHACK_IDLE_HACKING_SPEC.md`); this file
is just the prioritized "what's next."

## How this list works
- **Now** = actively building. **Next** = teed up. **Later** = agreed, not scheduled.
- Check items off (`[x]`) and add a one-line "done — <commit>" when finished.
- Anyone (any Claude session, any day) reads this first to know where things stand.

## Working across sessions (so it doesn't get confusing)
The friction isn't "using another session" — sessions always end eventually. The
fix is that **the written state is the shared brain**: this backlog + the spec +
the git history + Claude's project memory. As long as those are kept current and
we **commit small finished chunks** (see `WORKFLOW.md`), any session — this one
continued, or a brand-new one — can pick up cleanly. The only thing to avoid is
**two sessions editing at the same time** (that causes real conflicts); one at a
time is totally fine.

---

## Guiding principle: GUI-first
**TwitcHack is played in the GUI (the /twitchack page). Twitch chat and the
on-screen feed should show *outcomes and story*, never command syntax.**
- Players act via **buttons**, not by typing `!run` / `!buy`.
- `!commands` still exist under the hood (they power the web buttons), but they're
  an implementation detail — not the player-facing interface.
- The bot should not post `!command` instructions or spam to **Twitch chat** for
  game actions.
- The **feed** shows narrative ("b7h30 cracked WPA2 — +340 cash"), not "!run".

---

## Where we are (resume point — last session 2026-06-07/08)
Idle-hacking is the live focus and it's deep now. Shipped (commit hashes in the
roadmap below):
- **GUI-first migration — COMPLETE.** Game actions play in the GUI; Twitch chat +
  feed show outcomes, not `!commands`. Shop drawer; drops → feed + Grab buttons;
  "TWITCHACK LIVE" header; top stats strip removed.
- **Per-machine rigs** — each machine its own slots + clock; total concurrency =
  the sum; you pick which machine to run a hack on (Rig row selector).
- **Hardware ladder:** SBC (1 slot) → Laptop (3) → Desktop (6), plus a rented
  **Cloud VPS** (4, no wear, ongoing rent).
- **Content/stats:** bandwidth → exfil ("Database exfiltration"); **Corporate
  data heist** (Desktop-exclusive); **wear & tear** (condition → slowdown →
  repair sink; 0% = ¼ speed); **AIO cooling + overclock** (per-machine part,
  1.5× speed / 2.5× wear; realistic — laptop is sealed, SBC/desktop tinkerable);
  **VPS rental** (2nd cash sink).
- The flicker fix (dirty-checked renders) so buttons don't churn on updates.

Everything above is committed. **NOTE:** as of this checkpoint these commits are
local-only — not yet pushed to GitHub (see end of this file).

## Next up (pick one)
1. **Trace / jail-on-failure risk system** ← *recommended*: it's the prerequisite
   that UNBLOCKS both the botnet and VPN/stealth. Today a failed hack just costs
   time; this adds a chance a risky/failed hack "traces" you → cooldown/jail
   (repurpose `game/jail.py`). Stealth/VPN then mitigates it.
2. **Botnet** — the VPS's spicier sibling (more slots, cheap, unreliable/risky).
   Wants the risk system (1) first.
3. **VPN / stealth** — `stealth` stat lowers trace/jail risk. Wants (1) first.
4. **Software upgrades** — the second upgrade *axis* (exploit kits / scripts →
   per-category speed/success boosts). Self-contained, no prerequisite.
5. **Deferred wear layers** — needs-maintenance-to-start / hacks-can-fail /
   finite-repairs→death (Theo liked these; kept gentle for v1).
6. Smaller: **follow/sub drops bug** (EventSub 403 — see Bugs) · **slim the
   clicker attacks** (see Ideas) · a higher-bandwidth machine tier.

## Bugs / investigate
- [ ] **Follow/sub drops don't fire.** Items are supposed to drop when someone
      follows/subs (`random_item_drop` via `event_follow`/`event_subscription`).
      Likely root cause is upstream: the bot logs `EventSub setup failed: 403:
      You are not authorized to make this subscription` on boot — if EventSub
      never subscribes, the follow/sub events never arrive and the drop never
      runs. Investigate the EventSub auth/scopes first (the grab-button fix in
      `83a51c0` is downstream of this and won't be reached until events fire).

## Ideas / design
- [x] **Wear & tear v1** (`1aa5dd7`, `4ba6347`) — per-machine `condition` drops
      per completed hack; low condition **slows** the machine; **repair** with
      cash (pricier each time) = the game's first ongoing cash sink. GUI shows
      condition % + 🔧 repair buttons in the Rig row.
      **Deferred layers (build later):** "needs maintenance to start" (offline
      below a threshold); "hacks can fail" (rising fail chance with wear);
      finite repairs → machine permanently dies. (All pair with the future
      cooling/overclock stat: heat → faster wear.)
- [ ] **Slim the clicker attacks** (Theo, 2026-06-07): the game's focus is the
      hardware/idle side; the per-location clicker attacks are the Tier-0
      on-ramp and several are near-duplicates. Cut ~1 per location. Do it as a
      deliberate pass, not rushed — watch for: level-gate spacing (attacks carry
      the early leveling ladder), item→attack bonus mappings (`get_item_bonus`),
      and boss-battle usage. Keep ≥1–2 per location so movement still has a
      point. (Separate from idle-hacking content; schedule on its own.)

## Later

### Idle-hacking content roadmap
Design + stats in `TWITCHACK_IDLE_HACKING_SPEC.md` §5–6.
- [x] **Bandwidth → exfil** (`5ad246b`, `4558a89`) — `bandwidth` rig stat gates +
      speeds the new `exfil` category. SBC bw 1 (locked out), Laptop bw 4 (runs
      "Database exfiltration", faster via its fat pipe). GUI shows 🔒 on machines
      that can't run a hack. (Future: a high-bandwidth machine tier + a bigger
      heist hack gated higher.)
- [x] **Cooling → overclock** (`3524314`, `667ad16`) — AIO cooling is a
      per-machine part; once installed you toggle overclock: 1.5× speed, 2.5×
      wear. First per-machine "part." (Future: cooling tiers, a wear-reduction
      cooling, overclock as a dial instead of on/off.)
- [ ] **VPN / stealth** — `stealth` stat lowers trace/jail risk (needs the
      failure→trace model fleshed out first).
- [x] **VPS** (`4e3a7cb`, `5d12214`) — rented, non-wearing machine; ongoing rent
      (2nd cash sink), prepaid-block model, lapses if unpaid. Shop Rent button +
      Rig-row uptime/renew/cancel.
- [ ] **Botnet** — spicier sibling: more slots, cheap, but unreliable/risky.
      Best after the trace/jail-on-failure system (the risk it carries).
- [ ] **Software upgrades** — the missing *axis*: exploit kits / scripts / 0-days
      giving per-category speed/success boosts. The other half of the original
      "hardware **and** software" pitch.

---

_Older pre-idle-hacking design notes live in `TwitcHackToDo.md` (historical)._
