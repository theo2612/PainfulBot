# Command Cheat Sheet

This is an internal list of public and hidden commands/triggers for PainfulBot (b7h30 channel). Hidden/owner-only commands are noted; do not share broadly if you want them to stay secret.

## Public / Visible Commands
- `!hello` — greet.
- `!coinflip` — heads/tails.
- `!roll` / `!d4`/`!d6`/`!d8`/`!d10`/`!d12`/`!d20`/`!d100` — roll dice.
- `!secret` — mantra response.
- `!start` — register player.
- `!help` — list game commands.
- `!attacks` — attacks for current location.
- `!hack <location>` — move; locations: email, /etc/shadow, website, database, server, network, evilcorp.
- `!points` — show points.
- `!leaderboard` — top 5 players.
- `!status [user]` — show status (self or target).
- `!battle` — show boss battle status and join instructions.
- `!bossbattle` — start boss battle (cooldown enforced internally).
- `!joinbattle` — join active boss battle.
- Attack commands (gated by location/level): `!phish`, `!spoof`, `!dump`, `!ffuf`, `!crack`, `!stealth`, `!bruteforce`, `!burp`, `!sqliw`, `!xss`, `!dumpdb`, `!sqlidb`, `!admin`, `!nmap`, `!revshell`, `!root`, `!ransom`, `!sniff`, `!mitm`, `!ddos`, `!drop`, `!tailgate`, `!socialengineer`.
- `!virus [user]` — owner-only attack; unauthorized users get penalized.
- Points admin: `!ownerpoints <amt>` (owner only, self), `!assignpoints <user> <amt>` (owner only).
- Item drop admin: `!droprandom` (owner only) — drop up to 2 random items (no hidden-only).
- Owner patch event: `!patchtuesday` — random global outcome (points loss or gain; may drop Root Beer Flask).
- Diagnostics: `!statusbot` (owner) and `!session` (owner) — bot/battle/Monday/audio/drops/hidden stats.
- Chat MVP: `!mvp` (owner) — once per stream; picks a recent registered chatter and gifts a unique cosmetic item plus +50 points.
- Items/inventory: `!items` — show your items (with buffs) and currently dropped items.
- Monday AI: `!monday [prompt]` — snarky Monday response; cooldown applies.
- Monday roast: `!mondayinsulttheo` — Monday generates a fresh roast of Theo (facts baked in).

## Event/Trigger-Based Behavior
- Follow/Sub EventSub: random item drop announced; claim with `!grab <item>`.
- `!grab <item>` — claim a currently dropped item.
- Saying “neovim” — escalating point penalties (25 → 50 → 100 → 200, etc.), clamps to 0; may yank a random item from user and drop it; sends randomized snark.
- Chat contains `#GoBrowns` — one-time per session per user: awards `Tiny Browns Helmet` (🏈) and Browns fan message.
- Monday mention trigger: @theo2820 (any case) routes to the `!monday` handler with the same cooldown and length clamp.
- Monday random replies: Monday may randomly respond to chat (respecting global/user cooldowns and chance); always nice/snark mix toward the host.
- Audio nudges: Monday monitors chat for loose matches (e.g., hacking/jobs/AI/cats/complaining) and silently fires the best-matching audio command (global cooldown + per-user cooldowns, plus extra rarity for `!daddy`). Messages starting with `!` are ignored.

## Hidden Commands (session-limited)
- `!uuddlrlrba` — Konami code: gives `NES` or `Contra Cartridge` and +50 points (once per user per bot session).
- `!coffee` — gives `A Fresh Hot Cup of Black Coffee` and +25 points (once per user per session).
- `!mondayinsulttheo` — see above (fresh AI roast; off-limits: family).
  - Tuning in code under `mondayinsulttheo` (system prompt).

## Items (with emoji)
- 🦈 Wireshark, 💥 Metasploit, 🕷️ EvilGinx, 🔌 O.MG Cable, 💿 VX Underground HDD, 🍪 Cookies, 📡 Nmap, 🗝️ Hydra, 🪫 YubiKey, 🔍 Shodan API Key, 🐉 Kali ISO, 🎮 NES, 🔫 Contra Cartridge, ☕ A Fresh Hot Cup of Black Coffee, 🏈 Tiny Browns Helmet, 🧉 Root Beer Flask, 🧾 Mimikatz, 📼 Golden Cassette Tape, 🥷 Jet Black Hoodie, 🎹 RGB Keyboard (Purple).

## Notes
- Points/levels: points clamp at 0; levels never decrease once earned.
- Boss battle: max 5 challengers; rewards include +5 max HP; cooldown is enforced in code (check `last_battle_time` logic).
- Hidden command usage is tracked per stream/day (resets daily).
- Drops expire after ~15 minutes and duplicate drops of the same item are blocked; hidden-only items never appear in `!droprandom`.
- MVP cosmetic drop is once per stream; selects from recent registered chatters (skips unregistered).
