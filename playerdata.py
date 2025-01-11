from PainfulBot import *

class Player:
    def __init__(self, username, level, health, items, location, points, started):
        self.username = username
        self.level = level
        self.health = health
        self.items = items if items else []
        self.location = location
        self.points = points
        self.started = started

    def to_dict(self):
        """Converts the Player object to a dictionary for JSON serialization."""
        return {
            'username': self.username,
            'level': self.level,
            'health': self.health,
            'items': self.items,
            'location': self.location,
            'points': self.points,
            'started': self.started

        }

    @classmethod
    def from_dict(cls, username, data):
        """Creates a Player object from a dictionary."""
        player = cls(
            username=username,
            level=data.get('level', 1),
            health=data.get('health', 10),
            items=data.get('items', []),
            location=data.get('location', 'home'),
            points=data.get('points', 0),
            started=data.get('started', 0)
        )
        player.items = data.get('items', [])
        return player
