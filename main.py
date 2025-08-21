import os
import sys
import json
import re
import asyncio
import traceback
import time
import uuid
import types
import io
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

# agora importa discord (após garantir shim)
import discord
from discord.ext import commands, tasks
from discord.ui import View, button

from flask import Flask
from threading import Thread

# --- PIL / requests para gerar a imagem do ranking ---
try:
    from PIL import Image, ImageDraw, ImageFont, ImageOps
except Exception:
    Image = ImageDraw = ImageFont = ImageOps = None

try:
    import requests
except Exception:
    requests = None

# -------------------- KEEP ALIVE (Flask) --------------------
app = Flask('')

@app.route('/')
def home():
    return "Bot está rodando!"

def run_flask():
    # servidor dev é suficiente para keep-alive no Render
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run_flask, daemon=True)
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

# -------------------- leitura robusta do token --------------------
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

if TOKEN:
    try:
        print(f"DEBUG: token presente. len={len(TOKEN)} first4={TOKEN[:4]} last4={TOKEN[-4:]}")
    except Exception:
        print("DEBUG: token presente (erro ao formatar preview).")
else:
    raise RuntimeError(
        "❌ Erro: DISCORD_TOKEN/TOKEN não encontrado nas env vars nem em /etc/secrets."
    )

# -------------------- leitura de outros ids via env --------------------
GUILD_ID = _int_env("GUILD_ID", 1213316038805164093)
BOOSTER_ROLE_ID = _int_env("BOOSTER_ROLE_ID", 1406307445306818683)
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
    1406308661810171965: {"categoria_id": 1213316039350296637, "prefixo_nome": "Call│"},
    1404889040007725107: {"categoria_id": 1213319157639020564, "prefixo_nome": "♨️|Java│"},
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
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_boosters_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

boosters_data = load_boosters_data()

# -------------------- VOICE STATE (criação segura) --------------------
@bot.event
async def on_voice_state_update(member, before, after):
    try:
        print(f"Voice state update: {member} entrou no canal {after.channel.id if after.channel else 'Nenhum'} (before: {before.channel.id if before.channel else 'Nenhum'})")
    except Exception:
        print("Voice state update: erro ao printar membro/canais")

    # criação de canal dinâmico
    if after.channel and after.channel.id in CANAL_FIXO_CONFIG:
        config = CANAL_FIXO_CONFIG[after.channel.id]
        guild = member.guild
        category = guild.get_channel(config["categoria_id"]) if guild else None

        if not category or not isinstance(category, discord.CategoryChannel):
            print(f"Categoria não encontrada (id: {config['categoria_id']})")
            return

        prefixo = config["prefixo_nome"]
        # cria lock se necessário (thread-safe-ish)
        lock = creation_locks.setdefault(after.channel.id, asyncio.Lock())

        async with lock:
            canais_existentes = [c for c in category.voice_channels if c.name.startswith(prefixo)]
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

            if new_channel:
                try:
                    template_channel = guild.get_channel(after.channel.id)
                    if template_channel:
                        await new_channel.edit(position=(template_channel.position + 1))
                except Exception as e:
                    print(f"Não foi possível ajustar a posição do canal: {e}")

                try:
                    await member.move_to(new_channel)
                    print(f"Movendo {member} para {new_channel.name}")
                except Exception as e:
                    print(f"Erro ao mover membro para o novo canal: {e}")

    # exclusão de canais vazios
    if before and before.channel:
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

# -------------------- Helpers e View --------------------
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

