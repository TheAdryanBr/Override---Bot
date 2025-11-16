# main.py — ranking + /denunciar (slash) + boas-vindas/saída (com auto-role)
import os
import sys
import json
import re
import asyncio
import aiohttp
import random
import logging as _logging
import traceback
import time
import uuid
import types
from typing import Optional
from datetime import datetime, timezone, timedelta

# ======== SHIM PARA `audioop` (ambientes minimalistas) ========
try:
    import audioop
except Exception:
    shim = types.ModuleType("audioop")
    def _noop_fragment(fragment, *a, **k): return fragment
    def _noop_int(*a, **k): return 0
    def _ratecv(fragment, width, nchannels, state, ratein, rateout):
        return fragment, state
    shim.rms = _noop_int
    shim.max = _noop_int
    shim.min = _noop_int
    shim.add = _noop_fragment
    shim.ratecv = _ratecv
    shim.lin2lin = _noop_fragment
    shim.tomono = _noop_fragment
    shim.tostereo = _noop_fragment
    sys.modules["audioop"] = shim

import discord
from discord.ext import commands, tasks
from discord.ui import View, button
from discord import app_commands

from flask import Flask
from threading import Thread

# -------------------- KEEP ALIVE (Flask) --------------------
app = Flask('')
@app.route('/')
def home():
    return "Bot está rodando!"
@app.route('/health')
def health():
    return "ok", 200

def run_flask():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run_flask, daemon=True)
    t.start()

# -------------------- MULTI-INSTANCE GUARD --------------------
if os.environ.get("RUNNING_INSTANCE") == "1":
    print("⚠️ Já existe uma instância ativa deste bot. Encerrando...")
    sys.exit()
os.environ["RUNNING_INSTANCE"] = "1"

# helpers / env reading
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

# IDs/Config
REPORT_CHANNEL_ID = _int_env("REPORT_CHANNEL_ID", 0)
ADMIN_ROLE_ID = _int_env("ADMIN_ROLE_ID", 0)
WELCOME_CHANNEL_ID = _int_env("WELCOME_CHANNEL_ID", 0)
WELCOME_LOG_CHANNEL_ID = _int_env("WELCOME_LOG_CHANNEL_ID", 0)
# NOVO: ID do cargo que será dado automaticamente ao entrar (opcional)
MEMBER_ROLE_ID = _int_env("MEMBER_ROLE_ID", 0)

GUILD_ID = _int_env("GUILD_ID", 1213316038805164093)
BOOSTER_ROLE_ID = _int_env("BOOSTER_ROLE_ID", 1406307445306818683)
CUSTOM_BOOSTER_ROLE_ID = _int_env("CUSTOM_BOOSTER_ROLE_ID", BOOSTER_ROLE_ID)

# ================== CONFIG DE VOICE ROOMS DINÂMICOS ==================
CANAL_FIXO_CONFIG = {
    1406308661810171965: {"categoria_id": 1213316039350296637, "prefixo_nome": "Call│"},
    1404889040007725107: {"categoria_id": 1213319157639020564, "prefixo_nome": "♨│Java│"},
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

# Guarda os canais criados para apagar depois
voice_rooms_criados = {}


intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

_log_bg = _logging.getLogger("bg_traffic")

# intervalos (segundos) - pode ajustar via env vars se quiser
BG_MIN_DELAY = int(os.environ.get("BG_MIN_DELAY", 5 * 60))   # 5 minutos
BG_MAX_DELAY = int(os.environ.get("BG_MAX_DELAY", 20 * 60))  # 20 minutos

# endpoints públicos leves para gerar tráfego de saída (não pingam seu próprio serviço)
BG_ENDPOINTS = [
    "https://api.github.com/zen",
    "https://httpbin.org/get"
]

BG_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (BotKeepAlive)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
}

