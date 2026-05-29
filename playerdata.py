
class Player:
    def __init__(self, username, level, health, items, location, points, started,
                 founder_tier=None, konami_last_at=None, cardboard_box_until=None,
                 last_attack_at=None, speed_strikes=0, last_strike_at=None,
                 jail=None, last_jail_released_at=None, offense_count=0,
                 bail_request_for=None, no_cap_until=None,
                 max_health=None, last_regen_at=None):
        self.username = username
        self.level = level
        # health == current HP; max_health == personal cap (50 start, +5/win, cap 1000).
        # Legacy records pre-dating the split stored only `health` which doubled as
        # the max — when max_health is omitted, treat the incoming health as the max
        # and start the player at full so the migration is non-punitive.
        if max_health is None:
            max_health = health
        self.max_health = max_health
        self.health = min(health, max_health)
        self.last_regen_at = last_regen_at  # ISO timestamp; drives 30s regen cooldown
        self.items = items if items else []
        self.location = location
        self.points = points
        self.started = started
        self.founder_tier = founder_tier  # e.g., "FOUNDER::31337" or None for non-founders
        self.konami_last_at = konami_last_at        # ISO timestamp of last Konami trigger
        self.cardboard_box_until = cardboard_box_until  # ISO timestamp when steal-immunity expires
        # Jail / speed-penalty state (see TWITCHACK_JAIL_RATELIMIT_SPEC.md)
        self.last_attack_at = last_attack_at if last_attack_at else {}  # {location: iso_ts}
        self.speed_strikes = speed_strikes
        self.last_strike_at = last_strike_at        # ISO timestamp; drives 10-min strike decay
        self.jail = jail                            # None or {"until": iso, "reason": str, "offense_number": int}
        self.last_jail_released_at = last_jail_released_at  # ISO; drives 24h ladder reset
        self.offense_count = offense_count          # persistent ladder rung (0..5+)
        self.bail_request_for = bail_request_for    # username (lowercase) the jailed player has tagged to bail them; None = no open request
        self.no_cap_until = no_cap_until            # ISO timestamp; while in the future the player bypasses the speed-penalty cap (Burner Laptop reward)

    def add_item(self, item_name):
        """Add `item_name` to the player's inventory, case-insensitively
        deduped. Returns True if the item was added, False if the player
        already owned it (in any case form). The canonical name from the
        ITEMS catalog is preferred over whatever casing the caller passed.
        """
        if not item_name:
            return False
        # Resolve to canonical name from the catalog if possible.
        try:
            from items import ITEMS
            canonical = next(
                (k for k in ITEMS if k.lower() == str(item_name).strip().lower()),
                str(item_name).strip(),
            )
        except Exception:
            canonical = str(item_name).strip()
        lower = canonical.lower()
        if any(str(i).strip().lower() == lower for i in self.items):
            return False
        self.items.append(canonical)
        return True

    def to_dict(self):
        """Converts the Player object to a dictionary for JSON serialization."""
        d = {
            'username': self.username,
            'level': self.level,
            'health': self.health,
            'max_health': self.max_health,
            'items': self.items,
            'location': self.location,
            'points': self.points,
            'started': self.started,
        }
        if self.last_regen_at:
            d['last_regen_at'] = self.last_regen_at
        if self.founder_tier:
            d['founder_tier'] = self.founder_tier
        if self.konami_last_at:
            d['konami_last_at'] = self.konami_last_at
        if self.cardboard_box_until:
            d['cardboard_box_until'] = self.cardboard_box_until
        if self.last_attack_at:
            d['last_attack_at'] = self.last_attack_at
        if self.speed_strikes:
            d['speed_strikes'] = self.speed_strikes
        if self.last_strike_at:
            d['last_strike_at'] = self.last_strike_at
        if self.jail:
            d['jail'] = self.jail
        if self.last_jail_released_at:
            d['last_jail_released_at'] = self.last_jail_released_at
        if self.offense_count:
            d['offense_count'] = self.offense_count
        if self.bail_request_for:
            d['bail_request_for'] = self.bail_request_for
        if self.no_cap_until:
            d['no_cap_until'] = self.no_cap_until
        return d

    @classmethod
    def from_dict(cls, username, data):
        """Creates a Player object from a dictionary."""
        player = cls(
            username=username,
            level=data.get('level', 1),
            health=data.get('health', 10),
            max_health=data.get('max_health'),
            last_regen_at=data.get('last_regen_at'),
            items=data.get('items', []),
            location=data.get('location', 'home'),
            points=data.get('points', 0),
            started=data.get('started', 0),
            founder_tier=data.get('founder_tier'),
            konami_last_at=data.get('konami_last_at'),
            cardboard_box_until=data.get('cardboard_box_until'),
            last_attack_at=data.get('last_attack_at'),
            speed_strikes=data.get('speed_strikes', 0),
            last_strike_at=data.get('last_strike_at'),
            jail=data.get('jail'),
            last_jail_released_at=data.get('last_jail_released_at'),
            offense_count=data.get('offense_count', 0),
            bail_request_for=data.get('bail_request_for'),
            no_cap_until=data.get('no_cap_until'),
        )
        player.items = data.get('items', [])
        return player
