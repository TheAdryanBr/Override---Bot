# cogs/background_traffic.py
import asyncio
import random
import aiohttp
import logging

from discord.ext import commands

_log = logging.getLogger("bg_traffic")

class BackgroundTrafficCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.task = None
        # configurações: podem ser ajustadas via env
        self.min_delay = int(os.environ.get("BG_MIN_DELAY", 5 * 60))
        self.max_delay = int(os.environ.get("BG_MAX_DELAY", 20 * 60))
        self.endpoints = [
            "https://api.github.com/zen",
            "https://httpbin.org/get"
        ]
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) BotKeepAlive"
        }

    @commands.Cog.listener()
    async def on_ready(self):
        # start once
        if self.task is None:
            self.task = self.bot.loop.create_task(self._loop())

    async def _loop(self):
        _log.info("Background traffic loop started.")
        try:
            async with aiohttp.ClientSession() as sess:
                while True:
                    delay = random.randint(self.min_delay, self.max_delay)
                    _log.info(f"bg sleep {delay}s")
                    await asyncio.sleep(delay)
                    url = random.choice(self.endpoints)
                    try:
                        async with sess.get(url, headers=self.headers, timeout=15) as r:
                            text = await r.text()
                            _log.info(f"bg ping -> {url} status={r.status} len={len(text) if text else 0}")
                    except Exception as e:
                        _log.warning(f"bg ping failed {e}")
        except asyncio.CancelledError:
            _log.info("Background traffic loop cancelled.")
        except Exception as e:
            _log.exception("Background traffic fatal: %s", e)

async def setup(bot):
   await bot.add_cog(BackgroundTrafficCog(bot))