async def _background_traffic_loop():
    """
    Loop infinito que cria tráfego de saída em intervalos aleatórios.
    Mantemos uma única ClientSession para todo o tempo para ser eficiente.
    """
    _log_bg.info("Background traffic loop iniciado.")
    try:
        async with aiohttp.ClientSession() as session:
            while True:
                delay = random.randint(BG_MIN_DELAY, BG_MAX_DELAY)
                _log_bg.info(f"bg sleeping {delay}s (min={BG_MIN_DELAY} max={BG_MAX_DELAY})")
                await asyncio.sleep(delay)

                url = random.choice(BG_ENDPOINTS)
                try:
                    # timeout curto para não travar
                    async with session.get(url, headers=BG_HEADERS, timeout=15) as resp:
                        # não precisamos do corpo inteiro — apenas garantir requisição
                        text = await resp.text()
                        _log_bg.info(f"bg ping -> {url} status={resp.status} len={len(text) if text else 0}")
                except Exception as e:
                    _log_bg.warning(f"bg ping falhou para {url}: {e}")
    except asyncio.CancelledError:
        _log_bg.info("Background traffic loop cancelado.")
    except Exception as e:
        _log_bg.exception("Erro fatal no background traffic loop: %s", e)

# garante que a task seja iniciada apenas 1 vez
async def _start_background_traffic_once():
    if getattr(bot, "_bg_task_started", False):
        return
    bot._bg_task_started = True
    # cria task no loop do bot
    bot.loop.create_task(_background_traffic_loop())

# registra um listener minimalista: ao conectar, inicializa a task (não substitui eventos on_ready existentes)
@bot.event
async def _bg_on_ready_starter():
    # tenta iniciar a task (a função cuida para não criar duplicadas)
    try:
        await _start_background_traffic_once()
    except Exception:
        _log_bg.exception("Falha ao iniciar background traffic task no on_ready.")

INSTANCE_ID = str(uuid.uuid4())[:8]
print(f"🚀 Instância iniciada com ID: {INSTANCE_ID}")

processing_commands = set()
creation_locks = {}
fixed_booster_message = None

# data file
DATA_FILE = "boosters_data.json"
def load_boosters_data():
    if not os.path.isfile(DATA_FILE):
        return {}
    with open(DATA_FILE, "r") as f:
        return json.load(f)
def save_boosters_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)
boosters_data = load_boosters_data()

# helper de tempo
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
    return "há " + ", ".join(parts[:-1]) + (" e " + parts[-1] if len(parts) > 1 else parts[0])

# ---------- Ranking embeds (1 embed por usuário) ----------
def build_embeds_for_page(boosters, page=0, per_page=5):
    embeds = []
    start = page
    end = min(page + per_page, len(boosters))
    for idx, (member, boost_time) in enumerate(boosters[start:end], start=1 + page):
        display_name = getattr(member, "display_name", getattr(member, "name", f"User {getattr(member,'id','???')}"))
        formatted_time = format_relative_time(boost_time)
        embed = discord.Embed(title=f"{idx}. {display_name}", description=f"🕒 Boostando desde {formatted_time}", color=discord.Color.purple())
        try:
            avatar_url = None
            if hasattr(member, "display_avatar"):
                avatar_url = member.display_avatar.url
            elif getattr(member, "avatar", None):
                avatar_url = member.avatar.url
            if avatar_url:
                embed.set_thumbnail(url=avatar_url)
        except Exception:
            pass
        if idx == 1 + page:
            embed.set_footer(text=f"Exibindo {start + 1}-{end} de {len(boosters)} boosters")
        embeds.append(embed)
    return embeds

