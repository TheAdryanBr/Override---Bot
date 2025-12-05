import discord
from discord.ext import commands
import aiohttp
import re
import asyncio
from bs4 import BeautifulSoup

TEST_GUILD_ID = 1384621028877144098
TEST_CHANNEL_ID = 1444576416145346621

MAIN_CHANNEL_ID = 1216133008680292412
PING_ROLE_ID = 1254471933588799618  # cargo para marcar

STEAM_REGEX = r"https?://store\.steampowered\.com/app/\d+/"
EPIC_REGEX = r"https?://store\.epicgames\.com/[^\s]+"
GOG_REGEX = r"https?://www\.gog\.com/en/game/[^\s]+"

# cache simples para evitar duplicatas
sent_cache = set()


class FreeStuffMonitor(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ---------------------------------------------------------
    # 1) Listener: ler mensagens do FreeStuff
    # ---------------------------------------------------------
    @commands.Cog.listener()
    async def on_message(self, msg: discord.Message):

        if msg.guild is None:
            return
        if msg.author.bot is False:
            return
        if msg.guild.id != TEST_GUILD_ID:
            return
        if msg.channel.id != TEST_CHANNEL_ID:
            return
        if not msg.embeds:
            return

        embed = msg.embeds[0]
        platform, url = self.extract_platform_and_url(embed)

        if platform is None or url is None:
            return

        key = f"{platform}:{url}"
        if key in sent_cache:
            return
        sent_cache.add(key)

        info = await self.fetch_game_info(platform, url)
        final_embed = self.build_final_embed(platform, embed, info)

        channel = self.bot.get_channel(MAIN_CHANNEL_ID)
        if channel:
            await channel.send(
                content=f"Novo jogo gratuito disponível! <@&{PING_ROLE_ID}>",
                embed=final_embed
            )

        # permite comandos (!testfree)
        await self.bot.process_commands(msg)

    # ---------------------------------------------------------
    # 2) Detectar plataforma e link
    # ---------------------------------------------------------
    def extract_platform_and_url(self, embed: discord.Embed):
        text = (embed.description or "") + " " + (embed.title or "") + " " + (embed.url or "")

        if re.search(STEAM_REGEX, text):
            url = re.search(STEAM_REGEX, text).group(0)
            return "Steam", url

        if re.search(EPIC_REGEX, text):
            url = re.search(EPIC_REGEX, text).group(0)
            return "Epic Games", url

        if re.search(GOG_REGEX, text):
            url = re.search(GOG_REGEX, text).group(0)
            return "GOG", url

        return None, None

    # ---------------------------------------------------------
    # 3) Buscar descrição, gênero e data final
    # ---------------------------------------------------------
    async def fetch_game_info(self, platform, url):
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, timeout=10) as resp:
                    html = await resp.text()
            except Exception:
                return {"desc": "Indisponível", "genres": "Indisponível", "end_date": "Indisponível"}

        soup = BeautifulSoup(html, "html.parser")

        if platform == "Steam":
            desc = soup.find("div", {"id": "game_area_description"})
            genres = soup.select_one(".details_block")

            try:
                desc_text = desc.get_text("\n", strip=True)[:900]
            except:
                desc_text = "Indisponível"

            try:
                genres_text = genres.get_text("\n", strip=True).split("Genre:")[1].split("\n")[0]
            except:
                genres_text = "Indisponível"

            return {"desc": desc_text, "genres": genres_text, "end_date": "Não informado"}

        if platform == "Epic Games":
            desc = soup.find("meta", {"name": "description"})
            desc_text = desc["content"] if desc else "Indisponível"

            return {
                "desc": desc_text[:900],
                "genres": "Indisponível",
                "end_date": "Não informado"
            }

        if platform == "GOG":
            desc = soup.find("meta", {"name": "description"})
            desc_text = desc["content"] if desc else "Indisponível"

            return {
                "desc": desc_text[:900],
                "genres": "Indisponível",
                "end_date": "Não informado"
            }

        return {"desc": "Indisponível", "genres": "Indisponível", "end_date": "Indisponível"}

    # ---------------------------------------------------------
    # 4) Montar o embed final
    # ---------------------------------------------------------
    def detect_price_type(self, original_embed):
        """Simples detecção de 'Free Weekend'."""
        text = (original_embed.description or "") + " " + (original_embed.title or "")
        if "weekend" in text.lower() or "fim de semana" in text.lower():
            return "weekend"
        return "free"

    def build_final_embed(self, platform, original_embed, info):
    embed = discord.Embed(
        title=original_embed.title,
        url=original_embed.url,
        color=original_embed.color or discord.Color.blue()
    )

    # Thumbnail da plataforma
    logos = {
        "Steam": "https://upload.wikimedia.org/wikipedia/commons/c/c1/Steam_Logo.png",
        "Epic Games": "https://upload.wikimedia.org/wikipedia/commons/3/31/Epic_Games_logo.png",
        "GOG": "https://upload.wikimedia.org/wikipedia/commons/6/6c/GOG.com_logo.png"
    }
    embed.set_thumbnail(url=logos.get(platform))

    # IMAGEM PRINCIPAL (capa do jogo)
    if original_embed.image:
        embed.set_image(url=original_embed.image.url)

    # -----------------------------------------
    # DESCRIÇÃO
    # -----------------------------------------
    embed.add_field(
        name="DESCRIÇÃO:",
        value=f"```{info['desc']}```",
        inline=False
    )

    # -----------------------------------------
    # GÊNEROS (em lista com bullet points)
    # -----------------------------------------
    genres_raw = info["genres"]

    # transforma "Action, Shooter, RPG" → lista
    genre_list = "• " + "\n• ".join(
        [g.strip() for g in genres_raw.replace(",", "\n").split("\n") if g.strip()]
    )

    embed.add_field(
        name="GÊNERO:",
        value=f"```{genre_list}```",
        inline=False
    )

    # -----------------------------------------
    # PREÇO
    # -----------------------------------------
    price_type = self.detect_price_type(original_embed)

    if price_type == "weekend":
        price_text = "```diff\n+ Gratuito (Fim de semana)\n```"
    elif price_type == "test":
        price_text = "```diff\n+ Gratuito (Test gratuito)\n```"
    else:
        price_text = "```diff\n+ Gratuito\n```"

    embed.add_field(
        name="PREÇO:",
        value=price_text,
        inline=False
    )

    # -----------------------------------------
    # DATA FINAL
    # -----------------------------------------
    end_date = info["end_date"] if info["end_date"] else "Não informado"

    embed.add_field(
        name="",
        value=f"```{end_date}```",
        inline=False
    )

    return embed

    # ---------------------------------------------------------
    # 5) Comando manual para testes
    # ---------------------------------------------------------
    @commands.command(name="testfree")
    async def test_free(self, ctx):
        await ctx.send("Comando funcionando!")

        fake_embed = discord.Embed(
            title="Exemplo — ARC Raiders",
            url="https://store.steampowered.com/app/1808500/ARC_Raiders/",
            color=655610,
            description="Jogo grátis disponível!"
        )

        fake_embed.set_image(
            url="https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/1808500/04baafaf64a5aa5f46ecda5d71889a4848dc0628/header.jpg"
        )

        info = {
            "desc": "ARC Raiders é uma aventura multijogador...",
            "genres": "Action, Shooter, Extraction",
            "end_date": "Não informado"
        }

        final = self.build_final_embed("Steam", fake_embed, info)
        await ctx.send(embed=final)


# ---------------------------------------------------------
# FUNÇÃO SETUP OBRIGATÓRIA
# ---------------------------------------------------------
async def setup(bot):
    await bot.add_cog(FreeStuffMonitor(bot))
