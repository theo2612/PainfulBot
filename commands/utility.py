"""Utility commands for PainfulBot."""
import asyncio
import os
import random
from pathlib import Path
from twitchio.ext import commands
from datetime import datetime
from openai import OpenAI
from bot.config import PREFIX, MONDAY_MODEL, MONDAY_COOLDOWN
from bot import memory as chatter_memory


_HTB_NOTES_BASE = Path.home() / "Documents/obsidian/docs/CTF/HTB"
_BOX_STATUS_COOLDOWN = 60  # seconds — prevent chat spam
_openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def _extract_box_notes(box_dir: Path) -> str:
    """Pull Status Summary + Next Steps from pentest-coach notes."""
    chunks = []

    # Find the writeup .md and extract Status Summary block
    for f in sorted(box_dir.glob("*.md"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            text = f.read_text(errors="replace")
            if "Status Summary" in text:
                start = text.index("Status Summary")
                chunks.append(text[start : start + 600])
                break
        except Exception:
            continue

    # attack-chain.md → Current Path + Next Steps
    chain = box_dir / "attack-chain.md"
    if chain.exists():
        try:
            ct = chain.read_text(errors="replace")
            for section in ("Current Path", "Next Steps"):
                if section in ct:
                    idx = ct.index(section)
                    chunks.append(ct[idx : idx + 300])
        except Exception:
            pass

    return "\n\n".join(chunks)[:900]


async def _summarize_for_chat(box_name: str, notes: str) -> str:
    """Ask GPT-4o-mini to turn box notes into a Twitch-friendly status line."""
    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: _openai_client.chat.completions.create(
                model=MONDAY_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You summarize HackTheBox CTF progress for Twitch chat viewers. "
                            "Be concise and clear. Include: box name, current stage "
                            "(recon/foothold/privesc/rooted), current user if known, and "
                            "what's happening next. Do NOT reveal full exploits or flags. "
                            "Hard limit: under 450 characters total. No markdown."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"Box: {box_name}\n\n{notes}\n\nSummarize for Twitch chat in under 450 chars.",
                    },
                ],
            ),
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return f"[HTB: {box_name}] Notes found but summary unavailable. Ask theo2820 in chat!"


