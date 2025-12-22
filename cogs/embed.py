import json
import asyncio
import discord
from discord.ext import commands


# -----------------------------
# View de confirmação
# -----------------------------
class ConfirmView(discord.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=60)
        self.author_id = author_id
        self.confirmed: bool | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "❌ Apenas quem executou o comando pode usar.",
                ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = True
        await interaction.response.edit_message(
            content="✅ Envio confirmado. Processando...",
            view=None
        )
        self.stop()

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = False
        await interaction.response.edit_message(
            content="❌ Envio cancelado.",
            view=None
        )
        self.stop()

    # -----------------------------
    # Comando principal
    # -----------------------------
    @commands.has_permissions(administrator=True)
    @commands.command(name="sendjson")
    async def sendjson(self, ctx, channel_id: int):
        channel = ctx.guild.get_channel(channel_id)
        if not channel:
            await ctx.reply("❌ Canal não encontrado.")
            return

        await ctx.reply(
            "📎 Envie **um arquivo `.json`** com os embeds.\n"
            "Você tem **3 minutos**."
        )

        def check(m: discord.Message):
            return (
                m.author.id == ctx.author.id
                and m.channel.id == ctx.channel.id
                and m.attachments
            )

        try:
            msg = await self.bot.wait_for("message", check=check, timeout=180)
        except asyncio.TimeoutError:
            await ctx.reply("⏰ Tempo esgotado.")
            return

        attachment = msg.attachments[0]

        if not attachment.filename.lower().endswith(".json"):
            await ctx.reply("❌ O arquivo precisa ser `.json`.")
            return

        try:
            raw = await attachment.read()
            data = json.loads(raw.decode("utf-8"))
        except Exception:
            await ctx.reply("❌ Erro ao ler o JSON.")
            return

        embeds = self._parse_embeds(data)

        if not embeds:
            await ctx.reply("❌ Nenhum embed encontrado.")
            return

        # -----------------------------
        # Preview com botões
        # -----------------------------
        EMBEDS_PER_MESSAGE = 10
        messages_needed = (len(embeds) + EMBEDS_PER_MESSAGE - 1) // EMBEDS_PER_MESSAGE

        preview = discord.Embed(
            title="📋 Preview do envio",
            description=(
                f"📦 **Embeds:** {len(embeds)}\n"
                f"✉️ **Mensagens:** {messages_needed}\n"
                f"📍 **Canal:** {channel.mention}\n\n"
                "Use os botões abaixo para confirmar ou cancelar."
            ),
            color=0xFAA61A
        )

        view = ConfirmView(ctx.author.id, embeds, channel)
        preview_msg = await ctx.reply(embed=preview, view=view)

        await view.wait()

        await preview_msg.edit(view=None)

        if view.confirmed is not True:
            await ctx.reply("❌ Envio cancelado.")
            return

        # -----------------------------
        # Envio controlado
        # -----------------------------
        DELAY = 1.2

        for i in range(0, len(embeds), EMBEDS_PER_MESSAGE):
            await channel.send(embeds=embeds[i:i + EMBEDS_PER_MESSAGE])
            await asyncio.sleep(DELAY)

        await ctx.reply("✅ Embeds enviados com sucesso.")


# -----------------------------
# Setup
# -----------------------------
async def setup(bot):
    await bot.add_cog(EmbedSender(bot))
