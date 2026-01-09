import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

import aiohttp
import discord
from discord.ext import commands
import re
import json

log = logging.getLogger("platform_monitor")


# =========================================================
# 1️⃣ MODELO DE DADOS
# =========================================================

class LiveData:
    def __init__(self, username: str, title: str, thumbnail: Optional[str],
                 profile_image: Optional[str], game: Optional[str], started_at: datetime):
        self.username = username
        self.title = title
        self.thumbnail = thumbnail
        self.profile_image = profile_image
        self.game = game
        self.started_at = started_at


# =========================================================
# 2️⃣ GERENCIADOR DE ESTADO
# =========================================================

class LiveStateManager:
    def __init__(self):
        self.is_online = False
        self.embed_sent = False
        self.current_live_id: Optional[str] = None

    def mark_online(self, live_id: str):
        if self.current_live_id != live_id:
            log.info("[State] Nova live detectada")
            self.current_live_id = live_id
            self.embed_sent = False
        self.is_online = True

    def mark_offline(self):
        log.info("[State] Live finalizada")
        self.is_online = False
        self.embed_sent = False
        self.current_live_id = None

    def can_send_embed(self) -> bool:
        return self.is_online and not self.embed_sent

    def mark_embed_sent(self):
        self.embed_sent = True
        log.info("[State] Embed marcado como enviado")


# =========================================================
# 3️⃣ COLETOR REAL
# =========================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://www.tiktok.com/",
}


class LiveDataCollector:
    async def collect(self, username: str) -> Optional[LiveData]:
        # 1️⃣ Tentativa via endpoint oficial
        url = f"https://www.tiktok.com/api/user/detail/?uniqueId={username}"
        async with aiohttp.ClientSession(headers=HEADERS) as session:
            try:
                async with session.get(url) as resp:
                    text = await resp.text()
                    if not text.startswith("{"):
                        log.warning("[Collector] Resposta não JSON")
                        return None
                    data = json.loads(text)
            except Exception as e:
                log.exception(f"[Collector] Falha ao pegar endpoint: {e}")
                return None

        user = data.get("userInfo", {}).get("user")
        if not user:
            log.warning("[Collector] User info não encontrada")
            return None

        room_id = user.get("roomId")
        if not room_id:
            log.warning("[Collector] Usuário offline")
            return None

        title = user.get("liveRoom", {}).get("title") or "🔴 LIVE NO TIKTOK"
        thumbnail = user.get("liveRoom", {}).get("coverUrl")
        profile_image = user.get("avatarLarger")
        game = user.get("liveRoom", {}).get("gameName")

        started_at = datetime.now(timezone.utc)

        return LiveData(
            username=username,
            title=title,
            thumbnail=thumbnail,
            profile_image=profile_image,
            game=game,
            started_at=started_at
        )


# =========================================================
# 4️⃣ BUILDER DE EMBED
# =========================================================

class EmbedBuilder:
    def build(self, data: LiveData) -> discord.Embed:
        embed = discord.Embed(
            title=data.title,
            description=f"@{data.username}",
            color=discord.Color.red(),
            timestamp=data.started_at
        )

        if data.game:
            embed.add_field(name="🎮 Jogo", value=data.game, inline=False)

        if data.profile_image:
            embed.set_author(name=data.username, icon_url=data.profile_image)

        if data.thumbnail:
            embed.set_image(url=data.thumbnail)

        embed.set_footer(text="YouTube: 🔴 Offline | Twitch: 🔴 Offline")

        return embed


# =========================================================
# 5️⃣ DISPATCHER
# =========================================================

class EmbedDispatcher:
    def __init__(self, bot: commands.Bot, channel_id: int, state: LiveStateManager):
        self.bot = bot
        self.channel_id = channel_id
        self.state = state

    async def dispatch(self, embed: discord.Embed):
        if not self.state.can_send_embed():
            log.warning("[Dispatcher] Embed ignorado (já enviado ou offline)")
            return

        channel = self.bot.get_channel(self.channel_id)
        if not channel:
            log.error("[Dispatcher] Canal não encontrado")
            return

        await channel.send(embed=embed)
        self.state.mark_embed_sent()


# =========================================================
# 6️⃣ COG PRINCIPAL
# =========================================================

class PlatformMonitor(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

        self.username = "theadryanbr"
        self.channel_id = 1214687236331667497

        self.state = LiveStateManager()
        self.collector = LiveDataCollector()
        self.builder = EmbedBuilder()
        self.dispatcher = EmbedDispatcher(bot, self.channel_id, self.state)

        self._dispatcher_task: Optional[asyncio.Task] = None

        log.info("[PlatformMonitor] Inicializado")

    async def cog_load(self):
        log.info("[PlatformMonitor] Dispatcher iniciado")
        self._dispatcher_task = asyncio.create_task(self.live_dispatch_loop())

    async def cog_unload(self):
        if self._dispatcher_task:
            self._dispatcher_task.cancel()
            log.info("[PlatformMonitor] Dispatcher cancelado")

    async def live_dispatch_loop(self):
        await self.bot.wait_until_ready()
        log.info("[PlatformMonitor] Dispatcher em execução")

        while not self.bot.is_closed():
            try:
                if self.state.can_send_embed():
                    data = await self.collector.collect(self.username)
                    if data:
                        embed = self.builder.build(data)
                        await self.dispatcher.dispatch(embed)
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.exception(f"[Dispatcher] Erro inesperado: {e}")
                await asyncio.sleep(15)

    # 🔌 HOOKS PÚBLICOS — CHAMAR DO WS
    def on_live_online(self, live_id: str):
        self.state.mark_online(live_id)

    def on_live_offline(self):
        self.state.mark_offline()


# =========================================================
# 7️⃣ SETUP
# =========================================================

async def setup(bot: commands.Bot):
    await bot.add_cog(PlatformMonitor(bot))