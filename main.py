# main.py — RENDER SAFE (Flask principal + bot em background)

import os
import sys
import traceback
import asyncio
import logging
from threading import Thread

import discord
from discord.ext import commands

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
                with open(p,"r") as f:
                    s=f.read().strip()
                    if s: return s
        except:
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
    raise RuntimeError("❌ DISCORD_TOKEN não encontrado!")

TOKEN = TOKEN.strip()
if TOKEN.lower().startswith("bot "):
    TOKEN = TOKEN[4:].strip()

# ─────────────────────────────
# INTENTS
# ─────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.guilds = True
intents.guild_messages = True
intents.dm_messages = True
intents.members = True
intents.presences = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ─────────────────────────────
# COGS
# ─────────────────────────────
COGS = [
    # "cogs.boosters",
    "cogs.denuncias",
    "cogs.welcome",
    "cogs.voice_rooms",
    "cogs.background_traffic",
    # "cogs.platform_monitor",
    "cogs.freestuff_monitor",
    "cogs.controle_owner",
    "cogs.autorole",
    "cogs.ai_chat",
    "cogs.embed",
]

# ─────────────────────────────
# READY
# ─────────────────────────────
_ready_once = False

@bot.event
async def on_ready():
    global _ready_once
    if _ready_once:
        return
    _ready_once = True

    print(f"[LOGADO] {bot.user} está online!")
    print("📦 Cogs carregados:")
    for name in bot.cogs:
        print(" -", name)

# ─────────────────────────────
# CARREGAMENTO DOS COGS
# ─────────────────────────────
async def load_all_cogs():
    for cog in COGS:
        try:
            print(f"[DEBUG] Carregando {cog}")
            await bot.load_extension(cog)
            print(f"[COG] OK: {cog}")
        except Exception as e:
            print(f"[COG ERRO] {cog}")
            traceback.print_exc()

# ─────────────────────────────
# TASK DO BOT
# ─────────────────────────────
async def bot_task():
    await load_all_cogs()
    try:
        await bot.start(TOKEN)
    except Exception as e:
        print("❌ Bot terminou com erro:", e)
        traceback.print_exc()

def schedule_bot():
    loop = asyncio.get_event_loop()
    loop.create_task(bot_task())

# ─────────────────────────────
# INÍCIO DO SERVIÇO
# ─────────────────────────────
if __name__ == "__main__":
    # ─────────────── FLASK ───────────────
    port = int(os.environ.get("PORT", 8080))
    Thread(target=lambda: serve_foreground(app, port=port), daemon=True).start()
    print(f"[FLASK] Servindo em porta {port}")

    # ─────────── BOT EM BACKGROUND ───────────
    print("[BOT] Programado para iniciar em background…")
    schedule_bot()

    # ─────────────── EVENT LOOP ───────────────
    try:
        asyncio.get_event_loop().run_forever()
    except KeyboardInterrupt:
        print("Encerrando…")
