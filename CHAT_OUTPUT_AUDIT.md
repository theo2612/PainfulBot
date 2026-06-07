# Chat-Output Audit (the GUI-first pass)

Goal: decide what the bot should still say in **Twitch chat** vs. move to the
**TwitcHack feed/GUI** vs. **silence**, per the GUI-first principle
(`DEV_BACKLOG.md`). This doc is the map + your decisions; the code changes follow.

---

## First, the one thing that makes this simple

There are **two kinds** of chat output, and they're not the same problem:

**A. Dual responses — `ctx.send(...)` (≈179 places).**
These go to Twitch chat **only when the command is typed in chat**. When the
*same* command comes from a GUI button, the response goes to the web client
instead (never chat). So the fix for almost all of these is **one decision**:

> **Decision A — when a *game* command is typed in Twitch chat, what happens?**
> 1. Keep replying in chat (today's behavior).
> 2. Replace with a single nudge → "Play at bossbattle.b7h30.com/twitchack".
> 3. Stay silent.
>
> Whatever you pick, the **GUI/button path keeps its responses** — this only
> changes the chat-typed path. One choice covers the bulk of the 179.

**B. Unconditional broadcasts — `connected_channels[0].send(...)` (≈18 places).**
These **always** post to chat no matter what. They're decided individually
(below, Decision B).

---

## Already GUI-first (no action needed) ✅
- **Idle hacking** — `!buy` / `!run` / `!jobs`: feed-only already.
- **Attack *results*** (success/fail payout lines): routed to the feed; only
  echoed to chat for GUI/web players. ✅
- **The leaks** are the attack *guard* messages, the level-up ping, and the
  broadcasts — covered below.

---

## A. Game commands (covered by Decision A) — recommended: **nudge or silence**

Grouped so you can override any single group if you want different handling.

| Group | Commands | What it says in chat today | Rec |
|-------|----------|----------------------------|-----|
| **Clicker attacks** | phish, spoof, dump, crack, stealth, bruteforce, ffuf, burp, sqliw, xss, dumpdb, sqlidb, admin, nmap, revshell, root, ransom, sniff, mitm, ddos, drop, tailgate, socialengineer | guard msgs ("register with !start", "you must be at email", "level too low"). *Results already feed-only.* | nudge/silence the guards → GUI |
| **Movement** | hack, attacks | "you moved to X", "available attacks: …" | GUI (location chips) handles it → silence |
| **Level-up ping** | (inside attack results) | "@you reached level N! 🎉" to chat | move to **feed** only |
| **PvP / economy** | steal, bail, requestbail, grab, junk, useburner | guards + results | move to feed/GUI |
| **Info** | status, points, leaderboard, items, jail, treasury | dumps stats to chat | **your call** — see note |
| **Onboarding** | start, help | welcome text / command list | keep a short one, or redirect to GUI |

> **Info commands are the one judgment call.** `!status` / `!points` /
> `!leaderboard` in chat are genuinely handy for viewers who *aren't* on the
> GUI page. Options: (a) keep them chat-friendly, (b) move to GUI only, or
> (c) keep a terse chat reply + full detail in GUI. Pick per the audience.

## Owner/admin (low volume, owner-only) — recommended: **keep or feed**
droprandom, dropitem, mvp, ownerpoints, ownercash, assignpoints, virus,
patchtuesday. These are you, occasionally. Harmless in chat; can move to feed
for consistency. **Rec: keep for now, revisit.**

---

## B. Unconditional broadcasts — decide each

| Line(s) | What it is | Rec |
|---------|-----------|-----|
| 858 | "{bot} is now online" on startup | keep (status) or silence |
| 1000–1067 | **Konami code** easter-egg replies | social fun — keep, or feed |
| 1087–1106 | **Coffee** easter-egg replies | social fun — keep, or feed |
| 1117–1137 | **Browns** easter-egg replies | social fun — keep, or feed |
| 1295 | random **Monday** reply to chatters | chatter (not a game action) — **keep** |
| 1322 | **Neovim** penalty quip | chatter — **keep** |
| 1367, 1385 | item-**drop announcements** (droprandom/dropitem) | drops already show in GUI → move to **feed** |
| 3524 | "☠️ @user has fallen!" (boss battle) | boss overlay shows it → feed/overlay or keep for hype |
| 3613, 3762 | boss-battle messages | feed/overlay or keep for hype |

---

## Genuine chatter — recommend **leave in chat** (not game mechanics)
`monday`, `mondayinsulttheo`, `streamsummary` (AI chat features), and the
easter eggs above. These are entertainment/social, not the game interface —
the GUI-first principle is about *game actions*, not silencing the bot's
personality.

---

## Your decisions (made 2026-06-07)
- **Decision A (game commands typed in chat):** ✅ **BLOCK + nudge** — IMPLEMENTED
  (`2614b4d`). A game command typed in chat does not run; the bot sends one
  rate-limited nudge to the GUI. `GUI_ONLY_COMMANDS` in PainfulBot.py is the
  list. Still work in chat (excluded): personality (monday/streamsummary),
  onboarding (start/help), owner/admin, boss-battle (bossbattle/joinbattle),
  and `hack` (doubles as the in-battle nuke).
- **Info commands (status/points/leaderboard/items):** ✅ **GUI only** — folded
  into the block above (they nudge to the GUI). Data lives on the card/feed.
- **Drop announcements (1367/1385):** ☐ keep · ☐ move to feed _(default: feed)_
- **Boss-battle broadcasts (3524/3613/3762):** ☐ keep (hype) · ☐ feed/overlay _(default: keep)_
- **Easter eggs (konami/coffee/browns):** ✅ keep in chat (bot personality)
- **Owner/admin confirmations:** ✅ keep for now

## Implementation note (so we don't edit 179 lines)
Decision A is **one central intercept**, not per-command edits: catch game
commands coming from Twitch chat (not WebCtx) in `event_message`/`handle_commands`,
send a **rate-limited** nudge, and skip (or run-then-suppress) the command. Needs
a set of which commands are "game" vs "chatter/personality" (the latter — monday,
neovim, easter eggs, streamsummary — pass through untouched). Info commands
(GUI-only) fold into the same intercept.
