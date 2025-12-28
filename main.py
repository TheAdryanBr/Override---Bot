# main.py — STABLE / SINGLE-LOGIN / RENDER SAFE
import os
import sys
import traceback
import uuid
import asyncio
import logging
import threading

import discord
from discord.ext import commands

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
    raise RuntimeError("❌ DISCORD_TOKEN não encontrado")

TOKEN = TOKEN.strip()
if TOKEN.lower().startswith("bot "):
    TOKEN = TOKEN[4:].strip()

# ─────────────────────────────
# INTENTS
# ─────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.dm_messages = True
intents.guilds = True
intents.guild_messages = True
intents.members = True
intents.presences = True

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
    "cogs.ai_chat",
    "cogs.embed",
]

# ─────────────────────────────
# READY (UMA VEZ)
# ─────────────────────────────
_ready_once = False

@bot.event
async def on_ready():
    global _ready_once
    if _ready_once:
        return
    _ready_once = True

    await asyncio.sleep(5)

    print(f"[LOGADO] {bot.user} está online")
    print("📦 Cogs carregados:")
    for name in bot.cogs:
        print(" -", name)

    # Proteção de sync
    if os.getenv("SYNC_COMMANDS") == "0":
        try:
            synced = await bot.tree.sync()
            print(f"[SLASH] {len(synced)} comandos sincronizados")
        except Exception as e:
            print("[SLASH ERRO]", e)
    else:
        print("[SLASH] Sync ignorado")

# ─────────────────────────────
# LOAD COGS
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
# FLASK KEEP ALIVE (THREAD)
# ─────────────────────────────
def start_keep_alive():
    try:
        from keep_alive import app, serve_foreground
        port = int(os.environ.get("PORT", 8080))
        serve_foreground(app, port=port)
    except Exception:
        traceback.print_exc()

# ─────────────────────────────
# MAIN
# ─────────────────────────────
async def main():
    await load_all_cogs()
    await bot.start(TOKEN)

if __name__ == "__main__":
    # Flask em background
    threading.Thread(
        target=start_keep_alive,
        daemon=True
    ).start()

    # BOT = PROCESSO PRINCIPAL
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Encerrando bot…")
    except Exception:
        traceback.print_exc()
