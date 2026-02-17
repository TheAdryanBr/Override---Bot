"""
welcome_bridge — Override

Objetivos (acordados):
- NÃO iniciar conversa
- NÃO virar autor principal
- NÃO quebrar cooldown
- NÃO interferir no ConversationManager
- Agregar múltiplas entradas (join spam)
- Delay humano e levemente aleatório
- Aparição rara, seca, sem educação automática

Agora:
- Sempre fala NO CHANNEL_MAIN (e em mais nenhum)
- Pode usar Gemini (via AIEngine) para variar o texto
- Pode desligar por .env
"""

import asyncio
import os
import random
import re
import time
from typing import Dict, List, Optional

import discord

# Canal principal (regra: o ai_chat do Override só fala no channel_main)
try:
    from utils import CHANNEL_MAIN as _CHANNEL_MAIN
except Exception:
    _CHANNEL_MAIN = 0

# Reaproveita teu engine Gemini (já usa AI_API_KEY por padrão)
try:
    from .ai_engine import AIEngine
except Exception:
    AIEngine = None  # type: ignore


def _env_flag(name: str, default: str = "1") -> bool:
    v = (os.getenv(name, default) or "").strip().lower()
    return v in ("1", "true", "yes", "y", "on")


def _one_line(text: str) -> str:
    t = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    t = re.sub(r"\s+", " ", t.replace("\n", " ")).strip()
    return t


def _clip(text: str, max_chars: int) -> str:
    t = _one_line(text)
    if not t:
        return ""
    if max_chars and len(t) > max_chars:
        t = t[: max_chars - 1].rstrip() + "…"
    return t


