# main.py — RENDER SAFE / FUTURE PROOF

import os
import traceback
import asyncio
import logging
import threading
import webhook_server

import discord
from keep_alive import app, serve_foreground
from discord.ext import commands
from dotenv import load_dotenv
from utils import OWNER_ID, GUILD_ID

load_dotenv()

# ✅ WelcomeBridge (opção A: serviço, não extension)
from cogs.ai_chat.welcome_bridge import WelcomeBridge

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
intents.typing = True

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
    "cogs.free_games",
    "cogs.controle_owner",
    "cogs.autorole",
    "cogs.embed",
    "cogs.reload_cogs",
    "cogs.lobby_counter",
    "cogs.promo_embed",
    "cogs.ai_chat",
    # "cogs.ai_chat.welcome_bridge",  # ✅ NÃO carregar como extension
    # "cogs.typing_probe"
]

# ✅ instancia única (não é cog / não é extension)
welcome_bridge = WelcomeBridge()

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
# BOT CLASS (auto guild sync no startup)
# ─────────────────────────────
class OverrideBot(commands.Bot):
    async def setup_hook(self) -> None:
        # 1) carrega todos os cogs ANTES de sync (isso evita CommandNotFound no boot)
        await load_all_cogs()

        # 2) sync rápido no servidor de teste (DEV) — global só via !sync global
        guild_obj = discord.Object(id=GUILD_ID)
        try:
            self.tree.copy_global_to(guild=guild_obj)
            synced = await self.tree.sync(guild=guild_obj)
            print(f"[AUTO SYNC] GUILD ok: {len(synced)} comandos no servidor {GUILD_ID}.")
        except Exception:
            print("[AUTO SYNC] Falhou")
            traceback.print_exc()

bot = OverrideBot(command_prefix="!", intents=intents)

# ─────────────────────────────
# READY
# ─────────────────────────────
@bot.event
async def on_ready():
    print(f"[LOGADO] {bot.user} está online")
    print("📦 Cogs carregados:")
    for name in bot.cogs:
        print(" -", name)

# ✅ evento de join: só encaminha pro bridge (sem mexer em conversa/cooldown)
@bot.event
async def on_member_join(member: discord.Member):
    try:
        welcome_bridge.notify_join(member)
    except Exception:
        traceback.print_exc()

# ─────────────────────────────
# SYNC COMMANDS (MANUAL)
# ─────────────────────────────
@bot.command(name="sync")
async def sync_cmd(ctx: commands.Context, scope: str = "guild"):
    if ctx.author.id != OWNER_ID:
        return

    try:
        if scope.lower() == "global":
            synced = await bot.tree.sync()
            await ctx.send(f"✅ Sync GLOBAL ok: {len(synced)} comandos.")
            return

        guild_obj = discord.Object(id=GUILD_ID)

        # ✅ Isso faz os comandos aparecerem rápido no servidor de teste
        bot.tree.copy_global_to(guild=guild_obj)

        synced = await bot.tree.sync(guild=guild_obj)
        await ctx.send(f"✅ Sync GUILD ok: {len(synced)} comandos no servidor {GUILD_ID}.")
    except Exception as e:
        await ctx.send(f"❌ Falha no sync: `{type(e).__name__}: {e}`")
        traceback.print_exc()

@bot.command(name="unsync_guild")
async def unsync_guild_cmd(ctx: commands.Context):
    """
    Remove TODOS os comandos de guild registrados no Discord para este servidor.
    Útil se ficou “entulhado” com comandos duplicados.

    Depois disso, rode:
      !sync guild
    """
    if ctx.author.id != OWNER_ID:
        return

    try:
        guild_obj = discord.Object(id=GUILD_ID)
        bot.tree.clear_commands(guild=guild_obj)
        synced = await bot.tree.sync(guild=guild_obj)
        await ctx.send(f"🧹 Limpei comandos do GUILD. Agora tem {len(synced)} comandos no guild.")
    except Exception as e:
        await ctx.send(f"❌ Falha ao limpar: `{type(e).__name__}: {e}`")
        traceback.print_exc()

# ─────────────────────────────
# BOT MAIN
# ─────────────────────────────
async def main():
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
