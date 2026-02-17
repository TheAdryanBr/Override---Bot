from typing import Optional, List
from datetime import datetime, timezone

import discord
from discord.ext import commands
from discord import app_commands

import utils  # <- IMPORTA O MÓDULO, não os valores
from utils import GUILD_ID  # esse pode continuar assim (constante)


# Motivos mais específicos
MOTIVO_CHOICES = [
    app_commands.Choice(name="🚫 Spam / Divulgação / Flood", value="spam"),
    app_commands.Choice(name="💬 Assédio / Ofensa / Humilhação", value="harassment"),
    app_commands.Choice(name="🤬 Discurso de ódio / Racismo / Preconceito", value="hate"),
    app_commands.Choice(name="🔪 Ameaça / Incitação à violência", value="threats"),
    app_commands.Choice(name="🕵️ Doxxing / Exposição de dados pessoais", value="doxxing"),
    app_commands.Choice(name="🎭 Fake / Impostor / Personificação", value="impersonation"),
    app_commands.Choice(name="💸 Golpe / Scam / Phishing", value="scam"),
    app_commands.Choice(name="🔞 Conteúdo sexual / NSFW", value="nsfw"),
    app_commands.Choice(name="🧒 Conteúdo envolvendo menor (gravíssimo)", value="minor"),
    app_commands.Choice(name="⚖️ Conteúdo ilegal / crimes / venda proibida", value="illegal"),
    app_commands.Choice(name="🧨 Raids / Trollagem pesada / Sabotagem", value="raid"),
    app_commands.Choice(name="📌 Quebra de regra do servidor (outros)", value="rules_other"),
]


class DenunciasCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def ensure_report_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        # ✅ usa utils.REPORT_CHANNEL_ID (fonte única)
        if utils.REPORT_CHANNEL_ID:
            ch = guild.get_channel(int(utils.REPORT_CHANNEL_ID))
            if isinstance(ch, discord.TextChannel):
                return ch
            # se não existe mais, zera
            utils.REPORT_CHANNEL_ID = 0

        # tenta achar por nome
        for c in guild.text_channels:
            if c.name.lower() in ("denuncias", "denúncias", "reports", "reportes", "modlog", "mod-log"):
                return c

        # cria canal privado
        try:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False, read_messages=False),
                guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_messages=True),
            }

            if utils.ADMIN_ROLE_ID:
                role = guild.get_role(int(utils.ADMIN_ROLE_ID))
                if role:
                    overwrites[role] = discord.PermissionOverwrite(
                        view_channel=True,
                        read_messages=True,
                        send_messages=True,
                    )

            ch = await guild.create_text_channel(
                "denuncias",
                overwrites=overwrites,
                reason="Canal de denúncias criado pelo bot",
            )
            utils.REPORT_CHANNEL_ID = ch.id
            return ch
        except Exception:
            return None

    def _compact(self, s: str, limit: int = 4000) -> str:
        s = (s or "").strip()
        if len(s) > limit:
            return s[: limit - 3] + "..."
        return s

    def _format_targets(self, targets: List[discord.Member]) -> str:
        lines = [f"- {m.mention} (`{m.id}`)" for m in targets]
        return "\n".join(lines) if lines else "—"

    @app_commands.guild_only()
    @app_commands.guilds(GUILD_ID)  # guild-only (instantâneo via !sync guild)
    @app_commands.command(
        name="denunciar",
        description="Enviar uma denúncia para a equipe (com anexos/links e motivo detalhado).",
    )
    @app_commands.describe(
        # ordem fixa
        denunciado_1="Usuário principal denunciado (Obrigatório)",
        denunciado_2="Outro usuário (opcional)",
        denunciado_3="Outro usuário (opcional)",
        denunciado_4="Outro usuário (opcional)",

        motivo="Selecione um motivo mais específico",
        detalhes="Explique o que aconteceu (Obrigatório)(quanto mais específico, melhor)",

        anexo_1="Print/vídeo/arquivo (opcional)",
        anexo_2="Print/vídeo/arquivo (opcional)",
        anexo_3="Print/vídeo/arquivo (opcional)",
        anexo_4="Print/vídeo/arquivo (opcional)",
        anexo_5="Print/vídeo/arquivo (opcional)",

        link_1="Link (opcional) – mensagem, vídeo, imagem, etc.",
        link_2="Link (opcional)",
        link_3="Link (opcional)",
    )
    @app_commands.choices(motivo=MOTIVO_CHOICES)
    async def denunciar(
        self,
        interaction: discord.Interaction,

        # (1) denunciados
        denunciado_1: discord.Member,
        denunciado_2: Optional[discord.Member] = None,
        denunciado_3: Optional[discord.Member] = None,
        denunciado_4: Optional[discord.Member] = None,

        # (2) motivo
        motivo: app_commands.Choice[str] = None,

        # (3) detalhes
        detalhes: str = None,

        # (4) evidências
        anexo_1: Optional[discord.Attachment] = None,
        anexo_2: Optional[discord.Attachment] = None,
        anexo_3: Optional[discord.Attachment] = None,
        anexo_4: Optional[discord.Attachment] = None,
        anexo_5: Optional[discord.Attachment] = None,

        link_1: Optional[str] = None,
        link_2: Optional[str] = None,
        link_3: Optional[str] = None,
    ):
        await interaction.response.defer(ephemeral=True)

        if interaction.guild is None:
            await interaction.followup.send("❌ Este comando só pode ser usado em servidores.", ephemeral=True)
            return

        if motivo is None:
            await interaction.followup.send("❌ Selecione um motivo.", ephemeral=True)
            return

        detalhes_txt = self._compact(detalhes or "", 3500)
        if not detalhes_txt:
            await interaction.followup.send("❌ Preencha os detalhes do ocorrido.", ephemeral=True)
            return

        guild = interaction.guild
        author = interaction.user
        channel_origin = interaction.channel

        report_channel = await self.ensure_report_channel(guild)
        if report_channel is None:
            await interaction.followup.send("❌ Não foi possível localizar/criar o canal de denúncias.", ephemeral=True)
            return

        # targets (remove duplicatas)
        targets_raw = [denunciado_1, denunciado_2, denunciado_3, denunciado_4]
        targets: List[discord.Member] = []
        seen = set()
        for t in targets_raw:
            if t and t.id not in seen:
                seen.add(t.id)
                targets.append(t)

        anexos = [a for a in [anexo_1, anexo_2, anexo_3, anexo_4, anexo_5] if a is not None]
        links = [l.strip() for l in [link_1, link_2, link_3] if l and l.strip()]

        ts = datetime.now(timezone.utc)
        embed = discord.Embed(
            title="🛑 Nova denúncia (via /denunciar)",
            color=discord.Color.dark_red(),
            timestamp=ts,
        )
        embed.add_field(name="Autor", value=f"{author.mention} (`{author.id}`)", inline=True)
        embed.add_field(name="Servidor", value=f"{guild.name} (`{guild.id}`)", inline=True)

        if isinstance(channel_origin, discord.abc.GuildChannel):
            embed.add_field(
                name="Canal de origem",
                value=f"{channel_origin.mention} (`{channel_origin.id}`)",
                inline=True,
            )
        else:
            embed.add_field(name="Canal de origem", value="—", inline=True)

        embed.add_field(name="Denunciado(s)", value=self._format_targets(targets), inline=False)
        embed.add_field(name="Motivo", value=motivo.name, inline=False)
        embed.add_field(name="Detalhes", value=detalhes_txt, inline=False)

        if links:
            embed.add_field(
                name="Links",
                value="\n".join(f"- {self._compact(l, 250)}" for l in links),
                inline=False,
            )

        if anexos:
            embed.add_field(
                name="Anexos",
                value="\n".join(f"- {a.filename} ({a.size} bytes)" for a in anexos[:10]),
                inline=False,
            )

        embed.set_footer(text=f"Denúncia enviada por {author.display_name} • {author.id}")

        mention_admin = ""
        if utils.ADMIN_ROLE_ID:
            role = guild.get_role(int(utils.ADMIN_ROLE_ID))
            if role:
                mention_admin = role.mention + " "

        files: List[discord.File] = []
        try:
            for a in anexos[:10]:
                files.append(await a.to_file())
        except Exception:
            files = []

        try:
            await report_channel.send(content=mention_admin, embed=embed, files=files)
        except Exception:
            await interaction.followup.send("❌ Erro ao encaminhar denúncia.", ephemeral=True)
            return

        await interaction.followup.send("✅ Denúncia enviada com sucesso.", ephemeral=True)


async def setup(bot: commands.Bot):
    # ✅ sem sync automático: você controla com !sync guild / !sync global
    await bot.add_cog(DenunciasCog(bot))