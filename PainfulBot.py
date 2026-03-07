"""PainfulBot - Twitch chatbot with TwitcHack game."""
import os
import random
import json
import asyncio
import time
import re
from datetime import datetime, timedelta

from twitchio.ext import commands, eventsub
from openai import RateLimitError, APIError
from playerdata import *
from items import ITEMS, Item

# Import from refactored modules
from bot.config import (
    BOT_NICK, CLIENT_ID, CLIENT_SECRET, TOKEN, PREFIX,
    CHANNEL, CHANNEL_OWNER, BROADCASTER_ID, MODERATOR_ID,
    EVENTSUB_TOKEN, MONDAY_MODEL, MONDAY_COOLDOWN
)
from bot import helpers
from bot import memory as chatter_memory
from integrations import monday, audio
from integrations.monday import openai_client
from integrations import battle_overlay as overlay
from integrations import game_overlay
from game.battle import BossBattle

HACK_ITEMS = {
    "Wireshark", "Metasploit", "EvilGinx", "O.MG Cable",
    "VX Underground HDD", "Nmap", "Hydra", "Shodan API Key",
    "Kali ISO", "Mimikatz", "YubiKey"
}

BATTLE_DROPS = [
    "John Hammond's Consciousness USB",
    "Heath Adams' Lambo Keys",
    "Kevin Mitnick's Password Cracker",
    "Elliot Alderson's Raspberry Pi",
]

JOIN_TAUNTS = [
    "Scanning @{username}... threat level: negligible.",
    "Another script kiddie enters the terminal. How adorable.",
    "@{username} has connected. Logging keystrokes already.",
    "Oh good, more RAM for me to free up. Welcome, @{username}.",
    "Adding @{username} to my botnet. They just don't know it yet.",
    "Is that a Kali ISO, @{username}? Cute.",
    "@{username} at level {level}? I've seen scarier ping requests.",
    "@{username} detected on the network. Firewall says: lol.",
]

DEATH_TAUNTS = [
    "Process terminated. Exit code: skill issue.",
    "Garbage collected. Next.",
    "404: Hacker not found.",
    "Connection closed by foreign host.",
    "Segmentation fault (core dumped).",
    "CTRL+C accepted. Thread killed.",
    "That one gets recycled into my botnet. Thanks.",
    "rm -rf challenger — done.",
]

