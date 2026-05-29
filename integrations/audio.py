"""Audio trigger system for PainfulBot."""
from datetime import datetime, timedelta
from bot.helpers import log_to_file, load_audio_triggers
from bot.config import PREFIX


def match_audio_clip(content, author_name, audio_triggers, audio_seen_users):
    """Return the best-matching audio clip command for given content (config-driven)."""
    text = content.lower()
    if text.startswith(PREFIX):
        return None
    if "@theo2820" in text:
        # Let mention-based Monday be handled elsewhere, don't block audio matching unless it's a command
        pass

    # Special-case: first message from configured user
    special_clip = None
    for trig in audio_triggers:
        fm_user = trig.get("first_message_user", "")
        if fm_user and author_name and author_name.lower() == fm_user.lower():
            if author_name.lower() not in audio_seen_users:
                special_clip = trig.get("clip")
            break
    if special_clip:
        return special_clip

    best = None
    best_hits = 0
    for trig in audio_triggers:
        clip = trig.get("clip")
        keywords = trig.get("keywords", [])
        hits = sum(1 for k in keywords if k.lower() in text)
        if hits > best_hits:
            best_hits = hits
            best = clip

    return best if best_hits > 0 else None


async def maybe_trigger_audio_clip(message, bot_state, channel):
    """
    Have Monday fire an audio command based on chat context.

    Args:
        message: Twitch message object
        bot_state: Dict with audio trigger state
        channel: Connected channel to send command to
    """
    if not message or not message.author or not message.content:
        return

    username = message.author.name.lower()
    now = datetime.now()

    # Global cooldown
    if now - bot_state['audio_last_trigger'] < bot_state['audio_global_cooldown']:
        return

    # Per-user cooldown (avoid spamming the same chatter)
    last_user_fire = bot_state['audio_user_last_trigger'].get(username, datetime.min)
    if now - last_user_fire < timedelta(minutes=10):
        return

    clip = match_audio_clip(
        message.content,
        message.author.name,
        bot_state['audio_triggers'],
        bot_state['audio_seen_users']
    )
    if not clip:
        # Track the fact we saw this user to prevent first-message logic firing later
        bot_state['audio_seen_users'].add(username)
        return

    # Per-clip cooldowns (from config) or global default
    clip_cooldown = bot_state['audio_global_cooldown']
    for trig in bot_state['audio_triggers']:
        if trig.get("clip") == clip:
            minutes = trig.get("cooldown_minutes")
            if minutes:
                clip_cooldown = timedelta(minutes=minutes)
            break
    last_clip_fire = bot_state['audio_clip_last_trigger'].get(clip, datetime.min)
    if now - last_clip_fire < clip_cooldown:
        bot_state['audio_seen_users'].add(username)
        return

    # Fire silently by sending the command
    try:
        await channel.send(clip)
        bot_state['audio_last_trigger'] = now
        bot_state['audio_clip_last_trigger'][clip] = now
        bot_state['audio_user_last_trigger'][username] = now
        bot_state['audio_seen_users'].add(username)
        bot_state['audio_triggers_fired'] += 1
    except Exception as e:
        log_to_file(f"Audio trigger send failed: {str(e)}")