# -------------------- View (botões) --------------------
class BoosterRankView(View):
    def __init__(self, boosters, is_personal=False):
        super().__init__(timeout=None)
        self.boosters = boosters or []
        self.page = 0
        self.per_page = 5
        self.is_personal = is_personal
        self.update_disabled()

    def update_disabled(self):
        total = len(self.boosters)
        try:
            prev_disabled = self.page <= 0
            next_disabled = (self.page + self.per_page) >= total
            if len(self.children) >= 4:
                self.children[0].disabled = prev_disabled
                self.children[2].disabled = prev_disabled
                self.children[3].disabled = next_disabled
        except Exception:
            pass

    @button(label="⬅ Voltar", style=discord.ButtonStyle.secondary, custom_id="previous")
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        new_page = max(0, self.page - self.per_page)
        if self.is_personal:
            self.page = new_page
            self.update_disabled()
            embeds = build_embeds_for_page(self.boosters, page=self.page, per_page=self.per_page)
            await interaction.response.edit_message(embeds=embeds, view=self)
        else:
            new_view = BoosterRankView(self.boosters, is_personal=True)
            new_view.page = new_page
            new_view.update_disabled()
            embeds = build_embeds_for_page(self.boosters, page=new_page, per_page=new_view.per_page)
            await interaction.response.send_message(embeds=embeds, view=new_view, ephemeral=True)

    @button(label="🔁 Atualizar", style=discord.ButtonStyle.primary, custom_id="refresh")
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        role = guild.get_role(CUSTOM_BOOSTER_ROLE_ID) if guild else None
        boosters = []
        if role and role.members:
            for member in role.members:
                user_id_str = str(member.id)
                start_time_str = boosters_data.get(user_id_str)
                start_time = (datetime.fromisoformat(start_time_str) if start_time_str else member.premium_since or datetime.now(timezone.utc))
                boosters.append((member, start_time))
            boosters.sort(key=lambda x: x[1])
        if self.is_personal:
            self.boosters = boosters
            self.page = 0
            self.update_disabled()
            embeds = build_embeds_for_page(self.boosters, page=self.page, per_page=self.per_page)
            await interaction.response.edit_message(embeds=embeds, view=self)
        else:
            new_view = BoosterRankView(boosters, is_personal=True)
            embeds = build_embeds_for_page(boosters, page=0, per_page=new_view.per_page)
            await interaction.response.send_message(embeds=embeds, view=new_view, ephemeral=True)

    @button(label="🏠 Início", style=discord.ButtonStyle.success, custom_id="home")
    async def home(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.is_personal:
            self.page = 0
            self.update_disabled()
            embeds = build_embeds_for_page(self.boosters, page=0, per_page=self.per_page)
            await interaction.response.edit_message(embeds=embeds, view=self)
        else:
            new_view = BoosterRankView(self.boosters, is_personal=True)
            embeds = build_embeds_for_page(self.boosters, page=0, per_page=new_view.per_page)
            await interaction.response.send_message(embeds=embeds, view=new_view, ephemeral=True)

    @button(label="➡ Avançar", style=discord.ButtonStyle.secondary, custom_id="next")
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        max_start = max(0, len(self.boosters) - self.per_page)
        new_page = min(max_start, self.page + self.per_page)
        if self.is_personal:
            self.page = new_page
            self.update_disabled()
            embeds = build_embeds_for_page(self.boosters, page=self.page, per_page=self.per_page)
            await interaction.response.edit_message(embeds=embeds, view=self)
        else:
            new_view = BoosterRankView(self.boosters, is_personal=True)
            new_view.page = new_page
            new_view.update_disabled()
            embeds = build_embeds_for_page(self.boosters, page=new_page, per_page=new_view.per_page)
            await interaction.response.send_message(embeds=embeds, view=new_view, ephemeral=True)

# -------------------- Comandos / lógica do ranking --------------------
@bot.command()
async def boosters(ctx):
    global fixed_booster_message
    if ctx.author.id in processing_commands:
        print(f"[{INSTANCE_ID}] ❌ Comando ignorado (duplicado): boosters")
        return
    processing_commands.add(ctx.author.id)
    try:
        if fixed_booster_message is not None:
            await ctx.send("✅ Mensagem de ranking já está ativa!")
        else:
            await send_booster_rank(ctx.channel)
    finally:
        processing_commands.remove(ctx.author.id)

@bot.command()
async def testboost(ctx):
    if ctx.author.id in processing_commands:
        print(f"[{INSTANCE_ID}] ❌ Comando ignorado (duplicado): testboost")
        return
    processing_commands.add(ctx.author.id)
    try:
        await send_booster_rank(ctx.channel, fake=True, tester=ctx.author)
    finally:
        processing_commands.remove(ctx.author.id)

async def send_booster_rank(channel, fake=False, tester=None, edit_message=None, page=0, per_page=5):
    """
    Envia N embeds por página (cada embed tem thumbnail = avatar do user).
    """
    global fixed_booster_message
    guild = bot.get_guild(GUILD_ID)
    boosters = []

    if fake and tester:
        now = datetime.now(timezone.utc)
        fake_boosters = [(tester, now - timedelta(days=10))]
        for i in range(1, 7):
            member = discord.Object(id=100000000000000000 + i)
            member.display_name = f"FakeUser{i}"
            fake_boosters.append((member, now - timedelta(days=i * 5)))
        boosters = fake_boosters
    else:
        if not guild:
            await channel.send("❌ Guild não encontrada (bot pode não estar no servidor).")
            return
        role = guild.get_role(CUSTOM_BOOSTER_ROLE_ID)
        if not role:
            await channel.send("❌ Cargo custom de booster não encontrado.")
            return
        for member in role.members:
            user_id_str = str(member.id)
            start_time_str = boosters_data.get(user_id_str)
            start_time = (datetime.fromisoformat(start_time_str) if start_time_str else member.premium_since or datetime.now(timezone.utc))
            boosters.append((member, start_time))
        boosters.sort(key=lambda x: x[1])

    if not boosters:
        if edit_message is None:
            await channel.send("❌ Nenhum booster encontrado.")
        return

    view = BoosterRankView(boosters, is_personal=False)
    embeds = build_embeds_for_page(boosters, page=page, per_page=per_page)

    try:
        if edit_message:
            try:
                await edit_message.edit(embeds=embeds, view=view)
                fixed_booster_message = edit_message
            except Exception:
                try:
                    await edit_message.delete()
                except Exception:
                    pass
                fixed_booster_message = await channel.send(embeds=embeds, view=view)
        else:
            fixed_booster_message = await channel.send(embeds=embeds, view=view)
    except Exception as e:
        print("Erro ao enviar/editar mensagem do ranking:", e)
        raise

# Evento para adicionar/remover cargo custom e salvar tempo boost
@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    guild = bot.get_guild(GUILD_ID)
    if not guild or (after and getattr(after, "guild", None) and after.guild.id != GUILD_ID):
        return

    booster_role = guild.get_role(BOOSTER_ROLE_ID) if guild else None
    custom_role = guild.get_role(CUSTOM_BOOSTER_ROLE_ID) if guild else None
    if not booster_role or not custom_role:
        print("Cargo oficial booster ou cargo custom não encontrado")
        return

    user_id_str = str(after.id)
    had_booster = booster_role in before.roles
    has_booster = booster_role in after.roles

    if not had_booster and has_booster:
        if custom_role not in after.roles:
            try:
                await after.add_roles(custom_role, reason="Usuário deu boost, cargo custom adicionado")
            except Exception as e:
                print("Erro ao adicionar cargo custom:", e)
        boosters_data[user_id_str] = datetime.now(timezone.utc).isoformat()
        save_boosters_data(boosters_data)
        print(f"Data de boost salva para {after.display_name}")

    elif had_booster and not has_booster:
        if custom_role in after.roles:
            try:
                await after.remove_roles(custom_role, reason="Usuário removeu boost, cargo custom removido")
            except Exception as e:
                print("Erro ao remover cargo custom:", e)
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
    await ctx.send(f"{member.display_name} está boostando {format_relative_time(start_time)}")

# -------------------- Denúncias (slash) --------------------
async def ensure_report_channel(guild: discord.Guild) -> Optional[discord.TextChannel]:
    global REPORT_CHANNEL_ID
    if REPORT_CHANNEL_ID:
        ch = guild.get_channel(REPORT_CHANNEL_ID)
        if isinstance(ch, discord.TextChannel):
            return ch
        REPORT_CHANNEL_ID = 0

    for c in guild.text_channels:
        if c.name.lower() in ("denuncias", "denúncias", "reports"):
            return c

    try:
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False, read_messages=False),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_messages=True)
        }
        if ADMIN_ROLE_ID:
            role = guild.get_role(ADMIN_ROLE_ID)
            if role:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, read_messages=True, send_messages=True)
        ch = await guild.create_text_channel("denuncias", overwrites=overwrites, reason="Canal de denúncias criado pelo bot")
        REPORT_CHANNEL_ID = ch.id
        print(f"[{INSTANCE_ID}] Canal de denúncias criado: {ch.id}")
        return ch
    except Exception as e:
        print(f"[{INSTANCE_ID}] Não foi possível criar canal de denúncias: {e}")
        return None