# -------------------- GERA IMAGEM DO RANKING (PIL usando textbbox) --------------------
def generate_ranking_image(boosters, page=0, per_page=5, width=900, row_height=80):
    """
    Gera uma imagem PNG em memória contendo o ranking com avatar ao lado do nome.
    Retorna um BytesIO pronto para ser enviado como arquivo.
    Usa draw.textbbox(...) para compatibilidade com Pillow 10+.
    """
    if Image is None or ImageDraw is None or ImageFont is None:
        return None

    # configurações visuais
    margin = 16
    avatar_size = 56
    gap = 12
    font_size_name = 18
    font_size_meta = 14

    try:
        name_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size_name)
        meta_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_size_meta)
    except Exception:
        name_font = ImageFont.load_default()
        meta_font = ImageFont.load_default()

    start = page
    end = min(page + per_page, len(boosters))
    rows = end - start
    height = margin * 2 + rows * row_height

    img = Image.new("RGBA", (width, max(height, 120)), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img)

    y = margin
    for i, (member, boost_time) in enumerate(boosters[start:end], start=1 + page):
        # avatar
        avatar_url = None
        try:
            if hasattr(member, 'display_avatar'):
                avatar_url = member.display_avatar.url
            elif getattr(member, 'avatar', None):
                avatar_url = member.avatar.url
        except Exception:
            avatar_url = None

        avatar_img = None
        if avatar_url and requests:
            try:
                r = requests.get(avatar_url, timeout=6)
                if r.status_code == 200:
                    avatar_img = Image.open(io.BytesIO(r.content)).convert("RGBA")
            except Exception:
                avatar_img = None

        if not avatar_img:
            # placeholder circle
            avatar_img = Image.new("RGBA", (avatar_size, avatar_size), (200, 200, 200, 255))

        # crop/fit avatar to square and circle mask
        avatar_img = ImageOps.fit(avatar_img, (avatar_size, avatar_size))
        mask = Image.new("L", (avatar_size, avatar_size), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.ellipse((0, 0, avatar_size, avatar_size), fill=255)
        img.paste(avatar_img, (margin, y + (row_height - avatar_size)//2), mask)

        # textos: name + meta
        name = getattr(member, 'display_name', getattr(member, 'name', f"User {getattr(member, 'id', '???')}"))
        formatted_time = format_relative_time(boost_time)
        name_x = margin + avatar_size + gap
        name_y = y + 8

        # largura / altura usando textbbox
        bbox = draw.textbbox((0, 0), name, font=name_font)
        name_h = bbox[3] - bbox[1]
        draw.text((name_x, name_y), name, font=name_font, fill=(32, 32, 32))

        meta_text = f"🕒 {formatted_time}"
        bbox_m = draw.textbbox((0, 0), meta_text, font=meta_font)
        meta_h = bbox_m[3] - bbox_m[1]
        draw.text((name_x, name_y + name_h + 6), meta_text, font=meta_font, fill=(100, 100, 100))

        # número da colocação à esquerda do avatar
        rank_text = f"{i}."
        bbox_r = draw.textbbox((0, 0), rank_text, font=name_font)
        r_w = bbox_r[2] - bbox_r[0]
        draw.text((margin - r_w - 8, name_y), rank_text, font=name_font, fill=(50, 50, 50))

        y += row_height

    # footer
    footer_text = f"Exibindo {start + 1}-{end} de {len(boosters)} boosters"
    bbox_f = draw.textbbox((0, 0), footer_text, font=meta_font)
    draw.text((margin, img.height - margin - (bbox_f[3] - bbox_f[1])), footer_text, font=meta_font, fill=(120, 120, 120))

    out = io.BytesIO()
    img.save(out, format="PNG")
    out.seek(0)
    return out


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
            # defensivo: só atualiza se existirem filhos
            if len(self.children) >= 4:
                self.children[0].disabled = prev_disabled
                self.children[2].disabled = prev_disabled
                self.children[3].disabled = next_disabled
        except Exception:
            pass

    def _display_name(self, member):
        return getattr(member, "display_name", getattr(member, "name", f"User {getattr(member, 'id', '???')}"))

    def _avatar_url(self, member):
        # tries multiple attributes to be compatible across discord.py versions / fake objects
        try:
            if hasattr(member, "display_avatar"):
                return member.display_avatar.url
        except:
            pass
        try:
            if getattr(member, "avatar", None):
                return member.avatar.url
        except:
            pass
        return None

    def build_embed(self):
        embed = discord.Embed(title="🏆 Top Boosters", color=discord.Color.purple())
        start = self.page
        end = min(self.page + self.per_page, len(self.boosters))
        for i, (member, boost_time) in enumerate(self.boosters[start:end], start=1 + self.page):
            formatted_time = format_relative_time(boost_time)
            embed.add_field(
                name=f"{i}. {self._display_name(member)}",
                value=f"🕒 Boostando desde {formatted_time}",
                inline=False
            )
        embed.set_footer(text=f"Exibindo {start + 1}-{end} de {len(self.boosters)} boosters")
        return embed

    # Botões: previous, refresh, home, next
    @button(label="⬅ Voltar", style=discord.ButtonStyle.secondary, custom_id="previous")
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        new_page = max(0, self.page - self.per_page)
        if self.is_personal:
            self.page = new_page
            self.update_disabled()
            await interaction.response.edit_message(embed=self.build_embed(), view=self)
        else:
            new_view = BoosterRankView(self.boosters, is_personal=True)
            new_view.page = new_page
            new_view.update_disabled()
            await interaction.response.send_message(embed=new_view.build_embed(), view=new_view, ephemeral=True)

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
            await interaction.response.edit_message(embed=self.build_embed(), view=self)
        else:
            new_view = BoosterRankView(boosters, is_personal=True)
            await interaction.response.send_message(embed=new_view.build_embed(), view=new_view, ephemeral=True)

    @button(label="🏠 Início", style=discord.ButtonStyle.success, custom_id="home")
    async def home(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.is_personal:
            self.page = 0
            self.update_disabled()
            await interaction.response.edit_message(embed=self.build_embed(), view=self)
        else:
            new_view = BoosterRankView(self.boosters, is_personal=True)
            await interaction.response.send_message(embed=new_view.build_embed(), view=new_view, ephemeral=True)

    @button(label="➡ Avançar", style=discord.ButtonStyle.secondary, custom_id="next")
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        max_start = max(0, len(self.boosters) - self.per_page)
        new_page = min(max_start, self.page + self.per_page)
        if self.is_personal:
            self.page = new_page
            self.update_disabled()
            await interaction.response.edit_message(embed=self.build_embed(), view=self)
        else:
            new_view = BoosterRankView(self.boosters, is_personal=True)
            new_view.page = new_page
            new_view.update_disabled()
            await interaction.response.send_message(embed=new_view.build_embed(), view=new_view, ephemeral=True)

# -------------------- Comandos / lógica --------------------
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

async def send_booster_rank(channel, fake=False, tester=None, edit_message=None):
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
    embed = view.build_embed()

    # gera imagem do ranking e anexa como arquivo (se possível)
    image_io = generate_ranking_image(boosters, page=0, per_page=5)
    try:
        if edit_message:
            try:
                await edit_message.edit(embed=embed, view=view)
                fixed_booster_message = edit_message
            except Exception:
                fixed_booster_message = await channel.send(embed=embed, view=view)
        else:
            if image_io:
                file = discord.File(image_io, filename="ranking.png")
                fixed_booster_message = await channel.send(embed=embed, view=view, file=file)
            else:
                fixed_booster_message = await channel.send(embed=embed, view=view)
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

# on_ready
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

# --------------- Start / Tratamento de erros ---------------
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
