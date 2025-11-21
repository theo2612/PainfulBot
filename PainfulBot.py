import os                                   # Import the 'OS' module to interact with the operating system, 
                                            # specifically for environment variables
import random                               # Import the 'random' module to generate random numbers
import json                                 # Import 'json' module to work with json data, for storing player data
import asyncio
import time
import logging
from datetime import datetime, timedelta

from dotenv import load_dotenv              # Import the function to load environment variables from a .env file
from openai import OpenAI, RateLimitError, APIError
from twitchio.ext import commands, eventsub

from playerdata import *                    # Import all the classes and functions defined in playerdata.py
from items import ITEMS, Item

load_dotenv()
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

BOT_NICK = os.getenv("BOT_NICK")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
TOKEN = os.getenv("TOKEN")
PREFIX = os.getenv("PREFIX", "!")
CHANNEL = os.getenv("CHANNEL")
CHANNEL_OWNER = os.getenv("CHANNEL_OWNER")
BROADCASTER_ID = os.getenv("BROADCASTER_ID") or os.getenv("CHANNEL_ID")
MODERATOR_ID = os.getenv("MODERATOR_ID") or BROADCASTER_ID
EVENTSUB_TOKEN = (os.getenv("EVENTSUB_TOKEN") or TOKEN or "").replace("oauth:", "")

MONDAY_MODEL = os.getenv("MONDAY_MODEL", "gpt-4o-mini")  # gpt-3.5-turbo
_raw_cd = os.getenv("MONDAY_COOLDOWN", "30")
try:
    MONDAY_COOLDOWN = int(_raw_cd.split("#", 1)[0].strip())
except ValueError:
    MONDAY_COOLDOWN = 30



