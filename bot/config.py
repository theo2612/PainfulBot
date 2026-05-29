"""Configuration and environment variables for PainfulBot."""
import os
from dotenv import load_dotenv

load_dotenv()

# Twitch Bot Configuration
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

# OpenAI/Monday Configuration
MONDAY_MODEL = os.getenv("MONDAY_MODEL", "gpt-4o-mini")

_raw_cd = os.getenv("MONDAY_COOLDOWN", "30")
try:
    MONDAY_COOLDOWN = int(_raw_cd.split("#", 1)[0].strip())
except ValueError:
    MONDAY_COOLDOWN = 15
