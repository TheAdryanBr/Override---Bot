import json
import asyncio
import discord
from discord.ext import commands


class EmbedSender(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # -----------------------------
    # Helper: JSON -> Embeds
    # -----------------------------
    def _parse_embeds(self, data: dict) -> list[discord.Embed]:
        embeds = []

        for e in data.get("embeds", []):
            embed = discord.Embed(
                description=e.get("description"),
                color=e.get("color")
            )

            if "title" in e:
                embed.title = e["title"]

            if "footer" in e and isinstance(e["footer"], dict):
                embed.set_footer(text=e["footer"].get("text"))

            if "author" in e and isinstance(e["author"], dict):
                embed.set_author(name=e["author"].get("name"))

            embeds.append(embed)

        return embeds

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
            "📎 Envie **um arquivo `.json`** contendo os embeds.\n"
            "O arquivo pode ser grande.\n"
            "Você tem **3 minutos**."
        )

        def check(m: discord.Message):
            return m.author == ctx.author and m.channel == ctx.channel and m.attachments

        try:
            msg = await self.bot.wait_for("message", check=check, timeout=180)
        except asyncio.TimeoutError:
            await ctx.reply("⏰ Tempo esgotado. Operação cancelada.")
            return

        attachment = msg.attachments[0]

        if not attachment.filename.lower().endswith(".json"):
            await ctx.reply("❌ O arquivo precisa ser `.json`.")
            return

        try:
            raw = await attachment.read()
            data = json.loads(raw.decode("utf-8"))
        except Exception:
            await ctx.reply("❌ Falha ao ler ou interpretar o JSON.")
            return

        embeds = self._parse_embeds(data)

        if not embeds:
            await ctx.reply("❌ Nenhum embed encontrado no JSON.")
            return

        # -----------------------------
        # Preview
        # -----------------------------
        EMBEDS_PER_MESSAGE = 10
        messages_needed = (len(embeds) + EMBEDS_PER_MESSAGE - 1) // EMBEDS_PER_MESSAGE

        preview = discord.Embed(
            title="📋 Preview do envio",
            description=(
                f"📦 **Embeds encontrados:** {len(embeds)}\n"
                f"✉️ **Mensagens necessárias:** {messages_needed}\n"
                f"📍 **Canal destino:** {channel.mention}\n\n"
                "Digite **confirmar** para enviar ou **cancelar** para abortar."
            ),
            color=0xFAA61A
        )

        await ctx.reply(embed=preview)

        def confirm_check(m: discord.Message):
            return (
                m.author.id == ctx.author.id
                and m.channel.id == ctx.channel.id
                and m.content
                and m.content.lower().strip() in ("confirmar", "cancelar")
            )

        try:
            confirm = await self.bot.wait_for("message", check=confirm_check, timeout=60)
        except asyncio.TimeoutError:
            await ctx.reply("⏰ Confirmação não recebida. Cancelado.")
            return

        if confirm.content.lower() == "cancelar":
            await ctx.reply("❌ Envio cancelado.")
            return

        # -----------------------------
        # Envio controlado
        # -----------------------------
        DELAY = 1.2

        for i in range(0, len(embeds), EMBEDS_PER_MESSAGE):
            chunk = embeds[i:i + EMBEDS_PER_MESSAGE]
            await channel.send(embeds=chunk)
            await asyncio.sleep(DELAY)

        await ctx.reply("✅ Embeds enviados com sucesso.")


# -----------------------------
# Setup
# -----------------------------
async def setup(bot):
    await bot.add_cog(EmbedSender(bot))
