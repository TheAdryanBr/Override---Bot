import discord
from discord.ext import commands

class AutoRole(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.role_id = 1213324989202309220  # <-- coloque o ID REAL aqui

    @commands.Cog.listener()
    async def on_member_join(self, member):
        print("[AUTOROLE] Membro entrou:", member)

        role = member.guild.get_role(self.role_id)

        print("[AUTOROLE] Cargo encontrado:", role)

        if role is None:
            print("[AUTOROLE] ERRO: Cargo não existe ou ID errado.")
            return
        
        try:
            await member.add_roles(role)
            print(f"[AUTOROLE] Cargo {role.name} aplicado a {member}.")
        except Exception as e:
            print("[AUTOROLE] ERRO ao adicionar cargo:", e)

async def setup(bot):
    await bot.add_cog(AutoRole(bot))
