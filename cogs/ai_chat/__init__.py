# cogs/ai_chat/__init__.py
from .ai_chat import AIChatCog

async def setup(bot):
    await bot.add_cog(AIChatCog(bot))
