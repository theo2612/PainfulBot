"""Boss battle game logic."""


class BossBattle:
    """Represents an active boss battle with multiple challengers."""

    def __init__(self, boss_name, boss_health):
        self.boss_name = boss_name
        self.boss_health = boss_health
        self.challenger_team = {}  # Dict of {username: health}
        self.join_phase = True
        self.join_timer = 30  # Seconds
        self.team_damage = 0  # Track total team damage for rewards
        self.hack_used = set()          # usernames who've already used !hack
        self.per_player_damage = {}     # {username: total_damage_dealt} for MVP
        self.fallen = []                # ordered list of players who died (for summary)
        self.consciousness_used = set() # players who've burned their Consciousness USB save
