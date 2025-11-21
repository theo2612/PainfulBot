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
- `!bossbattle` — start boss battle (cooldown enforced internally).
- `!joinbattle` — join active boss battle.
- Attack commands (gated by location/level): `!phish`, `!spoof`, `!dump`, `!crack`, `!stealth`, `!bruteforce`, `!burp`, `!sqliw`, `!xss`, `!dumpdb`, `!sqlidb`, `!admin`, `!revshell`, `!root`, `!ransom`, `!sniff`, `!mitm`, `!ddos`, `!drop`, `!tailgate`, `!socialengineer`.
- `!virus [user]` — owner-only attack; unauthorized users get penalized.
- Points admin: `!ownerpoints <amt>` (owner only, self), `!assignpoints <user> <amt>` (owner only).
- Item drop admin: `!droprandom` (owner only) — drop 1–5 random items.
- Owner patch event: `!patchtuesday` — random global outcome (points loss or gain; may drop Root Beer Flask).
- Items/inventory: `!items` — show your items (with buffs) and currently dropped items.
- Monday AI: `!monday [prompt]` — snarky Monday response; cooldown applies.
- Monday roast: `!mondayinsulttheo` — Monday generates a fresh roast of Theo (facts baked in).

## Event/Trigger-Based Behavior
- Follow/Sub EventSub: random item drop announced; claim with `!grab <item>`.
- `!grab <item>` — claim a currently dropped item.
- Saying “neovim” — escalating point penalties (25 → 50 → 100 → 200, etc.), clamps to 0; may yank a random item from user and drop it; sends randomized snark.
- Chat contains `#GoBrowns` — one-time per session per user: awards `Tiny Browns Helmet` (🏈) and Browns fan message.

## Hidden Commands (session-limited)
- `!uuddlrlrba` — Konami code: gives `NES` or `Contra Cartridge` and +50 points (once per user per bot session).
- `!coffee` — gives `A Fresh Hot Cup of Black Coffee` and +25 points (once per user per session).
- `!mondayinsulttheo` — see above (fresh AI roast; off-limits: family).
  - Tuning in code under `mondayinsulttheo` (system prompt).

## Items (with emoji)
- 🦈 Wireshark, 💥 Metasploit, 🕷️ EvilGinx, 🔌 O.MG Cable, 💿 VX Underground HDD, 🍪 Cookies, 📡 Nmap, 🗝️ Hydra, 🪫 YubiKey, 🔍 Shodan API Key, 🐉 Kali ISO, 🎮 NES, 🔫 Contra Cartridge, ☕ A Fresh Hot Cup of Black Coffee, 🏈 Tiny Browns Helmet, 🧉 Root Beer Flask.

## Notes
- Points/levels: points clamp at 0; levels never decrease once earned.
- Boss battle: max 5 challengers; rewards include +5 max HP; cooldown is enforced in code (check `last_battle_time` logic).
- Hidden command usage is tracked per stream/day (resets daily).
