# main.py — CLEAN + FUNCTIONAL VERSION
import os
import sys
import traceback
import uuid
import threading
import asyncio

import discord
from discord.ext import commands

# ===== ENV HELPERS =====
def _int_env(name, default):
    v = os.environ.get(name)
    if v is None:
        return default
    try: return int(v)
    except:
        try: return int(v.strip())
        except: return default

def _read_secret_file(paths):
    for p in paths:
        try:
            if os.path.isfile(p):
                with open(p,"r") as f:
                    s=f.read().strip()
                    if s: return s
        except: pass
    return None

_secret_paths = [
    "/etc/secrets/DISCORD_TOKEN",
    "/etc/secrets/discord_token",
    "/run/secrets/discord_token",
    "/var/run/secrets/discord_token",
    "./.env.discord"
]

TOKEN = (
    os.getenv("DISCORD_TOKEN") or
    os.getenv("TOKEN") or
    _read_secret_file(_secret_paths)
)

if not TOKEN:
    raise RuntimeError("❌ DISCORD_TOKEN não encontrado!")

TOKEN = TOKEN.strip()
if TOKEN.lower().startswith("bot "):
    TOKEN = TOKEN[4:].strip()

# ===== CONFIGS =====
REPORT_CHANNEL_ID = _int_env("REPORT_CHANNEL_ID", 0)
ADMIN_ROLE_ID    = _int_env("ADMIN_ROLE_ID", 0)
WELCOME_CHANNEL_ID = _int_env("WELCOME_CHANNEL_ID", 0)
WELCOME_LOG_CHANNEL_ID = _int_env("WELCOME_LOG_CHANNEL_ID", 0)
MEMBER_ROLE_ID = _int_env("MEMBER_ROLE_ID", 0)

GUILD_ID = _int_env("GUILD_ID", 0)
BOOSTER_ROLE_ID = _int_env("BOOSTER_ROLE_ID", 0)
CUSTOM_BOOSTER_ROLE_ID = _int_env("CUSTOM_BOOSTER_ROLE_ID", BOOSTER_ROLE_ID)

# ===== ANTI-MULTI INSTANCE =====
if os.environ.get("RUNNING_INSTANCE") == "1":
    print("⚠️ Instância já ativa. Abortando.")
    sys.exit()
os.environ["RUNNING_INSTANCE"] = "1"

# ===== BOT INIT =====
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# ===== LISTA DE COGS =====
COGS = [
    "cogs.boosters",
    "cogs.denuncias",
    "cogs.welcome",
    "cogs.voice_rooms",
    "cogs.background_traffic",
    "cogs.platform_monitor",
    "cogs.freestuff_monitor",
    "cogs.controle_owner",
]

# ===== EVENTO DE SYNC =====
@bot.event
async def on_ready():
    print(f"[LOGADO] {bot.user} está online!")

    try:
        synced = await bot.tree.sync()
        print(f"[SLASH] {len(synced)} comandos sincronizados.")
    except Exception as e:
        print("[SLASH ERRO]", e)

    print(f"Bot iniciado como {bot.user} (ID {bot.user.id})")

# ===== CARREGAMENTO DOS COGS =====
async def load_all_cogs():
    for cog in COGS:
        try:
            await bot.load_extension(cog)
            print(f"[COG] Carregado: {cog}")
        except Exception as e:
            print(f"[COG ERRO] {cog}: {e}")
            traceback.print_exc()

# ===== THREAD DO BOT =====
def _start_bot_thread():
    async def runner():
        await load_all_cogs()
        await bot.start(TOKEN)

    def thread_target():
        try:
            asyncio.run(runner())
        except Exception as e:
            print("❌ Erro ao iniciar bot:", type(e).__name__, "-", e)
            traceback.print_exc()

    t = threading.Thread(target=thread_target, daemon=True)
    t.start()

# ===== EXPOSE CONFIG =====
bot.MAIN_CONFIG = {
    "REPORT_CHANNEL_ID": REPORT_CHANNEL_ID,
    "ADMIN_ROLE_ID": ADMIN_ROLE_ID,
    "WELCOME_CHANNEL_ID": WELCOME_CHANNEL_ID,
    "WELCOME_LOG_CHANNEL_ID": WELCOME_LOG_CHANNEL_ID,
    "MEMBER_ROLE_ID": MEMBER_ROLE_ID,
    "GUILD_ID": GUILD_ID,
    "BOOSTER_ROLE_ID": BOOSTER_ROLE_ID,
    "CUSTOM_BOOSTER_ROLE_ID": CUSTOM_BOOSTER_ROLE_ID,
    "INSTANCE_ID": str(uuid.uuid4())[:8],
}

print(f"[MAIN] Instance ID: {bot.MAIN_CONFIG['INSTANCE_ID']}")

# ===== RUN – VERSÃO 100% FUNCIONAL COM FLASK + DMs =====
if __name__ == "__main__":
    # 1. Primeiro carrega todos os cogs (síncrono, antes de tudo)
    async def load_cogs_startup():
        for cog in COGS:
            try:
                await bot.load_extension(cog)
                print(f"[COG] Carregado: {cog}")
            except Exception as e:
                print(f"[COG ERRO] {cog}: {e}")
                traceback.print_exc()

    # 2. Função principal do bot (roda no event loop principal)
    async def bot_main():
        await load_cogs_startup()
        await bot.start(TOKEN)

    # 3. Inicia o Flask em thread separada (ele faz o ping e mantém o Render acordado)
    def start_flask():
        from keep_alive import app, serve_foreground
        port = int(os.environ.get("PORT", 8080))
        print(f"[FLASK] Iniciando servidor na porta {port} para keep-alive")
        serve_foreground(app, port=port)

    import threading
    threading.Thread(target=start_flask, daemon=True).start()

    # 4. Agora roda o bot no loop principal → DMs voltam a funcionar 100%
    print("[BOT] Iniciando bot no event loop principal...")
    asyncio.run(bot_main())
