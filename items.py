from dataclasses import dataclass
from typing import Dict

@dataclass
class Item:
    name: str
    description: str
    level_required: int

ITEMS: Dict[str, Item] = {
    "Wireshark": Item("Wireshark", "Network packet analyzer", 10),
    "Metasploit": Item("Metasploit", "Penetration testing framework", 30),
    "EvilGinx": Item("EvilGinx", "Phishing attack framework", 20),
    "O.MG Cable": Item("O.MG Cable", "Hardware attack tool", 15),
    "VX Underground HDD": Item("VX Underground HDD", "Collection of malware samples", 25),
    "Cookies": Item("Cookies", "Stored session data", 15),
    "Nmap": Item("Nmap", "Port scanner and enumerator", 12),
    "Hydra": Item("Hydra", "Brute force toolkit", 22),
    "YubiKey": Item("YubiKey", "Hardware token for social engineering flex", 18),
    "Shodan API Key": Item("Shodan API Key", "External intel tooling", 28),
    "Kali ISO": Item("Kali ISO", "Preloaded attack distro", 8),
    "NES": Item("NES", "Classic console power-up", 30),
    "Contra Cartridge": Item("Contra Cartridge", "Up, up, down, down for extra lives", 30),
    "A Fresh Hot Cup of Black Coffee": Item("A Fresh Hot Cup of Black Coffee", "Keeps you hacking all night", 5),
    "Tiny Browns Helmet": Item("Tiny Browns Helmet", "Mandatory fandom initiation", 5),
    "Root Beer Flask": Item("Root Beer Flask", "Soothing elixir after patch nights", 12)
}
