# cogs/boosters.py
import os
import json
from datetime import datetime, timezone, timedelta
import discord
from discord.ext import commands, tasks
from discord.ui import View, button

DATA_FILE = os.environ.get("BOOSTERS_DATA_FILE", "boosters_data.json")
GUILD_ID = int(os.environ.get("GUILD_ID", 0))
BOOSTER_ROLE_ID = int(os.environ.get("BOOSTER_ROLE_ID", 0))
CUSTOM_BOOSTER_ROLE_ID = int(os.environ.get("CUSTOM_BOOSTER_ROLE_ID", BOOSTER_ROLE_ID))

def load_data():
    if not os.path.isfile(DATA_FILE):
        return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except:
            return {}

def save_data(d):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=4, ensure_ascii=False)

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
                start_time_str = self.cog_data.get(user_id_str) if hasattr(self, "cog_data") else None
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

class BoosterCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data = load_data()
        self.fixed_message_id = None
        self.update_task = None

    @commands.command()
    async def boosters(self, ctx):
        if getattr(ctx.author, "id", None) in getattr(self.bot, "processing_commands", set()):
            return
        self.bot.processing_commands = getattr(self.bot, "processing_commands", set())
        self.bot.processing_commands.add(ctx.author.id)
        try:
            if self.fixed_message_id:
                await ctx.send("✅ Mensagem de ranking já está ativa")
            else:
                await self.send_booster_rank(ctx.channel)
        finally:
            self.bot.processing_commands.remove(ctx.author.id)

    @commands.command()
    async def testboost(self, ctx):
        self.bot.processing_commands = getattr(self.bot, "processing_commands", set())
        if ctx.author.id in self.bot.processing_commands:
            return
        self.bot.processing_commands.add(ctx.author.id)
        try:
            await self.send_booster_rank(ctx.channel, fake=True, tester=ctx.author)
        finally:
            self.bot.processing_commands.remove(ctx.author.id)

    async def send_booster_rank(self, channel, fake=False, tester=None, edit_message=None, page=0, per_page=5):
        guild = self.bot.get_guild(GUILD_ID)
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
                start_time_str = self.data.get(user_id_str)
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
                    self.fixed_message_id = edit_message.id
                except Exception:
                    try:
                        await edit_message.delete()
                    except Exception:
                        pass
                    sent = await channel.send(embeds=embeds, view=view)
                    self.fixed_message_id = sent.id
            else:
                sent = await channel.send(embeds=embeds, view=view)
                self.fixed_message_id = sent.id
        except Exception as e:
            print("Erro ao enviar/editar mensagem do ranking:", e)
            raise

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if not after or not getattr(after, "guild", None):
            return
        guild = self.bot.get_guild(GUILD_ID)
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

    @commands.command()
    async def boosttime(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        user_id_str = str(member.id)
        if user_id_str not in self.data:
            await ctx.send(f"{member.display_name} não possui boost ativo registrado")
            return
        start_time = datetime.fromisoformat(self.data[user_id_str])
        await ctx.send(f"{member.display_name} está boostando {format_relative_time(start_time)}")

    @commands.Cog.listener()
    async def on_ready(self):
        # start periodic update if needed
        if self.update_task is None:
            self.update_task = self.bot.loop.create_task(self._periodic_update())

    async def _periodic_update(self):
        while True:
            try:
                await asyncio.sleep(3600)
                if self.fixed_message_id:
                    try:
                        msg = await self.bot.get_channel(self.bot.MAIN_CONFIG.get("WELCOME_CHANNEL_ID") or 0).fetch_message(self.fixed_message_id)
                        await self.send_booster_rank(msg.channel, edit_message=msg)
                        print("[BOOSTERS] Mensagem fixa atualizada")
                    except Exception:
                        pass
            except asyncio.CancelledError:
                return
            except Exception:
                await asyncio.sleep(60)

async def setup(bot):
    await bot.add_cog(BoosterCog(bot))
