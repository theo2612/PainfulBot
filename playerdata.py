class Player:
    def __init__(self, username, level, health, items, location, points):
        self.username = username
        self.level = level
        self.health = health
        self.items = items
        self.location = location
        self.points = points

    def to_dict(self):
        """Converts the Player object to a dictionary for JSON serialization."""
        return {
            'username': self.username,
            'level': self.level,
            'health': self.health,
            'items': self.items,
            'location': self.location,
            'points': self.points

        }

    @classmethod
    def from_dict(cls, data):
        """Creates a Player object from a dictionary."""
        return cls(
            username=data['username'],
            level=data.get('level', 1),
            health=data.get('health', 10),
            items=data.get('items', []),
            location=data.get('location', 'home'),
            points=data.get('points', 0)

        )
