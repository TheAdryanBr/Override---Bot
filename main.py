# shim_audioop_main.py (substitua o seu main.py por este)
# Forçar uso de PyNaCl para resolver possíveis problemas de áudio (se instalar)
import os
os.environ.setdefault("DISCORD_INSTANCE", "true")

# ======= SHIM: cria um módulo 'audioop' falso caso não exista =======
# Isso evita que a importação do discord.py falhe em ambientes sem o módulo C audioop.
import types, sys

try:
    import audioop  # se existir, ótimo
except Exception:
    shim = types.ModuleType("audioop")
    shim.__doc__ = "Shim module for audioop — raises RuntimeError when functions are used."
    def __getattr__(name):
        def _missing(*args, **kwargs):
            raise RuntimeError(
                "audioop não disponível neste ambiente. "
                "Funções de áudio/voz do discord irão falhar se forem chamadas."
            )
        return _missing
    # Permite from audioop import * sem crash ao acessar atributos desconhecidos.
    shim.__getattr__ = __getattr__
    sys.modules["audioop"] = shim
# ===================================================================

# tenta importar PyNaCl (opcional)
try:
    import nacl  # só necessário se usar voice
except Exception:
    # se não existir, não falha aqui — falhará mais tarde quando usar voz
    pass

import sys
import json
import re
import asyncio
import traceback
import time
import uuid
import threading
from datetime import datetime, timezone, timedelta

import discord
from discord.ext import commands, tasks
from discord.ui import View, button

from flask import Flask

# ==================== CONFIGURAÇÃO INICIAL ====================
app = Flask(__name__)

# ==================== SISTEMA DE TOKEN (fallbacks) ====================
def _read_secret_file(paths):
    for path in paths:
        try:
            if os.path.isfile(path):
                with open(path, "r", encoding="utf-8") as f:
                    s = f.read().strip()
                    if s:
                        return s
        except Exception:
            continue
    return None

def get_valid_token():
    secret_paths = [
        "/etc/secrets/DISCORD_TOKEN",
        "/etc/secrets/discord_token",
        "/run/secrets/DISCORD_TOKEN",
        "./.env.discord",
        "./.env"
    ]
    env_checks = ["DISCORD_TOKEN", "DISGORD_TOKEN", "TOKEN"]

    token = None
    source = None
    for ev in env_checks:
        val = os.getenv(ev)
        if val:
            token = val
            source = f"env:{ev}"
            break

    if not token:
        val = _read_secret_file(secret_paths)
        if val:
            token = val
            source = f"file:{secret_paths}"

    if not token:
        raise RuntimeError(
            "❌ Token não encontrado. Configure DISCORD_TOKEN (ou TOKEN) nas env vars "
            "ou utilize um secret file. Após atualizar, redeploy/restart."
        )

    token = token.strip()
    if token.lower().startswith("bot "):
        token = token[4:].strip()

    # checagem simples
    if not re.match(r"^[A-Za-z0-9\._\-]{20,200}$", token):
        preview = (token[:4] + "..." + token[-4:]) if len(token) >= 8 else token
        raise ValueError(f"Token com formato suspeito (preview: {preview}) - gere novo token se necessário. origem={source}")

    masked = token[:4] + "..." + token[-4:]
    print(f"🔑 Token carregado (preview: {masked}) — origem: {source}")
    return token

# Pega token (não deixar hardcoded)
TOKEN = get_valid_token()

# ==================== CONFIG DO BOT ====================
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

GUILD_ID = _int_env("GUILD_ID", 1213316038805164093)
BOOSTER_ROLE_ID = _int_env("BOOSTER_ROLE_ID", 1248070897697427467)
CUSTOM_BOOSTER_ROLE_ID = _int_env("CUSTOM_BOOSTER_ROLE_ID", BOOSTER_ROLE_ID)

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

INSTANCE_ID = str(uuid.uuid4())[:8]
print(f"🚀 Instância iniciada com ID: {INSTANCE_ID}")

