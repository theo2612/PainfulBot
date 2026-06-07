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
  - [ ] Move drop announcements to the feed; decide boss-battle broadcasts.

### Per-machine rigs + Hardware row (decided 2026-06-07)
Replace the "best machine only" model: each owned machine is its **own
workstation** with its own job slots AND its own clock speed. Total concurrency
= sum across owned machines; you pick which machine to run a hack on (speed
matters — slow SBC vs faster Laptop). UI: the command panel's "Shop" row becomes
a **Hardware** row to select the active machine; the shop stays on the floating
🛒 tab. Core-model change — jobs get tagged to a machine, slots counted per
machine, `rig_stats`/`job_slots`/`can_run`/`start_hack`/`duration_for` updated,
with tests. (Custom-tower parts later assemble into one machine.)

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

## Later

### Idle-hacking content roadmap
Design + stats in `TWITCHACK_IDLE_HACKING_SPEC.md` §5–6.
- [ ] **Bandwidth → exfil** — new `bandwidth` rig stat; gates + speeds exfil
      hacks. (Suggested first content piece, after the Shop exists.)
- [ ] **Cooling → overclock** — raises the clock cap → faster hacks.
- [ ] **VPN / stealth** — `stealth` stat lowers trace/jail risk (needs the
      failure→trace model fleshed out first).
- [ ] **Cloud / botnet** — non-physical job slots (parallelism without parts).
- [ ] **Software upgrades** — the missing *axis*: exploit kits / scripts / 0-days
      giving per-category speed/success boosts. The other half of the original
      "hardware **and** software" pitch.

---

_Older pre-idle-hacking design notes live in `TwitcHackToDo.md` (historical)._
