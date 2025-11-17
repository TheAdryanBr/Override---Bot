# cogs/denuncias.py
import os
from typing import Optional
from datetime import datetime, timezone

import discord
from discord.ext import commands
from discord import app_commands

REPORT_CHANNEL_ID = int(os.environ.get("REPORT_CHANNEL_ID", 0))
ADMIN_ROLE_ID = int(os.environ.get("ADMIN_ROLE_ID", 0))

CATEGORY_CHOICES = [
    app_commands.Choice(name="Spam / Publicidade", value="spam"),
    app_commands.Choice(name="Assédio / Abuso", value="assedio"),
    app_commands.Choice(name="Conteúdo ilegal / perigoso", value="ilegal"),
    app_commands.Choice(name="Violação de regras (outros)", value="outro"),
]

class DenunciasCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def ensure_report_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        global REPORT_CHANNEL_ID
        if REPORT_CHANNEL_ID:
            ch = guild.get_channel(REPORT_CHANNEL_ID)
            if isinstance(ch, discord.TextChannel):
                return ch
            REPORT_CHANNEL_ID = 0

        for c in guild.text_channels:
            if c.name.lower() in ("denuncias", "denúncias", "reports"):
                return c

        try:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False, read_messages=False),
                guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_messages=True)
            }
            if ADMIN_ROLE_ID:
                role = guild.get_role(ADMIN_ROLE_ID)
                if role:
                    overwrites[role] = discord.PermissionOverwrite(view_channel=True, read_messages=True, send_messages=True)
            ch = await guild.create_text_channel("denuncias", overwrites=overwrites, reason="Canal de denúncias criado pelo bot")
            REPORT_CHANNEL_ID = ch.id
            return ch
        except Exception:
            return None

    @app_commands.command(name="denunciar", description="Enviar denúncia para a equipe (admins receberão).")
    @app_commands.describe(
        categoria="Categoria da denúncia",
        detalhes="Descreva o que aconteceu (opcional).",
        link="Link de referência (opcional)",
    )
    @app_commands.choices(categoria=CATEGORY_CHOICES)
    async def denunciar(self, interaction: discord.Interaction, categoria: app_commands.Choice[str], detalhes: Optional[str] = None, link: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)
        if interaction.guild is None:
            await interaction.followup.send("❌ Este comando só pode ser usado em servidores.", ephemeral=True)
            return
        guild = interaction.guild
        author = interaction.user
        channel_origin = interaction.channel

        report_channel = await self.ensure_report_channel(guild)
        if report_channel is None:
            await interaction.followup.send("❌ Não foi possível localizar/criar o canal de denúncias. Contate a staff.", ephemeral=True)
            return

        ts = datetime.now(timezone.utc)
        embed = discord.Embed(title="🛑 Nova denúncia (via /denunciar)", color=discord.Color.dark_red(), timestamp=ts)
        embed.add_field(name="Autor", value=f"{author} (`{author.id}`)", inline=True)
        embed.add_field(name="Servidor", value=f"{guild.name} (`{guild.id}`)", inline=True)
        embed.add_field(name="Canal de origem", value=f"{channel_origin.mention} (`{channel_origin.id}`)", inline=True)
        embed.add_field(name="Categoria", value=categoria.name, inline=True)

        if detalhes:
            txt = detalhes.strip()
            if len(txt) > 4000:
                txt = txt[:3997] + "..."
            embed.add_field(name="Descrição", value=txt, inline=False)

        if link:
            embed.add_field(name="Link", value=link, inline=False)

        embed.set_footer(text=f"Denúncia enviada por {author.display_name} • {author.id}")

        mention_admin = ""
        if ADMIN_ROLE_ID:
            role = guild.get_role(ADMIN_ROLE_ID)
            if role:
                mention_admin = role.mention + " "

        try:
            await report_channel.send(content=mention_admin, embed=embed)
        except Exception:
            await interaction.followup.send("❌ Erro ao encaminhar denúncia. Tente novamente mais tarde.", ephemeral=True)
            return

        await interaction.followup.send("✅ Denúncia enviada com sucesso. A equipe responsável será notificada.", ephemeral=True)

def setup(bot):
    bot.add_cog(DenunciasCog(bot))
