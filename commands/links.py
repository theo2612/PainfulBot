"""Link / info commands for PainfulBot — single-line responses pointing chat at external URLs."""
from twitchio.ext import commands


class LinksCommands(commands.Cog):
    """Static link responses: hub, gear, lab, training, setup, merch, guides, battlecam."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='links')
    async def links(self, ctx):
        """Link to the all-in-one b7h30 hub page."""
        await ctx.send(f"@{ctx.author.name} Everything b7h30 in one spot — streams, socials, gear, training, merch: https://links.b7h30.com/")

    @commands.command(name='gear')
    async def gear(self, ctx):
        """Link to the full gear/setup page."""
        await ctx.send(f"@{ctx.author.name} My full setup — desktop, homelab, stream gear, and training resources: https://gear.b7h30.com/")

    @commands.command(name='lab')
    async def lab(self, ctx):
        """Link to the Proxmox homelab section."""
        await ctx.send(f"@{ctx.author.name} My Proxmox homelab build — what I run CTF labs on: https://gear.b7h30.com/#proxmox")

    @commands.command(name='training')
    async def training(self, ctx):
        """Link to HTB and TCM training resources."""
        await ctx.send(f"@{ctx.author.name} Cyber training I use and recommend — Hack The Box & TCM Security: https://gear.b7h30.com/#training")

    @commands.command(name='setup')
    async def setup(self, ctx):
        """Link to the stream gear section."""
        await ctx.send(f"@{ctx.author.name} Stream gear — mic, monitors, keyboard, and more: https://gear.b7h30.com/#stream")

    @commands.command(name='merch')
    async def merch(self, ctx):
        """Link to the Fourthwall merch shop."""
        await ctx.send(f"@{ctx.author.name} b7h30 merch — tees, hoodies, stickers, mugs: https://b7h30-shop.fourthwall.com/")

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

    @commands.command(name='motivation')
    async def motivation(self, ctx):
        """Drop a little motivation."""
        await ctx.send(f"@{ctx.author.name} https://gr.ht/i/motivation.webp")


def prepare(bot):
    """Standard Cog setup function."""
    bot.add_cog(LinksCommands(bot))
