import os

from groq import Groq
from discord.ext import commands


class AI(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    @commands.command()
    async def chat(self, ctx, *, query: str):
        async with ctx.typing():
            try:
                response = self.client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[
                        {"role": "system", "content": "Responda de forma curta e direta, sem enrolação. Evite listas longas e textos extensos."},
                        {"role": "user", "content": query},
                    ],
                )
                text = response.choices[0].message.content
                for i in range(0, len(text), 2000):
                    await ctx.send(text[i:i + 2000])
            except Exception as e:
                await ctx.send(f"Erro: {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(AI(bot))
