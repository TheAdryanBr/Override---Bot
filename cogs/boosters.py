# cogs/boosters.py
import os
import json
import asyncio
from datetime import datetime, timezone
import discord
from discord.ext import commands
from discord.ui import View, button

# ------------------ Configs / Arquivos ------------------
DATA_FILE = os.environ.get("BOOSTERS_DATA_FILE", "boosters_data.json")
META_FILE = os.environ.get("BOOSTERS_META_FILE", "boosters_meta.json")
GUILD_ID = int(os.environ.get("GUILD_ID", 0))
BOOSTER_ROLE_ID = int(os.environ.get("BOOSTER_ROLE_ID", 0))
CUSTOM_BOOSTER_ROLE_ID = int(os.environ.get("CUSTOM_BOOSTER_ROLE_ID", BOOSTER_ROLE_ID))
# canal fixo para o ranking (padrão pro que você informou)
BOOSTER_RANK_CHANNEL_ID = int(os.environ.get("BOOSTER_RANK_CHANNEL_ID", 1415478538114564166))

# ------------------ Helpers de arquivo ------------------
def load_json_file(path):
    try:
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def save_json_file(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print("[BOOSTERS] Erro ao salvar JSON", path, e)

# ------------------ Dados persistentes ------------------
def load_data():
    return load_json_file(DATA_FILE)

def save_data(d):
    save_json_file(DATA_FILE, d)

def load_meta():
    return load_json_file(META_FILE)

def save_meta(m):
    save_json_file(META_FILE, m)

# ------------------ Time formatting ------------------
def format_relative_time(boost_time):
    if boost_time is None:
        return "tempo desconhecido"
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

# ------------------ Embeds builder ------------------
def build_embeds_for_page(boosters, page=0, per_page=5):
    embeds = []
    start = page
    end = min(page + per_page, len(boosters))
    for idx, (member, boost_time) in enumerate(boosters[start:end], start=1 + page):
        display_name = getattr(member, "display_name", getattr(member, "name", f"User {getattr(member,'id','???')}"))
        formatted_time = format_relative_time(boost_time)
        embed = discord.Embed(title=f"{idx}. {display_name}",
                              description=f"🕒 Boostando desde {formatted_time}",
                              color=discord.Color.purple())
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

# ------------------ View (botões) ------------------
class BoosterRankView(View):
    def __init__(self, boosters, is_personal=False):
        super().__init__(timeout=None)
        self.boosters = boosters or []
        self.page = 0
        self.per_page = 5
        self.is_personal = is_personal
        # cog_data será atribuída pelo cog ao criar a view
        self.cog_data = None
        self.update_disabled()

    def update_disabled(self):
        total = len(self.boosters)
        try:
            prev_disabled = self.page <= 0
            next_disabled = (self.page + self.per_page) >= total
            if len(self.children) >= 4:
                # assuming order of buttons
                self.children[0].disabled = prev_disabled  # previous
                self.children[2].disabled = prev_disabled  # home?
                self.children[3].disabled = next_disabled  # next
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
            new_view.cog_data = getattr(self, "cog_data", None)
            new_view.update_disabled()
            embeds = build_embeds_for_page(self.boosters, page=new_page, per_page=new_view.per_page)
            await interaction.response.send_message(embeds=embeds, view=new_view, ephemeral=True)

    @button(label="🔁 Atualizar", style=discord.ButtonStyle.primary, custom_id="refresh")
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        # defer for safety; ephemeral for non-personal views
        await interaction.response.defer(ephemeral=not self.is_personal)
        guild = interaction.guild
        role = guild.get_role(CUSTOM_BOOSTER_ROLE_ID) if guild else None
        boosters = []
        if role and role.members:
            for member in role.members:
                user_id_str = str(member.id)
                start_time = None
                # prefer saved data (cog_data), then premium_since, else None
                if hasattr(self, "cog_data") and self.cog_data:
                    start_str = self.cog_data.get(user_id_str)
                    if start_str:
                        try:
                            start_time = datetime.fromisoformat(start_str)
                        except Exception:
                            start_time = None
                if start_time is None:
                    start_time = member.premium_since if getattr(member, "premium_since", None) else None
                boosters.append((member, start_time))
            # sort: entries with None at the end
            boosters.sort(key=lambda x: (x[1] is None, x[1] if x[1] is not None else datetime.max))

        if self.is_personal:
            self.boosters = boosters
            self.page = 0
            self.update_disabled()
            embeds = build_embeds_for_page(self.boosters, page=self.page, per_page=self.per_page)
            try:
                # in application context edit original response, fallback to followup
                await interaction.edit_original_response(embeds=embeds, view=self)
            except Exception:
                await interaction.followup.send(embeds=embeds, view=self, ephemeral=True)
        else:
            new_view = BoosterRankView(boosters, is_personal=True)
            new_view.cog_data = getattr(self, "cog_data", None)
            embeds = build_embeds_for_page(boosters, page=0, per_page=new_view.per_page)
            await interaction.followup.send(embeds=embeds, view=new_view, ephemeral=True)

    @button(label="🏠 Início", style=discord.ButtonStyle.success, custom_id="home")
    async def home(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.is_personal:
            self.page = 0
            self.update_disabled()
            embeds = build_embeds_for_page(self.boosters, page=0, per_page=self.per_page)
            await interaction.response.edit_message(embeds=embeds, view=self)
        else:
            new_view = BoosterRankView(self.boosters, is_personal=True)
            new_view.cog_data = getattr(self, "cog_data", None)
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
            new_view.cog_data = getattr(self, "cog_data", None)
            new_view.update_disabled()
            embeds = build_embeds_for_page(self.boosters, page=new_page, per_page=new_view.per_page)
            await interaction.response.send_message(embeds=embeds, view=new_view, ephemeral=True)

# ------------------ Cog ------------------
class BoosterCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data = load_data()
        self.meta = load_meta()  # will contain fixed_message_id, fixed_channel_id
        self.fixed_message_id = self.meta.get("fixed_message_id")
        self.fixed_channel_id = self.meta.get("fixed_channel_id")
        self.update_task = None

    def _save_fixed_message(self):
        self.data["_fixed_message_id"] = self.fixed_message_id
        self.data["_fixed_channel_id"] = self.fixed_channel_id
        save_data(self.data)

    # ------------------ util ------------------
    def _save_state(self):
        self.meta["fixed_message_id"] = self.fixed_message_id
        self.meta["fixed_channel_id"] = self.fixed_channel_id
        save_meta(self.meta)

    def _get_rank_channel(self):
        ch = self.bot.get_channel(BOOSTER_RANK_CHANNEL_ID)
        return ch

    # ------------------ public commands (hybrid) ------------------
@commands.hybrid_command(name="boosters", with_app_command=True)
async def boosters(self, ctx: commands.Context):
    """
    Comando híbrido: funciona como !boosters e /boosters.
    - Prefix: apaga comando do usuário e envia aviso por DM.
    - Slash: envia resposta ephemeral.
    - Cria/gerencia a mensagem fixa no canal configurado.
    """

    # Detectar se é slash ou prefix
    is_app = ctx.interaction is not None

    # Prefix → tentar apagar mensagem do usuário
    if not is_app:
        try:
            await ctx.message.delete()
        except Exception:
            pass

    # Verificar se já existe mensagem fixa
    exists = False
    if self.fixed_message_id and self.fixed_channel_id:
        try:
            ch = self.bot.get_channel(self.fixed_channel_id)
            if ch:
                await ch.fetch_message(self.fixed_message_id)
                exists = True
        except Exception:
            exists = False

    # Se já existe → avisar apenas o usuário
    if exists:
        text = f"A mensagem fixa já está ativa no canal <#{BOOSTER_RANK_CHANNEL_ID}>"

        if is_app:
            await ctx.respond(text, ephemeral=True)
        else:
            # DM ou fallback
            try:
                await ctx.author.send(text)
            except:
                try:
                    msg = await ctx.send(text)
                    await asyncio.sleep(8)
                    await msg.delete()
                except:
                    pass
        return

    # Criar nova mensagem fixa
    rank_channel = self._get_rank_channel()
    if rank_channel is None:
        txt = f"❌ Canal de ranking fixo não encontrado (ID={BOOSTER_RANK_CHANNEL_ID})."
        if is_app:
            await ctx.respond(txt, ephemeral=True)
        else:
            try:
                await ctx.author.send(txt)
            except:
                m = await ctx.send(txt)
                await asyncio.sleep(8)
                await m.delete()
        return

    # Gerar os boosters atuais
    boosters = self._get_current_boosters()
    if not boosters:
        txt = "❌ Nenhum booster encontrado."
        if is_app:
            await ctx.respond(txt, ephemeral=True)
        else:
            try:
                await ctx.author.send(txt)
            except:
                m = await ctx.send(txt)
                await asyncio.sleep(8)
                await m.delete()
        return

    # Criar view + embeds
    view = BoosterRankView(boosters, is_personal=False)
    view.cog_data = self.data

    embeds = build_embeds_for_page(boosters, page=0, per_page=view.per_page)

    # Enviar mensagem fixa
    sent = await rank_channel.send(embeds=embeds, view=view)

    # Registrar IDs
    self.fixed_message_id = sent.id
    self.fixed_channel_id = rank_channel.id
    self._save_fixed_message()

    # Resposta para o usuário
    confirmation = f"✅ Mensagem fixa criada no canal <#{rank_channel.id}>"

    if is_app:
        await ctx.respond(confirmation, ephemeral=True)
    else:
        try:
            await ctx.author.send(confirmation)
        except:
            m = await ctx.send(confirmation)
            await asyncio.sleep(8)
            await m.delete()

        # generate boosters list & send message
        boosters = []
        guild = self.bot.get_guild(GUILD_ID) if GUILD_ID else rank_channel.guild
        role = None
        try:
            role = guild.get_role(CUSTOM_BOOSTER_ROLE_ID) if guild else None
        except Exception:
            role = None

        if role:
            for member in role.members:
                user_id_str = str(member.id)
                start_time = None
                start_time_str = self.data.get(user_id_str)
                if start_time_str:
                    try:
                        start_time = datetime.fromisoformat(start_time_str)
                    except Exception:
                        start_time = None
                if start_time is None:
                    start_time = member.premium_since if getattr(member, "premium_since", None) else None
                boosters.append((member, start_time))
            boosters.sort(key=lambda x: (x[1] is None, x[1] if x[1] is not None else datetime.max))
        else:
            # no role found -> send minimal message
            try:
                sent = await rank_channel.send("❌ Cargo custom de booster não encontrado para gerar ranking.")
                self.fixed_message_id = sent.id
                self.fixed_channel_id = rank_channel.id
                self._save_state()
            except Exception:
                pass
            txt = f"❌ Cargo de boosters não configurado no servidor."
            if is_app:
                await ctx.respond(txt, ephemeral=True)
            else:
                try:
                    await ctx.author.send(txt)
                except Exception:
                    pass
            return

        if not boosters:
            try:
                sent = await rank_channel.send("❌ Nenhum booster encontrado.")
                self.fixed_message_id = sent.id
                self.fixed_channel_id = rank_channel.id
                self._save_state()
            except Exception:
                pass
            txt = "❌ Nenhum booster encontrado."
            if is_app:
                await ctx.respond(txt, ephemeral=True)
            else:
                try:
                    await ctx.author.send(txt)
                except Exception:
                    pass
            return

        # create view and send message (always to fixed rank channel)
        view = BoosterRankView(boosters, is_personal=False)
        view.cog_data = self.data
        embeds = build_embeds_for_page(boosters, page=0, per_page=view.per_page)

        try:
            # try to recover an existing message first
            if self.fixed_message_id and self.fixed_channel_id:
                try:
                    ch = self.bot.get_channel(self.fixed_channel_id)
                    if ch:
                        msg = await ch.fetch_message(self.fixed_message_id)
                        await msg.edit(embeds=embeds, view=view)
                        self.fixed_message_id = msg.id
                        self.fixed_channel_id = ch.id
                        self._save_state()
                        # respond to user that message was restored/updated
                        text = f"Mensagem fixa atualizada em <#{BOOSTER_RANK_CHANNEL_ID}>"
                        if is_app:
                            await ctx.respond(text, ephemeral=True)
                        else:
                            try:
                                await ctx.author.send(text)
                            except Exception:
                                pass
                        return
                except Exception:
                    # broken existing message -> will create new below
                    pass

            sent = await rank_channel.send(embeds=embeds, view=view)
            self.fixed_message_id = sent.id
            self.fixed_channel_id = rank_channel.id
            self._save_state()

            text = f"Mensagem fixa criada em <#{BOOSTER_RANK_CHANNEL_ID}>"
            if is_app:
                await ctx.respond(text, ephemeral=True)
            else:
                try:
                    await ctx.author.send(text)
                except Exception:
                    pass

        except Exception as e:
            print("[BOOSTERS] Erro ao enviar mensagem fixa:", type(e).__name__, e)
            if is_app:
                await ctx.respond("❌ Erro ao criar mensagem fixa.", ephemeral=True)
            else:
                try:
                    await ctx.author.send("❌ Erro ao criar mensagem fixa.")
                except Exception:
                    pass

    # ------------- test command -------------
    @commands.command(name="testboost")
    async def testboost(self, ctx):
        # keep old behavior: send a fake ranking in the current channel
        now = datetime.now(timezone.utc)
        fake_boosters = []
        fake_boosters.append((ctx.author, now - timedelta(days=10)))
        for i in range(1, 7):
            member = discord.Object(id=100000000000000000 + i)
            member.display_name = f"FakeUser{i}"
            fake_boosters.append((member, now - timedelta(days=i * 5)))
        view = BoosterRankView(fake_boosters, is_personal=False)
        view.cog_data = self.data
        embeds = build_embeds_for_page(fake_boosters, page=0, per_page=view.per_page)
        try:
            await ctx.send(embeds=embeds, view=view)
        except Exception:
            pass

    # ------------- boosttime -------------
    @commands.command(name="boosttime")
    async def boosttime(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        user_id_str = str(member.id)
        if user_id_str not in self.data:
            await ctx.send(f"{member.display_name} não possui boost ativo registrado")
            return
        try:
            start_time = datetime.fromisoformat(self.data[user_id_str])
        except Exception:
            await ctx.send(f"{member.display_name} não possui um tempo válido registrado")
            return
        await ctx.send(f"{member.display_name} está boostando {format_relative_time(start_time)}")

    # ------------- listeners -------------
    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        try:
            if not after or not getattr(after, "guild", None):
                return
            guild = self.bot.get_guild(GUILD_ID) if GUILD_ID else after.guild
            if not guild or guild.id != getattr(after.guild, "id", None):
                return
            booster_role = guild.get_role(BOOSTER_ROLE_ID) if guild else None
            custom_role = guild.get_role(CUSTOM_BOOSTER_ROLE_ID) if guild else None
            if not booster_role or not custom_role:
                return

            user_id_str = str(after.id)
            had_booster = booster_role in before.roles
            has_booster = booster_role in after.roles

            if not had_booster and has_booster:
                if custom_role not in after.roles:
                    try:
                        await after.add_roles(custom_role, reason="Usuário deu boost, cargo custom adicionado")
                    except Exception:
                        pass
                self.data[user_id_str] = datetime.now(timezone.utc).isoformat()
                save_data(self.data)
            elif had_booster and not has_booster:
                if custom_role in after.roles:
                    try:
                        await after.remove_roles(custom_role, reason="Usuário removeu boost, cargo custom removido")
                    except Exception:
                        pass
                if user_id_str in self.data:
                    del self.data[user_id_str]
                    save_data(self.data)
        except Exception:
            pass

    # ------------- periodic update -------------
    @commands.Cog.listener()
    async def on_ready(self):
        # start periodic update if needed
        if self.update_task is None:
            self.update_task = self.bot.loop.create_task(self._periodic_update())

    async def _periodic_update(self):
        while True:
            try:
                # check every hour; adjust for testing if needed
                await asyncio.sleep(3600)
                if self.fixed_message_id and getattr(self, "fixed_channel_id", None):
                    try:
                        ch = self.bot.get_channel(self.fixed_channel_id)
                        if ch is None:
                            continue
                        msg = await ch.fetch_message(self.fixed_message_id)
                        # edit the pinned message
                        await self._edit_fixed_message(msg)
                        print("[BOOSTERS] Mensagem fixa atualizada")
                    except Exception:
                        # if message missing or failed, try to recreate next loop
                        pass
            except asyncio.CancelledError:
                return
            except Exception:
                await asyncio.sleep(60)

    # helper to build and edit the fixed message (reused)
    async def _edit_fixed_message(self, msg):
        # regenerate boosters list
        rank_channel = msg.channel
        guild = self.bot.get_guild(GUILD_ID) if GUILD_ID else rank_channel.guild
        role = None
        try:
            role = guild.get_role(CUSTOM_BOOSTER_ROLE_ID) if guild else None
        except Exception:
            role = None

        boosters = []
        if role:
            for member in role.members:
                user_id_str = str(member.id)
                start_time = None
                start_time_str = self.data.get(user_id_str)
                if start_time_str:
                    try:
                        start_time = datetime.fromisoformat(start_time_str)
                    except Exception:
                        start_time = None
                if start_time is None:
                    start_time = member.premium_since if getattr(member, "premium_since", None) else None
                boosters.append((member, start_time))
            boosters.sort(key=lambda x: (x[1] is None, x[1] if x[1] is not None else datetime.max))

        if not boosters:
            try:
                await msg.edit(content="❌ Nenhum booster encontrado.", embeds=[], view=None)
            except Exception:
                pass
            return

        view = BoosterRankView(boosters, is_personal=False)
        view.cog_data = self.data
        embeds = build_embeds_for_page(boosters, page=0, per_page=view.per_page)
        try:
            await msg.edit(embeds=embeds, view=view)
        except Exception:
            # if editing fails (deleted or permissions), try recreate
            try:
                new = await rank_channel.send(embeds=embeds, view=view)
                self.fixed_message_id = new.id
                self.fixed_channel_id = rank_channel.id
                self._save_state()
            except Exception:
                pass

async def setup(bot):
    await bot.add_cog(BoosterCog(bot))
