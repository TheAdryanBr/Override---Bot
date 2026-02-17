import asyncio
import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import discord
from discord.ext import commands, tasks


CONFIG_PATH = "data/multi_counters.json"

# ========== Anti-rate-limit ==========
# intervalo mínimo entre renomes do MESMO canal (segundos)
MIN_RENAME_INTERVAL_SEC = 60

# intervalo do loop periódico (segundos)
UPDATE_LOOP_SEC = 60

# debounce para juntar vários eventos
EVENT_DEBOUNCE_SEC = 8


def _load_config() -> dict:
    if not os.path.exists(CONFIG_PATH):
        return {}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_config(cfg: dict) -> None:
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def _as_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default


@dataclass
class CounterSpec:
    channel_id: int
    mode: str  # all | humans | bots | role
    name_format: str
    role_id: int = 0  # only for mode=role


def _is_counter_channel(ch: Optional[discord.abc.GuildChannel]) -> bool:
    return isinstance(ch, (discord.VoiceChannel, discord.StageChannel))


# remove chars invisíveis comuns que quebram mention
_INVIS = ["\u200b", "\u200c", "\u200d", "\ufeff", "\u2060"]
_CHANNEL_ID_RE = re.compile(r"(\d{15,25})")


def _extract_channel_id(raw: str) -> Optional[int]:
    s = raw
    for c in _INVIS:
        s = s.replace(c, "")
    m = _CHANNEL_ID_RE.search(s)
    if not m:
        return None
    return int(m.group(1))


