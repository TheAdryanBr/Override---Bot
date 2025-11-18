# cogs/platform_monitor.py
import os
import asyncio
from datetime import datetime, time
import discord
from discord.ext import commands, tasks

import aiohttp

# Platform scrapers
from platforms.tiktok import check_tiktok_live
from platforms.youtube import check_youtube_live
from platforms.twitch import check_twitch_live


# ------------------------------------------------------------
# CONFIGS
# ------------------------------------------------------------
PLATFORM_CHANNEL_ID = int(os.getenv("PLATFORM_STATUS_CHANNEL_ID", 0))

CREATOR = "theadryanbr"

CHECK_INTERVAL = 180  # 3 min


# ------------------------------------------------------------
# JANELAS DE HORÁRIO
# ------------------------------------------------------------
LIVE_WINDOWS = [
    (time(12, 0), time(15, 0)),
    (time(19, 0), time(23, 0)),
]


def _now_in_live_window():
    now = datetime.now().time()
    for start, end in LIVE_WINDOWS:
        if start <= now <= end:
            return True
    return False


# ------------------------------------------------------------
# COG
# ------------------------------------------------------------
class PlatformMonitor(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()
        self.was_live = False
        self.monitor_task.start()

    def cog_unload(self):
        if self.monitor_task.is_running():
            self.monitor_task.cancel()
        asyncio.create_task(self.session.close())

# ------------------Comando de testes------------------------
        
        @commands.command(name="testlive")
    async def testlive(self, ctx):
        """
        Simula uma live no TikTok sem realmente entrar ao vivo.
        Gera o mesmo embed que o sistema real enviaria.
        """

        # Cargo a ser mencionado
        role_id = 1254470641944494131
        role = ctx.guild.get_role(role_id)
        mention_text = role.mention if role else "@live"

        # --- Dados simulados do TikTok ---
        tiktok_title = "TESTE — Live de Simulação"
        tiktok_game = "Just Chatting (Simulação)"
        tiktok_url = "https://www.tiktok.com/@TheAdryanBr/live"

        # --- Check falso das outras plataformas ---
        yt_live = True      # simulação
        twitch_live = False # simulação

        yt_status = "🔴 Ao vivo" if yt_live else "⚫ Offline"
        twitch_status = "🔴 Ao vivo" if twitch_live else "⚫ Offline"

        # --- Criação do embed ---
        embed = discord.Embed(
            title=f"🔴 Live no TikTok — @TheAdryanBr",
            description=f"**{tiktok_title}**\n🎮 Jogo: **{tiktok_game}**\n\n👉 **Assista agora:**\n{tiktok_url}",
            color=discord.Color.red()
        )

        embed.set_thumbnail(url="https://i.imgur.com/qU9f7uf.png")

        embed.add_field(
            name="📌 Outras plataformas",
            value=(
                f"**YouTube:** {yt_status}\n"
                f"**Twitch:** {twitch_status}"
            ),
            inline=False
        )

        embed.set_footer(text="Simulação — Nenhuma plataforma foi realmente verificada")

        await ctx.send(f"{mention_text}", embed=embed)
    # --------------------------------------------------------
    # ROTINA PRINCIPAL
    # --------------------------------------------------------
    @tasks.loop(seconds=CHECK_INTERVAL)
    async def monitor_task(self):
        if not PLATFORM_CHANNEL_ID:
            return

        if not _now_in_live_window():
            return

        # 1 — TikTok primeiro
        tt_live = await check_tiktok_live(CREATOR, session=self.session)

        # Se não está em live no TikTok, só atualiza o status e para
        if not tt_live:
            await self._update_status(
                tiktok=False,
                youtube=None,
                twitch=None
            )
            return

        # 2 — Agora YouTube e Twitch
        yt_live = await check_youtube_live(CREATOR, session=self.session)
        tw_live = await check_twitch_live(CREATOR, session=self.session)

        await self._update_status(
            tiktok=True,
            youtube=bool(yt_live),
            twitch=bool(tw_live)
        )

    # --------------------------------------------------------
    # ATUALIZA STATUS E NOTIFICA
    # --------------------------------------------------------
    async def _update_status(self, tiktok, youtube, twitch):
        channel = self.bot.get_channel(PLATFORM_CHANNEL_ID)
        if not channel:
            return

        ROLE_ID = 1254470641944494131

        def fmt(state):
            if state is True:
                return "🟢 Ao vivo"
            if state is False:
                return "🔴 Offline"
            return "⚪ Indefinido"

        embed = discord.Embed(
            title="📡 Status de Transmissão",
            color=discord.Color.purple(),
            timestamp=datetime.utcnow()
        )

        embed.add_field(name="TikTok", value=fmt(tiktok), inline=False)

        if tiktok:
            embed.add_field(name="YouTube", value=fmt(youtube), inline=False)
            embed.add_field(name="Twitch", value=fmt(twitch), inline=False)

        embed.set_footer(text="Atualizado automaticamente")

        # -------------------------
        # Avisar somente quando entrar ao vivo
        # -------------------------
        if tiktok and not self.was_live:
            try:
                await channel.send(
                    content=f"<@&{ROLE_ID}> 🔴 **O Adryan está AO VIVO!**",
                    embed=embed
                )
            except Exception:
                pass

        self.was_live = bool(tiktok)

    @monitor_task.before_loop
    async def before_loop(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(PlatformMonitor(bot))