CATEGORY_CHOICES = [
    app_commands.Choice(name="Spam / Publicidade", value="spam"),
    app_commands.Choice(name="Assédio / Abuso", value="assedio"),
    app_commands.Choice(name="Conteúdo ilegal / perigoso", value="ilegal"),
    app_commands.Choice(name="Violação de regras (outros)", value="outro"),
]

@bot.tree.command(name="denunciar", description="Enviar denúncia para a equipe (admins receberão).")
@app_commands.describe(
    categoria="Categoria da denúncia",
    detalhes="Descreva o que aconteceu (opcional).",
    link="Link de referência (opcional)",
    anexo1="Arquivo 1 (opcional)",
    anexo2="Arquivo 2 (opcional)",
    anexo3="Arquivo 3 (opcional)",
)
@app_commands.choices(categoria=CATEGORY_CHOICES)
async def denunciar(
    interaction: discord.Interaction,
    categoria: app_commands.Choice[str],
    detalhes: Optional[str] = None,
    link: Optional[str] = None,
    anexo1: Optional[discord.Attachment] = None,
    anexo2: Optional[discord.Attachment] = None,
    anexo3: Optional[discord.Attachment] = None,
):
    await interaction.response.defer(ephemeral=True)

    if interaction.guild is None:
        await interaction.followup.send("❌ Este comando só pode ser usado em servidores.", ephemeral=True)
        return

    guild = interaction.guild
    author = interaction.user
    channel_origin = interaction.channel

    report_channel = None
    if REPORT_CHANNEL_ID:
        report_channel = guild.get_channel(REPORT_CHANNEL_ID)
    if report_channel is None:
        report_channel = await ensure_report_channel(guild)
    if report_channel is None:
        await interaction.followup.send("❌ Não foi possível localizar/criar o canal de denúncias. Contate a staff.", ephemeral=True)
        return

    ts = datetime.now(timezone.utc)
    embed = discord.Embed(title="🛑 Nova denúncia (via /denunciar)", color=discord.Color.dark_red(), timestamp=ts)
    embed.add_field(name="Autor", value=f"{author} (`{author.id}`)", inline=True)
    embed.add_field(name="Servidor", value=f"{guild.name} (`{guild.id}`)", inline=True)
    embed.add_field(name="Canal de origem", value=f"{channel_origin.mention} (`{channel_origin.id}`)", inline=True)
    embed.add_field(name="Categoria", value=categoria.name, inline=True)

    if detalhes:
        txt = detalhes.strip()
        if len(txt) > 4000:
            txt = txt[:3997] + "..."
        embed.add_field(name="Descrição", value=txt, inline=False)

    if link:
        embed.add_field(name="Link", value=link, inline=False)

    embed.set_footer(text=f"Denúncia enviada por {author.display_name} • {author.id}")

    attachments = [a for a in (anexo1, anexo2, anexo3) if a is not None]
    files_to_send = []
    failed = []
    for a in attachments:
        try:
            f = await a.to_file(use_cached=True)
            files_to_send.append(f)
        except Exception as e:
            print(f"[{INSTANCE_ID}] Erro ao baixar attachment {getattr(a,'url',None)}: {e}")
            failed.append(getattr(a, "url", str(a)))

    mention_admin = ""
    if ADMIN_ROLE_ID:
        role = guild.get_role(ADMIN_ROLE_ID)
        if role:
            mention_admin = role.mention + " "

    try:
        if files_to_send:
            sent = await report_channel.send(content=mention_admin, embed=embed, files=files_to_send)
        else:
            sent = await report_channel.send(content=mention_admin, embed=embed)

        if failed:
            await report_channel.send(f"Atenção: alguns attachments não puderam ser baixados: " + ", ".join(failed))
    except Exception as e:
        print(f"[{INSTANCE_ID}] Erro ao enviar denúncia para o canal: {e}")
        await interaction.followup.send("❌ Erro ao encaminhar denúncia. Tente novamente mais tarde.", ephemeral=True)
        return

    await interaction.followup.send("✅ Denúncia enviada com sucesso. A equipe responsável será notificada.", ephemeral=True)

