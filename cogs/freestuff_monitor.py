import discord
from discord.ext import commands
import aiohttp
import re
from bs4 import BeautifulSoup

# ─────────────────────────────
# CONFIG
# ─────────────────────────────
TEST_GUILD_ID = 1384621027627372714
TEST_CHANNEL_ID = 1444576416145346621

MAIN_CHANNEL_ID = 1216133008680292412
PING_ROLE_ID = 1254470219305324564

FREESTUFF_BOT_ID = 672822334641537041  # ⬅️ COLOQUE O ID REAL DO FREESTUFF

# ─────────────────────────────
# REGEX
# ─────────────────────────────
STEAM_REGEX = r"https?://store\.steampowered\.com/app/\d+/"
EPIC_REGEX = r"https?://store\.epicgames\.com/[^\s]+"
GOG_REGEX = r"https?://www\.gog\.com/en/game/[^\s]+"

sent_cache = set()
MAX_CACHE = 200


class FreeStuffMonitor(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ─────────────────────────────
    # LISTENER
    # ─────────────────────────────
    @commands.Cog.listener()
    async def on_message(self, msg: discord.Message):

        await self.bot.process_commands(msg)

        if not msg.guild:
            return

        if msg.guild.id != TEST_GUILD_ID:
            return

        if msg.channel.id != TEST_CHANNEL_ID:
            return

        # 🔒 Garante que é o FreeStuff
        if msg.author.id != FREESTUFF_BOT_ID:
            return

        if not msg.embeds:
            return

        embed = next(
            (e for e in msg.embeds if e.title or e.description or e.url),
            None
        )
        if not embed:
            return

        platform, url = self.extract_platform_and_url(embed)
        if not platform or not url:
            return

        key = f"{platform}:{url}"
        if key in sent_cache:
            return

        sent_cache.add(key)
        if len(sent_cache) > MAX_CACHE:
            sent_cache.pop()

        info = await self.fetch_game_info(platform, url)
        final_embed = self.build_final_embed(platform, embed, info)

        channel = self.bot.get_channel(MAIN_CHANNEL_ID)
        if not channel:
            return

        try:
            await channel.send(
                content=f"🎮 **Novo jogo gratuito disponível!** <@&{PING_ROLE_ID}>",
                embed=final_embed
            )
        except Exception as e:
            print(f"[FreeStuff] Erro ao enviar mensagem: {e}")

    # ─────────────────────────────
    # EXTRAÇÃO
    # ─────────────────────────────
    def extract_platform_and_url(self, embed: discord.Embed):
        text = " ".join([
            embed.title or "",
            embed.description or "",
            embed.url or ""
        ])

        for name, regex in (
            ("Steam", STEAM_REGEX),
            ("Epic Games", EPIC_REGEX),
            ("GOG", GOG_REGEX),
        ):
            match = re.search(regex, text)
            if match:
                return name, match.group(0)

        return None, None

    # ─────────────────────────────
    # SCRAPING
    # ─────────────────────────────
    async def fetch_game_info(self, platform, url):
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, timeout=10) as resp:
                    html = await resp.text()
            except Exception:
                return self.empty_info()

        soup = BeautifulSoup(html, "html.parser")

        try:
            if platform == "Steam":
                desc = soup.find("div", id="game_area_description")
                genres = soup.select_one(".details_block")

                return {
                    "desc": desc.get_text("\n", strip=True)[:900] if desc else "Indisponível",
                    "genres": self.extract_genres(genres),
                    "end_date": "Não informado"
                }

            desc = soup.find("meta", {"name": "description"})
            return {
                "desc": desc["content"][:900] if desc else "Indisponível",
                "genres": "Indisponível",
                "end_date": "Não informado"
            }

        except Exception:
            return self.empty_info()

    def empty_info(self):
        return {
            "desc": "Indisponível",
            "genres": "Indisponível",
            "end_date": "Indisponível"
        }

    def extract_genres(self, block):
        if not block:
            return "Indisponível"

        text = block.get_text("\n", strip=True)
        if "Genre:" in text:
            return text.split("Genre:")[1].split("\n")[0]
        return "Indisponível"

    # ─────────────────────────────
    # EMBED FINAL
    # ─────────────────────────────
    def detect_price_type(self, embed):
        text = f"{embed.title or ''} {embed.description or ''}".lower()
        if "weekend" in text or "fim de semana" in text:
            return "weekend"
        return "free"

    def build_final_embed(self, platform, original, info):
        embed = discord.Embed(
            title=original.title,
            url=original.url,
            color=original.color or discord.Color.blue()
        )

        logos = {
            "Steam": "https://upload.wikimedia.org/wikipedia/commons/c/c1/Steam_Logo.png",
            "Epic Games": "https://upload.wikimedia.org/wikipedia/commons/3/31/Epic_Games_logo.png",
            "GOG": "https://upload.wikimedia.org/wikipedia/commons/6/6c/GOG.com_logo.png"
        }
        embed.set_thumbnail(url=logos.get(platform))

        if original.image:
            embed.set_image(url=original.image.url)

        embed.add_field(
            name="DESCRIÇÃO",
            value=f"```{info['desc']}```",
            inline=False
        )

        embed.add_field(
            name="GÊNERO",
            value=f"```{info['genres']}```",
            inline=False
        )

        price = "```diff\n+ Gratuito\n```"
        if self.detect_price_type(original) == "weekend":
            price = "```diff\n+ Gratuito (Fim de semana)\n```"

        embed.add_field(name="PREÇO", value=price, inline=False)
        embed.add_field(name="", value=f"```{info['end_date']}```", inline=False)

        return embed

    # ─────────────────────────────
    # TESTE
    # ─────────────────────────────
    @commands.command(name="testfree")
    async def test_free(self, ctx):
        await ctx.send("✅ Comando funcionando!")


async def setup(bot):
    await bot.add_cog(FreeStuffMonitor(bot))
