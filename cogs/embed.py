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
            "📥 Envie até **3 mensagens** contendo JSON.\n"
            "Digite **finalizar** quando terminar."
        )

        collected_embeds: list[discord.Embed] = []

        MAX_JSON_MESSAGES = 3
        TIMEOUT = 180  # segundos
        EMBEDS_PER_MESSAGE = 10
        DELAY = 1.2

        def check(m: discord.Message):
            return m.author == ctx.author and m.channel == ctx.channel

        for _ in range(MAX_JSON_MESSAGES):
            try:
                msg = await self.bot.wait_for("message", check=check, timeout=TIMEOUT)
            except asyncio.TimeoutError:
                await ctx.reply("⏰ Tempo esgotado. Operação cancelada.")
                return

            if msg.content.lower().strip() == "finalizar":
                break

            try:
                data = json.loads(msg.content)
            except json.JSONDecodeError:
                await ctx.reply("❌ JSON inválido. Operação cancelada.")
                return

            embeds = self._parse_embeds(data)
            if not embeds:
                await ctx.reply("❌ Nenhum embed encontrado nesse JSON.")
                return

            collected_embeds.extend(embeds)

        if not collected_embeds:
            await ctx.reply("❌ Nenhum embed para enviar.")
            return

        # -----------------------------
        # Envio controlado
        # -----------------------------
        for i in range(0, len(collected_embeds), EMBEDS_PER_MESSAGE):
            chunk = collected_embeds[i:i + EMBEDS_PER_MESSAGE]
            await channel.send(embeds=chunk)
            await asyncio.sleep(DELAY)

        await ctx.reply("✅ Embeds enviados com sucesso.")


# -----------------------------
# Setup do Cog
# -----------------------------
async def setup(bot):
    await bot.add_cog(EmbedSender(bot))

