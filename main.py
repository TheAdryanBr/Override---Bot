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
    return "Bot está rodando!"

def run():
    # Uso do servidor de desenvolvimento é suficiente para keep-alive no Render
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# -------------------- MULTI-INSTANCE GUARD --------------------
if os.environ.get("RUNNING_INSTANCE") == "1":
    print("⚠️ Já existe uma instância ativa deste bot. Encerrando...")
    sys.exit()

os.environ["RUNNING_INSTANCE"] = "1"

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

# -------------------- leitura robusta do token (Opção A) --------------------
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

# caminhos comuns para Secret Files + fallback local
_secret_paths = [
    "/etc/secrets/DISCORD_TOKEN",
    "/etc/secrets/discord_token",
    "/run/secrets/discord_token",
    "/var/run/secrets/discord_token",
    "./.env.discord"
]

# tenta em env vars primeiro (DISCORD_TOKEN preferencial), depois TOKEN, depois secret files
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise ValueError("Token não encontrado! Configure a variável DISCORD_TOKEN no Render")
# limpeza: remove prefixo "Bot " se alguém colou com ele, e trim espaços
if TOKEN:
    TOKEN = TOKEN.strip()
    if TOKEN.lower().startswith("bot "):
        TOKEN = TOKEN[4:].strip()

# debug seguro — mostra só presença e alguns caracteres não sensíveis
if TOKEN:
    try:
        print(f"DEBUG: token presente. len={len(TOKEN)} first4={TOKEN[:4]} last4={TOKEN[-4:]}")
    except Exception:
        print("DEBUG: token presente (erro ao formatar preview).")
else:
    raise RuntimeError(
        "❌ Erro: DISCORD_TOKEN/TOKEN não encontrado nas env vars nem em /etc/secrets. "
        "Verifique Render → Environment (ou Secret Files) e redeploy."
    )
# -------------------- FIM leitura do token --------------------

# -------------------- leitura de outros ids via env --------------------
GUILD_ID = _int_env("GUILD_ID", 1213316038805164093)
BOOSTER_ROLE_ID = _int_env("BOOSTER_ROLE_ID", 1248070897697427467)
CUSTOM_BOOSTER_ROLE_ID = _int_env("CUSTOM_BOOSTER_ROLE_ID", BOOSTER_ROLE_ID)

# -------------------- BOT SETUP --------------------
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# ID único para identificar a instância atual
INSTANCE_ID = str(uuid.uuid4())[:8]
print(f"🚀 Instância iniciada com ID: {INSTANCE_ID}")

# Anti-duplicação
processing_commands = set()

# locks por canal template para evitar criação simultânea duplicada
creation_locks = {}

# Mensagem fixa do ranking (objeto discord.Message)
fixed_booster_message = None

# -------- CONFIG DE CANAIS FIXOS/ CATEGORIAS -------------
CANAL_FIXO_CONFIG = {
    1404889040007725107: {
        "categoria_id": 1213316039350296637,
        "prefixo_nome": "Call│"
    },
    1404886431075401858: {
        "categoria_id": 1213319157639020564,
        "prefixo_nome": "♨️|Java│"
    },
    1213319477429801011: {
        "categoria_id": 1213319157639020564,
        "prefixo_nome": "🪨|Bedrock|"
    },
    1213321053196263464: {
        "categoria_id": 1213319620287664159,
        "prefixo_nome": "🎧│Call│"
    },
    1213322485479637012: {
        "categoria_id": 1213322073594793994,
        "prefixo_nome": "👥│Dupla│"
    },
    1213322743123148920: {
        "categoria_id": 1213322073594793994,
        "prefixo_nome": "👥│Trio│"
    },
    1213322826564767776: {
        "categoria_id": 1213322073594793994,
        "prefixo_nome": "👥│Squad│"
    },
    1216123178548465755: {
        "categoria_id": 1216123032138154008,
        "prefixo_nome": "👥│Duo│"
    },
    1216123306579595274: {
        "categoria_id": 1216123032138154008,
        "prefixo_nome": "👥│Trio│"
    },
    1216123421688205322: {
        "categoria_id": 1216123032138154008,
        "prefixo_nome": "👥│Team│"
    },
    1213533210907246592: {
        "categoria_id": 1213532914520690739,
        "prefixo_nome": "🎧│Sala│"
    },
}

# ----------- ARQUIVO PARA SALVAR TEMPO DE BOOSTERS --------------
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
# -----------------------------------------------------------------------

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
        # defensivo: evita index error se botões não existirem por algum motivo
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
            await interaction.response.send_message(embed=embed, view=new_view, ephemeral=True)

# -------------------- Comandos / lógica do seu bot (mantive quase tudo) --------------------
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
        if not guild:
            print("send_booster_rank: guild não encontrada (bot.get_guild retornou None)")
            boosters = []
        else:
            role = guild.get_role(CUSTOM_BOOSTER_ROLE_ID)
            boosters = []
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

    before_roles = set(before.roles)
    after_roles = set(after.roles)

    booster_role = guild.get_role(BOOSTER_ROLE_ID)
    custom_role = guild.get_role(CUSTOM_BOOSTER_ROLE_ID)
    if not booster_role or not custom_role:
        print("Cargo oficial booster ou cargo custom não encontrado")
        return

    user_id_str = str(after.id)

    # Ganhou cargo oficial
    if booster_role not in before_roles and booster_role in after_roles:
        # Dá cargo custom se não tiver
        if custom_role not in after_roles:
            await after.add_roles(custom_role, reason="Usuário deu boost, cargo custom adicionado")
            print(f"Cargo custom adicionado a {after.display_name}")

        # Salva data/hora atual no JSON
        boosters_data[user_id_str] = datetime.now(timezone.utc).isoformat()
        save_boosters_data(boosters_data)
        print(f"Data de boost salva para {after.display_name}")

    # Perdeu cargo oficial
    elif booster_role in before_roles and booster_role not in after_roles:
        # Remove cargo custom se tiver
        if custom_role in after_roles:
            await after.remove_roles(custom_role, reason="Usuário removeu boost, cargo custom removido")
            print(f"Cargo custom removido de {after.display_name}")

        # Remove do JSON
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

# on_ready (mantive a sua lógica de iniciar task e view)
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

# --------------- Start / Tratamento de erros (evita loop em 429) ---------------
def start_bot():
    try:
        keep_alive()  # inicia keep-alive antes do bot
        bot.run(TOKEN)
    except Exception as e:
        print("❌ Erro ao iniciar o bot:", type(e).__name__, "-", e)
        txt = str(e).lower()
        if "429" in txt or "too many requests" in txt or "rate limit" in txt or "access denied" in txt:
            print("\n🚫 DETECTADO: 429 / bloqueio por Cloudflare ou excesso de tentativas.")
            print("➡ Soluções sugeridas:")
            print("   1) Regenerar token no Discord Developer Portal.")
            print("   2) Atualizar DISCORD_TOKEN nas Environment Variables do Render.")
            print("   3) Se persistir, IP do host pode estar bloqueado — tentar outro host ou contactar Render.")
        traceback.print_exc()
        time.sleep(5)
        sys.exit(1)

if __name__ == "__main__":
    start_bot()