processing_commands = set()
creation_locks = {}
fixed_booster_message = None

# -------- CONFIG DE CANAIS FIXOS/ CATEGORIAS -------------
CANAL_FIXO_CONFIG = {
    1404889040007725107: {"categoria_id": 1213316039350296637, "prefixo_nome": "Call│"},
    1404886431075401858: {"categoria_id": 1213319157639020564, "prefixo_nome": "♨️|Java│"},
    1213319477429801011: {"categoria_id": 1213319157639020564, "prefixo_nome": "🪨|Bedrock|"},
    1213321053196263464: {"categoria_id": 1213319620287664159, "prefixo_nome": "🎧│Call│"},
    1213322485479637012: {"categoria_id": 1213322073594793994, "prefixo_nome": "👥│Dupla│"},
    1213322743123148920: {"categoria_id": 1213322073594793994, "prefixo_nome": "👥│Trio│"},
    1213322826564767776: {"categoria_id": 1213322073594793994, "prefixo_nome": "👥│Squad│"},
    1216123178548465755: {"categoria_id": 1216123032138154008, "prefixo_nome": "👥│Duo│"},
    1216123306579595274: {"categoria_id": 1216123032138154008, "prefixo_nome": "👥│Trio│"},
    1216123421688205322: {"categoria_id": 1216123032138154008, "prefixo_nome": "👥│Team│"},
    1213533210907246592: {"categoria_id": 1213532914520690739, "prefixo_nome": "🎧│Sala│"},
}

# ----------- ARQUIVO PARA SALVAR TEMPO DE BOOSTERS --------------
DATA_FILE = "boosters_data.json"

def load_boosters_data():
    if not os.path.isfile(DATA_FILE):
        return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_boosters_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

boosters_data = load_boosters_data()

# -------------------- VOICE STATE (criação segura) --------------------
@bot.event
async def on_voice_state_update(member, before, after):
    try:
        print(f"Voice state update: {member} entrou no canal {after.channel.id if after.channel else 'Nenhum'} (before: {before.channel.id if before.channel else 'Nenhum'})")
    except Exception:
        print("Voice state update: erro ao printar membro/canais")

    # -------------- criação de canal dinâmico ----------------
    if after.channel and after.channel.id in CANAL_FIXO_CONFIG:
        config = CANAL_FIXO_CONFIG[after.channel.id]
        guild = member.guild

        # garante CategoryChannel pelo ID
        category = guild.get_channel(config["categoria_id"])
        if not category or not isinstance(category, discord.CategoryChannel):
            print(f"Categoria não encontrada ou não é CategoryChannel (id: {config['categoria_id']})")
        else:
            prefixo = config["prefixo_nome"]

            # lock por template
            lock = creation_locks.get(after.channel.id)
            if lock is None:
                lock = asyncio.Lock()
                creation_locks[after.channel.id] = lock

            async with lock:
                # canais existentes da categoria com o prefixo
                canais_existentes = [c for c in category.voice_channels if c.name.startswith(prefixo)]

                # extrai números já usados (ex.: "Call│ 1")
                usados = set()
                pattern = rf'^{re.escape(prefixo)}\s*(\d+)$'
                for c in canais_existentes:
                    m = re.search(pattern, c.name)
                    if m:
                        try:
                            usados.add(int(m.group(1)))
                        except:
                            pass

                numero = 1
                while numero in usados:
                    numero += 1

                nome_canal = f"{prefixo} {numero}"

                # cria o canal na categoria correta
                try:
                    new_channel = await guild.create_voice_channel(
                        name=nome_canal,
                        category=category,
                        user_limit=5,
                        reason="Dynamic voice room created"
                    )
                    print(f"Canal criado: {new_channel.name} (ID: {new_channel.id})")
                except Exception as e:
                    print(f"Erro ao criar canal: {e}")
                    new_channel = None

                # tenta posicionar o novo canal logo após o canal template
                if new_channel:
                    try:
                        template_channel = guild.get_channel(after.channel.id)
                        if template_channel:
                            await new_channel.edit(position=(template_channel.position + 1))
                    except Exception as e:
                        print(f"Não foi possível ajustar a posição do canal: {e}")

                    # move o usuário para o novo canal
                    try:
                        await member.move_to(new_channel)
                        print(f"Movendo {member} para {new_channel.name}")
                    except Exception as e:
                        print(f"Erro ao mover membro para o novo canal: {e}")

    # -------------- exclusão de canais vazios --------------
    if before.channel:
        try:
            categorias_usadas = {conf["categoria_id"] for conf in CANAL_FIXO_CONFIG.values()}
            if before.channel.category_id in categorias_usadas and before.channel.id not in CANAL_FIXO_CONFIG:
                if len(before.channel.members) == 0:
                    try:
                        print(f"Canal vazio detectado: {before.channel.name}, deletando...")
                        await before.channel.delete(reason="Dynamic voice room became empty")
                    except Exception as e:
                        print(f"Erro ao deletar canal vazio: {e}")
        except Exception as e:
            print(f"Erro na rotina de exclusão: {e}")

