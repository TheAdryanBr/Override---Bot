import asyncio
import logging
import time
from typing import Optional, Dict, Tuple, Any

import discord
from discord.ext import commands

from webhook_server import webhook_queue, ensure_webhook_server
from utils import PLATFORM_LIVE_CHANNEL_ID, PLATFORM_PING_ROLE_ID

log = logging.getLogger("platform_monitor")


def _norm(x: Any) -> Optional[str]:
    if x is None:
        return None
    if not isinstance(x, str):
        x = str(x)
    x = x.strip()
    return x or None


def _empty(v: Any) -> bool:
    return v in (None, "", [], {}, ())


def _get(payload: dict, *keys: str):
    for k in keys:
        if k in payload and not _empty(payload[k]):
            return payload[k]
    return None


def _deep_get(obj: Any, keys: set[str]) -> Any:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in keys and not _empty(v):
                return v
        for v in obj.values():
            found = _deep_get(v, keys)
            if not _empty(found):
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _deep_get(item, keys)
            if not _empty(found):
                return found
    return None


def _extract(payload: dict):
    base = payload
    data = payload.get("data") if isinstance(payload.get("data"), dict) else None
    if data:
        merged = dict(data)
        merged.update({k: v for k, v in base.items() if k != "data"})
        payload = merged

    event = _norm(_get(payload, "event", "type", "action", "name"))
    username = _norm(_get(payload, "username", "unique_id", "uniqueId", "user"))
    if username:
        username = username.lstrip("@")

    title = _norm(_get(payload, "title", "live_title", "liveTitle", "room_title", "roomTitle", "roomTitleText"))
    game = _norm(_get(payload, "game", "gameName", "game_name", "category", "category_name", "categoryName", "partitionName"))
    thumb = _norm(_get(payload, "thumb", "thumbnail", "thumb_url", "thumbUrl", "cover", "coverUrl", "cover_url", "coverURL", "coverImageUrl"))
    live_url = _norm(_get(payload, "live_url", "liveUrl", "shareUrl", "share_url", "url", "link"))

    # deep fallback (quando vier aninhado)
    if not title:
        title = _norm(_deep_get(base, {"title", "live_title", "liveTitle", "room_title", "roomTitle", "roomTitleText", "roomName"}))
    if not game:
        game = _norm(_deep_get(base, {"game", "gameName", "game_name", "category", "category_name", "categoryName", "partitionName", "subCategoryName"}))
    if not thumb:
        thumb = _norm(_deep_get(base, {"thumb", "thumbnail", "thumb_url", "thumbUrl", "cover", "coverUrl", "cover_url", "coverURL", "coverImageUrl", "roomCover"}))
    if not live_url:
        live_url = _norm(_deep_get(base, {"live_url", "liveUrl", "shareUrl", "share_url", "url", "link"}))

    return event.lower() if event else None, username, title, game, thumb, live_url


def _build_live_embed(
    username: str,
    title: Optional[str],
    game: Optional[str],
    thumb: Optional[str],
    live_url: Optional[str],
) -> discord.Embed:
    url = live_url or f"https://www.tiktok.com/@{username}/live"

    embed = discord.Embed(
        title=title or "🔴 AO VIVO NO TIKTOK",
        url=url,
        description=f'🎮 Jogo: {game or "Sem informação"}',
        color=discord.Color.red(),
    )

    if thumb:
        embed.set_image(url=thumb)

    # sem footer (você pediu)
    return embed


class PlatformMonitor(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

        self.live_active: bool = False
        self.live_username: Optional[str] = None
        self.live_message: Optional[discord.Message] = None

        self._last_event_ts: Dict[Tuple[str, str], float] = {}
        self.task: Optional[asyncio.Task] = None

    async def cog_load(self):
        await ensure_webhook_server()
        self.task = asyncio.create_task(self.webhook_consumer())

    async def cog_unload(self):
        if self.task:
            self.task.cancel()

    async def webhook_consumer(self):
        await self.bot.wait_until_ready()
        log.info("[PlatformMonitor] Consumer ativo")

        while not self.bot.is_closed():
            got_item = False
            try:
                payload = await asyncio.wait_for(webhook_queue.get(), timeout=5.0)
                got_item = True

                event, username, title, game, thumb, live_url = _extract(payload)
                src = payload.get("source_event") if isinstance(payload, dict) else None
                log.info(
                    f"[Webhook] event={event} src={src} username={username} "
                    f"title={bool(title)} game={bool(game)} thumb={bool(thumb)}"
                )

                if not event or not username:
                    log.warning(f"[Webhook] Payload inválido (faltando event/username): {payload}")
                    continue

                now = time.time()
                key = (event, username)
                window = 10 if event == "live_end" else 15
                if now - self._last_event_ts.get(key, 0.0) < window:
                    continue
                self._last_event_ts[key] = now

                if event in ("live_start", "stream_start", "online"):
                    await self.handle_live_start(username, title, game, thumb, live_url)
                elif event in ("live_info", "stream_info", "update"):
                    await self.handle_live_info(username, title, game, thumb, live_url)
                elif event in ("live_end", "stream_end", "offline"):
                    await self.handle_live_end(username)
                else:
                    log.info(f"[Webhook] Evento ignorado: {event}")

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception:
                log.exception("[PlatformMonitor] Erro no consumer")
            finally:
                if got_item:
                    try:
                        webhook_queue.task_done()
                    except Exception:
                        pass

    async def _get_channel(self) -> discord.abc.Messageable:
        channel = self.bot.get_channel(PLATFORM_LIVE_CHANNEL_ID)
        if channel is None:
            channel = await self.bot.fetch_channel(PLATFORM_LIVE_CHANNEL_ID)
        return channel

    async def handle_live_start(
        self,
        username: str,
        title: Optional[str],
        game: Optional[str],
        thumb: Optional[str],
        live_url: Optional[str],
    ):
        if self.live_active and self.live_username == username:
            return

        channel = await self._get_channel()

        self.live_active = True
        self.live_username = username

        embed = _build_live_embed(username, title, game, thumb, live_url)

        allowed = discord.AllowedMentions(roles=True)
        self.live_message = await channel.send(
            content=f"<@&{PLATFORM_PING_ROLE_ID}>",
            embed=embed,
            allowed_mentions=allowed,
        )

    async def handle_live_info(
        self,
        username: str,
        title: Optional[str],
        game: Optional[str],
        thumb: Optional[str],
        live_url: Optional[str],
    ):
        # se ainda não anunciou, o primeiro info vira start (pinga uma vez)
        if (not self.live_active) or (not self.live_message) or (self.live_username != username):
            await self.handle_live_start(username, title, game, thumb, live_url)
            return

        embed = _build_live_embed(username, title, game, thumb, live_url)
        await self.live_message.edit(embed=embed)

    async def handle_live_end(self, username: str):
        if not self.live_active or self.live_username != username:
            return

        self.live_active = False
        self.live_username = None

        if self.live_message:
            embed = discord.Embed(
                title="⚫ LIVE ENCERRADA",
                color=discord.Color.dark_grey(),
            )
            try:
                await self.live_message.edit(embed=embed)
            except Exception:
                pass
            self.live_message = None


async def setup(bot):
    await bot.add_cog(PlatformMonitor(bot))