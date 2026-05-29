#!/usr/bin/env bash
# Snake's Cardboard Box / Konami easter egg engagement report.
#
# Run anytime, or schedule via cron — see install instructions at the bottom.
# Output goes to stdout. Pipe to mail / file / Discord webhook as desired.

set -u

PLAYER_FILE="/home/b7h30/PainfulBot/player_data.json"
BOT_LOG="/home/b7h30/PainfulBot/bot.log"

echo "═══════════════════════════════════════════════════════════════"
echo "  Snake's Cardboard Box engagement report — $(date -Iseconds)"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# ── 1. Adoption: who triggered Konami at all ────────────────────────
echo "▌ Konami triggers (all-time)"
python3 - <<EOF
import json
with open("$PLAYER_FILE") as f:
    d = json.load(f)
triggered = sorted(
    [(n, p.get("konami_last_at")) for n, p in d.items() if p.get("konami_last_at")],
    key=lambda x: x[1] or ""
)
print(f"  {len(triggered)} unique player(s) have triggered Konami:")
for n, ts in triggered:
    print(f"    {n:<25} last: {ts}")
if not triggered:
    print("    (none)")
EOF
echo ""

# ── 2. Currently inside a 1-hour box ────────────────────────────────
echo "▌ Currently steal-immune (active Cardboard Box)"
python3 - <<EOF
import json
from datetime import datetime
with open("$PLAYER_FILE") as f:
    d = json.load(f)
now = datetime.now()
active = []
for n, p in d.items():
    raw = p.get("cardboard_box_until")
    if not raw:
        continue
    try:
        exp = datetime.fromisoformat(raw)
    except ValueError:
        continue
    if exp > now:
        active.append((n, exp))
print(f"  {len(active)} player(s) currently in box:")
for n, exp in active:
    mins = int((exp - now).total_seconds() / 60)
    print(f"    {n:<25} {mins}m left")
if not active:
    print("    (none)")
EOF
echo ""

# ── 3. Steal-immunity saves: how often did the perk actually block? ─
echo "▌ Steal blocks (perk-saves over the last 7 days)"
if [ -f "$BOT_LOG" ]; then
    # Look at recent log lines mentioning the immunity message
    SAVES=$(grep -iE "Cardboard Box.*can't even see|hacking from Snake's Cardboard" "$BOT_LOG" 2>/dev/null | wc -l)
    echo "  $SAVES recorded steal attempt(s) blocked by the box"
else
    echo "  (bot.log not found at $BOT_LOG)"
fi
echo ""

# ── 4. Chat mentions in bot.log ─────────────────────────────────────
echo "▌ Chat mentions (last 30 hits in bot.log)"
if [ -f "$BOT_LOG" ]; then
    HITS=$(grep -iE "cardboard|konami|backdoor|snake" "$BOT_LOG" 2>/dev/null | tail -30)
    if [ -z "$HITS" ]; then
        echo "  (no mentions found)"
    else
        echo "$HITS" | sed 's/^/  /'
    fi
else
    echo "  (bot.log not found)"
fi
echo ""

# ── 5. Konami HTTP traffic (recent boss-battle events) ──────────────
echo "▌ Recent web_command 'konami' traffic (boss-battle service)"
KONAMI_HITS=$(sudo journalctl -u boss-battle.service --since "7 days ago" --no-pager 2>/dev/null | grep -iE "\| konami \|" | tail -20)
if [ -z "$KONAMI_HITS" ]; then
    echo "  (no journal entries — service may not log command traffic, or none in window)"
else
    echo "$KONAMI_HITS" | sed 's/^/  /'
fi

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  Report complete."
echo "═══════════════════════════════════════════════════════════════"