@denunciar.error
async def denunciar_error(interaction: discord.Interaction, error):
    try:
        print(f"[{INSTANCE_ID}] Erro no /denunciar: {error}")
        await interaction.followup.send("❌ Ocorreu um erro ao processar sua denúncia.", ephemeral=True)
    except Exception:
        pass

# -------------------- BOAS-VINDAS / SAÍDA --------------------
# convert color from your JSON negative value if desired
_WELCOME_COLOR_RAW = -2342853
_WELCOME_COLOR = _WELCOME_COLOR_RAW & 0xFFFFFF

def _find_welcome_channel(guild: discord.Guild) -> Optional[discord.TextChannel]:
    if WELCOME_CHANNEL_ID:
        ch = guild.get_channel(WELCOME_CHANNEL_ID)
        if isinstance(ch, discord.TextChannel):
            return ch
    candidates = {"welcome", "welcomes", "boas-vindas", "bem-vindos", "entradas", "entrada", "welcome-channel"}
    for c in guild.text_channels:
        if c.name.lower() in candidates:
            return c
    return None

def _build_welcome_embed(member: discord.Member) -> discord.Embed:
    # Use display_name inside the embed (so it doesn't render as a raw <@id> inside code blocks)
    title = f"``` {member.display_name} | 𝘽𝙚𝙢-𝙫𝙞𝙣𝙙𝙤(𝙖)! 👋```"
    description = f"```Seja bem vindo (a) {member.display_name}, agradeço por ter entrado no servidor, espero que goste dele, jogue e converse muito.```"
    embed = discord.Embed(title=title, description=description, color=discord.Color(_WELCOME_COLOR))
    try:
        avatar_url = member.display_avatar.url
        embed.set_thumbnail(url=avatar_url)
    except Exception:
        pass
    embed.add_field(
        name="📢│𝙁𝙞𝙦𝙪𝙚 𝙖𝙩𝙚𝙣𝙩𝙤!",
        value="Leias as regras no canal: <#1213332268618096690>\nDuvidas e sugestões no canal: <#1259311950958170205>\nAgora vai lá aproveitar 😁",
        inline=False
    )
    return embed