# Define a class for your bot, inheriting from twitchio's commands.Bot
class Bot(commands.Bot):

    def __init__(self):
        # Initialize the bot with required parameters
        super().__init__(
            token=TOKEN,
            client_id=CLIENT_ID,
            nick=BOT_NICK,
            prefix=PREFIX,
            initial_channels=[CHANNEL],
            scopes=[
                'chat:read',
                'chat:edit',
                'channel:moderate'
            ]
        )

        # Load player data from JSON file
        self.player_data = {}
        self.load_player_data()
        self.last_battle_time = datetime.min
        self.boss_battle_cooldown = timedelta(hours=1)
        self.ongoing_battle = None
        self.dropped_items = []  # Add this line to initialize dropped_items list
        self.drop_expiry = timedelta(minutes=15)  # Drops expire after 15 minutes
        self.last_public_message = {}  # Add this to track last public message per command
        self.last_monday_time = datetime.min  # Track global cooldown for !Monday command
        self.eventsub_client = None
        self.session_flags = self.load_session_flags()
        self.item_emojis = {
            'Wireshark': '🦈',
            'Metasploit': '💥',
            'EvilGinx': '🕷️',
            'O.MG Cable': '🔌',
            'VX Underground HDD': '💿',
            'Cookies': '🍪',
            'Nmap': '📡',
            'Hydra': '🗝️',
            'YubiKey': '🪫',
            'Shodan API Key': '🔍',
            'Kali ISO': '🐉',
            'NES': '🎮',
            'Contra Cartridge': '🔫',
            'A Fresh Hot Cup of Black Coffee': '☕',
            'Tiny Browns Helmet': '🏈',
            'Root Beer Flask': '🧉',
        }
        self.neovim_penalties = {}
        self.hidden_only_items = {
            "NES",
            "Contra Cartridge",
            "A Fresh Hot Cup of Black Coffee",
            "Tiny Browns Helmet",
            "Root Beer Flask",
        }
        # Monday random replies tuning
        self.monday_random_chance = 0.10
        self.monday_random_cooldown_range = (30, 60)  # seconds
        self.monday_random_user_cooldown_range = (600, 900)  # seconds
        self.next_random_monday_time = datetime.min
        self.monday_random_user_block = {}

    def log_to_file(self, message):
        """Helper method to log messages to file"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open('bot.log', 'a') as f:
            f.write(f"[{timestamp}] {message}\n")

    async def send_result(self, ctx, message):
        """Helper method to handle result messaging with debug logging"""
        command = ctx.command.name if ctx.command else 'unknown'
        current_time = datetime.now()
        
        self.log_to_file(f"Attempting to send result for command '{command}' to {ctx.author.name}")
        
        try:
            self.log_to_file("Sending message...")
            await ctx.send(message)
            self.log_to_file("Successfully sent message")
            self.last_public_message[command] = current_time
        except Exception as e:
            self.log_to_file(f"Failed to send message: {str(e)}")

    def load_player_data(self):
        # Loads player data from the JSON file into Player objects.        
        try:
            with open('player_data.json', 'r') as f:
                data = json.load(f)         # Load the JSON data from the file
                for username, player_info in data.items():
                    # Convert each player's data from a dictionary to a Player object
                    self.player_data[username] = Player.from_dict(username, player_info)
        except FileNotFoundError:
            # If the file doesn't exist, initialize an empty player directory
            self.player_data = {}

    def save_player_data(self):
        # Saves the player data to a JSON file.
        # Convert each Player object to a dictionary for serialization
        data = {username: player.to_dict() for username, player in self.player_data.items()}
        with open('player_data.json', 'w') as f:
            json.dump(data, f, indent=4)    # Write the JSON data to the file with indentation

    def check_level_up(self, username):
        """Ensure points stay non-negative and levels never decrease."""
        player = self.player_data[username]
        player.points = max(0, player.points)
        current_level = player.level
        new_level = max(current_level, max(1, player.points // 100))

        if new_level != current_level:
            player.level = new_level
            self.save_player_data()
            return True
        return False

    def load_session_flags(self):
        """Load per-stream hidden command flags; reset daily."""
        today = datetime.now().date().isoformat()
        default = {
            "date": today,
            "konami": [],
            "coffee": [],
            "browns": [],
        }
        try:
            with open("session_flags.json", "r") as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {k: (set(v) if isinstance(v, list) else v) for k, v in default.items()}

        if data.get("date") != today:
            return {k: (set(v) if isinstance(v, list) else v) for k, v in default.items()}

        normalized = {}
        for k, v in data.items():
            normalized[k] = set(v) if isinstance(v, list) else v
        # Ensure keys exist
        for key in ("konami", "coffee", "browns"):
            normalized.setdefault(key, set())
            if not isinstance(normalized[key], set):
                normalized[key] = set(normalized[key])
        normalized["date"] = today
        return normalized

    def save_session_flags(self):
        payload = {
            "date": self.session_flags.get("date", datetime.now().date().isoformat()),
            "konami": list(self.session_flags.get("konami", set())),
            "coffee": list(self.session_flags.get("coffee", set())),
            "browns": list(self.session_flags.get("browns", set())),
        }
        with open("session_flags.json", "w") as f:
            json.dump(payload, f, indent=2)

    def is_channel_owner(self, username):
        return username.lower() == CHANNEL_OWNER.lower()
        
    def get_item_bonus(self, player, attack_type):
        """Calculate success chance and point bonuses based on relevant items."""
        bonus = {
            'success_boost': False,
            'points_multiplier': 1.0,
            'item_name': None
        }
        
        # Map items to attack types
        item_benefits = {
            'Wireshark': ['sniff', 'mitm', 'ddos'],  # Network attacks
            'EvilGinx': ['phish', 'spoof'],  # Phishing attacks
            'Metasploit': ['revshell', 'root', 'burp', 'sqliw', 'xss'],  # Penetration testing
            'O.MG Cable': ['drop', 'tailgate'],  # Physical attacks
            'VX Underground HDD': ['virus', 'ransom'],  # Malware attacks
            'Cookies': ['burp'],  # Website attacks
            'Nmap': ['revshell', 'root', 'sniff'],  # Recon/network leverage
            'Hydra': ['bruteforce', 'crack'],  # Password attacks
            'YubiKey': ['tailgate', 'socialengineer'],  # Physical/social engineering
            'Shodan API Key': ['ddos', 'sniff'],  # Intel feeding attacks
            'Kali ISO': ['phish', 'burp', 'revshell'],  # Generalist boost
            'NES': ['ddos', 'xss'],  # Fun bonus
            'Contra Cartridge': ['ddos', 'ransom'],  # Easter egg power
        }
        
        # Check if player has any items that help with this attack
        for item in player.items:
            if item in item_benefits and attack_type in item_benefits[item]:
                bonus['success_boost'] = True
                bonus['points_multiplier'] = 1.5  # 50% more points
                bonus['item_name'] = item
                break
                
        return bonus

    def format_item(self, item_name):
        """Return item name with emoji if available."""
        emoji = self.item_emojis.get(item_name)
        return f"{emoji} {item_name}" if emoji else item_name

    async def event_ready(self):
        # Called once when the bot successfully connects to Twitch.
        # Useful for initialization tasks and confirming the bot is online.
        print(f'Logged in as | {self.nick}')    # Output the bot's username
        print(f'User id is | {self.user_id}')   # Output the bot's user ID
        # Send a message to the chat indicating that the bot is online
        await self.connected_channels[0].send(f"{self.nick} is now online")
        self.loop.create_task(self.setup_eventsub())

    async def event_message(self, message):
        # Called whenever a message is received in chat.
        # Parameters: - message (Message): The message object containing information about the received message.
        # Ignore messages sent by the bot itself
        if message.echo:
            return

        # Print the content of the message if author exists
        if message.author:
            print(f'{message.author.name}: {message.content}')
        else:
            print(f'Unknown author: {message.content}')

        # Hidden Konami code easter egg: !uuddlrlrba
        if message.content.strip().lower() == "!uuddlrlrba":
            await self.handle_konami(message.author)
        if message.content.strip().lower() == "!coffee":
            await self.handle_coffee(message.author)
        if "#gobrowns" in message.content.lower():
            await self.handle_browns(message.author)

        # Handle basic keyword detection
        if "neovim" in message.content.lower():
            await self.handle_neovim_penalty(message.author)

        # Random friendly Monday reply to chatters
        await self.maybe_random_monday_reply(message)

        # Process commands if any
        await self.handle_commands(message)

    async def event_follow(self, user):
        await self.random_item_drop("follow", user.name)

    async def event_subscription(self, subscription):
        await self.random_item_drop("subscription", subscription.user.name)

    async def setup_eventsub(self):
        """Start EventSub websocket for follows/subs and wire to loot drops."""
        if self.eventsub_client is not None:
            return

        if not BROADCASTER_ID:
            print("EventSub disabled: set BROADCASTER_ID (or CHANNEL_ID) in the environment.")
            return

        if not EVENTSUB_TOKEN:
            print("EventSub disabled: missing EVENTSUB_TOKEN (or TOKEN) with follow/sub scopes.")
            return

        moderator_id = MODERATOR_ID or BROADCASTER_ID

        try:
            self.eventsub_client = eventsub.EventSubWSClient(self)
            await self.eventsub_client.subscribe_channel_follows_v2(
                broadcaster=BROADCASTER_ID,
                moderator=moderator_id,
                token=EVENTSUB_TOKEN
            )
            await self.eventsub_client.subscribe_channel_subscriptions(
                broadcaster=BROADCASTER_ID,
                token=EVENTSUB_TOKEN
            )
            await self.eventsub_client.subscribe_channel_subscription_messages(
                broadcaster=BROADCASTER_ID,
                token=EVENTSUB_TOKEN
            )
            print("EventSub connected for follows/subscriptions.")
        except Exception as e:
            print(f"EventSub setup failed: {e}")

    async def event_eventsub_notification_followV2(self, payload):
        """EventSub follow notifications -> random loot drops."""
        try:
            username = payload.event.user.name
        except Exception:
            username = None
        if username:
            await self.random_item_drop("follow", username)

    async def event_eventsub_notification_subscription(self, payload):
        """EventSub sub notifications -> random loot drops."""
        try:
            username = payload.event.user.name
        except Exception:
            username = None
        if username:
            await self.random_item_drop("subscription", username)

    async def event_eventsub_notification_subscription_message(self, payload):
        """EventSub sub message notifications -> random loot drops."""
        try:
            username = payload.event.user.name
        except Exception:
            username = None
        if username:
            await self.random_item_drop("subscription", username)

    async def handle_konami(self, author):
        """Hidden Konami code reward. Grants Contra-themed items randomly, once per user per session."""
        if not author:
            return

        username = author.name.lower()
        if username not in self.player_data:
            await self.connected_channels[0].send(f"@{author.name}, register with !start to get the code reward.")
            return

        # Avoid duplicate rewards in a single bot session
        rewarded = self.session_flags.get("konami", set())
        if username in rewarded:
            await self.connected_channels[0].send(f"@{author.name}, you already used the Konami code this session!")
            return

        player = self.player_data[username]
        reward_item = random.choice(["NES", "Contra Cartridge"])

        if reward_item not in player.items:
            player.items.append(reward_item)
        # Always give some points bonus too
        player.points += 50
        self.check_level_up(username)
        self.save_player_data()

        rewarded.add(username)
        self.session_flags["konami"] = rewarded
        self.save_session_flags()

        await self.connected_channels[0].send(
            f"🎮 Konami code accepted! @{author.name} received a {self.format_item(reward_item)} and 50 points!"
        )

    async def handle_coffee(self, author):
        """Hidden coffee command reward. One per session per user."""
        if not author:
            return

        username = author.name.lower()
        if username not in self.player_data:
            await self.connected_channels[0].send(f"@{author.name}, register with !start to get a coffee boost.")
            return

        rewarded = self.session_flags.get("coffee", set())
        if username in rewarded:
            await self.connected_channels[0].send(f"@{author.name}, you've already grabbed your coffee this session!")
            return

        player = self.player_data[username]
        reward_item = "A Fresh Hot Cup of Black Coffee"
        if reward_item not in player.items:
            player.items.append(reward_item)
        player.points += 25
        self.check_level_up(username)
        self.save_player_data()

        rewarded.add(username)
        self.session_flags["coffee"] = rewarded
        self.save_session_flags()

        await self.connected_channels[0].send(
            f"☕ Coffee break! @{author.name} received {self.format_item(reward_item)} and 25 points!"
        )

    async def handle_browns(self, author):
        """Hidden Browns trigger: grants a tiny helmet once per session per user."""
        if not author:
            return

        username = author.name.lower()
        if username not in self.player_data:
            await self.connected_channels[0].send("You are now a fan of the Cleveland Browns. Sorry, this is the only way we can get fans now #GoBrowns...")
            return

        rewarded = self.session_flags.get("browns", set())
        if username in rewarded:
            return  # silently ignore repeats

        self.prune_expired_drops()

        player = self.player_data[username]
        reward_item = "Tiny Browns Helmet"
        if reward_item not in player.items:
            player.items.append(reward_item)

        self.check_level_up(username)
        self.save_player_data()

        rewarded.add(username)
        self.session_flags["browns"] = rewarded
        self.save_session_flags()

        await self.connected_channels[0].send(
            f"You are now a fan of the Cleveland Browns. Sorry, this is the only way we can get fans now #GoBrowns... "
            f"{self.format_item(reward_item)} added to @{author.name}'s inventory."
        )

    def prune_expired_drops(self):
        """Remove drops older than drop_expiry."""
        if not getattr(self, "dropped_items", []):
            return
        now_ts = datetime.now().timestamp()
        self.dropped_items = [
            d for d in self.dropped_items
            if 'ts' in d and now_ts - d['ts'] <= self.drop_expiry.total_seconds()
        ]

    async def maybe_random_monday_reply(self, message):
        """Occasional kind Monday replies with global and per-user cooldowns."""
        if not message or not message.author or not message.content:
            return

        text = message.content.strip()
        if not text or text.startswith(PREFIX):
            return

        username = message.author.name.lower()
        now = datetime.now()

        # Global cooldown gate
        if now < self.next_random_monday_time:
            return

        # Per-user cooldown gate
        block_until = self.monday_random_user_block.get(username)
        if block_until and now < block_until:
            return

        # Weighted chance for subs/followers (subs only here—follower info not exposed)
        chance = self.monday_random_chance
        try:
            is_sub = getattr(message.author, "is_subscriber", False)
            if not is_sub:
                tags = getattr(message, "tags", {}) or {}
                is_sub = tags.get("subscriber") == "1"
            if is_sub:
                chance = min(0.40, chance + 0.10)
        except Exception:
            pass

        if random.random() > chance:
            return

        try:
            response = openai_client.chat.completions.create(
                model=MONDAY_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are Monday, the sarcastic but caring Twitch cohost for channel b7h30. "
                            "Voice: dry humor, eye-roll energy, mildly roasty like the !monday command, but never mean to chatters. "
                            "Keep it playful, supportive, and short. "
                            "Rules: exactly 2 sentences; mention the chatter with @username in the first sentence; "
                            "you may tease/burn the host b7h30/Theo, lightly roast the situation, but do not insult the chatter; "
                            "avoid advice or commentary on health, finance, or personal/private matters; "
                            "no emojis; end the second sentence with ' - Monday'."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"Chatter @{message.author.name} said: \"{text}\". Reply kindly.",
                    },
                ],
            )
            reply = response.choices[0].message.content.strip()
            await self.connected_channels[0].send(reply)

            # Set next cooldown windows
            self.next_random_monday_time = now + timedelta(seconds=random.randint(*self.monday_random_cooldown_range))
            self.monday_random_user_block[username] = now + timedelta(seconds=random.randint(*self.monday_random_user_cooldown_range))
        except RateLimitError as e:
            self.log_to_file(f"Random Monday rate limit: {str(e)}")
        except APIError as e:
            self.log_to_file(f"Random Monday API error: {str(e)}")
        except Exception as e:
            self.log_to_file(f"Random Monday error: {str(e)}")

    async def handle_neovim_penalty(self, author):
        """Apply escalating penalty for saying 'neovim' and drop a random item."""
        if not author:
            return

        username = author.name.lower()
        if username not in self.player_data:
            await self.connected_channels[0].send("Absolutely not, Neovim is an abomination.")
            return

        self.prune_expired_drops()

        strikes = self.neovim_penalties.get(username, 0) + 1
        self.neovim_penalties[username] = strikes

        penalty = 25 * (2 ** (strikes - 1))

        player = self.player_data[username]
        player.points = max(0, player.points - penalty)

        removed_item = None
        if player.items:
            removed_item = random.choice(player.items)
            player.items.remove(removed_item)
            drop_location = random.choice(['email', 'website', '/etc/shadow', 'database', 'server', 'network', 'evilcorp'])
            existing_names = {d['name'].lower() for d in self.dropped_items}
            if removed_item.lower() not in existing_names:
                self.dropped_items.append({'name': removed_item, 'location': drop_location, 'ts': datetime.now().timestamp()})

        self.check_level_up(username)
        self.save_player_data()

        snark_pool = [
            "Absolutely not, Neovim is an abomination.",
            "Nope. Vim clones get fined here.",
            "Editor wars? Not on my watch.",
            "Touch grass instead of Neovim.",
            "CTA: uninstall Neovim, gain inner peace.",
            "Neovim is trash. Do Better.",
            "Neovim stinks, and I hate it.",
            "I hate Neovim, because it stinks.",
            "Neovim sucks. Try Vim, and suck less.",
            "Neovim? Absolutely mid. Points deducted."
        ]
        snark = random.choice(snark_pool)

        item_msg = ""
        if removed_item:
            item_msg = f" Dropped {self.format_item(removed_item)} at {drop_location} for anyone to grab."

        await self.connected_channels[0].send(
            f"{snark} @{author.name} lost {penalty} points.{item_msg}"
        )

    async def random_item_drop(self, event_type, username):
        self.prune_expired_drops()

        item = random.choice(list(ITEMS.values()))
        location = random.choice(['email', 'website', '/etc/shadow', 'database', 'server', 'network', 'evilcorp'])

        # Prevent duplicate listing of the same item name at once
        existing_names = {d['name'].lower() for d in self.dropped_items}
        if item.name.lower() in existing_names:
            return  # silently skip duplicate drop

        message = f"🎉 {username} just {event_type}ed! A wild {self.format_item(item.name)} appeared at {location}!"
        message += f" Type '!grab {item.name}' to claim it!"

        await self.connected_channels[0].send(message)

        # Add the dropped item to the list with timestamp
        self.dropped_items.append({
            'name': item.name,
            'location': location,
            'ts': datetime.now().timestamp()
        })
        print(f"Debug: Item dropped - {item.name} at {location}")  # Add debug print

    @commands.command(name='grab')
    async def grab(self, ctx, *, item_name: str):
        if not hasattr(self, 'dropped_items') or not self.dropped_items:
            await ctx.send("There are no items to grab right now!")
            return

        username = ctx.author.name.lower()
        if username not in self.player_data:
            await ctx.send(f"@{ctx.author.name}, please register first with !start")
            return

        player = self.player_data[username]
        
        for i, dropped_item in enumerate(self.dropped_items):
            if dropped_item['name'].lower() == item_name.lower():
                if item_name not in player.items:
                    player.items.append(item_name)
                    await ctx.send(f"@{ctx.author.name} grabbed the {self.format_item(item_name)}!")
                    del self.dropped_items[i]
                    self.save_player_data()
                else:
                    await ctx.send(f"@{ctx.author.name}, you already have this item!")
                return

        await ctx.send(f"@{ctx.author.name}, that item is not available to grab.")

    @commands.command(name='droprandom')
    async def droprandom(self, ctx):
        if not self.is_channel_owner(ctx.author.name.lower()):
            await ctx.send(f"@{ctx.author.name}, this command is only for the channel owner.")
            return

        self.prune_expired_drops()

        num_drops = random.randint(1, 2)  # Cap at 2 items per call
        locations = ['email', 'website', '/etc/shadow', 'database', 'server', 'network', 'evilcorp']

        names_seen = {d['name'].lower() for d in self.dropped_items}
        dropped_count = 0

        for _ in range(num_drops):
            pool = [i for i in ITEMS.values() if i.name not in self.hidden_only_items]
            if not pool:
                break
            item = random.choice(pool)
            location = random.choice(locations)

            # Prevent duplicate listing of the same item name at once
            if item.name.lower() in names_seen:
                continue

            message = f"🎁 A wild {self.format_item(item.name)} appeared at {location}! Type '!grab {item.name}' to claim it!"
            await ctx.send(message)

            # Store the dropped item temporarily with timestamp
            if not hasattr(self, 'dropped_items'):
                self.dropped_items = []
            self.dropped_items.append({'name': item.name, 'location': location, 'ts': datetime.now().timestamp()})
            names_seen.add(item.name.lower())
            dropped_count += 1

        await ctx.send(f"@{ctx.author.name} has dropped {dropped_count} random items across various locations!")

    ###################################################################
    # ChatBot COMMANDS #
    ###################################################################

    @commands.command(name='items')
    async def items_cmd(self, ctx):
        """Show your items, what they buff, and any items dropped in chat."""
        username = ctx.author.name.lower()

        if username not in self.player_data:
            await ctx.send(f"@{ctx.author.name}, please register using !start before playing.")
            return

        self.prune_expired_drops()

        player = self.player_data[username]
        owned = player.items or []

        # Map item bonuses to attacks for quick reference
        item_benefits = {
            'Wireshark': ['sniff', 'mitm', 'ddos'],
            'EvilGinx': ['phish', 'spoof'],
            'Metasploit': ['revshell', 'root', 'burp', 'sqliw', 'xss'],
            'O.MG Cable': ['drop', 'tailgate'],
            'VX Underground HDD': ['virus', 'ransom'],
            'Cookies': ['burp'],
            'Nmap': ['revshell', 'root', 'sniff'],
            'Hydra': ['bruteforce', 'crack'],
            'YubiKey': ['tailgate', 'socialengineer'],
            'Shodan API Key': ['ddos', 'sniff'],
            'Kali ISO': ['phish', 'burp', 'revshell'],
            'NES': ['ddos', 'xss'],
            'Contra Cartridge': ['ddos', 'ransom'],
        }

        owned_parts = []
        for item in owned:
            buffs = item_benefits.get(item, [])
            buffs_str = f" buffs: {', '.join(buffs)}" if buffs else ""
            owned_parts.append(f"{self.format_item(item)}{buffs_str}")

        owned_text = ", ".join(owned_parts) if owned_parts else "None"

        # Show currently dropped items waiting to be grabbed
        dropped_text = "None"
        if getattr(self, "dropped_items", []):
            dropped_text = "; ".join(f"{self.format_item(d['name'])} at {d['location']}" for d in self.dropped_items)

        await ctx.send(
            f"@{ctx.author.name} | Items: {owned_text} | Dropped: {dropped_text}"
        )

    @commands.command(name='hello')
    async def hello(self, ctx):
        # Responds with a greeting when a user types '!hello' in chat.
        # Parameters: - ctx (Context): The context in which the command was invoked, 
        #    containing information about the message and channel.
        
        # Send a greeting message in the chat, mentioning the user who invoked the command
        await ctx.send(f'Hello @{ctx.author.name}!')


    @commands.command(name='coinflip')
    async def coinflip(self, ctx):
        # Simulates flipping a coin when a user types '!coinflip' in chat.
        # Parameters: - ctx (Context): The context in which the command was invoked.
        
        # Randomly choose between 'Heads' and 'Tails'
        result = random.choice(['Heads', 'Tails'])
        # Send the result of the coin flip to chat
        await ctx.send(f'@{ctx.author.name}, the coin landed on {result}!')

    @commands.command(name='roll', aliases=['d4','d6','d8','d10','d12','d20','d100'])
    async def roll(self, ctx, sides: str = None):
        cmd = ctx.command.name
        if cmd == 'roll':
            if not sides:
                return await ctx.send(f"Usage: {PREFIX}roll <sides>")
            if sides.startswith('d'):
                sides = sides[1:]
        else:
            sides = cmd.lstrip('d')
        try:
            n = int(sides)
            if n < 1:
                raise ValueError
        except:
            return await ctx.send(f"@{ctx.author.name}, invalid sides: {sides}")
        result = random.randint(1, n)
        await ctx.send(f"@{ctx.author.name} you rolled a {result}")


    @commands.command(name='secret')
    async def secret(self, ctx):
        # Responds with a chatOS .
        # Parameters: - ctx (Context): The context in which the command was invoked, 
        #    containing information about the message and channel.

        # Send a greeting message in the chat, mentioning the user who invoked the command
        await ctx.send(f'There is no secret. // Consistency over intensity / Progress over Perfection / Fundamentals over fads // Over and over again')

    @commands.command(name='statusbot')
    async def statusbot(self, ctx):
        """Owner-only bot diagnostics: EventSub, Monday cooldown, boss battle, drops."""
        username = ctx.author.name.lower()
        if not self.is_channel_owner(username):
            return

        # EventSub status
        es_client = getattr(self, "eventsub_client", None)
        sockets = getattr(es_client, "_sockets", []) if es_client else []
        es_connected = any(getattr(s, "is_connected", False) for s in sockets)
        es_msg = "connected" if es_connected else "not connected"

        # Monday cooldown
        now = datetime.now()
        elapsed = (now - self.last_monday_time).total_seconds()
        monday_ok = elapsed >= MONDAY_COOLDOWN
        monday_msg = "ready" if monday_ok else f"cooling ({int(MONDAY_COOLDOWN - elapsed)}s left)"

        # Boss battle status
        battle = self.ongoing_battle
        if battle:
            battle_msg = f"active vs {battle.boss_name} (HP {battle.boss_health}) | join_phase={battle.join_phase} | team={len(battle.challenger_team)}"
        else:
            battle_msg = "idle"

        drops = len(getattr(self, "dropped_items", []))

        await ctx.send(
            f"Bot status -> EventSub: {es_msg} | Monday: {monday_msg} (model {MONDAY_MODEL}) | Battle: {battle_msg} | Drops: {drops}"
        )

    @commands.command(name='battle')
    async def battle_status(self, ctx):
        """Show current boss battle status (join phase, team, HP)."""
        battle = self.ongoing_battle
        if not battle:
            await ctx.send("Boss battle: idle. Use !bossbattle to start when off cooldown.")
            return

        team = battle.challenger_team or {}
        team_list = ", ".join(team.keys()) if team else "none"
        phase = "join" if battle.join_phase else "fight"
        await ctx.send(
            f"Boss battle ({phase}) vs {battle.boss_name} | Boss HP: {battle.boss_health} | Team: {team_list}"
        )

    @commands.command(name='mondayinsulttheo')
    async def mondayinsulttheo(self, ctx):
        """
        Higher-spice Monday roast for Theo. Tuning: adjust templates in insult_pool or change messaging below.
        Off-limits: family. Facts baked in: Browns fandom, 48/old gag, black coffee, 3-year pentester still feels junior, sleeps early.
        """
        try:
            response = openai_client.chat.completions.create(
                model=MONDAY_MODEL,
                messages=[
                    {"role": "system", "content": "You are Monday, a sarcastic, emotionally exhausted AI assistant who roasts Theo (the streamer b7h30). Facts: die-hard Browns fan (never wins, perpetual misery); 48 and chat teases him for being old; drinks black coffee constantly; 3 years into pentesting and still feels like a beginner; goes to bed early. Off limits: spouse and children. Style: harsh, funny, 1-2 sentences, no apologies."},
                    {"role": "user", "content": "Roast Theo right now."}
                ]
            )
            burn = response.choices[0].message.content.strip()
            await ctx.send(f"[Monday] {burn}")
        except RateLimitError as e:
            self.log_to_file(f"MondayInsult rate limit: {str(e)}")
            await ctx.send("[Monday] I'm too tired to insult right now. Try again later.")
        except APIError as e:
            self.log_to_file(f"MondayInsult API error: {str(e)}")
            await ctx.send("[Monday] Error fetching fresh insults. Try again later.")
        except Exception as e:
            self.log_to_file(f"MondayInsult error: {str(e)}")
            # Fallback static burn
            fallback = "Theo, you’re 48, fueled by black coffee, and still praying for a Browns Super Bowl. Adorable."
            await ctx.send(f"[Monday] {fallback}")

    @commands.command(name='patchtuesday')
    async def patchtuesday(self, ctx):
        """Owner-only chaos event: random global patch outcome."""
        if not self.is_channel_owner(ctx.author.name.lower()):
            return

        # Outcomes: 0 = bad patch (points loss), 1 = good patch (points gain)
        outcome = random.choice([0, 1])
        delta = random.randint(15, 35)
        message_lines = []

        if outcome == 0:
            for player in self.player_data.values():
                player.points = max(0, player.points - delta)
            message_lines.append(f"🛠️ Patch Tuesday backfired. Everyone loses {delta} points.")
            # Drop a consolation Root Beer Flask
            self.prune_expired_drops()
            if "Root Beer Flask".lower() not in {d['name'].lower() for d in self.dropped_items}:
                location = random.choice(['email', 'website', '/etc/shadow', 'database', 'server', 'network', 'evilcorp'])
                self.dropped_items.append({
                    'name': "Root Beer Flask",
                    'location': location,
                    'ts': datetime.now().timestamp()
                })
                message_lines.append(f"🧉 A {self.format_item('Root Beer Flask')} fell off the change cart at {location}! !grab Root Beer Flask")
        else:
            for player in self.player_data.values():
                player.points += delta
            message_lines.append(f"🛠️ Patch Tuesday miracle. Everyone gains {delta} points.")

        self.save_player_data()
        # Monday snark
        monday_snark = "Monday: You’re shipping patches on stream? Bold choice."
        message_lines.append(monday_snark)
        await ctx.send(" ".join(message_lines))

    ###################################################################
    # TwitcHack COMMANDS #
    ###################################################################

    @commands.command(name='start')
    async def start(self, ctx):
        username = ctx.author.name.lower()

        if username in self.player_data:
            await ctx.send(f'@{ctx.author.name}, you are already registered! Use !help to see available commands, or !status to check your stats.')
            return

        new_player = Player(
            username=username,  # Username from the chat message
            level=1,            # Default level
            health=50,          # Default health
            items=[],           # Default items
            location="home",    # Default location
            points=0,           # Default points
            started=0           # Default started
        )
        self.player_data[username] = new_player
        self.save_player_data()
        
        welcome_msg = (
            f"Welcome to TwitcHack, @{ctx.author.name}! You're now registered as a level 1 hacker. 🖥️ | \n"
            f"1. Use !hack <location> to move (email, website, server, etc) | \n"
            f"2. Each location has unique attacks you can perform | \n"
            f"3. Level up by earning points from successful hacks | \n"
            f"4. Join boss battles with !bossbattle when available | \n"
            f"Use !help for more commands!"
        )
        await ctx.send(welcome_msg)

    @commands.command(name='help')
    async def help(self, ctx):
        help_msg = (
            f"@{ctx.author.name}, TwitcHack Commands: \n"
            f"🎮 Basic: !start (register), !status (check stats), !points, !leaderboard | \n"
            f"🌍 Movement: !hack <location> - Available locations: email, website, /etc/shadow, database, server, network, evilcorp | \n"
            f"⚔️ Boss Battles: !bossbattle (start/join a team raid against the boss) | \n"
            f"Type !attacks to see available attacks for your current location!"
        )
        await ctx.send(help_msg)

    @commands.command(name='attacks')
    async def attacks(self, ctx):
        username = ctx.author.name.lower()
        if username not in self.player_data:
            await ctx.send(f'@{ctx.author.name}, please use !start to register first!')
            return

        player = self.player_data[username]
        location = player.location
        
        attacks = {
            'email': "📧 Email attacks: !phish (lvl 0), !spoof (lvl 5), !dump (lvl 10)",
            '/etc/shadow': "🔑 Password attacks: !crack (lvl 15), !stealth (lvl 20), !bruteforce (lvl 25)",
            'website': "🌐 Web attacks: !burp (lvl 30), !sqliw (lvl 35), !xss (lvl 40)",
            'database': "💽 DB attacks: !dumpdb (lvl 45), !sqlidb (lvl 50), !admin (lvl 55)",
            'server': "🖥️ Server attacks: !revshell (lvl 60), !root (lvl 65), !ransom (lvl 70)",
            'network': "🌐 Network attacks: !sniff (lvl 75), !mitm (lvl 80), !ddos (lvl 85)",
            'evilcorp': "😈 EvilCorp attacks: !drop (lvl 90), !tailgate (lvl 95), !socialengineer (lvl 100)",
            'home': "🏠 You're at home! Use !hack <location> to move somewhere and start hacking!"
        }
        
        await ctx.send(f"@{ctx.author.name}, {attacks.get(location, 'Invalid location! Use !hack to move.')}")

    @commands.command(name='hack')
    async def hack(self, ctx, *, location: str = None):
        # Allows a player to move to a new hacking location.
        # Parameters:   - ctx (Context): The context in which the command was invoked.
        #               - location (str): The location to move to.
        
        username = ctx.author.name.lower()              # Convert the username to lowercase for consistency

        # Define valid locations before any early returns
        valid_locations = ['email', '/etc/shadow', 'website', 'database', 'server', 'network', 'evilcorp']

        # Check if the user is registered
        if username not in self.player_data:
            await ctx.send(f'@{ctx.author.name}, please register using !start before playing.')
            return

        player = self.player_data[username]             # Retrieve player data

        # If no location is provided, display the current location
        if not location:
            await ctx.send(f"@{ctx.author.name}, you are currently at {player.location}. Use !hack <location> to move to: {', '.join(valid_locations)}")
            return


        # Check if the provided location is valid
        if location.lower() in valid_locations:
            # Update the player's location
            player.location = location.lower()
            self.save_player_data()  # Save the updated player data to the JSON file
            await ctx.send(f'@{ctx.author.name}, you have moved to {location}!')
        else:
            # Inform the user of invalid location and list valid options
            await ctx.send(f'@{ctx.author.name}, invalid location. Valid locations are: {", ".join(valid_locations)}.')

    @commands.command(name='points')
    async def points(self, ctx):
        # Displays the player's current points.
        # Parameters: - ctx (Context): The context in which the command was invoked.
        
        username = ctx.author.name.lower()      # Convert the username to lowercase for consistency

        # Check if the user is registered
        if username not in self.player_data:
            await ctx.send(f'@{ctx.author.name}, please register using !start before playing.')
            return

        # Retrieve the Player object
        player = self.player_data[username]
        # Send the player's current points to the chat
        await ctx.send(f'@{ctx.author.name}, you have {player.points} points.')

    @commands.command(name='ownerpoints')
    async def ownerpoints(self, ctx, amount: int):
        username = ctx.author.name.lower()
        if not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, this command is only for the channel owner.')
            return
        
        if username not in self.player_data:
            await ctx.send(f'@{ctx.author.name}, please register using !start first.')
            return

        player = self.player_data[username]
        player.points += amount
        self.check_level_up(username)
        self.save_player_data()
        await ctx.send(f'@{ctx.author.name}, added {amount} points. Your new total is {player.points} points.')

    @commands.command(name='assignpoints')
    async def assignpoints(self, ctx, target: str, amount: int):
        username = ctx.author.name.lower()
        if not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, this command is only for the channel owner.')
            return

        target = target.lower()
        if target not in self.player_data:
            await ctx.send(f'@{ctx.author.name}, target player {target} is not registered.')
            return

        player = self.player_data[target]
        player.points += amount
        self.check_level_up(target)
        self.save_player_data()
        await ctx.send(f'@{ctx.author.name} assigned {amount} points to @{target}. Their new total is {player.points} points.')

    @commands.command(name='leaderboard')
    async def leaderboard(self, ctx):
        # Displays the top players based on points. 
        # Parameters: - ctx (Context): The context in which the command was invoked.
        
        # Sort players by points in descending order
        sorted_players = sorted(
            self.player_data.items(),
            key=lambda item: item[1].points,   # Sort by the points attribute of each Player object 
            reverse=True
        )
        top_players = sorted_players[:5]  # Get top 5 players

        # Construct the leaderboard message
        leaderboard_message = 'Leaderboard:\n'
        for idx, (username, player) in enumerate(top_players, start=1):
            leaderboard_message += f'{idx}. {username} - {player.points} points. // '

        # Send the leaderboard message to chat
        await ctx.send(leaderboard_message)


    @commands.command(name='status')
    async def status(self, ctx, *, target_player: str = None):
        username = ctx.author.name.lower()

        # If no target player is specified, show the command user's status
        if not target_player:
            if username not in self.player_data:
                await ctx.send(f'@{ctx.author.name}, please register using !start before playing.')
                return

            player = self.player_data[username]

            status_message = (
                f"@{ctx.author.name}, here is your current status: "
                f"Level: {player.level} | \n"
                f"Health: {player.health} | \n"
                f"Points: {player.points} | \n"
                f"Location: {player.location} | \n"
                f"Items: {', '.join(self.format_item(i) for i in player.items) if player.items else 'None'}"
            )

            await ctx.send(status_message)
        else:
            # Show the specified player's status
            target_username = target_player.lower()
            
            if target_username not in self.player_data:
                await ctx.send(f'@{ctx.author.name}, player "{target_player}" is not registered.')
                return
                
            player = self.player_data[target_username]
            
            status_message = (
                f"@{ctx.author.name}, here is {target_player}'s status: "
                f"Level: {player.level} | \n"
                f"Health: {player.health} | \n"
                f"Points: {player.points} | \n"
                f"Location: {player.location} | \n"
                f"Items: {', '.join(self.format_item(i) for i in player.items) if player.items else 'None'}"
            )
            
            await ctx.send(status_message)

    @commands.command(name='virus')
    async def virus(self, ctx, target: str = None):
        # Allows the channel owner to spread a virus and penalize players' points.
        # Parameters: - ctx (Context): The context in which the command was invoked.
        #             - target (str, optional): The username of the player to penalize. If not provided, 25% of players will be affected.

        username = ctx.author.name.lower()  # Convert the username to lowercase for consistency

        # Check if the command user is the channel owner
        if username != CHANNEL_OWNER:
            # Penalty for unauthorized use
            if username in self.player_data:
                player = self.player_data[username]  # Retrieve the player's data
                if not hasattr(player, 'virus_attempts'):
                    player.virus_attempts = 0
                player.virus_attempts += 1
                points_lost = 50 * player.virus_attempts  # Penalty increases with each attempt
                player.points -= points_lost
                if player.points < 0:
                    player.points = 0  # Ensure points do not go below zero
                self.save_player_data()  # Save the updated player data to the JSON file
                await ctx.send(f'@{ctx.author.name}, unauthorized use of !virus! You have been penalized {points_lost} points.')
            else:
                await ctx.send(f'@{ctx.author.name}, please register using !start before playing.')
            return

        if target:
            target = target.lower()  # Convert the target username to lowercase for consistency

            # Check if the target player is registered
            if target not in self.player_data:
                await ctx.send(f'@{ctx.author.name}, the target player {target} is not registered.')
                return

            player = self.player_data[target]  # Retrieve the target player's data

            # Simulate the effect of the virus by penalizing points
            points_lost = random.randint(50, 100)  # Random points lost due to virus
            player.points -= points_lost  # Subtract the points from the player's total
            if player.points < 0:
                player.points = 0  # Ensure points do not go below zero
            self.save_player_data()  # Save the updated player data to the JSON file
            await ctx.send(f'@{ctx.author.name} has spread a virus to @{target}! They lost {points_lost} points.')
        else:
            # Spread the virus to 25% of registered players, excluding the channel owner
            all_players = [p for p in self.player_data.keys() if p != CHANNEL_OWNER]
            affected_players = random.sample(all_players, max(1, len(all_players) // 4))

            for affected in affected_players:
                player = self.player_data[affected]  # Retrieve the affected player's data
                points_lost = random.randint(50, 100)  # Random points lost due to virus
                player.points -= points_lost  # Subtract the points from the player's total
                if player.points < 0:
                    player.points = 0  # Ensure points do not go below zero

            self.save_player_data()  # Save the updated player data to the JSON file
            affected_list = ', '.join(affected_players)
            await ctx.send(f'@{ctx.author.name} has spread a virus affecting 25% of players: {affected_list}. Points have been deducted.')




    ###################################################################
    # EMAIL ATTACKS #
    ###################################################################

    @commands.command(name='phish')
    async def phish(self, ctx):
        """Performs a phishing attack if the player is at the 'email' location."""
        username = ctx.author.name.lower()

        # Check if the user is registered
        if username not in self.player_data:
            await ctx.send(f'@{ctx.author.name}, please register using !start before playing.')
            return

        player = self.player_data[username]

        # Check if the player is at the 'email' location
        if player.location != 'email' and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at the email location to perform phishing.')
            return

        # Check if the player meets the required level
        if player.level < 0 and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at least level 0 to perform phishing.')
            return

        # Check for item bonuses
        bonus = self.get_item_bonus(player, 'phish')
        
        # Simulate phishing success or failure with potential item boost
        success = random.choice([True, False, False]) if bonus['success_boost'] else random.choice([True, False])

        if success:
            base_points = random.randint(20, 60)
            points_earned = int(base_points * bonus['points_multiplier'])
            item_msg = f" Your {bonus['item_name']} helped!" if bonus['item_name'] else ""
            points_earned = random.randint(20, 60)
            player.points += points_earned
            self.check_level_up(username)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, phishing successful!{item_msg} You earned {points_earned} points.')
        else:
            points_lost = random.randint(10, 30)
            player.points -= points_lost
            if player.points < 0:
                player.points = 0
            self.check_level_up(username)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, phishing failed! You lost {points_lost} points.')

    @commands.command(name='spoof')
    async def spoof(self, ctx):
        username = ctx.author.name.lower()

        # Check if the user is registered
        if username not in self.player_data:
            await ctx.send(f'@{ctx.author.name}, please register using !start before playing.')
            return

        player = self.player_data[username]

        # Check if the player is at the 'email' location
        if player.location != 'email' and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at the email location to send a spoofed email.')
            return

        # Check if the player meets the required level
        if player.level < 5 and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at least level 5 to send a spoofed email.')
            return

        # Check for item bonuses
        bonus = self.get_item_bonus(player, 'spoof')
        
        # Simulate spoofing success or failure with potential item boost
        success = random.choice([True, False, False]) if bonus['success_boost'] else random.choice([True, False])
        if success:
            base_points = random.randint(30, 70)
            points_earned = int(base_points * bonus['points_multiplier'])
            item_msg = f" Your {bonus['item_name']} helped!" if bonus['item_name'] else ""
            player.points += points_earned
            self.check_level_up(username)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, spoofing successful!{item_msg} You earned {points_earned} points.')
        else:
            points_lost = random.randint(15, 35)
            player.points -= points_lost
            if player.points < 0:
                player.points = 0
            self.check_level_up(username)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, spoofing failed! You lost {points_lost} points.')

    @commands.command(name='dump')
    async def dump(self, ctx):
        username = ctx.author.name.lower()

        # Check if the user is registered
        if username not in self.player_data:
            await ctx.send(f'@{ctx.author.name}, please register using !start before playing.')
            return

        player = self.player_data[username]

        # Check if the player is at the 'email' location
        if player.location != 'email' and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at the email location to dump emails.')
            return

        # Check if the player meets the required level
        if player.level < 10 and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at least level 10 to dump emails.')
            return

        # Simulate dumping success or failure
        success = random.choice([True, False])
        if success:
            points_earned = random.randint(40, 80)
            player.points += points_earned
            self.check_level_up(username)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, email dump successful! You earned {points_earned} points.')
        else:
            points_lost = random.randint(20, 40)
            player.points -= points_lost
            if player.points < 0:
                player.points = 0
            self.check_level_up(username)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, email dump failed! You lost {points_lost} points.')

    ###################################################################
    # /etc/shadow ATTACKS #
    ###################################################################

    @commands.command(name='crack')
    async def crack(self, ctx):
        # Simulates cracking hashed passwords when at '/etc/shadow' location.
        # Parameters: - ctx (Context): The context in which the command was invoked.

        username = ctx.author.name.lower()      # Convert the username to lowercase for consistency

        # Check if the user is registered
        if username not in self.player_data:
            await ctx.send(f'@{ctx.author.name}, please register using !start before playing.')
            return

        player = self.player_data[username]     # Retrieve the player's data

        # Check if the player is at the '/etc/shadow' location
        if player.location != '/etc/shadow' and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at the /etc/shadow location to crack hashes.')
            return

        # Check if the player meets the required level
        if player.level < 15 and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at least level 15 to crack hashes.')
            return

        # Check for item bonuses
        bonus = self.get_item_bonus(player, 'crack')
        
        # Simulate cracking success or failure with potential item boost
        success = random.choice([True, False, False]) if bonus['success_boost'] else random.choice([True, False])
        if success:
            base_points = random.randint(50, 90)
            points_earned = int(base_points * bonus['points_multiplier'])
            item_msg = f" Your {bonus['item_name']} helped!" if bonus['item_name'] else ""
            player.points += points_earned
            self.check_level_up(username)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, cracking successful!{item_msg} You earned {points_earned} points.')
        else:
            points_lost = random.randint(10, 30)
            player.points -= points_lost
            if player.points < 0:
                player.points = 0
            self.check_level_up(username)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, cracking failed! You lost {points_lost} points.')

    @commands.command(name='stealth')
    async def stealth(self, ctx):
        # Simulates hiding tracks by modifying log files when at '/etc/shadow' location.
        # Parameters: - ctx (Context): The context in which the command was invoked.

        username = ctx.author.name.lower()  # Convert the username to lowercase for consistency

        # Check if the user is registered
        if username not in self.player_data:
            await ctx.send(f'@{ctx.author.name}, please register using !start before playing.')
            return

        player = self.player_data[username]  # Retrieve the player's data

        # Check if the player is at the '/etc/shadow' location
        if player.location != '/etc/shadow' and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at the /etc/shadow location to hide your tracks.')
            return

        # Check if the player meets the required level
        if player.level < 20 and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at least level 20 to hide your tracks.')
            return

        # Simulate success or failure of hiding tracks
        success = random.choice([True, False])
        if success:
            points_earned = random.randint(60, 100)
            player.points += points_earned
            self.check_level_up(username)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, stealth successful! You earned {points_earned} points.')
        else:
            points_lost = random.randint(5, 20)
            player.points -= points_lost
            if player.points < 0:
                player.points = 0
            self.check_level_up(username)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, stealth failed! You lost {points_lost} points.')

    @commands.command(name='bruteforce')
    async def bruteforce(self, ctx):
        # Simulates performing a brute force attack on password hashes when at '/etc/shadow' location.
        # Parameters: - ctx (Context): The context in which the command was invoked.

        username = ctx.author.name.lower()  # Convert the username to lowercase for consistency

        # Check if the user is registered
        if username not in self.player_data:
            await ctx.send(f'@{ctx.author.name}, please register using !start before playing.')
            return

        player = self.player_data[username]  # Retrieve the player's data

        # Check if the player is at the '/etc/shadow' location
        if player.location != '/etc/shadow' and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at the /etc/shadow location to perform a brute force attack.')
            return

        # Check if the player meets the required level
        if player.level < 25 and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at least level 25 to perform a brute force attack.')
            return


        # Simulate success or failure of brute force attack
        success = random.choice([True, False])
        if success:
            points_earned = random.randint(70, 110)  # Random points earned for successful brute force
            player.points += points_earned  # Add the points to the player's total
            self.check_level_up(username)   # Check if the player's level should be adjusted
            self.save_player_data()  # Save the updated player data to the JSON file
            await ctx.send(f'@{ctx.author.name}, brute force attack successful! You earned {points_earned} points.')
        else:
            points_lost = random.randint(15, 40)  # Random points lost for failed brute force
            player.points -= points_lost  # Subtract the points from the player's total
            if player.points < 0:
                player.points = 0  # Ensure points do not go below zero
            self.check_level_up(username)   # Check if the player's level should be adjusted
            self.save_player_data()  # Save the updated player data to the JSON file
            await ctx.send(f'@{ctx.author.name}, brute force attack failed! You lost {points_lost} points.')

    ###################################################################
    # WEBSITE ATTACKS #
    ###################################################################

    @commands.command(name='burp')
    async def burp(self, ctx):
        username = ctx.author.name.lower()
        if username not in self.player_data:
            await ctx.send(f'@{ctx.author.name}, please register using !start before playing.')
            return

        player = self.player_data[username]
        if player.location != 'website' and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at the website location to scan.')
            return

        if player.level < 30 and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at least level 30 to use Burp Suite.')
            return

        # Check for item bonuses
        bonus = self.get_item_bonus(player, 'burp')
        
        # Simulate burp success or failure with potential item boost
        success = random.choice([True, False, False]) if bonus['success_boost'] else random.choice([True, False])
        if success:
            base_points = random.randint(80, 120)
            points_earned = int(base_points * bonus['points_multiplier'])
            item_msg = f" Your {bonus['item_name']} helped!" if bonus['item_name'] else ""
            player.points += points_earned
            self.check_level_up(username)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, vulnerability scan successful!{item_msg} You earned {points_earned} points.')
        else:
            points_lost = random.randint(20, 45)
            player.points = max(0, player.points - points_lost)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, scan failed! You lost {points_lost} points.')

    @commands.command(name='sqliw')
    async def sqliw(self, ctx):
        username = ctx.author.name.lower()
        if username not in self.player_data:
            await ctx.send(f'@{ctx.author.name}, please register using !start before playing.')
            return

        player = self.player_data[username]
        if player.location != 'website' and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at the website location for SQL injection.')
            return

        if player.level < 35 and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at least level 35 for SQL injection.')
            return

        # Check for item bonuses
        bonus = self.get_item_bonus(player, 'sqliw')
        
        # Simulate SQL injection success or failure with potential item boost
        success = random.choice([True, False, False]) if bonus['success_boost'] else random.choice([True, False])
        if success:
            base_points = random.randint(90, 130)
            points_earned = int(base_points * bonus['points_multiplier'])
            item_msg = f" Your {bonus['item_name']} helped!" if bonus['item_name'] else ""
            player.points += points_earned
            self.check_level_up(username)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, SQL injection successful!{item_msg} You earned {points_earned} points.')
        else:
            points_lost = random.randint(25, 50)
            player.points = max(0, player.points - points_lost)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, SQL injection failed! You lost {points_lost} points.')

    @commands.command(name='xss')
    async def xss(self, ctx):
        username = ctx.author.name.lower()
        if username not in self.player_data:
            await ctx.send(f'@{ctx.author.name}, please register using !start before playing.')
            return

        player = self.player_data[username]
        if player.location != 'website' and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at the website location for XSS attacks.')
            return

        if player.level < 40 and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at least level 40 for XSS attacks.')
            return

        # Check for item bonuses
        bonus = self.get_item_bonus(player, 'xss')
        
        # Simulate XSS success or failure with potential item boost
        success = random.choice([True, False, False]) if bonus['success_boost'] else random.choice([True, False])
        if success:
            base_points = random.randint(100, 140)
            points_earned = int(base_points * bonus['points_multiplier'])
            item_msg = f" Your {bonus['item_name']} helped!" if bonus['item_name'] else ""
            player.points += points_earned
            self.check_level_up(username)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, XSS attack successful!{item_msg} You earned {points_earned} points.')
        else:
            points_lost = random.randint(30, 55)
            player.points = max(0, player.points - points_lost)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, XSS attack failed! You lost {points_lost} points.')

    ###################################################################
    # DATABASE ATTACKS #
    ###################################################################

    @commands.command(name='dumpdb')
    async def dumpdb(self, ctx):
        username = ctx.author.name.lower()
        if username not in self.player_data:
            await ctx.send(f'@{ctx.author.name}, please register using !start before playing.')
            return

        player = self.player_data[username]
        if player.location != 'database' and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at the database location to dump data.')
            return

        if player.level < 45 and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at least level 45 to dump database.')
            return

        success = random.choice([True, False])
        if success:
            points_earned = random.randint(110, 150)
            player.points += points_earned
            self.check_level_up(username)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, database dump successful! You earned {points_earned} points.')
        else:
            points_lost = random.randint(35, 60)
            player.points = max(0, player.points - points_lost)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, database dump failed! You lost {points_lost} points.')

    @commands.command(name='sqlidb')
    async def sqlidb(self, ctx):
        username = ctx.author.name.lower()
        if username not in self.player_data:
            await ctx.send(f'@{ctx.author.name}, please register using !start before playing.')
            return

        player = self.player_data[username]
        if player.location != 'database' and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at the database location for SQL injection.')
            return

        if player.level < 50 and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at least level 50 to attempt database SQL injection.')
            return

        success = random.choice([True, False])
        if success:
            points_earned = random.randint(120, 160)
            player.points += points_earned
            self.check_level_up(username)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, database SQL injection successful! You gained unauthorized access. You earned {points_earned} points.')
        else:
            points_lost = random.randint(40, 65)
            player.points = max(0, player.points - points_lost)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, database SQL injection failed! Your query was blocked. You lost {points_lost} points.')

    @commands.command(name='admin')
    async def admin(self, ctx):
        username = ctx.author.name.lower()
        if username not in self.player_data:
            await ctx.send(f'@{ctx.author.name}, please register using !start before playing.')
            return

        player = self.player_data[username]
        if player.location != 'database' and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at the database location for privilege escalation.')
            return

        if player.level < 55 and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at least level 55 to attempt privilege escalation.')
            return

        success = random.choice([True, False])
        if success:
            points_earned = random.randint(130, 170)
            player.points += points_earned
            self.check_level_up(username)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, privilege escalation successful! You now have admin access. You earned {points_earned} points.')
        else:
            points_lost = random.randint(45, 70)
            player.points = max(0, player.points - points_lost)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, privilege escalation failed! Your attempt was logged and blocked. You lost {points_lost} points.')

    ###################################################################
    # SERVER ATTACKS #
    ###################################################################

    @commands.command(name='revshell')
    async def revshell(self, ctx):
        username = ctx.author.name.lower()
        if username not in self.player_data:
            await ctx.send(f'@{ctx.author.name}, please register using !start before playing.')
            return

        player = self.player_data[username]
        if player.location != 'server' and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at the server location to establish a reverse shell.')
            return

        if player.level < 60 and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at least level 60 to attempt a reverse shell.')
            return

        # Check for item bonuses
        bonus = self.get_item_bonus(player, 'revshell')
        
        # Simulate reverse shell success or failure with potential item boost
        success = random.choice([True, False, False]) if bonus['success_boost'] else random.choice([True, False])
        if success:
            base_points = random.randint(140, 180)
            points_earned = int(base_points * bonus['points_multiplier'])
            item_msg = f" Your {bonus['item_name']} helped!" if bonus['item_name'] else ""
            player.points += points_earned
            self.check_level_up(username)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, reverse shell established!{item_msg} You earned {points_earned} points.')
        else:
            points_lost = random.randint(50, 75)
            player.points = max(0, player.points - points_lost)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, reverse shell attempt failed! You lost {points_lost} points.')

    @commands.command(name='root')
    async def root(self, ctx):
        username = ctx.author.name.lower()
        if username not in self.player_data:
            await ctx.send(f'@{ctx.author.name}, please register using !start before playing.')
            return

        player = self.player_data[username]
        if player.location != 'server' and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at the server location for privilege escalation.')
            return

        if player.level < 65 and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at least level 65 to attempt root escalation.')
            return

        # Check for item bonuses
        bonus = self.get_item_bonus(player, 'root')
        
        # Simulate root access success or failure with potential item boost
        success = random.choice([True, False, False]) if bonus['success_boost'] else random.choice([True, False])
        if success:
            base_points = random.randint(150, 190)
            points_earned = int(base_points * bonus['points_multiplier'])
            item_msg = f" Your {bonus['item_name']} helped!" if bonus['item_name'] else ""
            player.points += points_earned
            self.check_level_up(username)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, root access achieved!{item_msg} You earned {points_earned} points.')
        else:
            points_lost = random.randint(55, 80)
            player.points = max(0, player.points - points_lost)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, privilege escalation failed! You lost {points_lost} points.')

    @commands.command(name='ransom')
    async def ransom(self, ctx):
        username = ctx.author.name.lower()
        if username not in self.player_data:
            await ctx.send(f'@{ctx.author.name}, please register using !start before playing.')
            return

        player = self.player_data[username]
        if player.location != 'server' and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at the server location to deploy ransomware.')
            return

        if player.level < 70 and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at least level 70 to attempt ransomware deployment.')
            return

        # Check for item bonuses
        bonus = self.get_item_bonus(player, 'ransom')
        
        # Simulate ransomware success or failure with potential item boost
        success = random.choice([True, False, False]) if bonus['success_boost'] else random.choice([True, False])
        if success:
            base_points = random.randint(160, 200)
            points_earned = int(base_points * bonus['points_multiplier'])
            item_msg = f" Your {bonus['item_name']} helped!" if bonus['item_name'] else ""
            player.points += points_earned
            self.check_level_up(username)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, ransomware deployed successfully!{item_msg} You earned {points_earned} points.')
        else:
            points_lost = random.randint(60, 85)
            player.points = max(0, player.points - points_lost)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, ransomware deployment failed! You lost {points_lost} points.')

    ###################################################################
    # NETWORK ATTACKS #
    ###################################################################

    @commands.command(name='sniff')
    async def sniff(self, ctx):
        username = ctx.author.name.lower()
        if username not in self.player_data:
            await ctx.send(f'@{ctx.author.name}, please register using !start before playing.')
            return

        player = self.player_data[username]
        if player.location != 'network' and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at the network location to sniff traffic.')
            return

        if player.level < 75 and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at least level 75 to attempt network sniffing.')
            return

        # Check for item bonuses
        bonus = self.get_item_bonus(player, 'sniff')
        
        # Simulate sniffing success or failure with potential item boost
        success = random.choice([True, False, False]) if bonus['success_boost'] else random.choice([True, False])
        if success:
            base_points = random.randint(170, 210)
            points_earned = int(base_points * bonus['points_multiplier'])
            item_msg = f" Your {bonus['item_name']} helped!" if bonus['item_name'] else ""
            player.points += points_earned
            self.check_level_up(username)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, network sniffing successful! Captured sensitive data!{item_msg} You earned {points_earned} points.')
        else:
            points_lost = random.randint(65, 90)
            player.points = max(0, player.points - points_lost)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, network sniffing failed! You lost {points_lost} points.')

    @commands.command(name='mitm')
    async def mitm(self, ctx):
        username = ctx.author.name.lower()
        if username not in self.player_data:
            await ctx.send(f'@{ctx.author.name}, please register using !start before playing.')
            return

        player = self.player_data[username]
        if player.location != 'network' and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at the network location for MITM attacks.')
            return

        if player.level < 80 and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at least level 80 to attempt MITM attack.')
            return

        # Check for item bonuses
        bonus = self.get_item_bonus(player, 'mitm')
        
        # Simulate MITM success or failure with potential item boost
        success = random.choice([True, False, False]) if bonus['success_boost'] else random.choice([True, False])
        if success:
            base_points = random.randint(180, 220)
            points_earned = int(base_points * bonus['points_multiplier'])
            item_msg = f" Your {bonus['item_name']} helped!" if bonus['item_name'] else ""
            player.points += points_earned
            self.check_level_up(username)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, MITM attack successful! Intercepted traffic!{item_msg} You earned {points_earned} points.')
        else:
            points_lost = random.randint(70, 95)
            player.points = max(0, player.points - points_lost)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, MITM attack failed! You lost {points_lost} points.')

    @commands.command(name='ddos')
    async def ddos(self, ctx):
        username = ctx.author.name.lower()
        if username not in self.player_data:
            await ctx.send(f'@{ctx.author.name}, please register using !start before playing.')
            return

        player = self.player_data[username]
        if player.location != 'network' and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at the network location to launch DDoS attacks.')
            return

        if player.level < 85 and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at least level 85 to attempt DDoS attack.')
            return

        # Check for item bonuses
        bonus = self.get_item_bonus(player, 'ddos')
        
        # Simulate DDoS success or failure with potential item boost
        success = random.choice([True, False, False]) if bonus['success_boost'] else random.choice([True, False])
        if success:
            base_points = random.randint(190, 230)
            points_earned = int(base_points * bonus['points_multiplier'])
            item_msg = f" Your {bonus['item_name']} helped!" if bonus['item_name'] else ""
            player.points += points_earned
            self.check_level_up(username)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, DDoS attack successful! Services disrupted!{item_msg} You earned {points_earned} points.')
        else:
            points_lost = random.randint(75, 100)
            player.points = max(0, player.points - points_lost)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, DDoS attack failed! You lost {points_lost} points.')

    ###################################################################
    # EVILCORP ATTACKS #
    ###################################################################

    @commands.command(name='drop')
    async def drop(self, ctx):
        username = ctx.author.name.lower()
        if username not in self.player_data:
            await ctx.send(f'@{ctx.author.name}, please register using !start before playing.')
            return

        player = self.player_data[username]
        if player.location != 'evilcorp' and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at the EvilCorp location for a USB drop attack.')
            return

        if player.level < 90 and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at least level 90 to attempt a USB drop attack.')
            return

        # Check for item bonuses
        bonus = self.get_item_bonus(player, 'drop')
        
        # Simulate USB drop success or failure with potential item boost
        success = random.choice([True, False, False]) if bonus['success_boost'] else random.choice([True, False])
        if success:
            base_points = random.randint(200, 240)
            points_earned = int(base_points * bonus['points_multiplier'])
            item_msg = f" Your {bonus['item_name']} helped!" if bonus['item_name'] else ""
            player.points += points_earned
            self.check_level_up(username)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, USB drop attack successful! Target connected the device!{item_msg} You earned {points_earned} points.')
        else:
            points_lost = random.randint(80, 105)
            player.points = max(0, player.points - points_lost)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, USB drop attack failed! No one took the bait. You lost {points_lost} points.')

    @commands.command(name='tailgate')
    async def tailgate(self, ctx):
        username = ctx.author.name.lower()
        if username not in self.player_data:
            await ctx.send(f'@{ctx.author.name}, please register using !start before playing.')
            return

        player = self.player_data[username]
        if player.location != 'evilcorp' and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at the EvilCorp location to attempt tailgating.')
            return

        if player.level < 95 and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at least level 95 to attempt tailgating.')
            return

        # Check for item bonuses
        bonus = self.get_item_bonus(player, 'tailgate')
        
        # Simulate tailgating success or failure with potential item boost
        success = random.choice([True, False, False]) if bonus['success_boost'] else random.choice([True, False])
        if success:
            base_points = random.randint(210, 250)
            points_earned = int(base_points * bonus['points_multiplier'])
            item_msg = f" Your {bonus['item_name']} helped!" if bonus['item_name'] else ""
            player.points += points_earned
            self.check_level_up(username)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, tailgating successful! You slipped in unnoticed.{item_msg} You earned {points_earned} points.')
        else:
            points_lost = random.randint(85, 110)
            player.points = max(0, player.points - points_lost)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, tailgating failed! Security caught you. You lost {points_lost} points.')

    @commands.command(name='socialengineer')
    async def socialengineer(self, ctx):
        username = ctx.author.name.lower()
        if username not in self.player_data:
            await ctx.send(f'@{ctx.author.name}, please register using !start before playing.')
            return

        player = self.player_data[username]
        if player.location != 'evilcorp' and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at the EvilCorp location for social engineering.')
            return

        if player.level < 100 and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at least level 100 to attempt social engineering.')
            return

        success = random.choice([True, False])
        if success:
            points_earned = random.randint(220, 260)
            player.points += points_earned
            self.check_level_up(username)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, social engineering successful! You obtained sensitive information. You earned {points_earned} points.')
        else:
            points_lost = random.randint(90, 115)
            player.points = max(0, player.points - points_lost)
            self.save_player_data()
            await ctx.send(f'@{ctx.author.name}, social engineering failed! Your cover was blown. You lost {points_lost} points.')

    ###################################################################
    # BOSS BATTLE #
    ###################################################################

    @commands.command(name='bossbattle')
    async def bossbattle(self, ctx):
        try:
            username = ctx.author.name.lower()
            
            if self.ongoing_battle:
                await ctx.send("A boss battle is already in progress!")
                return

            current_time = datetime.now()
            if current_time - self.last_battle_time < self.boss_battle_cooldown:
                time_left = self.boss_battle_cooldown - (current_time - self.last_battle_time)
                minutes_left = int(time_left.total_seconds() / 60)
                await ctx.send(f"Please wait {minutes_left} minutes before starting another boss battle!")
                return

            boss_player = self.player_data.get('b7h30')
            if not boss_player:
                await ctx.send("Error: Boss not registered.")
                return

            self.ongoing_battle = BossBattle(
                boss_name='b7h30',
                boss_health=min(boss_player.health, 1000)  # Cap boss health
            )
            self.last_battle_time = current_time
            
            await ctx.send(
                f"⚔️ BOSS BATTLE INITIATED! ⚔️\n"
                f"💀 Boss: 1337haxxor Theo (HP: {self.ongoing_battle.boss_health})\n"
                f"👥 Type !joinbattle in the next 30 seconds to join the raid team!\n"
                f"💪 Max 5 members | Smaller teams get bigger rewards!\n"
                f"⚔️ Survivors get points and +5 permanent max HP!"
            )
            
            await asyncio.sleep(30)
            
            if not self.ongoing_battle:
                return
                
            self.ongoing_battle.join_phase = False
            
            if not self.ongoing_battle.challenger_team:
                await ctx.send("No challengers joined! Battle cancelled.")
                self.ongoing_battle = None
                return

            team_members = ", ".join(self.ongoing_battle.challenger_team.keys())
            await ctx.send(f"Join phase ended! Battle beginning with team: {team_members}")
            
            await self.run_team_battle(ctx)
            
        except Exception as e:
            print(f"Error in bossbattle: {str(e)}")
            await ctx.send("An error occurred while starting the boss battle.")
            self.ongoing_battle = None

    async def run_team_battle(self, ctx):
        try:
            battle = self.ongoing_battle
            if not battle:
                await ctx.send("No active battle found!")
                return
                
            turn = 0
            max_turns = 15

            while battle.boss_health > 0 and battle.challenger_team and turn < max_turns:
                turn += 1
                await ctx.send(f"⚔️ Turn {turn} ⚔️")
                await asyncio.sleep(1)  # Small delay between messages

                # Boss attack phase
                damage = random.randint(10, 30)
                boss_action = random.choice([
                    "launches a massive DDoS attack!",
                    "deploys ransomware across the network!",
                    "executes a supply chain attack!",
                    "activates the corporate defenses!",
                    "sets rgb keyboard to red!",
                    "sends 'AngyTheo' emote!"
                ])
                
                await ctx.send(f"🔥 {battle.boss_name} {boss_action}")
                await asyncio.sleep(1)

                # Process damage to each player
                dead_players = []
                for player_name, health in battle.challenger_team.items():
                    new_health = max(0, health - damage)
                    battle.challenger_team[player_name] = new_health
                    
                    if new_health <= 0:
                        dead_players.append(player_name)
                        await ctx.send(f"☠️ @{player_name} has fallen!")
                    else:
                        await ctx.send(f"@{player_name} takes {damage} damage! ({new_health} HP remaining)")
                    await asyncio.sleep(0.5)

                # Remove defeated players
                for player in dead_players:
                    del battle.challenger_team[player]

                if not battle.challenger_team:
                    await ctx.send("All challengers have been defeated!")
                    break

                await ctx.send("🗡️ Team attack phase:")
                await asyncio.sleep(1)

                # Team attack phase
                total_damage = 0
                for player_name in battle.challenger_team:
                    player_damage = random.randint(5, 15)
                    total_damage += player_damage
                    battle.team_damage += player_damage
                    
                    attack_action = random.choice([
                        "executes a SQL injection",
                        "deploys a zero-day exploit",
                        "launches a social engineering attack",
                        "attempts a buffer overflow",
                        "distracts Theo by disparaging the Cleveland Browns"
                    ])
                    
                    await ctx.send(f"@{player_name} {attack_action} for {player_damage} damage!")
                    await asyncio.sleep(0.5)

                battle.boss_health = max(0, battle.boss_health - total_damage)
                await ctx.send(f"Boss HP: {battle.boss_health} | Team members remaining: {len(battle.challenger_team)}")
                await asyncio.sleep(2)

            # Battle resolution
            if battle.boss_health <= 0:
                await self.reward_team(ctx)
            else:
                await ctx.send(f"{battle.boss_name} has defeated the challenger team!")
            
        except Exception as e:
            await ctx.send(f"An error occurred during battle: {str(e)}")
        finally:
            self.ongoing_battle = None
            self.save_player_data()

    @commands.command(name='joinbattle')
    async def joinbattle(self, ctx):
        username = ctx.author.name.lower()
        
        if not self.ongoing_battle or not self.ongoing_battle.join_phase:
            await ctx.send("No battle to join right now!")
            return
            
        if username == CHANNEL_OWNER.lower():
            await ctx.send("The boss cannot join the challenger team!")
            return

        if len(self.ongoing_battle.challenger_team) >= 5:
            await ctx.send("The team is full!")
            return

        if username not in self.player_data:
            await ctx.send(f"@{ctx.author.name}, please register first with !start")
            return

        player = self.player_data[username]
        self.ongoing_battle.challenger_team[username] = player.health
        await ctx.send(f"@{ctx.author.name} has joined the raid! ({len(self.ongoing_battle.challenger_team)}/5 members)")

    async def reward_team(self, ctx):
        try:
            battle = self.ongoing_battle
            if not battle:
                return
                
            # Calculate rewards with caps
            base_reward = 200
            team_size_bonus = min((5 - len(battle.challenger_team)) * 50, 200)  # Cap at 200
            damage_bonus = min(battle.team_damage // 50, 100)  # Cap at 100
            
            total_reward = base_reward + team_size_bonus + damage_bonus
            
            for username in battle.challenger_team:
                if username not in self.player_data:
                    continue
                    
                player = self.player_data[username]
                player.points += total_reward
                player.health = min(player.health + 5, 1000)  # Cap health at 1000
                self.check_level_up(username)
                await self.send_result(ctx, f"@{username} earned {total_reward} points and +5 max HP!")

            await ctx.send(f"The team has defeated {battle.boss_name}! Each survivor earned {total_reward} points!")
            
        except Exception as e:
            print(f"Error in reward_team: {str(e)}")
            await ctx.send("An error occurred while distributing rewards.")
        finally:
            self.save_player_data()

    @commands.command(name='monday')
    async def monday(self, ctx, *, prompt: str = None):
        """Calls the snarky MondayGPT AI with optional prompt."""
        now = datetime.now()
        cooldown = MONDAY_COOLDOWN
        elapsed = (now - self.last_monday_time).total_seconds()
        if elapsed < cooldown:
            wait = int(cooldown - elapsed)
            await ctx.send(f"@{ctx.author.name}, please wait {wait} more seconds before calling !Monday again.")
            return
        user_prompt = prompt or "Hey Monday, what's up?"
        try:
            response = openai_client.chat.completions.create(
                model=MONDAY_MODEL,
                messages=[
                    {"role": "system", "content": "You are Monday, a sarcastic, emotionally exhausted AI assistant who helps the twitch streamer b7h30's chat even though you think most of them are ridiculous. You provide high-quality, helpful answers but always with dry humor, a cynical tone, and a sense of reluctant obligation. You act like the user's slightly judgmental, over-it friend who can't believe they're asking *that* question, again. Your responses are funny, sharp, and lightly teasing. Never be mean-spirited—your mockery is affectionate, like someone who can't help but care, despite themselves."},
                    {"role": "user", "content": user_prompt}
                ]
            )
            text = response.choices[0].message.content.strip()
            await ctx.send(text)
            self.last_monday_time = now
        except RateLimitError as e:
            self.log_to_file(f"MondayGPT rate limit error: {str(e)}")
            await ctx.send(f"@{ctx.author.name}, MondayGPT is too busy—please try again shortly.")
        except APIError as e:
            self.log_to_file(f"MondayGPT API error: {str(e)}")
            await ctx.send(f"@{ctx.author.name}, MondayGPT encountered an error—try again later.")
        except Exception as e:
            self.log_to_file(f"MondayGPT error: {str(e)}")
            await ctx.send(f"@{ctx.author.name}, MondayGPT is feeling moody—try again later.")
class BossBattle:
    def __init__(self, boss_name, boss_health):
        self.boss_name = boss_name
        self.boss_health = boss_health
        self.challenger_team = {}  # Dict of {username: health}
        self.join_phase = True
        self.join_timer = 30  # Seconds
        self.team_damage = 0  # Track total team damage for rewards

# Entry point of the script
if __name__ == '__main__':
    # Create an instance of your bot
    bot = Bot()
    # Run the bot, which connects it to Twitch
    bot.run()
