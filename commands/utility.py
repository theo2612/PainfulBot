"""Utility commands for PainfulBot."""
import random
from twitchio.ext import commands
from datetime import datetime
from bot.config import PREFIX, MONDAY_MODEL, MONDAY_COOLDOWN


class UtilityCommands(commands.Cog):
    """Simple utility commands like hello, coinflip, dice roll, etc."""

    def __init__(self, bot):
        self.bot = bot

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


def prepare(bot):
    """Standard Cog setup function."""
    bot.add_cog(UtilityCommands(bot))