def _build_leave_content(member: discord.Member) -> str:
    # leave message keeps the mention (mention in content will ping if user still exists)
    return f"({member.mention} saiu do servidor) Triste, mas vá com Deus meu mano."

@bot.event
async def on_member_join(member: discord.Member):
    try:
        # não processa bots
        if member.bot:
            return

        guild = member.guild
        if not guild:
            return
        channel = _find_welcome_channel(guild)
        if channel is None and WELCOME_CHANNEL_ID:
            try:
                ch = guild.get_channel(WELCOME_CHANNEL_ID)
                if isinstance(ch, discord.TextChannel):
                    channel = ch
            except Exception:
                channel = None
        if channel is None:
            print(f"[{INSTANCE_ID}] Canal de welcome não encontrado para guild {guild.id}; ignorando welcome.")
        else:
            embed = _build_welcome_embed(member)
            try:
                # send mention in content to guarantee the ping, embed uses display_name so no raw <@id> inside it
                await channel.send(content=member.mention, embed=embed, allowed_mentions=discord.AllowedMentions(users=True))
            except Exception as e:
                print(f"[{INSTANCE_ID}] Erro ao enviar mensagem de boas-vindas: {e}")

            if WELCOME_LOG_CHANNEL_ID:
                try:
                    log_ch = guild.get_channel(WELCOME_LOG_CHANNEL_ID)
                    if isinstance(log_ch, discord.TextChannel):
                        # logs: do not ping, only send embed
                        await log_ch.send(embed=embed)
                except Exception as e:
                    print(f"[{INSTANCE_ID}] Erro ao enviar welcome para canal de log: {e}")

        # ---------- auto-role: tenta atribuir cargo de membro ----------
        role = None
        # 1) se o ID está definido pelas envs, tenta pegar diretamente
        if MEMBER_ROLE_ID:
            try:
                role = guild.get_role(MEMBER_ROLE_ID)
            except Exception:
                role = None

        # 2) se não encontrou por ID, tenta achar por nome comum
        if role is None:
            candidate_names = {"membro", "member", "user", "usuario", "usuário", "participante"}
            role = next((r for r in guild.roles if r.name.lower() in candidate_names), None)

        # 3) se achou, verifica permissões/posição e tenta atribuir
        if role:
            try:
                # verifica se o bot tem manage_roles
                me = guild.me
                if me is None:
                    print(f"[{INSTANCE_ID}] Não foi possível recuperar guild.me para guild {guild.id}.")
                else:
                    # permission check
                    if not guild.me.guild_permissions.manage_roles:
                        print(f"[{INSTANCE_ID}] Bot não tem 'Manage Roles' — impossível atribuir cargo '{role.name}'.")
                    else:
                        # posição do cargo do bot deve ser maior que a posição do cargo a ser atribuído
                        if me.top_role.position <= role.position:
                            print(f"[{INSTANCE_ID}] Cargo do bot está abaixo ou igual ao cargo '{role.name}' (bot top: {me.top_role.position} <= role: {role.position}). Ajuste a posição do cargo do bot.")
                        else:
                            await member.add_roles(role, reason="Auto-role: atribuído ao entrar no servidor")
                            print(f"[{INSTANCE_ID}] Cargo '{role.name}' atribuído a {member} ({member.id})")
            except discord.Forbidden:
                print(f"[{INSTANCE_ID}] Sem permissão para atribuir o cargo '{role.name}'. Verifique 'Manage Roles' e a posição do cargo do bot.")
            except Exception as e:
                print(f"[{INSTANCE_ID}] Erro ao adicionar cargo '{getattr(role,'name',role)}' a {member}: {e}")
        else:
            print(f"[{INSTANCE_ID}] Cargo de membro não encontrado (MEMBER_ROLE_ID={MEMBER_ROLE_ID}). Não foi atribuído cargo automático.")

    except Exception as e:
        print(f"[{INSTANCE_ID}] Exception em on_member_join: {e}")

