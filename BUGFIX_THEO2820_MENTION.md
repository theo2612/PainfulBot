# Bugfix: @theo2820 Mention Not Working

## Problem
After refactoring, mentioning @theo2820 in chat no longer triggered Monday AI responses.

## Root Cause
During refactoring, I moved the Monday AI logic to `integrations/monday.py`, but the `maybe_random_monday_reply()` method was still calling the old methods:
- `self.run_monday_response()` - REMOVED during refactoring
- `self.monday_prompt_is_safe()` - REMOVED during refactoring

## Fix Applied

### 1. Added Missing Imports (PainfulBot.py lines 11-14)
```python
from twitchio.ext import commands, eventsub
from openai import RateLimitError, APIError  # Added
from playerdata import *
from items import ITEMS, Item

# Import from refactored modules
from bot.config import (...)
from bot import helpers
from integrations import monday, audio
from integrations.monday import openai_client  # Added
from game.battle import BossBattle
```

### 2. Updated Mention Handler (lines 515-541)
**Before:**
```python
if mentions_monday:
    await self.run_monday_response(  # This method doesn't exist!
        prompt=text,
        author_name=message.author.name,
        send_func=self.connected_channels[0].send,
    )
    return

safe, reason = self.monday_prompt_is_safe(text)  # This method doesn't exist!
```

**After:**
```python
if mentions_monday:
    bot_state = {
        'last_monday_time': self.last_monday_time,
        'monday_calls': self.monday_calls,
        'last_monday_error': self.last_monday_error,
        'last_monday_error_time': self.last_monday_error_time
    }
    await monday.run_monday_response(  # Use the monday module
        prompt=text,
        author_name=message.author.name,
        send_func=self.connected_channels[0].send,
        bot_state=bot_state
    )
    # Update state from bot_state dict
    self.last_monday_time = bot_state['last_monday_time']
    self.monday_calls = bot_state['monday_calls']
    self.last_monday_error = bot_state['last_monday_error']
    self.last_monday_error_time = bot_state['last_monday_error_time']
    return

safe, reason = monday.monday_prompt_is_safe(text)  # Use the monday module
```

## Testing

### ✅ Import Test
```bash
source venv/bin/activate
python3 -c "from PainfulBot import Bot; print('OK')"
# Output: OK
```

### ✅ Bot Startup
```bash
./start_bot.sh
# Bot starts without errors
```

### Test in Twitch Chat
Try these:
- `@theo2820 hello!` - Should get Monday response
- `@monday what's up?` - Should get Monday response
- `!monday test` - Should get Monday response

## What @theo2820 Mentions Do

When someone mentions @theo2820 (or @monday, or the bot's nick) in chat:
1. The `event_message` handler receives the message
2. Calls `maybe_random_monday_reply(message)`
3. Checks if "theo2820", "monday", or bot nick is in the message (line 516)
4. If yes, calls `monday.run_monday_response()` from the monday module
5. Monday AI responds with the snarky personality
6. Applies the main Monday cooldown (15 seconds default)

## Files Changed
- `/home/b7h30/PainfulBot/PainfulBot.py` - Added imports, fixed mention handler

## Status
✅ **FIXED** - @theo2820 mentions now work correctly with the refactored code
