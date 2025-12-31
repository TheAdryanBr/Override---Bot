# main.py — RENDER SAFE / FUTURE PROOF

import os
import traceback
import asyncio
import logging
import threading

import discord
from discord.ext import commands
from dotenv import load_dotenv
load_dotenv()

from keep_alive import app, serve_foreground

# ─────────────────────────────
# LOGS
# ─────────────────────────────
logging.basicConfig(level=logging.INFO)
logging.getLogger("discord.http").setLevel(logging.WARNING)

# ─────────────────────────────
# TOKEN
# ─────────────────────────────
def _read_secret_file(paths):
    for p in paths:
        try:
            if os.path.isfile(p):
                with open(p, "r") as f:
                    s = f.read().strip()
                    if s:
                        return s
        except Exception:
            pass
    return None


TOKEN = (
    os.getenv("DISCORD_TOKEN")
    or os.getenv("TOKEN")
    or _read_secret_file([
        "/etc/secrets/DISCORD_TOKEN",
        "/etc/secrets/discord_token",
        "/run/secrets/discord_token",
        "/var/run/secrets/discord_token",
        "./.env.discord",
    ])
)

if not TOKEN:
    raise RuntimeError("❌ DISCORD_TOKEN não encontrado")

TOKEN = TOKEN.strip()
if TOKEN.lower().startswith("bot "):
    TOKEN = TOKEN[4:].strip()

# ─────────────────────────────
# INTENTS
# ─────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = True
intents.guilds = True
intents.messages = True
intents.dm_messages = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ─────────────────────────────
# COGS
# ─────────────────────────────
COGS = [
    "cogs.boosters",
    "cogs.denuncias",
    "cogs.welcome",
    "cogs.voice_rooms",
    "cogs.background_traffic",
    "cogs.platform_monitor",
    "cogs.freestuff_monitor",
    "cogs.controle_owner",
    "cogs.autorole",
    "cogs.embed",
    "cogs.ai_chat",
]

# ─────────────────────────────
# READY
# ─────────────────────────────
@bot.event
async def on_ready():
    print(f"[LOGADO] {bot.user} está online")
    print("📦 Cogs carregados:")
    for name in bot.cogs:
        print(" -", name)

# ─────────────────────────────
# LOAD COGS
# ─────────────────────────────
async def load_all_cogs():
    for cog in COGS:
        try:
            print(f"[DEBUG] Carregando {cog}")
            await bot.load_extension(cog)
            print(f"[COG] OK: {cog}")
        except Exception:
            print(f"[COG ERRO] {cog}")
            traceback.print_exc()

# ─────────────────────────────
# BOT MAIN
# ─────────────────────────────
async def main():
    await load_all_cogs()
    await bot.start(TOKEN)

# ─────────────────────────────
# ENTRYPOINT
# ─────────────────────────────
if __name__ == "__main__":
    # Flask (Render keep-alive)
    port = int(os.environ.get("PORT", 10000))
    threading.Thread(
        target=lambda: serve_foreground(app, port=port),
        daemon=True
    ).start()
    print(f"[FLASK] Servindo em porta {port}")

    # Discord bot
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Encerrando…")
    except Exception:
        traceback.print_exc()
