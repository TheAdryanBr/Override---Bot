# main.py — carregador e start (mantém compatibilidade Render: Flask em foreground)
import os
import sys
import traceback
import uuid
import threading
from importlib import import_module

from discord.ext import commands

# ===== ENV HELPERS (copiado/adaptado do seu original) =====
def _int_env(name, default):
    v = os.environ.get(name)
    if v is None:
        return default
    try:
        return int(v)
    except:
        try:
            return int(v.strip())
        except:
            return default

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

_secret_paths = [
    "/etc/secrets/DISCORD_TOKEN",
    "/etc/secrets/discord_token",
    "/run/secrets/discord_token",
    "/var/run/secrets/discord_token",
    "./.env.discord"
]

TOKEN = os.getenv("DISCORD_TOKEN") or os.getenv("TOKEN") or _read_secret_file(_secret_paths)
if TOKEN:
    TOKEN = TOKEN.strip()
    if TOKEN.lower().startswith("bot "):
        TOKEN = TOKEN[4:].strip()

if not TOKEN:
    raise RuntimeError("❌ Erro: DISCORD_TOKEN/TOKEN não encontrado nas env vars nem em /etc/secrets.")

# ====== Configs que seu bot usa (padrão para leitura em cogs também) ======
REPORT_CHANNEL_ID = _int_env("REPORT_CHANNEL_ID", 0)
ADMIN_ROLE_ID = _int_env("ADMIN_ROLE_ID", 0)
WELCOME_CHANNEL_ID = _int_env("WELCOME_CHANNEL_ID", 0)
WELCOME_LOG_CHANNEL_ID = _int_env("WELCOME_LOG_CHANNEL_ID", 0)
MEMBER_ROLE_ID = _int_env("MEMBER_ROLE_ID", 0)

GUILD_ID = _int_env("GUILD_ID", 0)
BOOSTER_ROLE_ID = _int_env("BOOSTER_ROLE_ID", 0)
CUSTOM_BOOSTER_ROLE_ID = _int_env("CUSTOM_BOOSTER_ROLE_ID", BOOSTER_ROLE_ID)

# ================= Multi-instance guard (mantido) =================
if os.environ.get("RUNNING_INSTANCE") == "1":
    print("⚠️ Já existe uma instância ativa deste bot. Encerrando...")
    sys.exit()
os.environ["RUNNING_INSTANCE"] = "1"

# ===== Bot minimal init (interações de comandos/cogs) =====
import discord
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# ==== Lista de cogs a carregar ====
COGS = [
    "cogs.boosters",
    "cogs.denuncias",
    "cogs.welcome",
    "cogs.voice_rooms",
    "cogs.background_traffic",
]

# Carrega cogs
for cog in COGS:
    try:
        bot.load_extension(cog)
        print(f"[MAIN] Cog loaded: {cog}")
    except Exception as e:
        print(f"[MAIN] Erro ao carregar cog {cog}: {type(e).__name__} {e}")
        traceback.print_exc()

# Start helpers: inicia bot em thread daemon (para que Flask rode no processo principal)
def _start_bot_thread():
    def _run():
        try:
            bot.run(TOKEN)
        except Exception as e:
            print("❌ Erro ao iniciar o bot (thread):", type(e).__name__, "-", e)
            traceback.print_exc()
    t = threading.Thread(target=_run, daemon=True)
    t.start()

# Exponha algumas constantes para cogs que importarem main (opcional)
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

print(f"[MAIN] Instance id: {bot.MAIN_CONFIG['INSTANCE_ID']}")

# Run: start bot thread, then run Flask (keep_alive) in main thread (Render expects app in foreground)
if __name__ == "__main__":
    # Inicia o bot em background (daemon thread)
    _start_bot_thread()

    # Inicia Flask (keep_alive) em foreground — isso mantém o processo vivo e compatível com Render Web Service
    from keep_alive import app, serve_foreground

    port = int(os.environ.get("PORT", 8080))
    serve_foreground(app, port=port)
