from .ai_chat import AIChatCog

async def setup(bot):
    from .ai_chat import AIChatCog
    await bot.add_cog(AIChatCog(bot))
