# cogs/voice_rooms.py
import discord
from discord.ext import commands

CANAL_FIXO_CONFIG = {
    1406308661810171965: {"categoria_id": 1213316039350296637, "prefixo_nome": "🎧|Lobby│"},
    1404889040007725107: {"categoria_id": 1213319157639020564, "prefixo_nome": "♨│Java│"},
    1213319477429801011: {"categoria_id": 1213319157639020564, "prefixo_nome": "🪨|Bedrock|"},
    1213321053196263464: {"categoria_id": 1213319620287664159, "prefixo_nome": "🎧│Lobby│"},
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
        # mapa de canais criados pelo bot: {channel_id: {"owner": owner_id, "fixo": fixo_id}}
        self.created = {}

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        try:
            # --- criação de sala dinâmica ao entrar em canal fixo ---
            if after.channel and after.channel.id in CANAL_FIXO_CONFIG:
                cfg = CANAL_FIXO_CONFIG[after.channel.id]
                categoria = member.guild.get_channel(cfg["categoria_id"])
                prefixo = cfg["prefixo_nome"]
                # cria e move
                novo = await member.guild.create_voice_channel(name=f"{prefixo}{member.display_name}", category=categoria)
                await member.move_to(novo)
                # registra como criado pelo bot
                self.created[novo.id] = {"owner": member.id, "fixo": after.channel.id}

            # --- remoção simples se o canal deixado for um criado e agora vazio ---
            if before.channel and before.channel.id in self.created:
                canal = before.channel
                if len(canal.members) == 0:
                    try:
                        await canal.delete()
                        # remove do registro se estava lá
                        if canal.id in self.created:
                            del self.created[canal.id]
                    except Exception as e:
                        # debug leve - você pode trocar por logging se quiser
                        print(f"[VoiceRooms] não foi possível deletar canal {canal.id}: {e}")

            # --- camada extra: varre canais na(s) categoria(s) configurada(s) e apaga vazios não-fixos ---
            # Executa essa varredura sempre que alguém sai (ou troca de canal) para "limpar" sobras.
            # Limitamos a varredura às categorias que constam no CANAL_FIXO_CONFIG para evitar deletar canais fora do escopo.
            # Não tocamos nos canais listados como CANAL_FIXO_CONFIG keys.
            if before.channel:  # houve saída de algum canal
                guild = member.guild
                main_channel_ids = set(CANAL_FIXO_CONFIG.keys())
                allowed_category_ids = {cfg["categoria_id"] for cfg in CANAL_FIXO_CONFIG.values()}

                for vc in list(guild.voice_channels):
                    # ignora canais que são os canais fixos
                    if vc.id in main_channel_ids:
                        continue
                    # só analisa canais dentro das categorias configuradas (protege canais de outras partes do servidor)
                    if not vc.category or vc.category.id not in allowed_category_ids:
                        continue
                    # se estiver vazio, tenta deletar
                    if len(vc.members) == 0:
                        try:
                            # tenta deletar; apenas se bot tiver permissões
                            if vc.permissions_for(guild.me).manage_channels:
                                await vc.delete()
                                # remove do registro created caso exista
                                if vc.id in self.created:
                                    del self.created[vc.id]
                                print(f"[VoiceRooms] canal {vc.name} ({vc.id}) deletado por estar vazio.")
                            else:
                                print(f"[VoiceRooms] sem permissão para deletar canal {vc.name} ({vc.id}).")
                        except Exception as e:
                            print(f"[VoiceRooms] erro ao deletar canal {vc.name} ({vc.id}): {e}")

        except Exception as e:
            # evita que exceptions quebrem o listener; log para debug
            print(f"[VoiceRooms] erro no on_voice_state_update: {e}")

async def setup(bot):
    await bot.add_cog(VoiceRoomsCog(bot))