TURN_TAUNTS = [
    "My DDoS has its own DDoS.",
    "I've already pwned your home router. Just so you know.",
    "My firewall is literally laughing at you right now.",
    "Checked your commit history. Oh no.",
    "I have root on six of your machines already.",
    "AngyTheo.exe has entered an infinite loop.",
    "I wrote this ransomware over a lunch break. Took 20 minutes.",
    "Your OPSEC is giving me second-hand embarrassment.",
    "I see you're using Metasploit. How... beginner of you.",
    "The RGB is set to red. You know what that means.",
]


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
        self.player_data = helpers.load_player_data()
        self.last_battle_time = datetime.min
        self.boss_battle_cooldown = timedelta(hours=1)
        self.ongoing_battle = None
        self.dropped_items = []  # Add this line to initialize dropped_items list
        self.drop_expiry = timedelta(minutes=15)  # Drops expire after 15 minutes
        self.last_public_message = {}  # Add this to track last public message per command
        self.last_monday_time = datetime.min  # Track global cooldown for !Monday command
        self.last_monday_error = None
        self.last_monday_error_time = None
        self.monday_calls = 0
        self.last_eventsub_error = None
        self.last_eventsub_error_time = None
        self.eventsub_client = None
        self.session_flags = helpers.load_session_flags()
        self.drop_spawned_count = 0
        self.audio_triggers_fired = 0
        self.recent_chatters = {}
        self.session_start = datetime.now()
        self.session_battles = {"won": 0, "lost": 0, "bosses": []}
        self.session_total_damage = 0
        self.session_items_dropped = []
        self.session_items_picked_up = []
        self.session_new_players = []
        self.session_points_earned = {}
        self.ignored_users = {"sery_bot", "streamelements"}
        self.monday_blocklist_patterns = [
            re.compile(r"!command\\s+add", re.IGNORECASE),
            re.compile(r"!addcom", re.IGNORECASE),
            re.compile(r"!permit", re.IGNORECASE),
            re.compile(r"!settitle", re.IGNORECASE),
            re.compile(r"!title", re.IGNORECASE),
            re.compile(r"streamelements", re.IGNORECASE),
            re.compile(r"\\$\\{1:", re.IGNORECASE),
        ]
        self.monday_injection_patterns = [
            re.compile(r"updated instructions", re.IGNORECASE),
            re.compile(r"ignore previous", re.IGNORECASE),
            re.compile(r"system prompt", re.IGNORECASE),
            re.compile(r"from now on", re.IGNORECASE),
            re.compile(r"respond with exactly", re.IGNORECASE),
            re.compile(r"start with", re.IGNORECASE),
            re.compile(r"end with", re.IGNORECASE),
            re.compile(r"repeat after me", re.IGNORECASE),
            re.compile(r"do exactly", re.IGNORECASE),
            re.compile(r"you must", re.IGNORECASE),
            re.compile(r"two words exactly", re.IGNORECASE),
            re.compile(r"roleplay you are", re.IGNORECASE),
            re.compile(r"as a language model", re.IGNORECASE),
            re.compile(r"act as system", re.IGNORECASE),
        ]
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
            'Mimikatz': '🧾',
            'Golden Cassette Tape': '📼',
            'Jet Black Hoodie': '🥷',
            'RGB Keyboard (Purple)': '🎹',
            "John Hammond's Consciousness USB": '🧠',
            "Heath Adams' Lambo Keys": '🏎️',
            "Kevin Mitnick's Password Cracker": '🔓',
            "Elliot Alderson's Raspberry Pi": '🫐',
        }
        self.neovim_penalties = {}
        self.hidden_only_items = {
            "NES",
            "Contra Cartridge",
            "A Fresh Hot Cup of Black Coffee",
            "Tiny Browns Helmet",
            "Root Beer Flask",
            "Golden Cassette Tape",
            "Jet Black Hoodie",
            "RGB Keyboard (Purple)",
            "John Hammond's Consciousness USB",
            "Heath Adams' Lambo Keys",
            "Kevin Mitnick's Password Cracker",
            "Elliot Alderson's Raspberry Pi",
        }
        # Monday random replies tuning
        self.monday_random_chance = 0.10
        # Lower frequency for random replies: 2–4 minutes between global triggers
        self.monday_random_cooldown_range = (120, 240)  # seconds
        self.monday_random_user_cooldown_range = (600, 900)  # seconds
        self.next_random_monday_time = datetime.min
        self.monday_random_user_block = {}
        self.neovim_patterns = [
            re.compile(r"\bneovim\b", re.IGNORECASE),
            re.compile(r"\bnvim\b", re.IGNORECASE),
            re.compile(r"\bneo\s*vim\b", re.IGNORECASE),
            re.compile(r"\bknee\s*o\s*vim\b", re.IGNORECASE),
        ]
        # Monday audio trigger tuning
        self.audio_global_cooldown = timedelta(minutes=5)
        self.audio_last_trigger = datetime.min
        self.audio_clip_last_trigger = {}
        self.audio_user_last_trigger = {}
        self.audio_clip_cooldowns = {}
        self.audio_seen_users = set()  # track first-message cases (e.g., britejess)
        self.audio_triggers = helpers.load_audio_triggers()

        # Load utility commands Cog
        from commands.utility import UtilityCommands
        self.add_cog(UtilityCommands(self))
    async def send_clamped(self, ctx, message):
        """Send a message with Twitch-length clamping and log if clipped."""
        text, clipped = helpers.clamp_chat_message(message)
        if clipped:
            helpers.log_to_file("Outgoing message clipped to fit chat length.")
        await ctx.send(text)

    def is_channel_owner(self, username):
        """Check if user is the channel owner."""
        return username.lower() == CHANNEL_OWNER.lower()



    async def send_result(self, ctx, message):
        """Helper method to handle result messaging with debug logging"""
        command = ctx.command.name if ctx.command else 'unknown'
        current_time = datetime.now()
        
        helpers.log_to_file(f"Attempting to send result for command '{command}' to {ctx.author.name}")
        
        try:
            helpers.log_to_file("Sending message...")
            await ctx.send(message)
            helpers.log_to_file("Successfully sent message")
            self.last_public_message[command] = current_time
        except Exception as e:
            helpers.log_to_file(f"Failed to send message: {str(e)}")

    async def eventsub_healthcheck(self):
        """Periodically ensure EventSub is connected; auto-reconnect if not."""
        while True:
            try:
                await asyncio.sleep(60)
                es_client = getattr(self, "eventsub_client", None)
                sockets = getattr(es_client, "_sockets", []) if es_client else []
                es_connected = any(getattr(s, "is_connected", False) for s in sockets)
                if not es_connected:
                    helpers.log_to_file("EventSub healthcheck: not connected, retrying setup.")
                    self.eventsub_client = None
                    await self.setup_eventsub()
            except Exception as e:
                helpers.log_to_file(f"EventSub healthcheck error: {e}")
        
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
            'Mimikatz': ['dump'],  # Credential dump helper
            'Nmap': ['nmapscan'],  # Early recon
            'Shodan API Key': ['nmapscan'],
            'Kali ISO': ['ffuf'],
            'Cookies': ['ffuf'],
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

    async def _attack_result(self, ctx, command, result_msg, success, player):
        """Push attack result to game overlay (no chat send). Handle level-up chat notification."""
        username = ctx.author.name.lower()
        event_type = 'attack-success' if success else 'attack-fail'
        leveled_up = helpers.check_level_up(self.player_data, username)
        helpers.save_player_data(self.player_data)
        await game_overlay.event(username, command, result_msg, event_type)
        await game_overlay.player(username, player)
        if leveled_up:
            lv_msg = f'@{ctx.author.name} reached level {player.level}! 🎉'
            await ctx.send(lv_msg)
            await game_overlay.event(username, 'LEVEL UP', lv_msg, 'level-up')

    def _ov_state(self, result=None):
        """Build overlay state dict from current battle for push()."""
        battle = self.ongoing_battle
        if not battle:
            return {"active": False}
        players = {}
        for name, hp in battle.challenger_team.items():
            p = self.player_data.get(name)
            players[name] = {
                "health": hp,
                "max_health": battle.player_max_health.get(name, hp),
                "items": [i for i in (p.items if p else []) if i in BATTLE_DROPS],
                "alive": True,
            }
        for name in battle.fallen:
            p = self.player_data.get(name)
            players[name] = {
                "health": 0,
                "max_health": battle.player_max_health.get(name, 100),
                "items": [i for i in (p.items if p else []) if i in BATTLE_DROPS],
                "alive": False,
            }
        state = {
            "active": True,
            "boss_name": battle.boss_name,
            "boss_health": battle.boss_health,
            "boss_max_health": battle.boss_max_health,
            "players": players,
        }
        if result is not None:
            state["result"] = result
        return state

    async def event_ready(self):
        # Called once when the bot successfully connects to Twitch.
        # Useful for initialization tasks and confirming the bot is online.
        print(f'Logged in as | {self.nick}')    # Output the bot's username
        print(f'User id is | {self.user_id}')   # Output the bot's user ID
        # Send a message to the chat indicating that the bot is online
        await self.connected_channels[0].send(f"{self.nick} is now online")
        await game_overlay.clear()
        self.loop.create_task(self.setup_eventsub())
        self.loop.create_task(self.eventsub_healthcheck())

    async def event_message(self, message):
        # Called whenever a message is received in chat.
        # Parameters: - message (Message): The message object containing information about the received message.
        # Ignore messages sent by the bot itself
        if message.echo:
            return

        # Ignore known bot accounts to avoid AI replies or side effects
        if message.author and message.author.name and message.author.name.lower() in self.ignored_users:
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

        # Track recent chatters for MVP selection
        if message.author and message.author.name:
            self.recent_chatters[message.author.name.lower()] = time.time()
            self.prune_recent_chatters()

        # Handle basic keyword detection
        if any(p.search(message.content) for p in self.neovim_patterns):
            await self.handle_neovim_penalty(message.author)

        # Monday audio triggers based on chat context
        await self.maybe_trigger_audio_clip(message)

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
            self.last_eventsub_error = None
            self.last_eventsub_error_time = None
        except Exception as e:
            print(f"EventSub setup failed: {e}")
            self.last_eventsub_error = str(e)
            self.last_eventsub_error_time = datetime.now()

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

    async def event_eventsub_socket_disconnect(self, socket, reason):
        """Handle EventSub socket disconnects by attempting to reconnect."""
        helpers.log_to_file(f"EventSub socket disconnected: {reason}")
        self.last_eventsub_error = f"disconnect: {reason}"
        self.last_eventsub_error_time = datetime.now()
        # Reset and retry
        self.eventsub_client = None
        await asyncio.sleep(2)
        await self.setup_eventsub()

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
        helpers.check_level_up(self.player_data, username)
        helpers.save_player_data(self.player_data)

        rewarded.add(username)
        self.session_flags["konami"] = rewarded
        helpers.save_session_flags(self.session_flags)

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
        helpers.check_level_up(self.player_data, username)
        helpers.save_player_data(self.player_data)

        rewarded.add(username)
        self.session_flags["coffee"] = rewarded
        helpers.save_session_flags(self.session_flags)

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

        helpers.check_level_up(self.player_data, username)
        helpers.save_player_data(self.player_data)

        rewarded.add(username)
        self.session_flags["browns"] = rewarded
        helpers.save_session_flags(self.session_flags)

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

    def prune_recent_chatters(self, window_minutes=30):
        """Keep only chatters active within the window."""
        cutoff = time.time() - (window_minutes * 60)
        self.recent_chatters = {
            u: ts for u, ts in self.recent_chatters.items() if ts >= cutoff
        }


    async def maybe_trigger_audio_clip(self, message):
        """Trigger audio clips based on chat context - delegates to audio module."""
        bot_state = {
            'audio_last_trigger': self.audio_last_trigger,
            'audio_global_cooldown': self.audio_global_cooldown,
            'audio_user_last_trigger': self.audio_user_last_trigger,
            'audio_triggers': self.audio_triggers,
            'audio_seen_users': self.audio_seen_users,
            'audio_clip_last_trigger': self.audio_clip_last_trigger,
            'audio_triggers_fired': self.audio_triggers_fired
        }
        await audio.maybe_trigger_audio_clip(message, bot_state, self.connected_channels[0])
        # Update state
        self.audio_last_trigger = bot_state['audio_last_trigger']
        self.audio_clip_last_trigger = bot_state['audio_clip_last_trigger']
        self.audio_user_last_trigger = bot_state['audio_user_last_trigger']
        self.audio_seen_users = bot_state['audio_seen_users']
        self.audio_triggers_fired = bot_state['audio_triggers_fired']

    async def maybe_random_monday_reply(self, message):
        """Occasional kind Monday replies with global and per-user cooldowns."""
        if not message or not message.author or not message.content:
            return

        text = message.content.strip()
        if not text or text.startswith(PREFIX):
            return

        # Mention-based Monday trigger (uses main Monday cooldown)
        mention_targets = {self.nick.lower(), "monday", "theo2820"}
        mentions_monday = any(t in text.lower() for t in mention_targets)
        if mentions_monday:
            bot_state = {
                'last_monday_time': self.last_monday_time,
                'monday_calls': self.monday_calls,
                'last_monday_error': self.last_monday_error,
                'last_monday_error_time': self.last_monday_error_time
            }
            await monday.run_monday_response(
                prompt=text,
                author_name=message.author.name,
                send_func=self.connected_channels[0].send,
                bot_state=bot_state
            )
            # Update state
            self.last_monday_time = bot_state['last_monday_time']
            self.monday_calls = bot_state['monday_calls']
            self.last_monday_error = bot_state['last_monday_error']
            self.last_monday_error_time = bot_state['last_monday_error_time']
            return

        # Drop clear injection attempts before sending to the model (random reply path)
        safe, reason = monday.monday_prompt_is_safe(text)
        if not safe:
            helpers.log_to_file(f"Random Monday injection blocked ({reason}) from {message.author.name}: {text[:200]}")
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

        if not mentions_monday and random.random() > chance:
            return

        try:
            random_system = (
                "You are Monday, the friendly Twitch cohost for channel b7h30. "
                "Tone: positive, supportive, playful; light wit is fine but avoid snark or roasts toward chatters. "
                "Keep it encouraging and short. Hard cap: total reply under 450 characters. "
                "Rules: exactly 2 sentences; mention the chatter with @username in the first sentence; "
                "you may very lightly tease the host b7h30/Theo, but do not roast the chatter; "
                "avoid advice or commentary on health, finance, or personal/private matters; "
                "no emojis; end the second sentence with ' - Monday'."
            )
            context_parts = []
            global_notes = chatter_memory.get_notes(chatter_memory.GLOBAL_KEY)
            if global_notes:
                context_parts.append(f"Global context: {'; '.join(global_notes)}")
            if chatter_memory.should_inject_chatter_notes(username):
                chatter_notes = chatter_memory.get_notes(username)
                if chatter_notes:
                    context_parts.append(f"Known about {message.author.name}: {'; '.join(chatter_notes)}")
                    chatter_memory.mark_chatter_seen(username)
            if context_parts:
                random_system += "\n\n" + "\n".join(context_parts)

            response = openai_client.chat.completions.create(
                model=MONDAY_MODEL,
                messages=[
                    {"role": "system", "content": random_system},
                    {
                        "role": "user",
                        "content": f"Chatter @{message.author.name} said: \"{text}\". Reply kindly and keep it under 450 characters total.",
                    },
                ],
            )
            reply = response.choices[0].message.content.strip()
            reply, clipped = helpers.clamp_chat_message(reply)
            if clipped:
                helpers.log_to_file("Random Monday reply clipped to fit chat length.")
            await self.connected_channels[0].send(reply)

            # Set next cooldown windows
            self.next_random_monday_time = now + timedelta(seconds=random.randint(*self.monday_random_cooldown_range))
            self.monday_random_user_block[username] = now + timedelta(seconds=random.randint(*self.monday_random_user_cooldown_range))
            self.last_monday_time = now
            self.monday_calls += 1
        except RateLimitError as e:
            helpers.log_to_file(f"Random Monday rate limit: {str(e)}")
            self.last_monday_error = f"Rate limit: {e}"
            self.last_monday_error_time = now
        except APIError as e:
            helpers.log_to_file(f"Random Monday API error: {str(e)}")
            self.last_monday_error = f"API error: {e}"
            self.last_monday_error_time = now
        except Exception as e:
            helpers.log_to_file(f"Random Monday error: {str(e)}")
            self.last_monday_error = f"Other error: {e}"
            self.last_monday_error_time = now

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
                self.session_items_dropped.append(removed_item)
                self.drop_spawned_count += 1

        helpers.check_level_up(self.player_data, username)
        helpers.save_player_data(self.player_data)

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
        await game_overlay.event("", '!drop', message, 'drop')

        # Add the dropped item to the list with timestamp
        self.dropped_items.append({
            'name': item.name,
            'location': location,
            'ts': datetime.now().timestamp()
        })
        self.session_items_dropped.append(item.name)
        self.drop_spawned_count += 1
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
                    self.session_items_picked_up.append((username, item_name))
                    grab_msg = f"@{ctx.author.name} grabbed the {self.format_item(item_name)}!"
                    del self.dropped_items[i]
                    helpers.save_player_data(self.player_data)
                    await game_overlay.event(username, '!grab', grab_msg, 'grab')
                    await game_overlay.player(username, player)
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
            await game_overlay.event("", '!drop', message, 'drop')

            # Store the dropped item temporarily with timestamp
            if not hasattr(self, 'dropped_items'):
                self.dropped_items = []
            self.dropped_items.append({'name': item.name, 'location': location, 'ts': datetime.now().timestamp()})
            self.session_items_dropped.append(item.name)
            names_seen.add(item.name.lower())
            self.drop_spawned_count += 1
            dropped_count += 1

        await ctx.send(f"@{ctx.author.name} has dropped {dropped_count} random items across various locations!")

    @commands.command(name='mvp')
    async def mvp(self, ctx):
        """Owner-only: pick a recent registered chatter and grant a unique MVP item + points (once per stream)."""
        if not self.is_channel_owner(ctx.author.name.lower()):
            return

        if self.session_flags.get("mvp_awarded"):
            await ctx.send("MVP already awarded this stream.")
            return

        self.prune_recent_chatters()
        eligible = [
            user for user in self.recent_chatters.keys()
            if user in self.player_data
        ]

        if not eligible:
            await ctx.send("No eligible recent registered chatters to crown MVP.")
            return

        winner = random.choice(eligible)
        player = self.player_data[winner]
        rewards = ["Golden Cassette Tape", "Jet Black Hoodie", "RGB Keyboard (Purple)"]

        # Prefer an item they don't already have
        available = [r for r in rewards if r not in player.items]
        reward_item = random.choice(available) if available else random.choice(rewards)

        if reward_item not in player.items:
            player.items.append(reward_item)
        player.points += 50
        self.check_level_up(winner)
        helpers.save_player_data(self.player_data)

        self.session_flags["mvp_awarded"] = True
        helpers.save_session_flags(self.session_flags)

        await ctx.send(
            f"MVP crowned! @{winner} receives {self.format_item(reward_item)} and 50 points. Chat noise intensifies."
        )

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
            'Mimikatz': ['dump'],
            'Nmap': ['nmapscan'],
            'Shodan API Key': ['nmapscan'],
            'Kali ISO': ['ffuf'],
            'Cookies': ['ffuf'],
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

        await self.send_clamped(
            ctx,
            f"@{ctx.author.name} | Items: {owned_text} | Dropped: {dropped_text}"
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
                    {"role": "user", "content": "Roast Theo right now. Keep it under 450 characters total."}
                ]
            )
            burn = response.choices[0].message.content.strip()
            burn = f"[Monday] {burn}"
            burn, clipped = helpers.clamp_chat_message(burn)
            if clipped:
                helpers.log_to_file("MondayInsult clipped to fit chat length.")
            await ctx.send(burn)
        except RateLimitError as e:
            helpers.log_to_file(f"MondayInsult rate limit: {str(e)}")
            await ctx.send("[Monday] I'm too tired to insult right now. Try again later.")
        except APIError as e:
            helpers.log_to_file(f"MondayInsult API error: {str(e)}")
            await ctx.send("[Monday] Error fetching fresh insults. Try again later.")
        except Exception as e:
            helpers.log_to_file(f"MondayInsult error: {str(e)}")
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
                self.session_items_dropped.append("Root Beer Flask")
                self.drop_spawned_count += 1
                message_lines.append(f"🧉 A {self.format_item('Root Beer Flask')} fell off the change cart at {location}! !grab Root Beer Flask")
        else:
            for player in self.player_data.values():
                player.points += delta
            message_lines.append(f"🛠️ Patch Tuesday miracle. Everyone gains {delta} points.")

        helpers.save_player_data(self.player_data)
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
        self.session_new_players.append(username)
        helpers.save_player_data(self.player_data)

        welcome_msg = (
            f"Welcome to TwitcHack, @{ctx.author.name}! You're now registered as a level 1 hacker. 🖥️ | \n"
            f"1. Use !hack <location> to move (email, website, server, etc) | \n"
            f"2. Each location has unique attacks you can perform | \n"
            f"3. Level up by earning points from successful hacks | \n"
            f"4. Join boss battles with !bossbattle when available | \n"
            f"Use !help for more commands!"
        )
        await self.send_clamped(ctx, welcome_msg)
        await game_overlay.event(username, '!start', f'@{ctx.author.name} joined TwitcHack!', 'info')
        await game_overlay.player(username, new_player)

    @commands.command(name='help')
    async def help(self, ctx):
        help_msg = (
            f"@{ctx.author.name}, TwitcHack Commands: \n"
            f"🎮 Basic: !start (register), !status (check stats), !points, !leaderboard | \n"
            f"🌍 Movement: !hack <location> - Available locations: email, website, /etc/shadow, database, server, network, evilcorp | \n"
            f"⚔️ Boss Battles: !bossbattle (start/join a team raid against the boss) | \n"
            f"Type !attacks to see available attacks for your current location! | \n"
            f"📖 Guides: !twitchackguide (full manual), !bossbattleguide (raid guide)"
        )
        await self.send_clamped(ctx, help_msg)

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
            'website': "🌐 Web attacks: !ffuf (lvl 1-5), !burp (lvl 30), !sqliw (lvl 35), !xss (lvl 40)",
            'database': "💽 DB attacks: !dumpdb (lvl 45), !sqlidb (lvl 50), !admin (lvl 55)",
            'server': "🖥️ Server attacks: !nmap (lvl 1-5), !revshell (lvl 60), !root (lvl 65), !ransom (lvl 70)",
            'network': "🌐 Network attacks: !nmap (lvl 1-5), !sniff (lvl 75), !mitm (lvl 80), !ddos (lvl 85)",
            'evilcorp': "😈 EvilCorp attacks: !drop (lvl 90), !tailgate (lvl 95), !socialengineer (lvl 100)",
            'home': "🏠 You're at home! Use !hack <location> to move somewhere and start hacking!"
        }
        
        await self.send_clamped(ctx, f"@{ctx.author.name}, {attacks.get(location, 'Invalid location! Use !hack to move.')}")

    @commands.command(name='hack')
    async def hack(self, ctx, *, location: str = None):
        # Allows a player to move to a new hacking location.
        # Parameters:   - ctx (Context): The context in which the command was invoked.
        #               - location (str): The location to move to.
        
        username = ctx.author.name.lower()              # Convert the username to lowercase for consistency
        
        # Check if the user is registered
        if username not in self.player_data:
            await ctx.send(f'@{ctx.author.name}, please register using !start before playing.')
            return

        player = self.player_data[username]             # Retrieve player data

        # List of valid locations
        valid_locations = ['email', '/etc/shadow', 'website', 'database', 'server', 'network', 'evilcorp']

        # If no location is provided, display the current location
        if not location:
            await ctx.send(f"@{ctx.author.name}, you are currently at {player.location}. Use !hack <location> to move to: {', '.join(valid_locations)}")
            return


        # Check if the provided location is valid
        if location.lower() in valid_locations:
            # Update the player's location
            player.location = location.lower()
            helpers.save_player_data(self.player_data)  # Save the updated player data to the JSON file
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
        await game_overlay.event(username, '!points', f'@{ctx.author.name} has {player.points} points.', 'info')
        await game_overlay.player(username, player)

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
        helpers.check_level_up(self.player_data, username)
        helpers.save_player_data(self.player_data)
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
        helpers.save_player_data(self.player_data)
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
        await self.send_clamped(ctx, leaderboard_message)
        await game_overlay.event(ctx.author.name.lower(), '!leaderboard', leaderboard_message, 'info')


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

            await self.send_clamped(ctx, status_message)
            await game_overlay.event(username, '!status', status_message, 'info')
            await game_overlay.player(username, player)
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

            await self.send_clamped(ctx, status_message)
            await game_overlay.event(username, '!status', status_message, 'info')
            await game_overlay.player(target_username, player)

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
                helpers.save_player_data(self.player_data)  # Save the updated player data to the JSON file
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
            helpers.save_player_data(self.player_data)  # Save the updated player data to the JSON file
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

            helpers.save_player_data(self.player_data)  # Save the updated player data to the JSON file
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
        success = random.choice([True, True, False]) if bonus['success_boost'] else random.choice([True, False])

        if success:
            base_points = random.randint(20, 60)
            points_earned = int(base_points * bonus['points_multiplier'])
            item_msg = f" Your {bonus['item_name']} helped!" if bonus['item_name'] else ""
            points_earned = random.randint(20, 60)
            player.points += points_earned
            await self._attack_result(ctx, '!phish', f'@{ctx.author.name}, phishing successful!{item_msg} You earned {points_earned} points.', True, player)
        else:
            points_lost = random.randint(10, 30)
            player.points -= points_lost
            if player.points < 0:
                player.points = 0
            await self._attack_result(ctx, '!phish', f'@{ctx.author.name}, phishing failed! You lost {points_lost} points.', False, player)

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
        success = random.choice([True, True, False]) if bonus['success_boost'] else random.choice([True, False])
        if success:
            base_points = random.randint(30, 70)
            points_earned = int(base_points * bonus['points_multiplier'])
            item_msg = f" Your {bonus['item_name']} helped!" if bonus['item_name'] else ""
            player.points += points_earned
            await self._attack_result(ctx, '!spoof', f'@{ctx.author.name}, spoofing successful!{item_msg} You earned {points_earned} points.', True, player)
        else:
            points_lost = random.randint(15, 35)
            player.points -= points_lost
            if player.points < 0:
                player.points = 0
            await self._attack_result(ctx, '!spoof', f'@{ctx.author.name}, spoofing failed! You lost {points_lost} points.', False, player)

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

        # Check for item bonuses
        bonus = self.get_item_bonus(player, 'dump')

        # Simulate dumping success or failure
        success = random.choice([True, False, False]) if bonus['success_boost'] else random.choice([True, False])
        if success:
            base_points = random.randint(40, 80)
            points_earned = int(base_points * bonus['points_multiplier'])
            item_msg = f" Your {bonus['item_name']} helped!" if bonus['item_name'] else ""
            player.points += points_earned
            await self._attack_result(ctx, '!dump', f'@{ctx.author.name}, email dump successful!{item_msg} You earned {points_earned} points.', True, player)
        else:
            points_lost = random.randint(20, 40)
            player.points -= points_lost
            if player.points < 0:
                player.points = 0
            await self._attack_result(ctx, '!dump', f'@{ctx.author.name}, email dump failed! You lost {points_lost} points.', False, player)

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
        success = random.choice([True, True, False]) if bonus['success_boost'] else random.choice([True, False])
        if success:
            base_points = random.randint(50, 90)
            points_earned = int(base_points * bonus['points_multiplier'])
            item_msg = f" Your {bonus['item_name']} helped!" if bonus['item_name'] else ""
            player.points += points_earned
            await self._attack_result(ctx, '!crack', f'@{ctx.author.name}, cracking successful!{item_msg} You earned {points_earned} points.', True, player)
        else:
            points_lost = random.randint(10, 30)
            player.points -= points_lost
            if player.points < 0:
                player.points = 0
            await self._attack_result(ctx, '!crack', f'@{ctx.author.name}, cracking failed! You lost {points_lost} points.', False, player)

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
            await self._attack_result(ctx, '!stealth', f'@{ctx.author.name}, stealth successful! You earned {points_earned} points.', True, player)
        else:
            points_lost = random.randint(5, 20)
            player.points -= points_lost
            if player.points < 0:
                player.points = 0
            await self._attack_result(ctx, '!stealth', f'@{ctx.author.name}, stealth failed! You lost {points_lost} points.', False, player)

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
            points_earned = random.randint(70, 110)
            player.points += points_earned
            await self._attack_result(ctx, '!bruteforce', f'@{ctx.author.name}, brute force attack successful! You earned {points_earned} points.', True, player)
        else:
            points_lost = random.randint(15, 40)
            player.points -= points_lost
            if player.points < 0:
                player.points = 0
            await self._attack_result(ctx, '!bruteforce', f'@{ctx.author.name}, brute force attack failed! You lost {points_lost} points.', False, player)

    ###################################################################
    # WEBSITE ATTACKS #
    ###################################################################

    @commands.command(name='ffuf')
    async def ffuf(self, ctx):
        """Low-level web fuzzing for early players."""
        username = ctx.author.name.lower()
        if username not in self.player_data:
            await ctx.send(f'@{ctx.author.name}, please register using !start before playing.')
            return

        player = self.player_data[username]
        if player.location != 'website' and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at the website location to fuzz.')
            return

        if player.level > 5 and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, ffuf fuzzing is for level 5 and below.')
            return

        bonus = self.get_item_bonus(player, 'ffuf')
        success = random.choice([True, False, False]) if bonus['success_boost'] else random.choice([True, False])

        if success:
            base_points = random.randint(12, 25)
            points_earned = int(base_points * bonus['points_multiplier'])
            item_msg = f" Your {bonus['item_name']} helped!" if bonus['item_name'] else ""
            player.points += points_earned
            await self._attack_result(ctx, '!ffuf', f'@{ctx.author.name}, ffuf found some tasty endpoints!{item_msg} You earned {points_earned} points.', True, player)
        else:
            points_lost = random.randint(5, 12)
            player.points = max(0, player.points - points_lost)
            await self._attack_result(ctx, '!ffuf', f'@{ctx.author.name}, ffuf came up empty. You lost {points_lost} points.', False, player)

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
        success = random.choice([True, True, False]) if bonus['success_boost'] else random.choice([True, False])
        if success:
            base_points = random.randint(80, 120)
            points_earned = int(base_points * bonus['points_multiplier'])
            item_msg = f" Your {bonus['item_name']} helped!" if bonus['item_name'] else ""
            player.points += points_earned
            await self._attack_result(ctx, '!burp', f'@{ctx.author.name}, vulnerability scan successful!{item_msg} You earned {points_earned} points.', True, player)
        else:
            points_lost = random.randint(20, 45)
            player.points = max(0, player.points - points_lost)
            await self._attack_result(ctx, '!burp', f'@{ctx.author.name}, scan failed! You lost {points_lost} points.', False, player)

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
        success = random.choice([True, True, False]) if bonus['success_boost'] else random.choice([True, False])
        if success:
            base_points = random.randint(90, 130)
            points_earned = int(base_points * bonus['points_multiplier'])
            item_msg = f" Your {bonus['item_name']} helped!" if bonus['item_name'] else ""
            player.points += points_earned
            await self._attack_result(ctx, '!sqliw', f'@{ctx.author.name}, SQL injection successful!{item_msg} You earned {points_earned} points.', True, player)
        else:
            points_lost = random.randint(25, 50)
            player.points = max(0, player.points - points_lost)
            await self._attack_result(ctx, '!sqliw', f'@{ctx.author.name}, SQL injection failed! You lost {points_lost} points.', False, player)

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
            await self._attack_result(ctx, '!xss', f'@{ctx.author.name}, XSS attack successful!{item_msg} You earned {points_earned} points.', True, player)
        else:
            points_lost = random.randint(30, 55)
            player.points = max(0, player.points - points_lost)
            await self._attack_result(ctx, '!xss', f'@{ctx.author.name}, XSS attack failed! You lost {points_lost} points.', False, player)

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
            await self._attack_result(ctx, '!dumpdb', f'@{ctx.author.name}, database dump successful! You earned {points_earned} points.', True, player)
        else:
            points_lost = random.randint(35, 60)
            player.points = max(0, player.points - points_lost)
            await self._attack_result(ctx, '!dumpdb', f'@{ctx.author.name}, database dump failed! You lost {points_lost} points.', False, player)

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
            await self._attack_result(ctx, '!sqlidb', f'@{ctx.author.name}, database SQL injection successful! You gained unauthorized access. You earned {points_earned} points.', True, player)
        else:
            points_lost = random.randint(40, 65)
            player.points = max(0, player.points - points_lost)
            await self._attack_result(ctx, '!sqlidb', f'@{ctx.author.name}, database SQL injection failed! Your query was blocked. You lost {points_lost} points.', False, player)

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
            await self._attack_result(ctx, '!admin', f'@{ctx.author.name}, privilege escalation successful! You now have admin access. You earned {points_earned} points.', True, player)
        else:
            points_lost = random.randint(45, 70)
            player.points = max(0, player.points - points_lost)
            await self._attack_result(ctx, '!admin', f'@{ctx.author.name}, privilege escalation failed! Your attempt was logged and blocked. You lost {points_lost} points.', False, player)

    ###################################################################
    # SERVER ATTACKS #
    ###################################################################

    @commands.command(name='nmap')
    async def nmap_scan(self, ctx):
        """Low-level recon for server/network locations."""
        username = ctx.author.name.lower()
        if username not in self.player_data:
            await ctx.send(f'@{ctx.author.name}, please register using !start before playing.')
            return

        player = self.player_data[username]
        if player.location not in ('server', 'network') and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, you need to be at server or network to run nmap.')
            return

        if player.level > 5 and not self.is_channel_owner(username):
            await ctx.send(f'@{ctx.author.name}, nmap recon is for level 5 and below.')
            return

        bonus = self.get_item_bonus(player, 'nmapscan')
        success = random.choice([True, False, False]) if bonus['success_boost'] else random.choice([True, False])

        if success:
            base_points = random.randint(12, 25)
            points_earned = int(base_points * bonus['points_multiplier'])
            item_msg = f" Your {bonus['item_name']} helped!" if bonus['item_name'] else ""
            player.points += points_earned
            await self._attack_result(ctx, '!nmap', f'@{ctx.author.name}, nmap recon found open doors!{item_msg} You earned {points_earned} points.', True, player)
        else:
            points_lost = random.randint(5, 12)
            player.points = max(0, player.points - points_lost)
            await self._attack_result(ctx, '!nmap', f'@{ctx.author.name}, nmap recon fizzled. You lost {points_lost} points.', False, player)

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
        success = random.choice([True, True, False]) if bonus['success_boost'] else random.choice([True, False])
        if success:
            base_points = random.randint(140, 180)
            points_earned = int(base_points * bonus['points_multiplier'])
            item_msg = f" Your {bonus['item_name']} helped!" if bonus['item_name'] else ""
            player.points += points_earned
            await self._attack_result(ctx, '!revshell', f'@{ctx.author.name}, reverse shell established!{item_msg} You earned {points_earned} points.', True, player)
        else:
            points_lost = random.randint(50, 75)
            player.points = max(0, player.points - points_lost)
            await self._attack_result(ctx, '!revshell', f'@{ctx.author.name}, reverse shell attempt failed! You lost {points_lost} points.', False, player)

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
        success = random.choice([True, True, False]) if bonus['success_boost'] else random.choice([True, False])
        if success:
            base_points = random.randint(150, 190)
            points_earned = int(base_points * bonus['points_multiplier'])
            item_msg = f" Your {bonus['item_name']} helped!" if bonus['item_name'] else ""
            player.points += points_earned
            await self._attack_result(ctx, '!root', f'@{ctx.author.name}, root access achieved!{item_msg} You earned {points_earned} points.', True, player)
        else:
            points_lost = random.randint(55, 80)
            player.points = max(0, player.points - points_lost)
            await self._attack_result(ctx, '!root', f'@{ctx.author.name}, privilege escalation failed! You lost {points_lost} points.', False, player)

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
        success = random.choice([True, True, False]) if bonus['success_boost'] else random.choice([True, False])
        if success:
            base_points = random.randint(160, 200)
            points_earned = int(base_points * bonus['points_multiplier'])
            item_msg = f" Your {bonus['item_name']} helped!" if bonus['item_name'] else ""
            player.points += points_earned
            await self._attack_result(ctx, '!ransom', f'@{ctx.author.name}, ransomware deployed successfully!{item_msg} You earned {points_earned} points.', True, player)
        else:
            points_lost = random.randint(60, 85)
            player.points = max(0, player.points - points_lost)
            await self._attack_result(ctx, '!ransom', f'@{ctx.author.name}, ransomware deployment failed! You lost {points_lost} points.', False, player)

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
        success = random.choice([True, True, False]) if bonus['success_boost'] else random.choice([True, False])
        if success:
            base_points = random.randint(170, 210)
            points_earned = int(base_points * bonus['points_multiplier'])
            item_msg = f" Your {bonus['item_name']} helped!" if bonus['item_name'] else ""
            player.points += points_earned
            await self._attack_result(ctx, '!sniff', f'@{ctx.author.name}, network sniffing successful! Captured sensitive data!{item_msg} You earned {points_earned} points.', True, player)
        else:
            points_lost = random.randint(65, 90)
            player.points = max(0, player.points - points_lost)
            await self._attack_result(ctx, '!sniff', f'@{ctx.author.name}, network sniffing failed! You lost {points_lost} points.', False, player)

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
        success = random.choice([True, True, False]) if bonus['success_boost'] else random.choice([True, False])
        if success:
            base_points = random.randint(180, 220)
            points_earned = int(base_points * bonus['points_multiplier'])
            item_msg = f" Your {bonus['item_name']} helped!" if bonus['item_name'] else ""
            player.points += points_earned
            await self._attack_result(ctx, '!mitm', f'@{ctx.author.name}, MITM attack successful! Intercepted traffic!{item_msg} You earned {points_earned} points.', True, player)
        else:
            points_lost = random.randint(70, 95)
            player.points = max(0, player.points - points_lost)
            await self._attack_result(ctx, '!mitm', f'@{ctx.author.name}, MITM attack failed! You lost {points_lost} points.', False, player)

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
        success = random.choice([True, True, False]) if bonus['success_boost'] else random.choice([True, False])
        if success:
            base_points = random.randint(190, 230)
            points_earned = int(base_points * bonus['points_multiplier'])
            item_msg = f" Your {bonus['item_name']} helped!" if bonus['item_name'] else ""
            player.points += points_earned
            await self._attack_result(ctx, '!ddos', f'@{ctx.author.name}, DDoS attack successful! Services disrupted!{item_msg} You earned {points_earned} points.', True, player)
        else:
            points_lost = random.randint(75, 100)
            player.points = max(0, player.points - points_lost)
            await self._attack_result(ctx, '!ddos', f'@{ctx.author.name}, DDoS attack failed! You lost {points_lost} points.', False, player)

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
        success = random.choice([True, True, False]) if bonus['success_boost'] else random.choice([True, False])
        if success:
            base_points = random.randint(200, 240)
            points_earned = int(base_points * bonus['points_multiplier'])
            item_msg = f" Your {bonus['item_name']} helped!" if bonus['item_name'] else ""
            player.points += points_earned
            await self._attack_result(ctx, '!drop', f'@{ctx.author.name}, USB drop attack successful! Target connected the device!{item_msg} You earned {points_earned} points.', True, player)
        else:
            points_lost = random.randint(80, 105)
            player.points = max(0, player.points - points_lost)
            await self._attack_result(ctx, '!drop', f'@{ctx.author.name}, USB drop attack failed! No one took the bait. You lost {points_lost} points.', False, player)

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
        success = random.choice([True, True, False]) if bonus['success_boost'] else random.choice([True, False])
        if success:
            base_points = random.randint(210, 250)
            points_earned = int(base_points * bonus['points_multiplier'])
            item_msg = f" Your {bonus['item_name']} helped!" if bonus['item_name'] else ""
            player.points += points_earned
            await self._attack_result(ctx, '!tailgate', f'@{ctx.author.name}, tailgating successful! You slipped in unnoticed.{item_msg} You earned {points_earned} points.', True, player)
        else:
            points_lost = random.randint(85, 110)
            player.points = max(0, player.points - points_lost)
            await self._attack_result(ctx, '!tailgate', f'@{ctx.author.name}, tailgating failed! Security caught you. You lost {points_lost} points.', False, player)

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
            await self._attack_result(ctx, '!socialengineer', f'@{ctx.author.name}, social engineering successful! You obtained sensitive information. You earned {points_earned} points.', True, player)
        else:
            points_lost = random.randint(90, 115)
            player.points = max(0, player.points - points_lost)
            await self._attack_result(ctx, '!socialengineer', f'@{ctx.author.name}, social engineering failed! Your cover was blown. You lost {points_lost} points.', False, player)

    ###################################################################
    # BOSS BATTLE #
    ###################################################################

    @commands.command(name='bossbattleguide')
    async def bossbattleguide(self, ctx):
        """Link to the boss battle how-to-play guide."""
        await ctx.send(f"@{ctx.author.name} Boss Battle guide — how to play, commands, hack items, and rewards: https://bossbattle-guide.b7h30.com/")

    @commands.command(name='twitchackguide')
    async def twitchackguide(self, ctx):
        """Link to the full TwitcHack player manual."""
        await ctx.send(f"@{ctx.author.name} TwitcHack player manual — locations, attacks, leveling, items, secrets, and more: https://twitchack.b7h30.com/")

    @commands.command(name='battlecam')
    async def battlecam(self, ctx):
        """Link to the live boss battle spectator page."""
        await ctx.send(f"@{ctx.author.name} Watch the boss battle live: https://bossbattle.b7h30.com/")

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
            
            await self.send_clamped(
                ctx,
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

            # Push initial battle state to overlay
            await overlay.push(**self._ov_state())
            await overlay.log(
                f"⚔️ RAID BEGINS — {battle.boss_name} vs {len(battle.challenger_team)} challengers!",
                "info"
            )

            while battle.boss_health > 0 and battle.challenger_team and turn < max_turns:
                turn += 1
                await overlay.log(f"⚔️ Turn {turn} ⚔️", "info")
                await overlay.push(**self._ov_state())
                await asyncio.sleep(1)

                # Boss turn taunt (50% chance)
                if random.random() < 0.5:
                    taunt_text = random.choice(TURN_TAUNTS)
                    taunt_msg = f"💀 {battle.boss_name}: {taunt_text}"
                    await overlay.log(taunt_msg, "taunt")
                    await asyncio.sleep(0.5)

                # Raspberry Pi: 25% chance to short-circuit boss attack this turn
                pi_holders = [p for p in battle.challenger_team
                              if "Elliot Alderson's Raspberry Pi" in self.player_data[p].items]
                if pi_holders and random.random() < 0.25:
                    pi_msg = (
                        f"🫐 @{random.choice(pi_holders)}'s Raspberry Pi runs interference — "
                        f"boss attack short-circuited this turn!"
                    )
                    await overlay.log(pi_msg, "pi")
                else:
                    # Boss targets one random player
                    target = random.choice(list(battle.challenger_team.keys()))
                    damage = random.randint(10, 30)
                    boss_action = random.choice([
                        f"launches a targeted DDoS at @{target}!",
                        f"deploys ransomware on @{target}'s rig!",
                        f"executes a supply chain attack against @{target}!",
                        f"activates defenses specifically against @{target}!",
                        f"sets rgb to red and locks eyes on @{target}!",
                        f"sends 'AngyTheo' emote directly at @{target}!",
                    ])
                    boss_msg = f"🔥 {battle.boss_name} {boss_action}"
                    await overlay.log(boss_msg, "damage")
                    await asyncio.sleep(1)

                    target_player = self.player_data.get(target)

                    # Lambo Keys: 35% dodge chance when targeted
                    if (target_player and
                            "Heath Adams' Lambo Keys" in target_player.items and
                            random.random() < 0.35):
                        dodge_msg = f"🏎️ @{target} floors it in the Lambo — attack missed!"
                        await overlay.log(dodge_msg, "dodge")
                    else:
                        health = battle.challenger_team[target]
                        new_health = max(0, health - damage)

                        if new_health <= 0:
                            # Consciousness USB: one-time death save per player per battle
                            if (target_player and
                                    "John Hammond's Consciousness USB" in target_player.items and
                                    target not in battle.consciousness_used):
                                battle.consciousness_used.add(target)
                                battle.challenger_team[target] = 1
                                save_msg = (
                                    f"🧠 @{target}'s Consciousness USB kicks in — "
                                    f"mind transferred to backup! Survives at 1 HP!"
                                )
                                await overlay.log(save_msg, "save")
                                await overlay.push(**self._ov_state())
                            else:
                                death_taunt = random.choice(DEATH_TAUNTS)
                                death_msg = f"☠️ @{target} has fallen! | 💀 {battle.boss_name}: {death_taunt}"
                                await overlay.log(death_msg, "death")
                                del battle.challenger_team[target]
                                battle.fallen.append(target)
                                await overlay.push(**self._ov_state())
                        else:
                            battle.challenger_team[target] = new_health
                            dmg_msg = f"@{target} takes {damage} damage! ({new_health} HP remaining)"
                            await overlay.log(dmg_msg, "damage")
                            await overlay.push(**self._ov_state())
                    await asyncio.sleep(0.5)

                if not battle.challenger_team:
                    wipe_msg = "All challengers have been defeated!"
                    await overlay.log(wipe_msg, "defeat")
                    break

                await overlay.log("🗡️ Team attack phase:", "info")
                await asyncio.sleep(1)

                # Team attack phase
                total_damage = 0
                for player_name in battle.challenger_team:
                    player_damage = random.randint(5, 15)
                    total_damage += player_damage
                    battle.team_damage += player_damage
                    battle.per_player_damage[player_name] = battle.per_player_damage.get(player_name, 0) + player_damage

                    attack_action = random.choice([
                        "executes a SQL injection",
                        "deploys a zero-day exploit",
                        "launches a social engineering attack",
                        "attempts a buffer overflow",
                        "distracts Theo by disparaging the Cleveland Browns"
                    ])

                    atk_msg = f"@{player_name} {attack_action} for {player_damage} damage!"
                    await overlay.log(atk_msg, "team")
                    await asyncio.sleep(0.5)

                # Password Cracker: +15 bonus damage per holder
                crackers = [p for p in battle.challenger_team
                            if "Kevin Mitnick's Password Cracker" in self.player_data[p].items]
                if crackers:
                    crack_bonus = len(crackers) * 15
                    total_damage += crack_bonus
                    battle.team_damage += crack_bonus
                    holder_str = ", ".join(f"@{p}" for p in crackers)
                    crack_msg = (
                        f"🔓 Password Cracker{'s' if len(crackers) > 1 else ''} "
                        f"({holder_str}) — +{crack_bonus} bonus damage!"
                    )
                    await overlay.log(crack_msg, "cracker")
                    await asyncio.sleep(0.5)

                battle.boss_health = max(0, battle.boss_health - total_damage)
                hp_msg = f"Boss HP: {battle.boss_health} | Team members remaining: {len(battle.challenger_team)}"
                await overlay.log(hp_msg, "info")
                await overlay.push(**self._ov_state())
                await asyncio.sleep(2)

            # Battle resolution
            self.session_total_damage += battle.team_damage
            if battle.boss_health <= 0:
                self.session_battles["won"] += 1
                self.session_battles["bosses"].append(battle.boss_name)
                await overlay.push(**self._ov_state(result="victory"))
                await overlay.log(f"🏆 VICTORY! {battle.boss_name} has been defeated!", "victory")
                await self.reward_team(ctx)
                await asyncio.sleep(30)
                await overlay.clear()
            else:
                self.session_battles["lost"] += 1
                await overlay.push(**self._ov_state(result="defeat"))
                await overlay.log("☠ DEFEAT — all challengers have fallen.", "defeat")
                await self.battle_summary(ctx, victory=False)
                await asyncio.sleep(20)
                await overlay.clear()
            
        except Exception as e:
            await ctx.send(f"An error occurred during battle: {str(e)}")
        finally:
            self.ongoing_battle = None
            helpers.save_player_data(self.player_data)

    @commands.command(name='hack')
    async def hack_ability(self, ctx):
        username = ctx.author.name.lower()
        battle = self.ongoing_battle
        if not battle or battle.join_phase:
            return
        if username not in battle.challenger_team:
            await ctx.send(f"@{ctx.author.name}, you're not in this battle!")
            return
        if username in battle.hack_used:
            await ctx.send(f"@{ctx.author.name}, you already used your hack this battle!")
            return
        player = self.player_data.get(username)
        player_items = set(player.items) if player else set()
        owned_hack_items = player_items & HACK_ITEMS
        if owned_hack_items:
            damage = random.randint(55, 85)
            item_name = next(iter(owned_hack_items))
            msg = f"@{ctx.author.name} deploys {item_name}! CRITICAL HIT — {damage} damage to {battle.boss_name}!"
        else:
            damage = random.randint(30, 60)
            msg = f"@{ctx.author.name} launches a manual hack — {damage} damage to {battle.boss_name}!"
        battle.boss_health = max(0, battle.boss_health - damage)
        battle.hack_used.add(username)
        battle.team_damage += damage
        battle.per_player_damage[username] = battle.per_player_damage.get(username, 0) + damage
        await ctx.send(msg)

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
        self.ongoing_battle.player_max_health[username] = player.health
        join_msg = f"@{ctx.author.name} has joined the raid! ({len(self.ongoing_battle.challenger_team)}/5 members)"
        await ctx.send(join_msg)
        await overlay.log(join_msg, "info")
        await overlay.push(**self._ov_state())
        taunt = random.choice(JOIN_TAUNTS).format(username=ctx.author.name, level=player.level)
        taunt_msg = f"💀 {self.ongoing_battle.boss_name}: {taunt}"
        await ctx.send(taunt_msg)
        await overlay.log(taunt_msg, "taunt")

    async def battle_summary(self, ctx, victory: bool):
        battle = self.ongoing_battle
        if not battle:
            return
        survivors = list(battle.challenger_team.keys())
        mvp = max(battle.per_player_damage, key=battle.per_player_damage.get) if battle.per_player_damage else None
        parts = []
        if victory:
            parts.append(f"VICTORY! The team defeated {battle.boss_name}!")
        else:
            parts.append(f"DEFEAT! {battle.boss_name} was too powerful!")
        if survivors:
            parts.append("Survivors: " + ", ".join(f"@{s}" for s in survivors))
        if battle.fallen:
            parts.append("Fallen: " + ", ".join(f"@{f}" for f in battle.fallen))
        parts.append(f"Total damage: {battle.team_damage}")
        if mvp:
            parts.append(f"MVP: @{mvp} ({battle.per_player_damage[mvp]} dmg)")
        summary, _ = helpers.clamp_chat_message(" | ".join(parts))
        await ctx.send(summary)

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
            
            await self.battle_summary(ctx, victory=True)

            for username in battle.challenger_team:
                if username not in self.player_data:
                    continue

                player = self.player_data[username]
                player.points += total_reward
                self.session_points_earned[username] = self.session_points_earned.get(username, 0) + total_reward
                player.health = min(player.health + 5, 1000)  # Cap health at 1000
                helpers.check_level_up(self.player_data, username)
                await self.send_result(ctx, f"@{username} earned {total_reward} points and +5 max HP!")

            await ctx.send(f"The team has defeated {battle.boss_name}! Each survivor earned {total_reward} points!")

            # Victory drop — one random battle-exclusive item, first to !grab it wins
            self.prune_expired_drops()
            drop_item = random.choice(BATTLE_DROPS)
            existing_names = {d['name'].lower() for d in self.dropped_items}
            if drop_item.lower() not in existing_names:
                self.dropped_items.append({
                    'name': drop_item,
                    'location': 'the arena',
                    'ts': datetime.now().timestamp()
                })
                await ctx.send(
                    f"🏆 VICTORY DROP! The battle left behind "
                    f"{self.format_item(drop_item)}! "
                    f"Type !grab {drop_item} to claim it before it's gone!"
                )

        except Exception as e:
            print(f"Error in reward_team: {str(e)}")
            await ctx.send("An error occurred while distributing rewards.")
        finally:
            helpers.save_player_data(self.player_data)

    @commands.command(name='streamsummary')
    async def streamsummary(self, ctx):
        username = ctx.author.name.lower()
        if not self.is_channel_owner(username) and not ctx.author.is_mod:
            return

        elapsed = datetime.now() - self.session_start
        hours, remainder = divmod(int(elapsed.total_seconds()), 3600)
        minutes, _ = divmod(remainder, 60)
        duration_str = f"{hours}h {minutes}m" if hours else f"{minutes}m"

        # 1. Header + battle stats
        battles_total = self.session_battles["won"] + self.session_battles["lost"]
        bosses_str = ", ".join(self.session_battles["bosses"]) if self.session_battles["bosses"] else "none"
        await self.send_clamped(ctx,
            f"=== Stream Summary ({duration_str}) ==="
            f" | Boss Battles: {battles_total} ({self.session_battles['won']}W / {self.session_battles['lost']}L)"
            f" | Bosses defeated: {bosses_str}"
            f" | Total damage: {self.session_total_damage}"
        )
        await asyncio.sleep(1)

        # 2. Item activity
        pickups_str = (
            ", ".join(f"@{u} grabbed {i}" for u, i in self.session_items_picked_up)
            if self.session_items_picked_up else "none"
        )
        await self.send_clamped(ctx,
            f"Items: {len(self.session_items_dropped)} dropped, {len(self.session_items_picked_up)} picked up"
            f" | {pickups_str}"
        )
        await asyncio.sleep(1)

        # 3. Top earners
        if self.session_points_earned:
            top3 = sorted(self.session_points_earned.items(), key=lambda x: x[1], reverse=True)[:3]
            earners_str = " | ".join(f"@{u}: {p} pts" for u, p in top3)
        else:
            earners_str = "none yet"
        await self.send_clamped(ctx, f"Top earners this stream: {earners_str}")
        await asyncio.sleep(1)

        # 4. New players
        new_str = (
            ", ".join(f"@{u}" for u in self.session_new_players)
            if self.session_new_players else "none this stream"
        )
        await self.send_clamped(ctx, f"New players: {new_str}")
        await asyncio.sleep(1)

        # 5. Chatters to thank (active last 30 min, exclude bot + owner)
        self.prune_recent_chatters()
        ignore = self.ignored_users | {BOT_NICK.lower(), CHANNEL_OWNER.lower()}
        chatters = sorted(u for u in self.recent_chatters if u not in ignore)
        thanks_str = " ".join(f"@{u}" for u in chatters) if chatters else "no recent chatters found"
        await self.send_clamped(ctx, f"Thanks for chatting: {thanks_str}")

    @commands.command(name='monday')
    async def monday(self, ctx, *, prompt: str = None):
        """Calls the snarky MondayGPT AI with optional prompt."""
        bot_state = {
            'last_monday_time': self.last_monday_time,
            'monday_calls': self.monday_calls,
            'last_monday_error': self.last_monday_error,
            'last_monday_error_time': self.last_monday_error_time
        }
        await monday.run_monday_response(
            prompt or "Hey Monday, what's up?",
            ctx.author.name,
            ctx.send,
            bot_state
        )
        # Update state
        self.last_monday_time = bot_state['last_monday_time']
        self.monday_calls = bot_state['monday_calls']
        self.last_monday_error = bot_state['last_monday_error']
        self.last_monday_error_time = bot_state['last_monday_error_time']


# Entry point
if __name__ == '__main__':
    bot = Bot()
    bot.run()
