# cogs/ai_chat/ai_chat.py
import asyncio
import random
import re
import time

import discord
from discord.ext import commands
from utils import CHANNEL_MAIN, OWNER_ID, ADMIN_ROLE_ID, WELCOME_CHANNEL_ID as WELCOME_CHANNEL_ID_CONST

from utils import CHANNEL_MAIN

from .ai_engine import AIEngine
from .message_buffer import MessageBuffer
from .social_focus import SocialFocus
from .conversation_manager import ConversationManager
from .ai_state import AIStateManager
from .typing_tracker import TypingTracker
from .core import ChatCore
from .block_classifier import BlockClassifier


class CFG:
    # ---- modelo ----
    primary_models = ["gemini-2.5-flash"]
    fallback_models = []

    # ---- segurança / permissões ----
    owner_id = OWNER_ID
    admin_role_id = ADMIN_ROLE_ID
    WELCOME_CHANNEL_ID = WELCOME_CHANNEL_ID_CONST

    # ---- cooldown global do core ----
    cooldown = 30

    # ---- batch / fragmentos ----
    base_window = 3.0
    fragment_window = 8.0
    max_wait_soft = 14.0
    max_wait_hard = 60.0
    typing_grace = 12.0

    self_memory_limit = 6
    per_author_buffer_limit = 12

    # ---- addressing ----
    addressing_force_if_batch_age_lt = 1.2

    # ---- interjeições ----
    spontaneous_chance = 0.45
    spontaneous_global_cooldown = 18.0
    spontaneous_per_author_cooldown = 25.0

    secondary_window = 35.0
    secondary_max_turns = 2
    secondary_per_author_cooldown = 45.0

    # ---- tom (60/40) ----
    tone_analytic_ratio = 0.60
    tone_sarcasm_ratio = 0.40

    # ---- welcome bridge ----
    WELCOME_CHANNEL_ID = WELCOME_CHANNEL_ID
    
    # delay entre 1s e 4min
    welcome_delay_min = 1.0
    welcome_delay_max = 240.0

    # anti-spam (raid)
    welcome_per_user_cooldown = 60.0          # não dar boas-vindas repetidas pro mesmo cara rápido
    welcome_global_window = 120.0             # janela de contagem
    welcome_global_max_in_window = 4          # max boas-vindas na janela


_MENTION_ID_RE = re.compile(r"<@!?(?P<id>\d+)>")


class AIChatCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

        self.engine = AIEngine(
            primary_models=CFG.primary_models,
            fallback_models=CFG.fallback_models,
        )

        self.buffer = MessageBuffer(max_messages=CFG.per_author_buffer_limit)
        self.social = SocialFocus(timeout=120)

        self.conv = ConversationManager(
            idle_timeout=20 * 60,
            soft_exit_timeout=120,
            max_presence=8 * 60,
            recent_end_window=90,
        )

        self.state = AIStateManager(
            owner_id=CFG.owner_id,
            admin_role_id=CFG.admin_role_id,
            cooldown=CFG.cooldown,
        )

        self.typing = TypingTracker()
        self.block = BlockClassifier(self.engine)

        self.core = ChatCore(
            bot=self.bot,
            engine=self.engine,
            buffer=self.buffer,
            social_focus=self.social,
            conv=self.conv,
            state=self.state,
            typing=self.typing,
            block_classifier=self.block,
            base_window=CFG.base_window,
            fragment_window=CFG.fragment_window,
            max_wait_soft=CFG.max_wait_soft,
            max_wait_hard=CFG.max_wait_hard,
            typing_grace=CFG.typing_grace,
            self_memory_limit=CFG.self_memory_limit,
            per_author_buffer_limit=CFG.per_author_buffer_limit,
            addressing_force_if_batch_age_lt=CFG.addressing_force_if_batch_age_lt,
            spontaneous_chance=CFG.spontaneous_chance,
            spontaneous_global_cooldown=CFG.spontaneous_global_cooldown,
            spontaneous_per_author_cooldown=CFG.spontaneous_per_author_cooldown,
            secondary_window=CFG.secondary_window,
            secondary_max_turns=CFG.secondary_max_turns,
            secondary_per_author_cooldown=CFG.secondary_per_author_cooldown,
            tone_analytic_ratio=CFG.tone_analytic_ratio,
            tone_sarcasm_ratio=CFG.tone_sarcasm_ratio,
        )

        # --- welcome bridge state (não toca no cooldown do core) ---
        self._welcome_last_by_user = {}   # user_id -> ts
        self._welcome_global_hits = []    # [ts, ts, ...]
        self._welcome_pending = set()     # user_ids em fila

    def _now(self) -> float:
        return time.time()

    def _welcome_global_allow(self, now: float) -> bool:
        # limpa janela
        w = float(CFG.welcome_global_window)
        self._welcome_global_hits = [t for t in self._welcome_global_hits if (now - float(t)) <= w]
        return len(self._welcome_global_hits) < int(CFG.welcome_global_max_in_window)

    def _extract_target_member(self, message: discord.Message) -> discord.Member | None:
        """Tenta achar o membro que entrou a partir da mensagem no canal de boas-vindas."""
        guild = getattr(message, "guild", None)
        if not guild:
            return None

        # 1) mentions diretas
        try:
            for u in (message.mentions or []):
                if isinstance(u, discord.Member) and (not u.bot):
                    return u
                # às vezes vem como User; tenta pegar Member
                if hasattr(u, "id") and (not getattr(u, "bot", False)):
                    m = guild.get_member(int(u.id))
                    if m and (not m.bot):
                        return m
        except Exception:
            pass

        # 2) regex <@id>
        try:
            txt = (message.content or "")
            m = _MENTION_ID_RE.search(txt)
            if m:
                uid = int(m.group("id"))
                mem = guild.get_member(uid)
                if mem and (not mem.bot):
                    return mem
        except Exception:
            pass

        return None

    def _pick_welcome_line(self, name: str) -> str:
        # seco/analítico + sarcasmo leve (sem humilhar)
        lines = [
            f"{name}, chegou. Não quebra nada e tá ótimo.",
            f"{name} spawnou no servidor. Respira e escolhe um canal.",
            f"Bem-vindo, {name}. Se perder, finge que era parte do plano.",
            f"{name}, caiu aqui. Sem pressão… só as regras.",
            f"{name} entrou. Agora oficialmente tem mais alguém pra culpar quando der erro.",
            f"Chegou, {name}. Se for pra causar, pelo menos causa bonito.",
        ]
        return random.choice(lines)

    async def _delayed_welcome(self, guild_id: int, member_id: int, delay: float):
        try:
            await asyncio.sleep(float(delay))
            guild = self.bot.get_guild(int(guild_id))
            if not guild:
                return

            member = guild.get_member(int(member_id))
            if not member or member.bot:
                return

            ch = guild.get_channel(int(CHANNEL_MAIN))
            if not isinstance(ch, discord.TextChannel):
                return

            line = self._pick_welcome_line(member.display_name)
            content = f"{member.mention} {line}"

            await ch.send(
                content,
                allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False),
            )
        finally:
            # limpa pendência
            try:
                self._welcome_pending.discard(int(member_id))
            except Exception:
                pass

    async def _handle_welcome_channel_message(self, message: discord.Message):
        # só no canal de boas-vindas
        if int(getattr(message.channel, "id", 0) or 0) != int(CFG.WELCOME_CHANNEL_ID):
            return

        # ignora mensagens do próprio Override
        me = getattr(self.bot, "user", None)
        if me and int(getattr(message.author, "id", 0) or 0) == int(me.id):
            return

        # precisa achar um membro alvo
        target = self._extract_target_member(message)
        if not target:
            return

        now = self._now()

        # por-user cooldown
        last = float(self._welcome_last_by_user.get(int(target.id), 0.0) or 0.0)
        if last and (now - last) < float(CFG.welcome_per_user_cooldown):
            return

        # anti-raid global
        if not self._welcome_global_allow(now):
            return

        # não agenda duplicado
        if int(target.id) in self._welcome_pending:
            return

        self._welcome_last_by_user[int(target.id)] = now
        self._welcome_global_hits.append(now)
        self._welcome_pending.add(int(target.id))

        delay = random.uniform(float(CFG.welcome_delay_min), float(CFG.welcome_delay_max))
        asyncio.create_task(self._delayed_welcome(int(target.guild.id), int(target.id), delay))

    @commands.Cog.listener()
    async def on_typing(self, channel, user, when):
        if user.bot:
            return
        ch_id = getattr(channel, "id", None)
        if ch_id is None or ch_id != CHANNEL_MAIN:
            return
        try:
            self.core.notify_typing(user.id, ch_id)
        except Exception:
            return

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # ✅ welcome bridge precisa ver mensagem de bot no canal de boas-vindas
        try:
            if isinstance(message.channel, discord.TextChannel) and int(message.channel.id) == int(CFG.WELCOME_CHANNEL_ID):
                await self._handle_welcome_channel_message(message)
                return
        except Exception:
            pass

        # fluxo normal do ai_chat (ignora bots)
        if message.author.bot:
            return
        if not isinstance(message.channel, discord.TextChannel):
            return

        await self.core.handle_message(message, channel_main_id=CHANNEL_MAIN)