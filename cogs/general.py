import discord
from discord.ext import commands


class General(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command()
    async def salve(self, ctx):
        await ctx.send("Fala meu chefe, oq ce manda")


async def setup(bot: commands.Bot):
    await bot.add_cog(General(bot))
