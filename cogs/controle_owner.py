# cogs/controle_owner.py
import discord
from discord.ext import commands

class ControleOwner(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # ←←← MUDE AQUI COM SEU ID DO DISCORD (número puro, sem aspas)
        self.owner_id = 473962013031399425  # ← TROQUE POR SEU ID!!!

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # ================= DEBUG TOTAL (vai aparecer tudo no log) =================
        print(f"[DEBUG DM] Mensagem recebida!")
        print(f"    → Autor: {message.author} (ID: {message.author.id})")
        print(f"    → Tipo do canal: {message.channel.type}")   # deve mostrar "private" para DM
        print(f"    → Conteúdo: '{message.content}'")
        # =========================================================================

        # Ignora bots
        if message.author.bot:
            print("[DEBUG] Ignorado: mensagem de bot")
            return

        # Tem que ser DM (private)
        if not isinstance(message.channel, discord.DMChannel):
            print("[DEBUG] Ignorado: não é DM (é de servidor ou grupo)")
            return

        # Só o dono pode usar
        if message.author.id != self.owner_id:
            print(f"[DEBUG] Ignorado: não é o dono (owner_id = {self.owner_id})")
            return

        print("[DEBUG] PASSOU EM TODOS OS FILTROS → é o dono mandando DM!")

        # Tem que começar com >>
        if not message.content.startswith(">>"):
            print("[DEBUG] Ignorado: não começa com >>")
            return

        print("[DEBUG] Começa com >> → vai processar o comando")

        content = message.content[2:].strip()
        if not content:
            await message.reply("Uso: `>> <id-do-canal> mensagem`")
            return

        try:
            parts = content.split(" ", 1)
            channel_id = int(parts[0])
            texto = parts[1] if len(parts) > 1 else ""

            print(f"[DEBUG] Canal ID detectado: {channel_id}")
            print(f"[DEBUG] Texto a enviar: '{texto}'")

            if not texto:
                await message.reply("Você esqueceu a mensagem!")
                return

            channel = self.bot.get_channel(channel_id)
            if not channel:
                await message.reply(f"Canal não encontrado: `{channel_id}`\nVerifique o ID.")
                return

            await channel.send(texto)
            await message.add_reaction("Ok")
            print("[DEBUG] Mensagem enviada com sucesso!")

        except ValueError:
            await message.reply("ID do canal inválido! Tem que ser só número.")
            print("[DEBUG] Erro: ValueError → ID não é número")
        except discord.Forbidden:
            await message.add_reaction("Proibido")
            await message.reply("Sem permissão para falar nesse canal.")
            print("[DEBUG] Erro: Forbidden")
        except Exception as e:
            await message.add_reaction("Erro")
            await message.reply(f"Erro: `{type(e).__name__}`")
            print(f"[DEBUG] Erro inesperado: {e}")

        # Isso aqui é importante para não bloquear comandos normais
        await self.bot.process_commands(message)

async def setup(bot):
    await bot.add_cog(ControleOwner(bot))