class UtilityCommands(commands.Cog):
    """Simple utility commands like hello, coinflip, dice roll, etc."""

    def __init__(self, bot):
        self.bot = bot
        self._last_boxstatus = datetime.min

    @commands.command(name='hello')
    async def hello(self, ctx):
        """Responds with a greeting."""
        await ctx.send(f'Hello @{ctx.author.name}!')

    @commands.command(name='coinflip')
    async def coinflip(self, ctx):
        """Simulates flipping a coin."""
        result = random.choice(['Heads', 'Tails'])
        await ctx.send(f'@{ctx.author.name}, the coin landed on {result}!')

    @commands.command(name='roll', aliases=['d4', 'd6', 'd8', 'd10', 'd12', 'd20', 'd100'])
    async def roll(self, ctx, sides: str = None):
        """Roll a die with specified number of sides."""
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

    @commands.command(name='juststart')
    async def juststart(self, ctx):
        """Responds with a motivational message about starting."""
        await ctx.send(
            'Start now. Start where you are. Start with fear. Start with pain. Start with doubt. '
            'Start with hands shaking. Start with voice trembling but start. Start and don\'t stop. '
            'Start where you are, with what you have. Just... Start.'
        )

    @commands.command(name='secret')
    async def secret(self, ctx):
        """Responds with the chatOS message."""
        await ctx.send(
            f'There is no secret. // Consistency over intensity / '
            f'Progress over Perfection / Fundamentals over fads // Over and over again'
        )

    @commands.command(name='statusbot')
    async def statusbot(self, ctx):
        """Owner-only bot diagnostics: EventSub, Monday cooldown, boss battle, drops."""
        username = ctx.author.name.lower()
        if not self.bot.is_channel_owner(username):
            return

        # EventSub status
        es_client = getattr(self.bot, "eventsub_client", None)
        sockets = getattr(es_client, "_sockets", []) if es_client else []
        es_connected = any(getattr(s, "is_connected", False) for s in sockets)
        es_msg = "connected" if es_connected else "not connected"
        es_err = self.bot.last_eventsub_error or "none"
        es_err_time = self.bot.last_eventsub_error_time.strftime("%H:%M:%S") if self.bot.last_eventsub_error_time else "n/a"

        # Monday cooldown
        now = datetime.now()
        elapsed = (now - self.bot.last_monday_time).total_seconds()
        monday_ok = elapsed >= MONDAY_COOLDOWN
        monday_msg = "ready" if monday_ok else f"cooling ({int(MONDAY_COOLDOWN - elapsed)}s left)"
        last_monday = "never" if self.bot.last_monday_time == datetime.min else self.bot.last_monday_time.strftime("%H:%M:%S")
        last_monday_err = self.bot.last_monday_error or "none"
        last_monday_err_time = self.bot.last_monday_error_time.strftime("%H:%M:%S") if self.bot.last_monday_error_time else "n/a"

        # Boss battle status
        battle = self.bot.ongoing_battle
        if battle:
            battle_msg = f"active vs {battle.boss_name} (HP {battle.boss_health}) | join_phase={battle.join_phase} | team={len(battle.challenger_team)}"
        else:
            battle_msg = "idle"
        battle_cd_left = max(0, int((self.bot.boss_battle_cooldown - (now - self.bot.last_battle_time)).total_seconds()))

        drops = len(getattr(self.bot, "dropped_items", []))
        audio_cd_left = max(0, int((self.bot.audio_global_cooldown - (now - self.bot.audio_last_trigger)).total_seconds()))

        await self.bot.send_clamped(
            ctx,
            f"Bot status -> EventSub: {es_msg} (err={es_err} @ {es_err_time}) | Monday: {monday_msg} (last {last_monday}) err={last_monday_err} @ {last_monday_err_time} (model {MONDAY_MODEL}) | "
            f"Battle: {battle_msg} (cd {battle_cd_left}s) | Drops live: {drops} | Audio cd: {audio_cd_left}s | Audio triggers fired: {self.bot.audio_triggers_fired} | Drops spawned: {self.bot.drop_spawned_count}"
        )

    @commands.command(name='session')
    async def session_summary(self, ctx):
        """Owner-only: summarize session stats (drops, hidden usage, penalties, Monday/audio)."""
        username = ctx.author.name.lower()
        if not self.bot.is_channel_owner(username):
            return

        hidden_konami = len(self.bot.session_flags.get("konami", set()))
        hidden_coffee = len(self.bot.session_flags.get("coffee", set()))
        hidden_browns = len(self.bot.session_flags.get("browns", set()))
        mvp_awarded = "yes" if self.bot.session_flags.get("mvp_awarded", False) else "no"
        monday_calls = self.bot.monday_calls
        audio_count = self.bot.audio_triggers_fired
        drop_count = self.bot.drop_spawned_count
        pending_neovim = len(self.bot.neovim_penalties)

        await self.bot.send_clamped(
            ctx,
            f"Session -> Konami: {hidden_konami} | Coffee: {hidden_coffee} | Browns: {hidden_browns} | "
            f"MVP: {mvp_awarded} | Monday calls: {monday_calls} | Audio: {audio_count} | Drops: {drop_count} | "
            f"Neovim penalties queued: {pending_neovim}"
        )


    def _is_mod_or_owner(self, ctx):
        return self.bot.is_channel_owner(ctx.author.name.lower()) or ctx.author.is_mod

    @commands.command(name='remember')
    async def remember(self, ctx, target: str = None, *, note: str = None):
        """Mod/owner: add a memory note about a chatter or global context."""
        if not self._is_mod_or_owner(ctx):
            return
        if not target or not note:
            return await ctx.send(f"Usage: !remember <user|global> <note>")
        key = chatter_memory.GLOBAL_KEY if target.lower() == "global" else target.lower().lstrip('@')
        chatter_memory.add_note(key, note)
        label = "global notes" if key == chatter_memory.GLOBAL_KEY else f"@{target.lstrip('@')}"
        await ctx.send(f"Got it — note saved for {label}.")

    @commands.command(name='forget')
    async def forget(self, ctx, target: str = None):
        """Mod/owner: clear all memory notes for a chatter or global context."""
        if not self._is_mod_or_owner(ctx):
            return
        if not target:
            return await ctx.send("Usage: !forget <user|global>")
        key = chatter_memory.GLOBAL_KEY if target.lower() == "global" else target.lower().lstrip('@')
        chatter_memory.forget(key)
        label = "global notes" if key == chatter_memory.GLOBAL_KEY else f"@{target.lstrip('@')}"
        await ctx.send(f"Memory cleared for {label}.")

    @commands.command(name='whois')
    async def whois(self, ctx, target: str = None):
        """Mod/owner: read back what Monday knows about a chatter or global context."""
        if not self._is_mod_or_owner(ctx):
            return
        if not target:
            return await ctx.send("Usage: !whois <user|global>")
        key = chatter_memory.GLOBAL_KEY if target.lower() == "global" else target.lower().lstrip('@')
        notes = chatter_memory.get_notes(key)
        label = "Global" if key == chatter_memory.GLOBAL_KEY else f"@{target.lstrip('@')}"
        if not notes:
            return await ctx.send(f"{label}: no notes on file.")
        await self.bot.send_clamped(ctx, f"{label}: {' | '.join(notes)}")

    @commands.command(name='botcmds')
    async def botcmds(self, ctx):
        """Lists all public PainfulBot commands."""
        await ctx.send(
            "PainfulBot cmds | Utility: !hello, !coinflip, !roll/!d6/!d20/etc, !juststart, !secret, "
            "!boxstatus (HTB progress), !monday [prompt] (AI), !mondayinsulttheo | "
            "TwitcHack: !start, !status, !points, !leaderboard, !hack <location>, "
            "!attacks, !bossbattle, !joinbattle, !grab, !items | "
            "Game info: !help, !twitchackguide, !bossbattleguide, !battlecam"
        )

    @commands.command(name='boxstatus')
    async def boxstatus(self, ctx):
        """Summarize current HTB box progress from synced pentest-coach notes."""
        now = datetime.now()
        elapsed = (now - self._last_boxstatus).total_seconds()
        if elapsed < _BOX_STATUS_COOLDOWN:
            remaining = int(_BOX_STATUS_COOLDOWN - elapsed)
            return await ctx.send(f"@{ctx.author.name}, !boxstatus cooldown: {remaining}s left")

        if not _HTB_NOTES_BASE.exists():
            return await ctx.send("HTB notes not synced yet. Syncthing may still be setting up.")

        def _box_last_modified(d: Path) -> float:
            try:
                return max((f.stat().st_mtime for f in d.rglob("*.md")), default=0.0)
            except Exception:
                return 0.0

        try:
            box_dirs = sorted(
                [d for d in _HTB_NOTES_BASE.iterdir() if d.is_dir()],
                key=_box_last_modified,
                reverse=True,
            )
        except Exception:
            return await ctx.send("Could not read HTB notes folder.")

        if not box_dirs:
            return await ctx.send("No box notes found yet — theo2820 may not have started a box.")

        current_box = box_dirs[0]
        box_name = current_box.name
        notes = _extract_box_notes(current_box)

        if not notes:
            return await ctx.send(f"[HTB: {box_name}] Notes exist but are empty. Check back soon!")

        self._last_boxstatus = now
        summary = await _summarize_for_chat(box_name, notes)
        await self.bot.send_clamped(ctx, summary)


def prepare(bot):
    """Standard Cog setup function."""
    bot.add_cog(UtilityCommands(bot))
