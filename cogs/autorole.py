import discord
from discord.ext import commands

class AutoRole(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.role_id = 1213324989202309220  # coloque o ID do cargo

    @commands.Cog.listener()
    async def on_member_join(self, member):
        role = member.guild.get_role(self.role_id)
        if role:
            try:
                await member.add_roles(role)
            except:
                pass

async def setup(bot):
    await bot.add_cog(AutoRole(bot))
