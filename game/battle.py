"""Boss battle game logic."""

# The boss always starts every fight at full health. This is a property of the
# fight, not of any player record — the boss (b7h30) happens to also exist as an
# ordinary player whose max_health is the normal 50, so deriving the boss's HP
# from that record would (and did) cap the fight at 50 HP.
#
# Round 3 — HP cap raised from 1000 → 1500 to compensate for the per-item button
# damage that landed in Round 2.
BOSS_MAX_HEALTH = 1500


class BossBattle:
    """Represents an active boss battle with multiple challengers."""

    def __init__(self, boss_name, boss_health=BOSS_MAX_HEALTH):
        self.boss_name = boss_name
        self.boss_health = boss_health
        self.boss_max_health = boss_health
        self.challenger_team = {}  # Dict of {username: health}
        self.join_phase = True
        self.join_timer = 30  # Seconds
        self.team_damage = 0  # Track total team damage for rewards
        self.hack_used = set()          # usernames who've already used !hack
        self.per_player_damage = {}     # {username: total_damage_dealt} for MVP
        self.fallen = []                # ordered list of players who died (for summary)
        self.consciousness_used = set() # players who've burned their Consciousness USB save
        self.player_max_health = {}     # {username: hp at join time} for overlay HP bars

        # Round 2 — item-effect state (consumed by run_team_battle's boss turn):
        self.skip_boss_turns = 0           # # of upcoming boss turns to skip entirely
        self.weakness_next_turn = 0        # dmg reduction applied to boss's NEXT attack only
        self.bonus_points = {}             # {username: extra pts} added at reward time
        self.next_boss_damage = None       # pre-rolled by reveal_boss_damage so reveal is honest
        self.next_boss_target = None       # pre-rolled by reveal_boss_target