class WelcomeBridge:
    def __init__(
        self,
        *,
        # delays humanos
        min_delay: float = 6.0,
        max_delay: float = 14.0,
        aggregate_window: float = 18.0,

        # travas
        global_cooldown: float = 180.0,
        per_user_cooldown: float = 600.0,
        chance: float = 0.45,

        # IA / controle
        enabled: Optional[bool] = None,
        use_ai: Optional[bool] = None,
        max_chars: int = 220,
        model_preference: Optional[List[str]] = None,
    ):
        # liga/desliga via .env (sem precisar mexer no código)
        self.enabled = _env_flag("WELCOME_BRIDGE_ENABLED", "1") if enabled is None else bool(enabled)
        self.use_ai = _env_flag("WELCOME_BRIDGE_USE_AI", "1") if use_ai is None else bool(use_ai)

        self.max_chars = int(max_chars)

        # delays humanos
        self.min_delay = float(min_delay)
        self.max_delay = float(max_delay)

        # agrega joins próximos
        self.aggregate_window = float(aggregate_window)

        # travas
        self.global_cooldown = float(global_cooldown)
        self.per_user_cooldown = float(per_user_cooldown)
        self.chance = float(chance)

        # estado interno
        self._pending: Dict[int, List[discord.Member]] = {}
        self._pending_tasks: Dict[int, asyncio.Task] = {}

        self._last_global_ts: float = 0.0
        self._last_by_user: Dict[int, float] = {}

        # engine (lazy)
        self._engine = None
        self._model_preference = model_preference or [
            "gemini-2.0-flash-lite",
            "gemini-2.0-flash",
            "gemini-1.5-flash",
        ]

    # -------- API pública --------

    def notify_join(self, member: discord.Member):
        """
        Chamado pelo evento on_member_join
        """
        if not self.enabled:
            return
        if not member or not member.guild:
            return
        if getattr(member, "bot", False):
            return

        gid = int(member.guild.id)
        self._pending.setdefault(gid, []).append(member)

        if gid not in self._pending_tasks:
            self._pending_tasks[gid] = asyncio.create_task(self._flush_after(gid))

    # -------- interno --------

    async def _flush_after(self, guild_id: int):
        await asyncio.sleep(self.aggregate_window)

        members = self._pending.pop(guild_id, [])
        self._pending_tasks.pop(guild_id, None)
        if not members:
            return

        now = time.time()

        # cooldown global
        if (now - self._last_global_ts) < self.global_cooldown:
            return

        # chance de aparecer
        if random.random() > self.chance:
            return

        # filtra quem já recebeu welcome recentemente
        final: List[discord.Member] = []
        for m in members:
            last = float(self._last_by_user.get(int(m.id), 0.0) or 0.0)
            if (now - last) >= self.per_user_cooldown:
                final.append(m)

        if not final:
            return

        # delay humano antes de falar
        await asyncio.sleep(random.uniform(self.min_delay, self.max_delay))

        guild = final[0].guild

        # Canal: SOMENTE CHANNEL_MAIN
        channel = self._pick_channel_main_only(guild)
        if not channel:
            return

        # monta mensagem
        msg = await self._build_message(final)

        msg = _clip(msg, self.max_chars)
        if not msg:
            return

        try:
            await channel.send(
                msg,
                allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False),
            )
        except Exception:
            return

        # atualiza cooldowns
        self._last_global_ts = time.time()
        for m in final:
            self._last_by_user[int(m.id)] = self._last_global_ts

    # -------- helpers --------

    def _pick_channel_main_only(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        """
        Regra: WelcomeBridge só fala no CHANNEL_MAIN.
        Se não existir ou não puder falar, não fala em nenhum outro lugar.
        """
        if not _CHANNEL_MAIN:
            return None

        ch = guild.get_channel(int(_CHANNEL_MAIN))
        if not isinstance(ch, discord.TextChannel):
            return None

        try:
            me = guild.me
            if me and (not ch.permissions_for(me).send_messages):
                return None
        except Exception:
            pass

        return ch

    def _static_variations(self, mentions: List[str]) -> str:
        """
        Fallback sem IA: ainda varia bastante e marca as pessoas.
        1 linha, seco, sem pergunta.
        """
        if not mentions:
            return ""

        one = [
            "{u} chegou, vê se não quebra nada",
            "{u} entrou, mais um pra dar trabalho",
            "{u} apareceu, seja bem-vindo (a)",
            "{u} bem-vindo, sem bagunça em",
            "{u} mais um pra tropa",
            "{u} chegou, vai com calma",
        ]
        two = [
            "{a} e {b} chegaram, a dupla dinâmica",
            "{a} e {b} entraram, não inventem moda",
            "{a} e {b} colaram, bem-vindos (a)",
        ]
        three = [
            "{a}, {b} e {c} chegaram, ok",
            "{a}, {b} e {c} entraram, sem show",
        ]
        many = [
            "{a}, {b} e mais {n} chegaram",
            "{a}, {b} e mais {n} cairam de cabeça no lobby",
        ]

        if len(mentions) == 1:
            return random.choice(one).format(u=mentions[0])
        if len(mentions) == 2:
            return random.choice(two).format(a=mentions[0], b=mentions[1])
        if len(mentions) == 3:
            return random.choice(three).format(a=mentions[0], b=mentions[1], c=mentions[2])

        return random.choice(many).format(a=mentions[0], b=mentions[1], n=(len(mentions) - 2))

    def _ensure_engine(self):
        if self._engine is not None:
            return
        if not self.use_ai:
            self._engine = None
            return
        if AIEngine is None:
            self._engine = None
            return

        # Cria engine só para welcome (leve e barato)
        try:
            self._engine = AIEngine(models=list(self._model_preference))
        except Exception:
            self._engine = None

    async def _build_message(self, members: List[discord.Member]) -> str:
        mentions = [m.mention for m in members[:3]]
        if not mentions:
            return ""

        # Sem IA -> fallback variado
        if not self.use_ai:
            return self._static_variations(mentions)

        self._ensure_engine()
        if not self._engine:
            return self._static_variations(mentions)

        # Prompt curto, mantendo a essência sem “puxar conversa”
        # (1 linha, sem pergunta, seco, torto, menciona os caras)
        if len(members) == 1:
            target = f"O membro {mentions[0]} acabou de entrar."
        elif len(members) == 2:
            target = f"Os membros {mentions[0]} e {mentions[1]} acabaram de entrar."
        elif len(members) == 3:
            target = f"Os membros {mentions[0]}, {mentions[1]} e {mentions[2]} acabaram de entrar."
        else:
            target = f"Entrou um grupo: {mentions[0]}, {mentions[1]} e mais {len(members)-2}."

        prompt = (
            "Você é Override, um bot do Discord.\n"
            "Tarefa: mandar UMA mensagem de boas-vindas curta e seca.\n"
            "Regras:\n"
            "- 1 linha só (sem quebras)\n"
            "- sem perguntas\n"
            "- sem discurso bonitinho\n"
            "- mencione exatamente os @ que eu citar\n"
            "- tom: humano, preguiçoso, meio torto, às vezes levemente engraçado\n"
            f"- limite: até {self.max_chars} caracteres\n"
            "\n"
            f"Contexto: {target}\n"
            "Saída: apenas a mensagem final.\n"
        )

        try:
            out = await self._engine.generate_raw_text(
                prompt,
                max_output_tokens=90,
                temperature=0.95,
            )
        except Exception:
            return self._static_variations(mentions)

        msg = _one_line(out)

        # “segurança” contra o modelo inventar pergunta ou quebrar regra
        msg = msg.replace("?", "").strip()
        if not msg:
            return self._static_variations(mentions)

        # garante que pelo menos 1 mention apareceu
        if mentions[0] not in msg:
            # se o modelo “esqueceu”, injeta no começo
            msg = f"{mentions[0]} {msg}".strip()

        return msg