# -------------------- Helpers e View (mantive seu código) --------------------
def format_relative_time(boost_time):
    now = datetime.now(timezone.utc)
    diff = now - boost_time
    days = diff.days
    hours = diff.seconds // 3600
    minutes = (diff.seconds % 3600) // 60
    seconds = diff.seconds % 60
    parts = []
    if days > 0:
        parts.append(f"{days} dia{'s' if days > 1 else ''}")
    if hours > 0:
        parts.append(f"{hours} hora{'s' if hours > 1 else ''}")
    if minutes > 0:
        parts.append(f"{minutes} minuto{'s' if minutes > 1 else ''}")
    if seconds > 0 or not parts:
        parts.append(f"{seconds} segundo{'s' if seconds > 1 else ''}")
    if not parts:
        return "agora"
    return "há " + ", ".join(parts[:-1]) + (" e " + parts[-1] if len(parts) > 1 else "")

class BoosterRankView(View):
    def __init__(self, boosters, is_personal=False):
        super().__init__(timeout=None)
        self.boosters = boosters
        self.page = 0
        self.per_page = 5
        self.is_personal = is_personal
        self.update_disabled()

    def update_disabled(self):
        try:
            self.children[0].disabled = self.page == 0  # previous
            self.children[2].disabled = self.page == 0  # home
            self.children[3].disabled = self.page + self.per_page >= len(self.boosters)  # next
        except:
            pass

    def build_embed(self):
        embed = discord.Embed(title="🏆 Top Boosters", color=discord.Color.purple())
        start = self.page
        end = min(self.page + self.per_page, len(self.boosters))

        for i, (member, boost_time) in enumerate(self.boosters[start:end], start=1 + self.page):
            formatted_time = format_relative_time(boost_time)
            embed.add_field(
                name=f"{i}. {member.display_name}",
                value=f"🕒 Boostando desde {formatted_time}",
                inline=False
            )
        if self.boosters:
            try:
                embed.set_thumbnail(url=self.boosters[0][0].avatar.url if self.boosters[0][0].avatar else self.boosters[0][0].default_avatar.url)
            except:
                pass

        embed.set_footer(text=f"Exibindo {start + 1}-{end} de {len(self.boosters)} boosters")
        return embed

    @button(label="⬅ Voltar", style=discord.ButtonStyle.secondary, custom_id="previous")
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        new_page = max(0, self.page - self.per_page)
        if self.is_personal:
            self.page = new_page
            self.update_disabled()
            embed = self.build_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            new_view = BoosterRankView(self.boosters, is_personal=True)
            new_view.page = new_page
            new_view.update_disabled()
            embed = new_view.build_embed()
            await interaction.response.send_message(embed=embed, view=new_view, ephemeral=True)

    @button(label="🔁 Atualizar", style=discord.ButtonStyle.primary, custom_id="refresh")
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        role = guild.get_role(CUSTOM_BOOSTER_ROLE_ID)
        boosters = []
        if role and role.members:
            for member in role.members:
                user_id_str = str(member.id)
                start_time_str = boosters_data.get(user_id_str)
                if start_time_str:
                    start_time = datetime.fromisoformat(start_time_str)
                else:
                    start_time = member.premium_since or datetime.now(timezone.utc)
                boosters.append((member, start_time))
            boosters.sort(key=lambda x: x[1])
        if self.is_personal:
            self.boosters = boosters
            self.page = 0
            self.update_disabled()
            embed = self.build_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            new_view = BoosterRankView(boosters, is_personal=True)
            embed = new_view.build_embed()
            await interaction.response.send_message(embed=embed, view=new_view, ephemeral=True)

    @button(label="🏠 Início", style=discord.ButtonStyle.success, custom_id="home")
    async def home(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.is_personal:
            self.page = 0
            self.update_disabled()
            embed = self.build_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            new_view = BoosterRankView(self.boosters, is_personal=True)
            new_view.page = 0
            new_view.update_disabled()
            embed = new_view.build_embed()
            await interaction.response.send_message(embed=embed, view=new_view, ephemeral=True)

    @button(label="➡ Avançar", style=discord.ButtonStyle.secondary, custom_id="next")
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        new_page = min(len(self.boosters) - self.per_page, self.page + self.per_page)
        if self.is_personal:
            self.page = new_page
            self.update_disabled()
            embed = self.build_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            new_view = BoosterRankView(self.boosters, is_personal=True)
            new_view.page = new_page
            new_view.update_disabled()
            embed = new_view.build_embed()
            await interaction.response.send_message(embed=new_view.build_embed(), view=new_view, ephemeral=True)

# -------------------- Comandos / lógica do bot (mantido) --------------------
@bot.command()
async def boosters(ctx):
    global fixed_booster_message
    if ctx.author.id in processing_commands:
        print(f"[{INSTANCE_ID}] ❌ Comando ignorado (duplicado): boosters")
        return
    processing_commands.add(ctx.author.id)
    print(f"[{INSTANCE_ID}] ✅ Executando comando: boosters")

    if fixed_booster_message is not None:
        await ctx.send("✅ Mensagem de ranking já está ativa!")
    else:
        await send_booster_rank(ctx.channel)
    processing_commands.remove(ctx.author.id)

@bot.command()
async def testboost(ctx):
    if ctx.author.id in processing_commands:
        print(f"[{INSTANCE_ID}] ❌ Comando ignorado (duplicado): testboost")
        return
    processing_commands.add(ctx.author.id)
    print(f"[{INSTANCE_ID}] ✅ Executando comando: testboost")
    await send_booster_rank(ctx.channel, fake=True, tester=ctx.author)
    processing_commands.remove(ctx.author.id)

async def send_booster_rank(channel, fake=False, tester=None, edit_message=None):
    global fixed_booster_message
    guild = bot.get_guild(GUILD_ID)

    if fake and tester:
        now = datetime.now(timezone.utc)
        fake_boosters = [(tester, now - timedelta(days=10))]
        for i in range(1, 7):
            member = discord.Object(id=100000000000000000 + i)
            member.display_name = f"FakeUser{i}"
            member.avatar = tester.avatar
            fake_boosters.append((member, now - timedelta(days=i * 5)))
        boosters = fake_boosters
    else:
        boosters = []
        if guild:
            role = guild.get_role(CUSTOM_BOOSTER_ROLE_ID)
            if role:
                for member in role.members:
                    user_id_str = str(member.id)
                    start_time_str = boosters_data.get(user_id_str)
                    if start_time_str:
                        start_time = datetime.fromisoformat(start_time_str)
                    else:
                        start_time = member.premium_since or datetime.now(timezone.utc)
                    boosters.append((member, start_time))
                boosters.sort(key=lambda x: x[1])

    if not boosters:
        if edit_message is None:
            await channel.send("❌ Nenhum booster encontrado.")
        return

    view = BoosterRankView(boosters, is_personal=False)
    embed = view.build_embed()

    if edit_message:
        await edit_message.edit(embed=embed, view=view)
        fixed_booster_message = edit_message
    else:
        msg = await channel.send(embed=embed, view=view)
        fixed_booster_message = msg

# Evento para adicionar/remover cargo custom e salvar tempo boost
@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    guild = bot.get_guild(GUILD_ID)
    if not guild or after.guild.id != GUILD_ID:
        return

    booster_role = guild.get_role(BOOSTER_ROLE_ID)
    custom_role = guild.get_role(CUSTOM_BOOSTER_ROLE_ID)
    if not booster_role or not custom_role:
        print("Cargo oficial booster ou cargo custom não encontrado")
        return

    user_id_str = str(after.id)
    had_booster = booster_role in before.roles
    has_booster = booster_role in after.roles

    # Ganhou cargo oficial
    if not had_booster and has_booster:
        if custom_role not in after.roles:
            await after.add_roles(custom_role, reason="Usuário deu boost, cargo custom adicionado")
            print(f"Cargo custom adicionado a {after.display_name}")

        boosters_data[user_id_str] = datetime.now(timezone.utc).isoformat()
        save_boosters_data(boosters_data)
        print(f"Data de boost salva para {after.display_name}")

    # Perdeu cargo oficial
    elif had_booster and not has_booster:
        if custom_role in after.roles:
            await after.remove_roles(custom_role, reason="Usuário removeu boost, cargo custom removido")
            print(f"Cargo custom removido de {after.display_name}")

        if user_id_str in boosters_data:
            del boosters_data[user_id_str]
            save_boosters_data(boosters_data)
            print(f"Data de boost removida para {after.display_name}")

@bot.command()
async def boosttime(ctx, member: discord.Member = None):
    member = member or ctx.author
    user_id_str = str(member.id)

    if user_id_str not in boosters_data:
        await ctx.send(f"{member.display_name} não possui boost ativo registrado")
        return

    start_time = datetime.fromisoformat(boosters_data[user_id_str])
    formatted_time = format_relative_time(start_time)
    await ctx.send(f"{member.display_name} está boostando {formatted_time}")

@bot.event
async def on_ready():
    print(f"[{INSTANCE_ID}] ✅ Bot online como {bot.user}")
    try:
        bot.add_view(BoosterRankView([]))
    except Exception:
        pass
    try:
        update_booster_message.start()
    except Exception as e:
        print(f"Erro ao iniciar task update_booster_message: {e}")

@tasks.loop(seconds=3600)
async def update_booster_message():
    global fixed_booster_message
    if fixed_booster_message is None:
        return
    try:
        await send_booster_rank(fixed_booster_message.channel, edit_message=fixed_booster_message)
        print(f"[{INSTANCE_ID}] 🔄 Mensagem fixa do ranking atualizada automaticamente")
    except Exception as e:
        print(f"[{INSTANCE_ID}] ❌ Erro ao atualizar mensagem fixa: {e}")

# ==================== INICIALIZAÇÃO (keep-alive + bot em thread) ====================
def run_bot():
    @bot.event
    async def on_connect():
        print(f"🌐 Conectado ao Discord (latência: {round(bot.latency*1000)}ms)")

    @bot.event
    async def on_disconnect():
        print("⚠️ Desconectado do Discord - Tentando reconectar...")

    try:
        bot.run(TOKEN)
    except Exception as e:
        print(f"❌ Erro no bot: {type(e).__name__} - {e}")
        traceback.print_exc()
        os._exit(1)

if __name__ == '__main__':
    # Inicia o bot em uma thread separada
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()

    # Inicia o servidor Flask para keep-alive
    print("🌍 Iniciando servidor web (Flask)...")
    app.run(host='0.0.0.0', port=8080, debug=False)
