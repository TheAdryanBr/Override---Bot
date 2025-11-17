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

# Nome fixo do criador
CREATOR = "theadryanbr"   # você pediu assim

CHECK_INTERVAL = 180  # 3 minutos (seguro e leve)


# ------------------------------------------------------------
# HORÁRIOS PERMITIDOS
# ------------------------------------------------------------
LIVE_WINDOWS = [
    (time(12, 0), time(15, 0)),
    (time(19, 0), time(23, 0)),
]


def _now_in_live_window():
    """Retorna True se o horário atual está dentro de qualquer janela."""
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
        self.fixed_message_id = None
        self.monitor_task.start()

    def cog_unload(self):
        if self.monitor_task.is_running():
            self.monitor_task.cancel()
        asyncio.create_task(self.session.close())

    # --------------------------------------------------------
    # Util: obter ou criar mensagem fixa
    # --------------------------------------------------------
    async def _get_or_create_fixed_message(self):
        """Pega uma mensagem fixa existente ou cria uma nova."""
        channel = self.bot.get_channel(PLATFORM_CHANNEL_ID)
        if not channel:
            return None

        # Tentar recuperar mensagem existente
        if self.fixed_message_id:
            try:
                msg = await channel.fetch_message(self.fixed_message_id)
                return msg
            except:
                pass

        # Criar nova mensagem
        try:
            msg = await channel.send("🔍 Iniciando monitoramento de plataformas...")
            self.fixed_message_id = msg.id
            return msg
        except:
            return None

    # --------------------------------------------------------
    # Rotina principal
    # --------------------------------------------------------
    @tasks.loop(seconds=CHECK_INTERVAL)
    async def monitor_task(self):
        """Faz a verificação periódica."""
        if not PLATFORM_CHANNEL_ID:
            return

        # 1) verificar se estamos dentro dos horários permitidos
        if not _now_in_live_window():
            return

        # 2) checar TikTok primeiro (prioridade)
        tt_live = await check_tiktok_live(CREATOR, session=self.session)

        if not tt_live:
            # não está ao vivo → só atualizar status simples
            await self._update_status(
                tiktok=False,
                youtube=None,
                twitch=None
            )
            return

        # ----------------------------------------------------
        # Agora que TikTok está ao vivo → verificar outras
        # ----------------------------------------------------
        yt_live = await check_youtube_live(CREATOR, session=self.session)
        tw_live = await check_twitch_live(CREATOR, session=self.session)

        await self._update_status(
            tiktok=True,
            youtube=bool(yt_live),
            twitch=bool(tw_live)
        )

    # --------------------------------------------------------
    # Função de editar mensagem fixa
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
        return "⚪ Desconhecido"

    embed = discord.Embed(
        title="📡 Status de Transmissão",
        color=discord.Color.purple(),
        timestamp=datetime.utcnow()
    )

    embed.add_field(name="TikTok", value=fmt(tiktok), inline=False)

    if tiktok:  # se TikTok estiver ao vivo → checar outras
        embed.add_field(name="YouTube", value=fmt(youtube), inline=False)
        embed.add_field(name="Twitch", value=fmt(twitch), inline=False)

    embed.set_footer(text="Atualizado automaticamente")

    # Evitar SPAM: só notificar quando mudar de offline→online
    was_live = getattr(self, "was_live", False)

    if tiktok and not was_live:
        # primeira vez que detecta live → notifica
        try:
            await channel.send(
                content=f"<@&{ROLE_ID}> 🔴 **O Adryan está AO VIVO!**",
                embed=embed
            )
        except:
            pass

    # atualizar estado interno
    self.was_live = bool(tiktok)

    # --------------------------------------------------------
    # Start na primeira inicialização do bot
    # --------------------------------------------------------
    @monitor_task.before_loop
    async def before_loop(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(PlatformMonitor(bot))

