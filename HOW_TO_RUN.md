# How to Run PainfulBot (Refactored)

## Quick Start

### Option 1: Use the startup script
```bash
cd /home/b7h30/PainfulBot
./start_bot.sh
```

### Option 2: Manual start
```bash
cd /home/b7h30/PainfulBot
source venv/bin/activate
python3 PainfulBot.py
```

### Option 3: Use systemd service
```bash
sudo systemctl restart PainfulIT-bot.service
sudo systemctl status PainfulIT-bot.service
```

## Verifying It Works

### ✅ Import Test Passed
All modules imported successfully:
- bot.config
- bot.helpers
- integrations.monday
- integrations.audio
- game.battle
- commands.utility

### ✅ Check Logs
```bash
tail -f bot.log
```

### ✅ Test Commands in Twitch Chat
- `!hello` - Should greet you
- `!coinflip` - Should flip a coin
- `!roll 20` or `!d20` - Should roll a die
- `!start` - Should register you
- `!monday What's up?` - Should get Monday AI response

## What Changed (Reminder)

### Extracted to Modules
- **bot/config.py** - Environment variables
- **bot/helpers.py** - Data persistence, logging
- **integrations/monday.py** - Monday AI system
- **integrations/audio.py** - Audio triggers
- **commands/utility.py** - Utility commands (Cog)

### Main Bot (PainfulBot.py)
- Now imports from modules
- 2,300 lines (down from 2,687)
- All game commands still work
- Loads utility Cog automatically

## Troubleshooting

### "ModuleNotFoundError: No module named 'twitchio'"
**Solution**: You need to activate the venv first
```bash
source venv/bin/activate
python3 PainfulBot.py
```

### "ModuleNotFoundError: No module named 'bot'"
**Solution**: Run from the PainfulBot directory
```bash
cd /home/b7h30/PainfulBot
python3 PainfulBot.py
```

### Bot doesn't connect to Twitch
**Solution**: Check your .env file has valid credentials
```bash
cat .env | grep -E "TOKEN|CLIENT_ID|CHANNEL"
```

### Check if bot is running
```bash
ps aux | grep PainfulBot
```

### Kill the bot
```bash
pkill -f PainfulBot.py
```

## Rollback to Original

If you need to rollback:
```bash
cd /home/b7h30/PainfulBot
mv PainfulBot.py PainfulBot_refactored.py
cp PainfulBot.py.backup PainfulBot.py
```

## Files
- `PainfulBot.py` - Main bot (refactored)
- `PainfulBot.py.backup` - Original backup
- `PainfulBot_original.py` - Another backup
- `start_bot.sh` - Startup script
- `bot/`, `commands/`, `integrations/`, `game/` - New modules
