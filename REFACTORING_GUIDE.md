# PainfulBot Refactoring Guide

## What's Been Done

### Phase 1: Module Structure Created ✅
```
/home/b7h30/PainfulBot/
├── bot/
│   ├── __init__.py           # Package init
│   ├── config.py             # Environment variables & constants
│   └── helpers.py            # Utility functions (logging, data persistence, clamping)
├── commands/
│   ├── __init__.py
│   └── utility.py            # Example Cog: hello, coinflip, roll, secret, statusbot, session
├── integrations/
│   ├── __init__.py
│   ├── monday.py             # Monday AI/ChatGPT integration
│   └── audio.py              # Audio trigger system
├── game/
│   ├── __init__.py
│   └── battle.py             # BossBattle class
└── PainfulBot.py.backup      # Original backup
```

### Modules Extracted ✅
1. **bot/config.py** - All environment variables and constants
2. **bot/helpers.py** - Utility functions:
   - `log_to_file()`, `clamp_chat_message()`
   - `load_player_data()`, `save_player_data()`, `check_level_up()`
   - `load_session_flags()`, `save_session_flags()`
   - `load_audio_triggers()`

3. **integrations/monday.py** - Monday AI logic:
   - `monday_prompt_is_safe()` - Injection detection
   - `run_monday_response()` - Main Monday handler
   - Blocklist and injection patterns

4. **integrations/audio.py** - Audio triggers:
   - `match_audio_clip()` - Keyword matching
   - `maybe_trigger_audio_clip()` - Trigger handler with cooldowns

5. **game/battle.py** - BossBattle class

6. **commands/utility.py** - Example Cog with 6 commands:
   - hello, coinflip, roll, secret, statusbot, session

## Next Steps

### Option A: Full Command Extraction (Time-intensive)
Extract all 49 commands into Cogs:
- `commands/core.py` - start, help, hack, points, status, leaderboard
- `commands/attacks.py` - All 27 attack commands
- `commands/battle.py` - bossbattle, joinbattle
- `commands/items.py` - grab, droprandom, mvp, items
- `commands/admin.py` - virus, ownerpoints, assignpoints
- Remaining utility commands already in utility.py

### Option B: Hybrid Approach (Recommended)
1. Create `bot/bot.py` with main Bot class
2. Import and use helper functions from modules
3. Keep command methods in Bot class for now
4. Load utility Cog as example
5. Gradually extract more commands over time

### Option C: Use Current Structure
The modular structure is in place. Commands can be extracted incrementally as needed.

## How to Use the Refactored Code

### Using Helper Functions
```python
from bot.helpers import log_to_file, save_player_data, load_player_data

# In your bot
self.player_data = load_player_data()
log_to_file("Bot started")
save_player_data(self.player_data)
```

### Using Monday Integration
```python
from integrations.monday import run_monday_response

# In your command
await run_monday_response(
    prompt="Hello Monday",
    author_name=ctx.author.name,
    send_func=ctx.send,
    bot_state={
        'last_monday_time': self.last_monday_time,
        'monday_calls': self.monday_calls,
        'last_monday_error': self.last_monday_error,
        'last_monday_error_time': self.last_monday_error_time
    }
)
```

### Loading Cogs
```python
# In Bot.__init__()
from commands.utility import prepare as prepare_utility
prepare_utility(self)
```

## Benefits Achieved
- ✅ Separated concerns (config, helpers, integrations, game logic)
- ✅ Easier to test individual modules
- ✅ Example Cog pattern demonstrated
- ✅ Monday AI and audio systems isolated
- ✅ Helper functions can be reused
- ✅ Configuration centralized

## Testing Checklist
- [ ] Bot starts and connects to Twitch
- [ ] Utility commands work (!hello, !coinflip, !roll, !secret, !statusbot, !session)
- [ ] Monday integration works (!monday)
- [ ] Audio triggers fire on keywords
- [ ] Player data persists correctly
- [ ] Attack commands work (still in main bot)
- [ ] Boss battles function (still in main bot)
- [ ] EventSub integration works

## File Sizes Before/After
- **Before**: PainfulBot.py (2,687 lines)
- **After**:
  - bot/config.py: 25 lines
  - bot/helpers.py: 132 lines
  - integrations/monday.py: 167 lines
  - integrations/audio.py: 103 lines
  - game/battle.py: 12 lines
  - commands/utility.py: 125 lines
  - **Total extracted**: ~564 lines
  - **Remaining in main**: ~2,123 lines (mostly commands)

## Recommendation
Due to the scope (49 commands), I recommend Option B: Create a working bot.py that uses the helper modules, with the utility Cog as a working example. This provides immediate value while allowing gradual command extraction over time.

Commands can be extracted incrementally using the Cog pattern demonstrated in `commands/utility.py`.
