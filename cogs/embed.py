# cogs/embed.py
import json
import asyncio
import discord
from discord.ext import commands

MAX_PARTS = 3  # até 3 mensagens/embeds por envio

class EmbedConfirmView(discord.ui.View):
    def __init__(self, embeds: list[discord.Embed], channel_id: int, author_id: int):
        super().__init__(timeout=120)
        self.embeds = embeds
        self.channel_id = channel_id
        self.author_id = author_id

    @discord.ui.button(label="✅ Confirmar", style=discord.ButtonStyle.success, custom_id="embed_confirm")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Só o autor do comando pode confirmar
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Você não pode confirmar este embed.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            channel = await interaction.client.fetch_channel(self.channel_id)
        except discord.NotFound:
            await interaction.followup.send("❌ Canal não encontrado. Verifique o ID.", ephemeral=True)
            return
        except discord.Forbidden:
            await interaction.followup.send("❌ Não tenho permissão para enviar nesse canal.", ephemeral=True)
            return
        except Exception as e:
            await interaction.followup.send(f"❌ Erro ao acessar o canal: {e}", ephemeral=True)
            return

        # Envia os embeds em background
        async def _send_embeds():
            for emb in self.embeds:
                try:
                    await channel.send(embed=emb)
                    await asyncio.sleep(0.2)  # evita flood
                except Exception as e:
                    await interaction.followup.send(f"❌ Erro ao enviar embed: {e}", ephemeral=True)

        interaction.client.loop.create_task(_send_embeds())

        await interaction.followup.send("✅ Embed(s) enviado(s) com sucesso!", ephemeral=True)
        self.stop()

    @discord.ui.button(label="❌ Cancelar", style=discord.ButtonStyle.danger, custom_id="embed_cancel")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Você não pode cancelar este embed.", ephemeral=True)
            return

        await interaction.response.send_message("❌ Envio cancelado.", ephemeral=True)
        self.stop()


class EmbedSender(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="embedjson")
    async def embedjson(self, ctx: commands.Context, channel_id: int):
        """
        Envia embeds a partir de JSON via arquivo (.json)
        """
        if not ctx.message.attachments:
            await ctx.reply("❌ Envie um arquivo `.json` junto do comando.", mention_author=False)
            return

        attachment = ctx.message.attachments[0]

        if not attachment.filename.endswith(".json"):
            await ctx.reply("❌ O arquivo precisa ser `.json`.", mention_author=False)
            return

        data = await attachment.read()

        try:
            payload = json.loads(data.decode("utf-8"))
        except Exception:
            await ctx.reply("❌ JSON inválido.", mention_author=False)
            return

        # Aceita 1 embed ou lista
        if isinstance(payload, dict):
            payload = [payload]

        if not isinstance(payload, list):
            await ctx.reply("❌ Estrutura inválida de JSON.", mention_author=False)
            return

        if len(payload) > MAX_PARTS:
            await ctx.reply(f"❌ Máximo permitido: {MAX_PARTS} embeds por envio.", mention_author=False)
            return

        embeds: list[discord.Embed] = []
        for item in payload:
            try:
                emb = discord.Embed.from_dict(item)
                embeds.append(emb)
            except Exception:
                await ctx.reply("❌ Erro ao converter um dos embeds.", mention_author=False)
                return

        preview = discord.Embed(
            title="📋 Prévia de Envio",
            description=(
                f"Embeds prontos para envio: **{len(embeds)}**\n\n"
                "Clique em **Confirmar** para enviar ou **Cancelar**."
            ),
            color=discord.Color.blurple()
        )

        view = EmbedConfirmView(embeds, channel_id, ctx.author.id)
        await ctx.reply(embed=preview, view=view, mention_author=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(EmbedSender(bot))
