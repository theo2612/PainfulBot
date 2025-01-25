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
    "VX Underground HDD": Item("VX Underground HDD", "Collection of malware samples", 25)
}
