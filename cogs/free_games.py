import asyncio
import discord
from discord.ext import commands
import aiohttp
import re
from bs4 import BeautifulSoup
from collections import deque
from urllib.parse import urlsplit, urlunsplit

from utils import (
    FREESTUFF_TEST_GUILD_ID,       # Servidor A (onde tem FreeStuff + Override)
    FREESTUFF_TEST_CHANNEL_ID,     # Canal A (onde o FreeStuff posta) - pode ser canal "pai"
    FREESTUFF_MAIN_CHANNEL_ID,     # Canal B (destino)
    FREESTUFF_PING_ROLE_ID,        # Cargo no servidor B (opcional)
    FREESTUFF_BOT_ID,              # ID do bot FreeStuff
)

STEAM_REGEX = r"https?://store\.steampowered\.com/app/\d+(?:/|$)[^\s<>\]]*"
EPIC_REGEX  = r"https?://store\.epicgames\.com/[^\s<>\]]+"
GOG_REGEX   = r"https?://www\.gog\.com/en/game/[^\s<>\]]+"
GENERIC_URL = r"https?://[^\s<>\]]+"

MAX_CACHE = 200
DEBUG = True  # desligue quando estabilizar


class FreeStuffMonitor(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

        self.sent_cache = set()
        self.sent_order = deque(maxlen=MAX_CACHE)

        self.session = aiohttp.ClientSession(
            headers={
                "User-Agent": "Mozilla/5.0 (FreeStuffRelay/1.0)",
                "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
            }
        )

    def cog_unload(self):
        # bot.loop é depreciado; use asyncio.create_task
        if not self.session.closed:
            asyncio.create_task(self.session.close())

    # ─────────────────────────────
    # LISTENER
    # ─────────────────────────────
    @commands.Cog.listener()
    async def on_message(self, msg: discord.Message):
        if not msg.guild:
            return

        # Debug útil: confirma se o listener está recebendo mensagens do lugar certo
        if DEBUG and msg.guild.id == FREESTUFF_TEST_GUILD_ID:
            if msg.channel.id == FREESTUFF_TEST_CHANNEL_ID or (
                isinstance(msg.channel, discord.Thread) and msg.channel.parent_id == FREESTUFF_TEST_CHANNEL_ID
            ):
                print(
                    "[FreeStuff][DEBUG] Capturado no fonte:",
                    f"guild={msg.guild.id} channel={msg.channel.id} parent={getattr(msg.channel, 'parent_id', None)}",
                    f"author={msg.author} author_id={msg.author.id} webhook_id={msg.webhook_id}",
                    f"embeds={len(msg.embeds)} content_len={len(msg.content or '')}"
                )

        # Filtro servidor FONTE (Servidor A)
        if msg.guild.id != FREESTUFF_TEST_GUILD_ID:
            return

        # Filtro canal FONTE (aceita também mensagens em THREAD do canal)
        is_source_channel = (msg.channel.id == FREESTUFF_TEST_CHANNEL_ID)
        is_source_thread = isinstance(msg.channel, discord.Thread) and (msg.channel.parent_id == FREESTUFF_TEST_CHANNEL_ID)
        if not (is_source_channel or is_source_thread):
            return

        # Só mensagens do bot FreeStuff (ou webhook com mesmo nome, se você quiser permitir)
        if msg.author.id != FREESTUFF_BOT_ID:
            if DEBUG:
                print(f"[FreeStuff][DEBUG] Ignorado: author_id={msg.author.id} (esperado {FREESTUFF_BOT_ID}) webhook_id={msg.webhook_id}")
            return

        if not msg.embeds:
            if DEBUG:
                print("[FreeStuff][DEBUG] Ignorado: msg sem embeds (isso costuma ser MESSAGE CONTENT INTENT faltando)")
            return

        embed = next((e for e in msg.embeds if self.embed_has_any_text(e)), None)
        if not embed:
            if DEBUG:
                print("[FreeStuff][DEBUG] Ignorado: embeds vazios (sem texto/fields/url)")
            return

        platform, url = self.extract_platform_and_url(embed)

        # Fallback: se não bater Steam/Epic/GOG, pega qualquer URL (e ainda encaminha)
        if not url:
            text = self.extract_text_from_embed(embed)
            m = re.search(GENERIC_URL, text)
            if m:
                url = m.group(0)
                platform = platform or "Link"
                if DEBUG:
                    print("[FreeStuff][DEBUG] Fallback URL genérica:", url)

        if not url:
            if DEBUG:
                print("[FreeStuff][DEBUG] Não achou URL no embed. Dump:")
                print(self.debug_embed_dump(embed))
            return

        key = f"{platform}:{url}"
        if key in self.sent_cache:
            if DEBUG:
                print("[FreeStuff][DEBUG] Duplicado no cache:", key)
            return
        self._cache_add(key)

        info = await self.fetch_game_info(platform, url) if platform in ("Steam", "Epic Games", "GOG") else self.empty_info()
        final_embed = self.build_final_embed(platform or "Promo", embed, url, info)

        # Canal DESTINO (Servidor B)
        channel = self.bot.get_channel(FREESTUFF_MAIN_CHANNEL_ID)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(FREESTUFF_MAIN_CHANNEL_ID)
            except Exception as e:
                print(f"[FreeStuff] Não consegui fetch_channel do destino: {e}")
                return

        content = "🎮 **Novo jogo gratuito disponível!**"
        if FREESTUFF_PING_ROLE_ID and FREESTUFF_PING_ROLE_ID != 0:
            content += f" <@&{FREESTUFF_PING_ROLE_ID}>"

        try:
            await channel.send(
                content=content,
                embed=final_embed,
                allowed_mentions=discord.AllowedMentions(roles=True)
            )
            if DEBUG:
                print(f"[FreeStuff][DEBUG] Enviado para destino: {platform} - {url}")
        except Exception as e:
            print(f"[FreeStuff] Erro ao enviar mensagem: {e}")

    # ─────────────────────────────
    # HELPERS
    # ─────────────────────────────
    def embed_has_any_text(self, e: discord.Embed) -> bool:
        if (e.title or e.description or e.url):
            return True
        if e.fields:
            return True
        if getattr(e.footer, "text", None):
            return True
        if getattr(e.author, "name", None):
            return True
        return False

    def extract_text_from_embed(self, e: discord.Embed) -> str:
        parts = []
        parts += [e.title or "", e.description or "", e.url or ""]

        if getattr(e.author, "name", None):
            parts.append(e.author.name)
        if getattr(e.footer, "text", None):
            parts.append(e.footer.text)

        for f in (e.fields or []):
            parts.append(f.name or "")
            parts.append(f.value or "")

        if getattr(e.thumbnail, "url", None):
            parts.append(e.thumbnail.url)
        if getattr(e.image, "url", None):
            parts.append(e.image.url)

        return " ".join(p for p in parts if p).strip()

    def _normalize_steam_url(self, url: str) -> str:
        # Evita quebrar URL com querystring (ex: ...?snr=...).
        parts = urlsplit(url)
        path = parts.path
        if not path.endswith("/"):
            path += "/"
        return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))

    def extract_platform_and_url(self, embed: discord.Embed):
        text = self.extract_text_from_embed(embed)

        for name, regex in (
            ("Steam", STEAM_REGEX),
            ("Epic Games", EPIC_REGEX),
            ("GOG", GOG_REGEX),
        ):
            match = re.search(regex, text)
            if match:
                url = match.group(0)
                if name == "Steam":
                    url = self._normalize_steam_url(url)
                return name, url

        return None, None

    def debug_embed_dump(self, e: discord.Embed) -> str:
        out = []
        out.append(f"title={e.title!r}")
        out.append(f"description={(e.description or '')[:200]!r}")
        out.append(f"url={e.url!r}")
        out.append(f"author={(getattr(e.author,'name',None))!r}")
        out.append(f"footer={(getattr(e.footer,'text',None))!r}")
        out.append(f"fields={len(e.fields or [])}")
        if e.fields:
            out.append(f"field0_name={(e.fields[0].name or '')[:80]!r}")
            out.append(f"field0_value={(e.fields[0].value or '')[:200]!r}")
        return " | ".join(out)

    def _cache_add(self, key: str):
        self.sent_cache.add(key)
        self.sent_order.append(key)
        while len(self.sent_cache) > MAX_CACHE:
            old = self.sent_order.popleft()
            self.sent_cache.discard(old)

    # ─────────────────────────────
    # SCRAPING
    # ─────────────────────────────
    async def fetch_game_info(self, platform, url):
        try:
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=12), allow_redirects=True) as resp:
                html = await resp.text()
        except Exception:
            return self.empty_info()

        soup = BeautifulSoup(html, "html.parser")

        try:
            if platform == "Steam":
                desc = soup.find("div", id="game_area_description")
                details = soup.select_one(".details_block")
                return {
                    "desc": desc.get_text("\n", strip=True)[:900] if desc else "Indisponível",
                    "genres": self.extract_steam_genres(details),
                    "end_date": "Não informado",
                }

            meta = soup.find("meta", {"name": "description"})
            return {
                "desc": meta["content"][:900] if meta and meta.get("content") else "Indisponível",
                "genres": "Indisponível",
                "end_date": "Não informado",
            }
        except Exception:
            return self.empty_info()

    def empty_info(self):
        return {"desc": "Indisponível", "genres": "Indisponível", "end_date": "Indisponível"}

    def extract_steam_genres(self, block):
        if not block:
            return "Indisponível"
        text = block.get_text("\n", strip=True)
        for token in ("Genre:", "Gênero:", "Género:"):
            if token in text:
                return text.split(token, 1)[1].split("\n", 1)[0].strip()
        return "Indisponível"

    # ─────────────────────────────
    # EMBED FINAL
    # ─────────────────────────────
    def detect_price_type(self, embed):
        text = (self.extract_text_from_embed(embed)).lower()
        if "weekend" in text or "fim de semana" in text:
            return "weekend"
        return "free"

    def build_final_embed(self, platform, original, url, info):
        embed = discord.Embed(
            title=original.title or "Jogo grátis",
            url=url,
            color=original.color or discord.Color.blue(),
        )

        logos = {
            "Steam": "https://upload.wikimedia.org/wikipedia/commons/c/c1/Steam_Logo.png",
            "Epic Games": "https://upload.wikimedia.org/wikipedia/commons/3/31/Epic_Games_logo.png",
            "GOG": "https://upload.wikimedia.org/wikipedia/commons/6/6c/GOG.com_logo.png",
        }
        if logos.get(platform):
            embed.set_thumbnail(url=logos[platform])

        if getattr(original, "image", None) and getattr(original.image, "url", None):
            embed.set_image(url=original.image.url)

        embed.add_field(name="PLATAFORMA", value=f"```{platform}```", inline=False)
        embed.add_field(name="DESCRIÇÃO", value=f"```{info['desc']}```", inline=False)
        embed.add_field(name="GÊNERO", value=f"```{info['genres']}```", inline=False)

        price = "```diff\n+ Gratuito\n```"
        if self.detect_price_type(original) == "weekend":
            price = "```diff\n+ Gratuito (Fim de semana)\n```"

        embed.add_field(name="PREÇO", value=price, inline=False)
        embed.add_field(name="EXPIRA", value=f"```{info['end_date']}```", inline=False)

        return embed

    @commands.command(name="testfree")
    async def test_free(self, ctx):
        await ctx.send("✅ Comando funcionando!")


async def setup(bot):
    await bot.add_cog(FreeStuffMonitor(bot))