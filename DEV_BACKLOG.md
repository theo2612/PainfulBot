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

## Now
- **GUI-first chat migration** — in progress.
  - [x] Block game commands typed in Twitch chat → nudge to GUI (`2614b4d`).
  - [x] Info commands GUI-only (folded into the block).
  - [x] Header: "TWITCHACK LIVE" + twitch.tv/b7h30; removed the top stats strip (`667a087`).
  - [x] Build the Shop — right-side drawer, Hardware/Items/Software tabs (`e460af4`).
  - [x] Clean `!commands` out of the feed (`95ecf24`).
  - [x] Move drop announcements to the feed (`83a51c0`) — drops now feed + Grab
        button, no chat, no "!grab" syntax. (Also fixed: follow/sub drops had no
        grab button → were ungrabbable with !grab blocked.)
  - [ ] (optional) decide boss-battle broadcasts (kept in chat for now).

**GUI-first migration: COMPLETE.** Next theme = idle-hacking content (roadmap below).

### Per-machine rigs + Rig row — ✅ DONE (`77798a4`, `0b4bb0b`)
Each owned machine is its own workstation: own slots + own clock speed, total
concurrency = the sum, jobs tagged to a machine and timed by its clock. GUI Rig
row selects the active machine; Run targets it. (Future: custom-tower parts
assemble into one machine; owning multiple of the SAME machine type would need
instance ids — not built.)

## Next

### 1. Build a proper Shop in /twitchack
A real place to buy hardware (and soon items + software upgrades), so purchasing
never has to happen in Twitch chat.
- [ ] A dedicated Shop section/panel (not just the inline "Rig" row) listing
      buyable hardware with name, cost, and what it does. Buttons already exist;
      this is making it a deliberate "store," and extending it beyond hardware.
- [ ] Make sure buying works **only** in the GUI, not by typing `!buy` in chat
      (see item 3 — neutralize the chat side).

### 2. Clean `!commands` out of the feed
The feed currently shows raw command text, e.g. `@b7h30 !run @b7h30 started Port
scan…`. It should read as narrative without the `!run` / `!buy` prefix.
- [ ] Stop rendering the `command` label (or stop sending it) so feed entries are
      just the result/story.

### 3. Audit what the bot posts to Twitch chat
A pass over every place the bot does `ctx.send(...)` for a **game action**, and
replace chat output with the right GUI/feed behavior (per the principle above).
- [ ] Inventory the chat-posting commands (attacks, status, points, buy, etc.).
- [ ] Decide per command: move to feed/GUI, keep (non-game chatter), or silence.
- [ ] Neutralize game `!commands` typed directly in Twitch chat (so `!buy` in
      chat doesn't work / doesn't spam) — the GUI/WebCtx path stays.

> Items 1–3 are facets of the same GUI-first migration. Doing them together (or
> back-to-back) makes sense.

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
- [ ] **Cooling → overclock** — raises the clock cap → faster hacks.
- [ ] **VPN / stealth** — `stealth` stat lowers trace/jail risk (needs the
      failure→trace model fleshed out first).
- [ ] **Cloud / botnet** — non-physical job slots (parallelism without parts).
- [ ] **Software upgrades** — the missing *axis*: exploit kits / scripts / 0-days
      giving per-category speed/success boosts. The other half of the original
      "hardware **and** software" pitch.

---

_Older pre-idle-hacking design notes live in `TwitcHackToDo.md` (historical)._
