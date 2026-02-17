# cogs/voice_rooms.py
import asyncio
import time
from typing import Optional  # ✅ FIX: faltava isso

import discord
from discord.ext import commands
from utils import CANAL_FIXO_CONFIG

class VoiceRoomsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

        # {channel_id: {"owner": int, "fixo": int, "created_at": float}}
        self.created = {}

        # ✅ AGORA: (guild_id, fixo_id, user_id) -> channel_id  (1 sala por pessoa POR FIXO)
        self._owner_room = {}

        self._moving = set()          # user_ids em processo
        self._last_trigger = {}       # (user_id, fixo_id) -> ts

        # debounce agora serve só para evitar DUPLA CRIAÇÃO, mas NÃO pode impedir redirecionar
        self._debounce_seconds = 1.2

        self._delete_tasks = {}       # channel_id -> Task
        self._delete_delay = 6.0      # aumentado p/ evitar corrida (entrar no fix e voltar)

        self._cat_cache = {}          # (guild_id, category_id) -> CategoryChannel|None

        self._trigger_ids = set(CANAL_FIXO_CONFIG.keys())
        self._allowed_category_ids = {cfg["categoria_id"] for cfg in CANAL_FIXO_CONFIG.values()}
        self._prefixes = tuple({cfg["prefixo_nome"] for cfg in CANAL_FIXO_CONFIG.values()})

        self._cleanup_task = None
        self._cleanup_interval = 60.0

        # lock por usuário (evita corrida se o Discord mandar múltiplos eventos)
        self._user_locks = {}         # (guild_id, user_id) -> asyncio.Lock

    # ---------- background ----------
    def start_background(self):
        if self._cleanup_task and not self._cleanup_task.done():
            return
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    def cog_unload(self):
        try:
            if self._cleanup_task and not self._cleanup_task.done():
                self._cleanup_task.cancel()
        except Exception:
            pass

        for t in list(self._delete_tasks.values()):
            try:
                if t and not t.done():
                    t.cancel()
            except Exception:
                pass
        self._delete_tasks.clear()

    # ---------- utils ----------
    def _get_lock(self, guild_id: int, user_id: int) -> asyncio.Lock:
        key = (int(guild_id), int(user_id))
        lock = self._user_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._user_locks[key] = lock
        return lock

    def _session_key(self, guild_id: int, fixo_id: int, user_id: int):
        return (int(guild_id), int(fixo_id), int(user_id))

    def _get_category_cached(self, guild: discord.Guild, category_id: int):
        key = (guild.id, int(category_id))
        if key in self._cat_cache:
            return self._cat_cache[key]
        ch = guild.get_channel(int(category_id))
        cat = ch if isinstance(ch, discord.CategoryChannel) else None
        self._cat_cache[key] = cat
        return cat

    def _cancel_delete_if_any(self, channel_id: int):
        t = self._delete_tasks.get(channel_id)
        if t and not t.done():
            t.cancel()
        self._delete_tasks.pop(channel_id, None)

    def _remove_owner_mapping_for_channel(self, channel_id: int):
        # ✅ agora _owner_room é (guild, fixo, user) -> channel
        for key, cid in list(self._owner_room.items()):
            if cid == channel_id:
                self._owner_room.pop(key, None)

    async def _move_with_retry(self, member: discord.Member, channel: Optional[discord.VoiceChannel], reason: str, tries: int = 3):
        for i in range(tries):
            try:
                await member.move_to(channel, reason=reason)  # channel=None desconecta
                return True
            except Exception as e:
                if i == tries - 1:
                    print(f"[VoiceRooms] move falhou ({reason}): {e}")
                await asyncio.sleep(0.25 + 0.20 * i)
        return False

    async def _schedule_delete_if_empty(self, channel: discord.VoiceChannel):
        await asyncio.sleep(self._delete_delay)
        ch_id = getattr(channel, "id", 0)

        try:
            if channel and len(channel.members) == 0:
                await channel.delete(reason="Sala dinâmica vazia (auto)")
        except Exception:
            pass
        finally:
            self.created.pop(ch_id, None)
            self._delete_tasks.pop(ch_id, None)
            self._remove_owner_mapping_for_channel(ch_id)

    async def _cleanup_loop(self):
        try:
            await self.bot.wait_until_ready()
        except Exception:
            return

        while not self.bot.is_closed():
            try:
                await asyncio.sleep(self._cleanup_interval)

                for guild in list(self.bot.guilds):
                    me = guild.me
                    if not me:
                        continue

                    for vc in list(guild.voice_channels):
                        try:
                            if vc.id in self._trigger_ids:
                                continue
                            if not vc.category or vc.category.id not in self._allowed_category_ids:
                                continue
                            if not vc.name.startswith(self._prefixes):
                                continue
                            if len(vc.members) != 0:
                                continue
                            if not vc.permissions_for(me).manage_channels:
                                continue

                            await vc.delete(reason="Limpeza de sobras (auto)")
                            self.created.pop(vc.id, None)
                            self._delete_tasks.pop(vc.id, None)
                            self._remove_owner_mapping_for_channel(vc.id)
                        except Exception:
                            continue

            except asyncio.CancelledError:
                return
            except Exception:
                continue

    async def _create_room(self, guild: discord.Guild, base_vc: discord.VoiceChannel, categoria: Optional[discord.CategoryChannel], prefixo: str, member: discord.Member):
        # copia perms do fixo e garante dono
        overwrites = dict(base_vc.overwrites)
        ow = overwrites.get(member)
        if ow is None:
            ow = discord.PermissionOverwrite()
        ow.view_channel = True
        ow.connect = True
        ow.speak = True
        overwrites[member] = ow

        novo = await guild.create_voice_channel(
            name=f"{prefixo}{member.display_name}",
            category=(categoria or base_vc.category),
            overwrites=overwrites,
            bitrate=getattr(base_vc, "bitrate", None),
            user_limit=getattr(base_vc, "user_limit", 0),
            reason="Sala dinâmica criada (gatilho)",
        )
        return novo

    # ---------- main listener ----------
    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        try:
            if member.bot:
                return
            if before.channel == after.channel:
                return

            guild = member.guild
            if not guild:
                return

            # entrou em canal criado -> cancela delete
            if after.channel and after.channel.id in self.created:
                self._cancel_delete_if_any(after.channel.id)

            # ---------- gatilho: entrou em canal fixo ----------
            if after.channel and after.channel.id in CANAL_FIXO_CONFIG:
                base_vc = after.channel
                cfg = CANAL_FIXO_CONFIG[base_vc.id]
                prefixo = cfg["prefixo_nome"]

                me = guild.me
                if not me:
                    return

                perms_base = base_vc.permissions_for(me)
                if not perms_base.manage_channels or not perms_base.move_members:
                    print("[VoiceRooms] sem permissão manage_channels/move_members no canal fixo")
                    return

                categoria = self._get_category_cached(guild, cfg["categoria_id"]) or base_vc.category

                # lock por usuário (evita corrida)
                lock = self._get_lock(guild.id, member.id)
                if lock.locked():
                    # se evento duplicado chegar, não cria nada — mas também não deixa preso:
                    # tenta mover pro destino existente logo abaixo
                    pass

                async with lock:
                    now = time.time()
                    trig_key = (int(member.id), int(base_vc.id))
                    last_t = float(self._last_trigger.get(trig_key, 0.0) or 0.0)
                    too_soon = (now - last_t) < self._debounce_seconds
                    self._last_trigger[trig_key] = now

                    session_key = self._session_key(guild.id, base_vc.id, member.id)

                    # pega canal existente PARA ESTE FIXO (não mistura categoria)
                    existing_id = self._owner_room.get(session_key)
                    existing = guild.get_channel(int(existing_id)) if existing_id else None

                    dest = None

                    if isinstance(existing, discord.VoiceChannel) and existing.id in self.created:
                        info = self.created.get(existing.id) or {}
                        if int(info.get("owner", 0) or 0) == int(member.id) and int(info.get("fixo", 0) or 0) == int(base_vc.id):
                            self._cancel_delete_if_any(existing.id)

                            # regra: se vazio -> reutiliza
                            if len(existing.members) == 0:
                                dest = existing
                            else:
                                # se tem gente -> cria novo (a não ser que seja evento duplicado muito rápido)
                                if too_soon:
                                    dest = existing
                                else:
                                    novo = await self._create_room(guild, base_vc, categoria, prefixo, member)
                                    self.created[novo.id] = {"owner": member.id, "fixo": base_vc.id, "created_at": time.time()}
                                    self._owner_room[session_key] = novo.id
                                    dest = novo
                        else:
                            # mapeamento velho/errado
                            self._owner_room.pop(session_key, None)

                    if dest is None:
                        # cria do zero (para este fixo)
                        novo = await self._create_room(guild, base_vc, categoria, prefixo, member)
                        self.created[novo.id] = {"owner": member.id, "fixo": base_vc.id, "created_at": time.time()}
                        self._owner_room[session_key] = novo.id
                        dest = novo

                    # move para o destino (não deixa ficar no fixo)
                    moved = await self._move_with_retry(member, dest, reason="Mover para sala dinâmica")
                    if not moved:
                        # fallback seguro: se ele veio de uma sala dele (dinâmica), tenta voltar; senão desconecta
                        if before.channel and before.channel.id in self.created:
                            info = self.created.get(before.channel.id) or {}
                            if int(info.get("owner", 0) or 0) == int(member.id):
                                await self._move_with_retry(member, before.channel, reason="Fallback: voltar pra sala anterior do dono")
                                return

                        # não deixa preso no fixo
                        await self._move_with_retry(member, None, reason="Fallback: evitar ficar no canal fixo")

                        # se o destino era novo e ficou vazio, limpa
                        try:
                            await asyncio.sleep(0.4)
                            if isinstance(dest, discord.VoiceChannel) and len(dest.members) == 0:
                                await dest.delete(reason="Falha ao mover, limpando sala vazia")
                        except Exception:
                            pass
                        finally:
                            if isinstance(dest, discord.VoiceChannel):
                                self.created.pop(dest.id, None)
                                self._remove_owner_mapping_for_channel(dest.id)

                return

            # ---------- saiu de canal criado -> agenda delete ----------
            if before.channel and before.channel.id in self.created:
                canal = before.channel
                if len(canal.members) == 0:
                    self._cancel_delete_if_any(canal.id)
                    self._delete_tasks[canal.id] = asyncio.create_task(self._schedule_delete_if_empty(canal))

        except Exception as e:
            print(f"[VoiceRooms] erro no on_voice_state_update: {e}")


async def setup(bot: commands.Bot):
    cog = VoiceRoomsCog(bot)
    await bot.add_cog(cog)
    cog.start_background()