@bot.event
async def on_member_remove(member: discord.Member):
    try:
        guild = member.guild
        if not guild:
            return
        channel = _find_welcome_channel(guild)
        if channel is None and WELCOME_CHANNEL_ID:
            try:
                ch = guild.get_channel(WELCOME_CHANNEL_ID)
                if isinstance(ch, discord.TextChannel):
                    channel = ch
            except Exception:
                channel = None

        content = _build_leave_content(member)

        if channel:
            try:
                # send leave mention (allowed_mentions keeps control)
                await channel.send(content, allowed_mentions=discord.AllowedMentions(users=True))
            except Exception as e:
                print(f"[{INSTANCE_ID}] Erro ao enviar mensagem de saída: {e}")
        else:
            print(f"[{INSTANCE_ID}] Canal de welcome/leave não encontrado para guild {guild.id}; saída não enviada.")

        if WELCOME_LOG_CHANNEL_ID:
            try:
                log_ch = guild.get_channel(WELCOME_LOG_CHANNEL_ID)
                if isinstance(log_ch, discord.TextChannel):
                    await log_ch.send(content, allowed_mentions=discord.AllowedMentions(users=True))
            except Exception as e:
                print(f"[{INSTANCE_ID}] Erro ao enviar leave para canal de log: {e}")

    except Exception as e:
        print(f"[{INSTANCE_ID}] Exception em on_member_remove: {e}")

# on_ready
@bot.event
async def on_ready():
    print(f"[{INSTANCE_ID}] ✅ Bot online como {bot.user}")
    try:
        await bot.tree.sync()
        print(f"[{INSTANCE_ID}] Slash commands sincronizados.")
    except Exception as e:
        print(f"[{INSTANCE_ID}] Erro ao sincronizar slash commands: {e}")
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

# ================== EVENTO PARA VOICE ROOMS DINÂMICOS ==================
@bot.event
async def on_voice_state_update(member, before, after):
    # Criar canal se entrar em canal fixo
    if after.channel and after.channel.id in CANAL_FIXO_CONFIG:
        cfg = CANAL_FIXO_CONFIG[after.channel.id]
        categoria = member.guild.get_channel(cfg["categoria_id"])
        prefixo = cfg["prefixo_nome"]

        novo_canal = await member.guild.create_voice_channel(
            name=f"{prefixo}{member.display_name}",
            category=categoria
        )
        await member.move_to(novo_canal)

        voice_rooms_criados[novo_canal.id] = {"owner": member.id, "fixo": after.channel.id}
        print(f"[{INSTANCE_ID}] 🎤 Canal criado: {novo_canal.name} ({novo_canal.id})")

    # Deletar canal se ficar vazio
    if before.channel and before.channel.id in voice_rooms_criados:
        canal = before.channel
        if len(canal.members) == 0:
            try:
                await canal.delete()
                del voice_rooms_criados[canal.id]
                print(f"[{INSTANCE_ID}] ❌ Canal apagado: {canal.name} ({canal.id})")
            except Exception as e:
                print(f"[{INSTANCE_ID}] Erro ao deletar canal {canal.id}: {e}")

# start
def start_bot():
    try:
        keep_alive()
        bot.run(TOKEN)
    except Exception as e:
        print("❌ Erro ao iniciar o bot:", type(e).__name__, "-", e)
        traceback.print_exc()
        time.sleep(5)
        sys.exit(1)

if __name__ == "__main__":
    start_bot()
