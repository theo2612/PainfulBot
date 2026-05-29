"""Leveling curve + founder tier source of truth.

Season 2 curve (quadratic): total points required to reach level N is
`50 * N * (N - 1)`. Inverse derived via the quadratic formula.

Examples:
    points_for_level(1)   ==      0
    points_for_level(2)   ==    100
    points_for_level(5)   ==  1_000
    points_for_level(10)  ==  4_500
    points_for_level(100) == 495_000

Founder tiers are assigned ONCE during the Season 1 -> Season 2 migration
based on each player's pre-migration level. New players post-S2 launch do
not receive a founder tier.
"""
import math


def points_for_level(level: int) -> int:
    """Total cumulative points required to reach the given level."""
    if level <= 1:
        return 0
    return 50 * level * (level - 1)


def level_for_points(points: int) -> int:
    """Highest level reachable with the given total points (>= 1)."""
    p = max(0, int(points))
    # Solve 50 * N * (N - 1) <= P  =>  N <= (1 + sqrt(1 + P/12.5)) / 2
    n = int((1 + math.sqrt(1 + p / 12.5)) / 2)
    return max(1, n)


def points_to_next_level(level: int, points: int) -> int:
    """Points still needed to reach the next level (never negative)."""
    return max(0, points_for_level(level + 1) - int(points))


def points_for_n_levels_up(current_level: int, n: int, current_points: int) -> int:
    """Points needed for a player to gain `n` levels from their current level."""
    target = points_for_level(current_level + n)
    return max(0, target - int(current_points))


def founder_tier_for_old_level(old_level: int) -> str:
    """Map a Season 1 level to a founder tier label.

    Tiers (based on pre-migration / Season 1 level):
        100,000+  -> FOUNDER::31337
         10,000+  -> FOUNDER::1337
          1,000+  -> FOUNDER::H4CK3R
        anything  -> FOUNDER::0P3R4T0R
    """
    if old_level >= 100_000:
        return "FOUNDER::31337"
    if old_level >= 10_000:
        return "FOUNDER::1337"
    if old_level >= 1_000:
        return "FOUNDER::H4CK3R"
    return "FOUNDER::0P3R4T0R"
