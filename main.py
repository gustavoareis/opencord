import asyncio

import discord
from discord.ext import commands

from config import TOKEN

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=".", intents=intents)


async def main():
    async with bot:
        await bot.load_extension("cogs.music")
        await bot.start(TOKEN)


asyncio.run(main())
