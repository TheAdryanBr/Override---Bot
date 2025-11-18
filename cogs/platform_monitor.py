# cogs/platform_monitor.py
import asyncio
import discord
from discord.ext import commands, tasks
from datetime import datetime, time
import aiohttp

# -------- CONFIGS --------
PLATFORM_CHANNEL_ID = 1415478538114564166     # Canal onde será enviado
MENTION_ROLE_ID = 1254470641944494131        # Cargo para mencionar

USERNAME_TIKTOK = "theadryanbr"
USERNAME_YOUTUBE = "TheAdryanBr"
USERNAME_TWITCH = "theadryanbr"

CHECK_INTERVAL = 60  # segundos


# ====== IMPORTS DAS FUNÇÕES DE SCRAPING ======
from platforms.tiktok import check_tiktok_live
from platforms.youtube import check_youtube_live
from platforms.twitch import check_twitch_live


class PlatformMonitor(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.was_live = False
        self.monitor_task.start()

    # --------------------------------------------------------
    # Horário permitido
    # --------------------------------------------------------
    def is_allowed_time(self):
        now = datetime.now().time()
        start1 = time(12, 0)
        end1 = time(15, 0)

        start2 = time(20, 0)
        end2 = time(23, 59)

        return (start1 <= now <= end1) or (start2 <= now <= end2)

    # --------------------------------------------------------
    # Loop principal de monitoramento
    # --------------------------------------------------------
    @tasks.loop(seconds=CHECK_INTERVAL)
    async def monitor_task(self):
        # só monitora no horário
        if not self.is_allowed_time():
            self.was_live = False
            return

        # verificar tiktok primeiro
        tiktok = await check_tiktok_live(USERNAME_TIKTOK)

        if not tiktok:
            # está OFFLINE → resetar status
            self.was_live = False
            return

        # se já notificou, não envia novamente
        if self.was_live:
            return

        # está AO VIVO pela primeira vez no horário
        youtube = await check_youtube_live(USERNAME_YOUTUBE)
        twitch = await check_twitch_live(USERNAME_TWITCH)

        await self.send_live_embed(tiktok, youtube, twitch)

        # marcar como “já notificado”
        self.was_live = True

    # --------------------------------------------------------
    # Envio do embed
    # --------------------------------------------------------
    async def send_live_embed(self, tiktok, youtube, twitch):
        channel = self.bot.get_channel(PLATFORM_CHANNEL_ID)
        if not channel:
            return

        role = channel.guild.get_role(MENTION_ROLE_ID)

        # status extras
        yt_status = "🔴 AO VIVO" if youtube else "⚫ Offline"
        tw_status = "🔴 AO VIVO" if twitch else "⚫ Offline"

        embed = discord.Embed(
            title=f"🔴 {tiktok['title']}",
            description=f"**Clique para assistir:**\n{tiktok['url']}",
            color=discord.Color.red()
        )
        embed.add_field(name="YouTube", value=yt_status, inline=True)
        embed.add_field(name="Twitch", value=tw_status, inline=True)
        embed.set_image(url=tiktok["cover"])

        mention = role.mention if role else ""

        await channel.send(content=mention, embed=embed)

    # --------------------------------------------------------
    # Teste manual
    # --------------------------------------------------------
    @commands.command(name="testlive")
    async def testlive(self, ctx):
        youtube = {"live": True}
        twitch = {"live": True}
        fake_tiktok = {
            "title": "🔴 Teste de Live",
            "url": "https://www.tiktok.com/@theadryanbr/live",
            "cover": "https://p16-sign-va.tiktokcdn.com/tos-maliva-avt-0068/fake.jpg"
        }

        await self.send_live_embed(fake_tiktok, youtube, twitch)
        await ctx.send("Embed de teste enviado!", delete_after=8)

    # --------------------------------------------------------
    # Before Loop
    # --------------------------------------------------------
    @monitor_task.before_loop
    async def before_loop(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(PlatformMonitor(bot))
