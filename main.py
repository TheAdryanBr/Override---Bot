import os
import sys
import json
import re
import asyncio
import traceback
import time
import uuid
from datetime import datetime, timezone, timedelta

import discord
from discord.ext import commands, tasks
from discord.ui import View, button

from flask import Flask
from threading import Thread

# -------------------- KEEP ALIVE (Flask) --------------------
app = Flask('')

@app.route('/')
def home():
    return "✅ Bot operacional e conectado ao Discord"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run, daemon=True)
    t.start()

# -------------------- MULTI-INSTANCE GUARD --------------------
if os.environ.get("RUNNING_INSTANCE") == "1":
    print("⚠️ Já existe uma instância ativa deste bot. Encerrando...")
    sys.exit()

os.environ["RUNNING_INSTANCE"] = "1"

# -------------------- SISTEMA DE TOKEN APRIMORADO --------------------
def get_discord_token():
    """Obtém o token com múltiplos fallbacks e validação"""
    # 1. Tentativa via variáveis de ambiente (com correção de nome)
    token = os.getenv("DISCORD_TOKEN") or os.getenv("DISGORD_TOKEN") or os.getenv("TOKEN")
    
    # 2. Fallback para secret files
    if not token:
        secret_paths = [
            "/etc/secrets/DISCORD_TOKEN",
            "/etc/secrets/discord_token",
            "/run/secrets/discord_token",
            "/var/run/secrets/discord_token",
            "./.env.discord"
        ]
        token = _read_secret_file(secret_paths)
    
    # Validação e limpeza
    if not token:
        raise RuntimeError(
            "❌ Token não encontrado. Verifique: \n"
            "1. Variáveis de ambiente no Render (DISCORD_TOKEN)\n"
            "2. Secret Files (se configurado)\n"
            "3. Se o bot está ativado no Discord Developer Portal"
        )
    
    token = token.strip()
    if token.lower().startswith("bot "):
        token = token[4:].strip()
    
    # Debug seguro
    print(f"🔑 Token carregado. Tamanho: {len(token)} caracteres")
    print(f"    Primeiros 4: {token[:4]}... Últimos 4: ...{token[-4:]}")
    
    return token

def _read_secret_file(paths):
    """Lê arquivos secretos com tratamento de erros"""
    for p in paths:
        try:
            if os.path.isfile(p):
                with open(p, "r") as f:
                    content = f.read().strip()
                    if content:
                        return content
        except Exception:
            continue
    return None

TOKEN = get_discord_token()

# -------------------- helper para ler ints da env --------------------
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

# -------------------- leitura de outros ids via env --------------------
GUILD_ID = _int_env("GUILD_ID", 1213316038805164093)
BOOSTER_ROLE_ID = _int_env("BOOSTER_ROLE_ID", 1248070897697427467)
CUSTOM_BOOSTER_ROLE_ID = _int_env("CUSTOM_BOOSTER_ROLE_ID", BOOSTER_ROLE_ID)

# -------------------- BOT SETUP --------------------
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# [TODO O RESTO DO SEU CÓDIGO PERMANECE EXATAMENTE IGUAL A PARTIR DAQUI]
# ID único para identificar a instância atual
INSTANCE_ID = str(uuid.uuid4())[:8]
print(f"🚀 Instância iniciada com ID: {INSTANCE_ID}")

# ... [Todo o restante do seu código permanece inalterado] ...

# --------------- Start / Tratamento de erros APRIMORADO ---------------
def start_bot():
    try:
        keep_alive()  # inicia keep-alive antes do bot
        
        @bot.event
        async def on_connect():
            print(f"🌐 Conectado ao Discord (Latência: {round(bot.latency*1000)}ms)")
            
        @bot.event
        async def on_disconnect():
            print("⚠️ Desconectado do Discord - Tentando reconectar...")
        
        print("🔄 Iniciando bot...")
        bot.run(TOKEN)
        
    except discord.LoginFailure as e:
        print(f"❌ Falha no login: {e}")
        print("ℹ️ Soluções possíveis:")
        print("1. Verifique se o token está correto no Render")
        print("2. Gere um novo token no Discord Developer Portal")
        print("3. Verifique se o bot está ativado")
        sys.exit(1)
        
    except Exception as e:
        print(f"❌ Erro inesperado: {type(e).__name__} - {e}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    start_bot()
