"""Season 1 -> Season 2 migration.

One-time script that:
  1. Backs up player_data.json -> player_data.s1_backup.json
  2. Assigns every existing player a founder_tier based on their S1 level
  3. Recomputes their level using the new quadratic curve
  4. Leaves points / health / items / etc. untouched

Idempotent: refuses to run again if any player already has a founder_tier.

Usage:
    python3 migrate_s1_to_s2.py            # dry run (prints what it would do)
    python3 migrate_s1_to_s2.py --apply    # actually writes changes
"""
import json
import shutil
import sys
from datetime import datetime

from bot.leveling import level_for_points, founder_tier_for_old_level

PLAYER_FILE = "player_data.json"
BACKUP_FILE = "player_data.s1_backup.json"


def load():
    with open(PLAYER_FILE, "r") as f:
        return json.load(f)


def save(data):
    with open(PLAYER_FILE, "w") as f:
        json.dump(data, f, indent=4)


def main():
    apply = "--apply" in sys.argv
    data = load()

    already_migrated = [n for n, p in data.items() if p.get("founder_tier")]
    if already_migrated:
        print(f"ABORT: {len(already_migrated)} player(s) already have founder_tier set.")
        print(f"Sample: {already_migrated[:3]}")
        print("Migration appears to already be done. No changes made.")
        sys.exit(1)

    rows = []
    for username, player in data.items():
        old_level = int(player.get("level", 1))
        points = int(player.get("points", 0))
        new_level = level_for_points(points)
        tier = founder_tier_for_old_level(old_level)
        rows.append((username, old_level, new_level, points, tier))

    rows.sort(key=lambda r: -r[1])  # by old level desc

    print(f"\nSeason 1 -> Season 2 migration plan ({len(rows)} players)\n")
    print(f"{'username':<22} {'old_lvl':>10} {'new_lvl':>10} {'points':>12}  tier")
    print("-" * 80)
    for username, old, new, pts, tier in rows:
        print(f"{username:<22} {old:>10} {new:>10} {pts:>12}  {tier}")

    if not apply:
        print(f"\nDry run only. Re-run with --apply to write changes.")
        return

    shutil.copy(PLAYER_FILE, BACKUP_FILE)
    print(f"\nBackup written: {BACKUP_FILE}")

    for username, _, new_level, _, tier in rows:
        data[username]["level"] = new_level
        data[username]["founder_tier"] = tier

    save(data)
    print(f"Migration applied at {datetime.now().isoformat()}.")


if __name__ == "__main__":
    main()
