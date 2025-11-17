# cogs/voice_rooms.py
import os
import discord
from discord.ext import commands

CANAL_FIXO_CONFIG = {
    1406308661810171965: {"categoria_id": 1213316039350296637, "prefixo_nome": "Call│"},
    1404889040007725107: {"categoria_id": 1213319157639020564, "prefixo_nome": "♨│Java│"},
    1213319477429801011: {"categoria_id": 1213319157639020564, "prefixo_nome": "🪨|Bedrock|"},
    1213321053196263464: {"categoria_id": 1213319620287664159, "prefixo_nome": "🎧│Call│"},
    1213322485479637012: {"categoria_id": 1213322073594793994, "prefixo_nome": "👥│Dupla│"},
    1213322743123148920: {"categoria_id": 1213322073594793994, "prefixo_nome": "👥│Trio│"},
    1213322826564767776: {"categoria_id": 1213322073594793994, "prefixo_nome": "👥│Squad│"},
    1216123178548465755: {"categoria_id": 1216123032138154008, "prefixo_nome": "👥│Duo│"},
    1216123306579595274: {"categoria_id": 1216123032138154008, "prefixo_nome": "👥│Trio│"},
    1216123421688205322: {"categoria_id": 1216123032138154008, "prefixo_nome": "👥│Team│"},
    1213533210907246592: {"categoria_id": 1213532914520690739, "prefixo_nome": "🎧│Sala│"},
}

class VoiceRoomsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.created = {}

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        # criar
        try:
            if after.channel and after.channel.id in CANAL_FIXO_CONFIG:
                cfg = CANAL_FIXO_CONFIG[after.channel.id]
                categoria = member.guild.get_channel(cfg["categoria_id"])
                prefixo = cfg["prefixo_nome"]
                novo = await member.guild.create_voice_channel(name=f"{prefixo}{member.display_name}", category=categoria)
                await member.move_to(novo)
                self.created[novo.id] = {"owner": member.id, "fixo": after.channel.id}
            # apagar se vazio
            if before.channel and before.channel.id in self.created:
                canal = before.channel
                if len(canal.members) == 0:
                    try:
                        await canal.delete()
                        del self.created[canal.id]
                    except Exception:
                        pass
        except Exception:
            pass

async def setup(bot):
    bot.add_cog(VoiceRoomsCog(bot))
