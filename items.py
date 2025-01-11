class Item:
    def __init__(self, name, description, location_boost, boss_damage_boost, boss_defense_boost):
        self.name = name
        self.description = description
        self.location_boost = location_boost
        self.boss_damage_boost = boss_damage_boost
        self.boss_defense_boost = boss_defense_boost

ITEMS = {
    "EvilGinx": Item("EvilGinx", "Boosts email hacking", "email", 5, 0),
    "Burp Pro": Item("Burp Pro", "Enhances website hacking", "website", 5, 0),
    "Hydra": Item("Hydra", "Improves password cracking", "/etc/shadow", 5, 0),
    "Metasploit": Item("Metasploit", "Strengthens server attacks", "server", 5, 0),
    "SQLMap": Item("SQLMap", "Increases database hacking success", "database", 5, 0),
    "Wireshark": Item("Wireshark", "Boosts network attack efficiency", "network", 5, 0),
    "RubberDucky": Item("Hak5 RubberDucky", "Enhances Evil Corp infiltration", "evilcorp", 5, 0),
    "Wi-Fi Pineapple": Item("Hak5 Wi-Fi Pineapple", "Improves Evil Corp hacking", "evilcorp", 5, 0),
    "O.MG Cable": Item("O.MG Cable", "Increases Evil Corp attack success", "evilcorp", 5, 0),
    "VX Underground HDD": Item("VX Underground HDD", "Significantly boosts boss battle damage", None, 15, 0),
    "Zero-Day Exploit": Item("Zero-Day Exploit", "Provides strong defense in boss battles", None, 0, 15)
}
