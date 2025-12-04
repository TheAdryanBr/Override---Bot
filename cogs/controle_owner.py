# cogs/controle_owner.py
import discord
from discord.ext import commands

class ControleOwner(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # ⚠️ COLOQUE SEU ID AQUI (clique direito em você no Discord > Copiar ID)
        self.owner_id = 473962013031399425  # ← MUDE AQUI!!!

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignora mensagens de bots e que não sejam DM
        if message.author.bot:
            return
        if not isinstance(message.channel, discord.DMChannel):
            return
        if message.author.id != self.owner_id:
            return  # Só o dono pode usar

        # Processa apenas mensagens que começam com >>
        if not message.content.startswith(">>"):
            return

        # Remove o >> e separa o ID do canal do resto da mensagem
        content = message.content[2:].strip()
        if not content:
            await message.reply("Uso: `>> <id-do-canal> mensagem`")
            return

        try:
            # Separa o primeiro argumento como ID do canal
            parts = content.split(" ", 1)
            channel_id = int(parts[0])
            texto = parts[1] if len(parts) > 1 else ""

            if not texto:
                await message.reply("Você esqueceu a mensagem!")
                return

            channel = self.bot.get_channel(channel_id)
            if not channel:
                await message.reply(f"Canal não encontrado: `{channel_id}`\nVerifique o ID.")
                return

            # Envia a mensagem no canal desejado
            await channel.send(texto)
            await message.add_reaction("✅")

        except ValueError:
            await message.reply("ID do canal inválido! Tem que ser número.\nEx: `>> 123456789012345678 Olá pessoal!`")
        except discord.Forbidden:
            await message.add_reaction("❌")
            await message.reply(f"Sem permissão para falar no canal `{channel_id}`")
        except Exception as e:
            await message.add_reaction("❌")
            await message.reply(f"Erro inesperado: `{type(e).__name__}`")

    # Permite que o bot processe comandos mesmo com esse listener
    async def cog_command_error(self, ctx, error):
        pass

async def setup(bot):
    await bot.add_cog(ControleOwner(bot))
