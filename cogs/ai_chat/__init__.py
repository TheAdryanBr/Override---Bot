from .ai_chat import AIChat

async def setup(bot):
    await bot.add_cog(AIChat(bot))