class MultiCounters(commands.Cog):
    """
    Multi contadores com proteções fortes contra rate limit.

    Comandos:
      - !stats_preset [lobby_role_id opcional]
      - !counter_edit <canal_id_ou_mention> format="..." [mode=...] [role_id=...]
      - !counter_now
      - !counter_list
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cfg: Dict[str, Any] = _load_config()

        self._update_lock = asyncio.Lock()

        # debounce de eventos
        self._pending_event_update = False
        self._event_task: Optional[asyncio.Task] = None

        # por-canal: último rename (anti 429)
        self._last_rename_at: Dict[int, float] = {}

        # por-canal: último nome aplicado (extra proteção)
        self._last_applied_name: Dict[int, str] = {}

        self.update_loop.start()

    def cog_unload(self):
        self.update_loop.cancel()
        if self._event_task and not self._event_task.done():
            self._event_task.cancel()

    # ---------------- Config helpers ----------------

    def _gcfg(self, guild_id: int) -> dict:
        return self.cfg.get(str(guild_id), {"counters": []})

    def _set_gcfg(self, guild_id: int, gcfg: dict) -> None:
        self.cfg[str(guild_id)] = gcfg
        _save_config(self.cfg)

    def _get_counters(self, guild_id: int) -> List[CounterSpec]:
        gcfg = self._gcfg(guild_id)
        out: List[CounterSpec] = []
        for item in gcfg.get("counters", []):
            out.append(
                CounterSpec(
                    channel_id=_as_int(item.get("channel_id")),
                    mode=str(item.get("mode", "all")),
                    name_format=str(item.get("name_format", "{count}")),
                    role_id=_as_int(item.get("role_id", 0)),
                )
            )
        return out

    def _save_counters(self, guild_id: int, counters: List[CounterSpec]) -> None:
        gcfg = self._gcfg(guild_id)
        gcfg["counters"] = [
            {
                "channel_id": c.channel_id,
                "mode": c.mode,
                "name_format": c.name_format,
                "role_id": c.role_id,
            }
            for c in counters
        ]
        self._set_gcfg(guild_id, gcfg)

    def _upsert_counter(self, guild_id: int, spec: CounterSpec) -> None:
        counters = self._get_counters(guild_id)
        for i, c in enumerate(counters):
            if c.channel_id == spec.channel_id:
                counters[i] = spec
                self._save_counters(guild_id, counters)
                return
        counters.append(spec)
        self._save_counters(guild_id, counters)

    # ---------------- Permission lock ----------------

    async def _ensure_locked_visible(self, channel: discord.abc.GuildChannel) -> None:
        if not _is_counter_channel(channel):
            return

        guild = channel.guild
        everyone = guild.default_role

        overwrites = channel.overwrites

        ow_everyone = overwrites.get(everyone, discord.PermissionOverwrite())
        ow_everyone.view_channel = True
        ow_everyone.connect = False
        ow_everyone.speak = False
        ow_everyone.request_to_speak = False
        overwrites[everyone] = ow_everyone

        me = guild.me
        if me:
            ow_bot = overwrites.get(me, discord.PermissionOverwrite())
            ow_bot.view_channel = True
            ow_bot.connect = True
            ow_bot.manage_channels = True
            ow_bot.manage_permissions = True
            overwrites[me] = ow_bot

        await channel.edit(overwrites=overwrites, reason="Counters: lock & visibility")

    # ---------------- Counting logic ----------------

    def _count_all(self, guild: discord.Guild) -> int:
        return guild.member_count or 0

    def _count_humans_bots(self, guild: discord.Guild) -> Tuple[int, int]:
        humans = 0
        bots = 0
        for m in guild.members:
            if m.bot:
                bots += 1
            else:
                humans += 1
        return humans, bots

    def _count_role(self, guild: discord.Guild, role_id: int) -> int:
        role = guild.get_role(role_id)
        if not role:
            return 0
        return len(role.members)

    async def _compute_count(self, guild: discord.Guild, spec: CounterSpec) -> int:
        mode = spec.mode.lower().strip()

        if mode == "all":
            return self._count_all(guild)

        # humans/bots/role dependem do cache de membros (intents.members)
        if mode in ("humans", "bots"):
            humans, bots = self._count_humans_bots(guild)
            return humans if mode == "humans" else bots

        if mode == "role":
            return self._count_role(guild, spec.role_id)

        return 0

    async def _safe_rename(self, channel: discord.abc.GuildChannel, new_name: str) -> bool:
        """
        Protege contra 429:
        - não renomeia se foi há pouco tempo
        - não renomeia se já aplicou o mesmo nome recentemente
        """
        now = time.time()
        last = self._last_rename_at.get(channel.id, 0.0)
        if now - last < MIN_RENAME_INTERVAL_SEC:
            return False

        # extra: se já aplicou esse nome, não repete
        if self._last_applied_name.get(channel.id) == new_name:
            return False

        self._last_rename_at[channel.id] = now
        self._last_applied_name[channel.id] = new_name
        await channel.edit(name=new_name, reason="Counters: update")
        return True

    async def _update_one(self, guild: discord.Guild, spec: CounterSpec, *, force: bool = False) -> None:
        channel = guild.get_channel(spec.channel_id)
        if channel is None or not _is_counter_channel(channel):
            return

        count = await self._compute_count(guild, spec)

        try:
            new_name = spec.name_format.format(count=count)
        except Exception:
            new_name = f"{count}"

        # se não for force, só atualiza se mudou
        if not force and getattr(channel, "name", "") == new_name:
            self._last_applied_name[channel.id] = new_name
            return

        # garante lock (se puder)
        try:
            await self._ensure_locked_visible(channel)
        except discord.Forbidden:
            pass

        # rename com proteção
        try:
            if force:
                # force ainda respeita o intervalo mínimo (pra não tomar 429)
                await self._safe_rename(channel, new_name)
            else:
                await self._safe_rename(channel, new_name)
        except discord.Forbidden:
            pass

    async def update_all(self, *, force: bool = False) -> None:
        async with self._update_lock:
            for guild in self.bot.guilds:
                for spec in self._get_counters(guild.id):
                    await self._update_one(guild, spec, force=force)

    # ---------------- Events (debounced) ----------------

    def _schedule_event_update(self) -> None:
        """
        Em vez de renomear na hora (spam), a gente junta eventos e atualiza depois de um debounce.
        """
        if self._pending_event_update:
            return
        self._pending_event_update = True

        async def _run():
            await asyncio.sleep(EVENT_DEBOUNCE_SEC)
            self._pending_event_update = False
            await self.update_all(force=False)

        self._event_task = self.bot.loop.create_task(_run())

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        self._schedule_event_update()

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        self._schedule_event_update()

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        # Só dispara se cargos mudaram (seu Lobby depende disso)
        if before.roles != after.roles:
            self._schedule_event_update()

    # ---------------- Periodic loop (main updater) ----------------

    @tasks.loop(seconds=UPDATE_LOOP_SEC)
    async def update_loop(self):
        await self.update_all(force=False)

    @update_loop.before_loop
    async def before_update_loop(self):
        await self.bot.wait_until_ready()

    # ---------------- Commands ----------------

    @commands.has_permissions(administrator=True)
    @commands.command(name="counter_edit")
    async def counter_edit(self, ctx: commands.Context, channel_ref: str, *, rest: str = ""):
        """
        Uso recomendado:
          !counter_edit 1464132094782345356 format="✧ 𝐋𝐨𝐛𝐛𝐲 ꞉ {count}"

        Aceita mention:
          !counter_edit <#1464...> format="..."
        """
        chan_id = _extract_channel_id(channel_ref)
        if not chan_id:
            return await ctx.reply("Não entendi o canal. Use o ID (1464...) ou mention (<#...>).")

        channel = ctx.guild.get_channel(chan_id)
        if channel is None:
            return await ctx.reply("Canal não encontrado nesse servidor.")

        if not _is_counter_channel(channel):
            return await ctx.reply("Precisa ser canal de voz ou palco.")

        # encontra spec atual
        counters = self._get_counters(ctx.guild.id)
        current = next((c for c in counters if c.channel_id == channel.id), None)
        if current is None:
            return await ctx.reply("Esse canal não está registrado como contador.")

        # parse: mode= / role_id= / format=
        # format= pega tudo depois (com aspas)
        mode = current.mode
        role_id = current.role_id
        name_format = current.name_format

        # mode
        m = re.search(r"\bmode=(all|humans|bots|role)\b", rest, re.IGNORECASE)
        if m:
            mode = m.group(1).lower()

        # role_id
        m = re.search(r"\brole_id=(\d{15,25}|\d+)\b", rest, re.IGNORECASE)
        if m:
            role_id = int(m.group(1))

        # format (tudo após format=)
        if "format=" in rest:
            fmt = rest.split("format=", 1)[1].strip()
            # remove aspas externas se tiver
            if (fmt.startswith('"') and fmt.endswith('"')) or (fmt.startswith("'") and fmt.endswith("'")):
                fmt = fmt[1:-1]
            name_format = fmt

        if mode == "role":
            if not role_id:
                return await ctx.reply("mode=role exige role_id=...")
            if ctx.guild.get_role(role_id) is None:
                return await ctx.reply("role_id não existe nesse servidor.")

        new_spec = CounterSpec(channel.id, mode, name_format, role_id)
        self._upsert_counter(ctx.guild.id, new_spec)

        # força 1 update (mas ainda respeita anti-429)
        await self._update_one(ctx.guild, new_spec, force=True)
        await ctx.reply("✅ Editado. Se não mudar na hora por 429, espera ~1 minuto e ele atualiza sozinho.")

    @commands.has_permissions(administrator=True)
    @commands.command(name="counter_now")
    async def counter_now(self, ctx: commands.Context):
        await self.update_all(force=True)
        await ctx.reply("🔄 Update disparado. (Se estiver em 429, pode demorar.)")

    @commands.has_permissions(administrator=True)
    @commands.command(name="counter_list")
    async def counter_list(self, ctx: commands.Context):
        counters = self._get_counters(ctx.guild.id)
        if not counters:
            return await ctx.reply("Nenhum contador configurado.")

        lines = []
        for c in counters:
            ch = ctx.guild.get_channel(c.channel_id)
            ch_name = ch.name if ch else f"(sumiu: {c.channel_id})"
            extra = f" role_id={c.role_id}" if c.mode == "role" else ""
            lines.append(f"- `{c.mode}`{extra} -> **{ch_name}** | fmt: `{c.name_format}`")

        await ctx.reply("📌 Contadores:\n" + "\n".join(lines))

    # Preset simples opcional
    @commands.has_permissions(administrator=True)
    @commands.command(name="stats_preset")
    async def stats_preset(self, ctx: commands.Context, lobby_role_id: int = 0):
        guild = ctx.guild

        # cria categoria se não existir
        cat = discord.utils.get(guild.categories, name="SERVER STATS")
        if cat is None:
            cat = await guild.create_category(name="SERVER STATS", reason="Counters preset")

        async def get_or_create_voice(name: str) -> discord.VoiceChannel:
            for ch in cat.channels:
                if isinstance(ch, discord.VoiceChannel) and ch.name == name:
                    return ch
            return await guild.create_voice_channel(name=name, category=cat, reason="Counters preset")

        fmt_all = "𝐀𝐥𝐥 𝐌𝐞𝐦𝐛𝐞𝐫𝐬 ꞉ {count}"
        fmt_members = "𝐌𝐞𝐦𝐛𝐞𝐫𝐬 ꞉ {count}"
        fmt_bots = "𝐁𝐨𝐭𝐬 ꞉ {count}"
        fmt_lobby = "✧ 𝐋𝐨𝐛𝐛𝐲 ꞉ {count}"

        ch_all = await get_or_create_voice("All Members: 0")
        ch_members = await get_or_create_voice("Members: 0")
        ch_bots = await get_or_create_voice("Bots: 0")

        self._upsert_counter(guild.id, CounterSpec(ch_all.id, "all", fmt_all))
        self._upsert_counter(guild.id, CounterSpec(ch_members.id, "humans", fmt_members))
        self._upsert_counter(guild.id, CounterSpec(ch_bots.id, "bots", fmt_bots))

        if lobby_role_id and guild.get_role(int(lobby_role_id)):
            ch_lobby = await get_or_create_voice("Lobby: 0")
            self._upsert_counter(guild.id, CounterSpec(ch_lobby.id, "role", fmt_lobby, int(lobby_role_id)))

        await self.update_all(force=True)
        await ctx.reply("✅ Preset criado/atualizado.")


async def setup(bot: commands.Bot):
    await bot.add_cog(MultiCounters(bot))