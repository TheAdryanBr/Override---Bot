# cogs/ai_chat/core.py
"""
ChatCore — Override (AI Chat)

✅ O que esta versão entrega (do jeito que você descreveu):
- Batch por autor + fragmentos (aceita "de", "boa", etc se o batch já começou)
- Espera typing parar (via TypingTracker + typing_grace)
- Addressing inteligente: @ só quando precisa (ou quando batch fechou rápido / canal andou)
- Anti-loop WAIT (corta e responde curto se ficar preso esperando)
- Interjeições (secondary/spontaneous) com cooldown
- Memória curta das próprias mensagens (ChannelMemory) para não repetir
- Soft-exit humano (despedida com “tenho que ir” etc quando EXITING_SOFT)
- Read intent (tentativa segura): "Override lê isso" / reply, só se fora do cooldown
- Multi-pessoa de verdade:
  - ConversationManager POR AUTOR (não existe mais “autor principal” fixo)
  - Sessões temporárias por assunto (topic merge):
    - se assuntos parecidos: usa contexto dos dois/mais na mesma resposta
    - se parar: separa automaticamente
  - Não “troca autor” por causa disso: só usa contexto conjunto, mas responde ao autor que chamou

🆕 Ajustes nesta versão:
- Normalização leve (sem IA pesada):
  - bgl/bagui -> bagulho, vc/vcs -> voce/voces, ta/to -> tá/tô, pq -> porque...
  - kkkkk -> kkk
  - alongamento de letra (boooa -> booa)
- Topic merge mais estável:
  - não cria tópicos com mensagens curtas/ruído
"""

import asyncio
import logging
import random
import re
import time
from dataclasses import dataclass
from typing import Optional, Dict, List, Set

import discord

from .ai_engine import AIEngine
from .message_buffer import MessageBuffer
from .social_focus import SocialFocus
from .conversation_manager import ConversationManager, ConversationState
from .ai_decision import AIDecision, Decision
from .ai_state import AIStateManager
from .typing_tracker import TypingTracker

from .conversation_blocks import BlockBatch
from .block_classifier import BlockClassifier
from .interjection_policy import InterjectionPolicy
from .channel_memory import ChannelMemory
from .read_intent import build_read_intent, ReadIntent

log = logging.getLogger("ai_chat.core")

_MENTION_RE = re.compile(r"<@!?\d+>|<@&\d+>|<#\d+>")
_SPECIAL_MENTIONS = {"@everyone", "@here"}
_NAME_CALL_RE = re.compile(r"\boverride\b", re.IGNORECASE)

# palavras muito comuns pra não virar “assunto”
_STOPWORDS = {
    "de", "do", "da", "dos", "das", "a", "o", "as", "os", "um", "uma", "uns", "umas",
    "e", "ou", "mas", "que", "se", "pra", "para", "com", "sem", "em", "no", "na",
    "por", "porque", "como", "quando", "onde", "isso", "essa", "esse", "ai", "aí",
    "ta", "tá", "to", "tô", "vc", "vcs", "você", "vocês", "mano", "cara", "véi",
}


import re

# ----------------- util -----------------

_LINESEP_RE = re.compile(r"[\u2028\u2029]")  # separadores estranhos de linha

def strip_mentions(text: str) -> str:
    if not text:
        return ""
    t = _MENTION_RE.sub("", text)
    for m in _SPECIAL_MENTIONS:
        t = t.replace(m, "")
    return " ".join(t.strip().split())


def sanitize(text: str) -> str:
    # padroniza quebras e remove lixo de borda
    return (
        (text or "")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .strip()
    )


def _finalize_tail_one_line(t: str) -> str:
    t = (t or "").strip()

    # não terminar pendurado em pontuação “aberta”
    while t.endswith((",", ";", ":")):
        t = t[:-1].rstrip()

    # se não fechou com pontuação de fim, fecha com reticências
    if t and (t[-1] not in ".!?…"):
        t = t + "…"
    return t.strip()


def _truncate_smart(t: str, limit: int = 400) -> str:
    t = (t or "").strip()
    if len(t) <= limit:
        return t

    cut = t[:limit].rstrip()

    # tenta cortar num fim de frase
    last_end = max(cut.rfind("."), cut.rfind("!"), cut.rfind("?"), cut.rfind("…"))
    if last_end >= int(limit * 0.55):
        cut = cut[: last_end + 1].rstrip()
        return cut

    # senão corta num espaço bom
    last_space = cut.rfind(" ")
    if last_space >= int(limit * 0.70):
        cut = cut[:last_space].rstrip()

    while cut.endswith((",", ";", ":")):
        cut = cut[:-1].rstrip()

    return (cut + "…").strip()


def postprocess_override_output(text: str, limit: int = 400) -> str:
    """
    Garante:
    - sempre 1 linha (sem \n)
    - até 'limit' caracteres (default 400)
    - não termina com vírgula / cauda pendurada
    """
    t = sanitize(text)
    if not t:
        return ""

    # 1) sempre UMA linha
    t = _LINESEP_RE.sub("\n", t)
    t = t.replace("\n", " ")

    # 2) colapsa espaços
    t = " ".join(t.split()).strip()

    # 3) fecha cauda
    t = _finalize_tail_one_line(t)

    # 4) limita tamanho com corte “bonito”
    t = _truncate_smart(t, limit=limit)

    return t


def normalize(text: str) -> str:
    return " ".join((text or "").lower().split())

# --- normalização leve (sem IA, só higiene) ---

_REPEAT_RE = re.compile(r"(.)\1{2,}", re.IGNORECASE)  # aaa -> aa
_KKK_RE = re.compile(r"\bk{3,}\b", re.IGNORECASE)

_SLANG_MAP = {
    "bgl": "bagulho",
    "bagui": "bagulho",
    "bagulho": "bagulho",
    "ngc": "negocio",
    "pq": "porque",
    "q": "que",
    "vc": "voce",
    "vcs": "voces",
    "cê": "voce",
    "ce": "voce",
    "ta": "tá",
    "tá": "tá",
    "to": "tô",
    "tô": "tô",
    "tb": "tambem",
    "tbm": "tambem",
    "nd": "nada",
    "nn": "nao",
    "n": "nao",
    "nao": "nao",
}


def pre_normalize_light(text: str) -> str:
    """
    Normaliza só o suficiente pra:
    - reduzir variações "bgl/bagui/bagulho"
    - reduzir alongamento ("boooa" -> "booa")
    - colapsar 'kkkkkk' -> 'kkk'
    - padronizar espaços e remover menções (pra lógica/keywords)
    """
    t = normalize(strip_mentions(text))

    # risada "kkkkk" -> "kkk"
    t = _KKK_RE.sub("kkk", t)

    # reduz alongamento de caracteres (3+ vira 2)
    t = _REPEAT_RE.sub(r"\1\1", t)

    # troca gírias por forma base (mantendo pontuação do token)
    parts = re.split(r"(\s+)", t)  # mantém espaços
    for i, p in enumerate(parts):
        if not p or p.isspace():
            continue
        w = p.strip()
        w2 = w.strip(".,;:!?…\"'`()[]{}")
        if not w2:
            continue
        repl = _SLANG_MAP.get(w2, None)
        if repl:
            parts[i] = w.replace(w2, repl)
    return "".join(parts).strip()


def is_replying_to_bot(message: discord.Message, bot_user) -> bool:
    if not bot_user:
        return False
    ref = getattr(message, "reference", None)
    if not ref:
        return False
    resolved = getattr(ref, "resolved", None)
    if not resolved:
        return False
    try:
        return bool(resolved.author and resolved.author.id == bot_user.id)
    except Exception:
        return False


def is_name_called(message: discord.Message) -> bool:
    try:
        txt = (message.content or "")
    except Exception:
        return False
    return bool(txt and _NAME_CALL_RE.search(txt))


def looks_like_fragment_clean(clean: str) -> bool:
    c = pre_normalize_light(clean or "")
    if not c:
        return False

    greetings = (
        "oi", "opa", "eae", "eai", "eaí", "e aí", "salve", "fala",
        "bom dia", "boa tarde", "boa noite", "iae", "iai",
    )
    if c in greetings or any(c.startswith(g + " ") for g in greetings):
        return False

    closures = {
        "blz", "beleza", "ok", "okay", "entendi", "ta", "tá", "certo",
        "valeu", "vlw", "show", "fechou", "isso", "sim", "não", "nao",
        "kk", "kkk", "kkkk", "kkkkk", "kkkkkk", "hm", "hmm", "hmmm",
    }
    if c in closures:
        return False

    tail_words = {
        "porque", "quando", "onde", "como", "mas", "então", "entao", "daí", "dai", "aí", "ai",
        "que", "se", "pra", "para", "com", "sem", "de", "do", "da", "em", "no", "na",
        "sobre", "até", "ate", "e", "ou",
    }
    parts = c.split()
    if parts and parts[-1] in tail_words:
        return True

    if c.endswith((",", ":", ";")):
        return True
    if c.endswith("...") or c.endswith("…"):
        return True

    if "?" in c:
        return False
    if c.endswith((".", "!", "?", "…")):
        return False

    if len(parts) <= 1 and len(c) <= 12:
        return True
    if len(parts) >= 2 and len(c) <= 12:
        return False

    return False


def is_greeting_clean(clean: str) -> bool:
    c = pre_normalize_light(clean or "")
    if not c:
        return False
    greetings = (
        "oi", "opa", "eae", "eai", "eaí", "e aí", "salve", "fala",
        "bom dia", "boa tarde", "boa noite", "iae", "iai",
    )
    if c in greetings:
        return True
    return any(c.startswith(g + " ") for g in greetings)


def _kw_set(text: str) -> Set[str]:
    t = pre_normalize_light(text)
    toks = [w for w in re.split(r"[^a-z0-9á-ú_]+", t) if w]
    out = set()
    for w in toks:
        if len(w) <= 3:
            continue
        if w in _STOPWORDS:
            continue
        if w in ("kkk",):
            continue
        out.add(w)
    return out


def _jaccard(a: Set[str], b: Set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a.intersection(b))
    uni = len(a.union(b))
    return float(inter) / float(uni or 1)


# ----------------- topic sessions (merge por assunto) -----------------


@dataclass
class TopicSession:
    key: str
    keywords: Set[str]
    authors: Set[int]
    last_activity: float
    turns: int = 0  # só pra telemetria / heurísticas


# ----------------- core -----------------


class ChatCore:
    def __init__(
        self,
        *,
        bot: discord.Client,
        engine: AIEngine,
        buffer: MessageBuffer,
        social_focus: SocialFocus,
        conv: ConversationManager,
        state: AIStateManager,
        typing: TypingTracker,
        block_classifier: Optional[BlockClassifier] = None,
        base_window: float = 3.0,
        fragment_window: float = 8.0,
        max_wait_soft: float = 14.0,
        max_wait_hard: float = 60.0,
        typing_grace: float = 12.0,
        self_memory_limit: int = 6,
        per_author_buffer_limit: int = 12,

        # addressing / interjeições / tom
        addressing_force_if_batch_age_lt: float = 1.2,

        spontaneous_chance: float = 0.35,
        spontaneous_global_cooldown: float = 18.0,
        spontaneous_per_author_cooldown: float = 25.0,

        secondary_window: float = 35.0,
        secondary_max_turns: int = 2,
        secondary_per_author_cooldown: float = 45.0,

        tone_analytic_ratio: float = 0.60,
        tone_sarcasm_ratio: float = 0.40,

        # multi conversa / merge por assunto
        topic_ttl: float = 90.0,
        topic_similarity: float = 0.55,
        topic_min_shared: int = 2,
        topic_min_kw: int = 4,
        vibe_follow_chance: float = 0.35,
        vibe_follow_cooldown: float = 45.0,
    ):
        self.bot = bot
        self.engine = engine

        # buffers por autor (mensagens do user)
        self.buffers: Dict[int, MessageBuffer] = {}
        self.per_author_buffer_limit = int(per_author_buffer_limit)
        self.buffer = buffer  # compat

        self.social_focus = social_focus

        # Template de conversa (configs) + conversas por autor
        self.conv_template = conv
        self.conv_by_author: Dict[int, ConversationManager] = {}

        self.state = state
        self.typing = typing

        self.block = block_classifier

        self.base_window = float(base_window)
        self.fragment_window = float(fragment_window)
        self.max_wait_soft = float(max_wait_soft)
        self.max_wait_hard = float(max_wait_hard)
        self.typing_grace = float(typing_grace)

        # batches por autor
        self.pending_buffers: Dict[int, List[str]] = {}
        self.pending_tasks: Dict[int, asyncio.Task] = {}
        self.pending_meta: Dict[int, dict] = {}
        self.batch_first_ts: Dict[int, float] = {}
        self.batch_last_ts: Dict[int, float] = {}
        self.fragment_hold_until: Dict[int, float] = {}

        # memória anti-repetição por autor
        self.self_memory_by_author: Dict[int, List[str]] = {}
        self.self_memory_limit = int(self_memory_limit)

        self.decision = AIDecision()
        self.addressing_force_if_batch_age_lt = float(addressing_force_if_batch_age_lt)

        self.tone_analytic_ratio = float(tone_analytic_ratio)
        self.tone_sarcasm_ratio = float(tone_sarcasm_ratio)

        self.interject = InterjectionPolicy(
            spontaneous_chance=float(spontaneous_chance),
            spontaneous_global_cooldown=float(spontaneous_global_cooldown),
            spontaneous_per_author_cooldown=float(spontaneous_per_author_cooldown),
            secondary_window=float(secondary_window),
            secondary_max_turns=int(secondary_max_turns),
            secondary_per_author_cooldown=float(secondary_per_author_cooldown),
        )

        # memória curtinha do próprio Override no canal (pra não repetir igual)
        self.chanmem = ChannelMemory(max_lines=10)

        # multi conversa / merge por assunto
        self.topic_ttl = float(topic_ttl)
        self.topic_similarity = float(topic_similarity)
        self.topic_min_shared = int(topic_min_shared)
        self.topic_min_kw = int(topic_min_kw)

        self.topic_sessions: Dict[str, TopicSession] = {}
        self.author_topic: Dict[int, str] = {}

        # “deixa” (seguir vibe) — probabilístico, não padrão
        self.vibe_follow_chance = float(vibe_follow_chance)
        self.vibe_follow_cooldown = float(vibe_follow_cooldown)
        self._last_vibe_by_author: Dict[int, float] = {}

        # estado global “quem tá engajado agora” (pra secondary funcionar)
        self.global_active_author: Optional[int] = None
        self.global_state: ConversationState = ConversationState.OBSERVING
        self.global_state_ts: float = 0.0

    # -------- conversas --------

    def _new_conv_like_template(self) -> ConversationManager:
        tpl = self.conv_template
        idle_timeout = int(getattr(tpl, "idle_timeout", 20 * 60))
        soft_exit_timeout = int(getattr(tpl, "soft_exit_timeout", 120))
        max_presence = int(getattr(tpl, "max_presence", 8 * 60))
        recent_end_window = int(getattr(tpl, "recent_end_window", 90))
        return ConversationManager(
            idle_timeout=idle_timeout,
            soft_exit_timeout=soft_exit_timeout,
            max_presence=max_presence,
            recent_end_window=recent_end_window,
        )

    def _get_conv(self, author_id: int) -> ConversationManager:
        a = int(author_id)
        conv = self.conv_by_author.get(a)
        if conv:
            return conv
        conv = self._new_conv_like_template()
        self.conv_by_author[a] = conv
        return conv

    # -------- buffers por autor --------

    def _get_buffer(self, author_id: int) -> MessageBuffer:
        a = int(author_id)
        buf = self.buffers.get(a)
        if not buf:
            buf = MessageBuffer(max_messages=self.per_author_buffer_limit)
            self.buffers[a] = buf
        return buf

    def _get_self_memory(self, author_id: int) -> List[str]:
        a = int(author_id)
        mem = self.self_memory_by_author.get(a)
        if mem is None:
            mem = []
            self.self_memory_by_author[a] = mem
        return mem

    def notify_typing(self, author_id: int, channel_id: int):
        self.typing.notify_typing(author_id, channel_id)

    # -------- vibe (seguir deixa às vezes) --------

    def _should_follow_vibe(self, author_id: int) -> bool:
        a = int(author_id)
        now = time.time()
        last = float(self._last_vibe_by_author.get(a, 0.0) or 0.0)
        if last and (now - last) < self.vibe_follow_cooldown:
            return False
        if random.random() < self.vibe_follow_chance:
            self._last_vibe_by_author[a] = now
            return True
        return False

    # -------- memória do próprio Override (pra não repetir) --------

    def _tone_hint_with_self_memory(self, tone_hint: Optional[str] = None) -> str:
        recent = self.chanmem.recent(limit=4)
        if not recent:
            return (tone_hint or "").strip()

        mem_block = "RECENTE do Override (não repetir igual):\n- " + "\n- ".join(recent)
        if tone_hint:
            return (tone_hint.strip() + "\n\n" + mem_block).strip()
        return mem_block

    # -------- topics (merge por assunto) --------

    def _topic_cleanup(self):
        now = time.time()
        for key in list(self.topic_sessions.keys()):
            sess = self.topic_sessions.get(key)
            if not sess:
                continue
            if (now - float(sess.last_activity)) > self.topic_ttl:
                for a in list(sess.authors):
                    if self.author_topic.get(int(a)) == key:
                        self.author_topic.pop(int(a), None)
                self.topic_sessions.pop(key, None)

    def _topic_assign(self, author_id: int, text: str) -> Optional[str]:
        a = int(author_id)

        # trava extra: evita criar/colar tópico com ruído muito curto
        if len((strip_mentions(text) or "").strip()) < 18:
            return None

        kws = _kw_set(text)
        if len(kws) < self.topic_min_kw:
            return None

        best_key = None
        best_score = 0.0

        for key, sess in self.topic_sessions.items():
            score = _jaccard(kws, sess.keywords)
            shared = len(kws.intersection(sess.keywords))
            if shared < self.topic_min_shared:
                continue
            if score < self.topic_similarity:
                continue
            if score > best_score:
                best_score = score
                best_key = key

        now = time.time()
        if best_key:
            sess = self.topic_sessions[best_key]
            sess.authors.add(a)

            merged = set(list(sess.keywords)[:50])
            merged.update(list(kws)[:50])
            sess.keywords = set(list(merged)[:60])

            sess.last_activity = now
            sess.turns += 1
            self.author_topic[a] = best_key
            return best_key

        key = f"t{int(now)}:{a}:{random.randint(1000,9999)}"
        self.topic_sessions[key] = TopicSession(
            key=key,
            keywords=set(list(kws)[:60]),
            authors={a},
            last_activity=now,
            turns=1,
        )
        self.author_topic[a] = key
        return key

    def _topic_authors_for(self, author_id: int) -> Set[int]:
        a = int(author_id)
        key = self.author_topic.get(a)
        if not key:
            return {a}
        sess = self.topic_sessions.get(key)
        if not sess:
            return {a}
        return set(sess.authors) if sess.authors else {a}

    # -------- addressing --------

    def _needs_addressing(
        self,
        channel: discord.TextChannel,
        *,
        target_message_id: int,
        is_reply_to_bot: bool,
        batch_age: float = 9999.0,
    ) -> bool:
        if is_reply_to_bot:
            return False

        try:
            if float(batch_age) < float(self.addressing_force_if_batch_age_lt):
                return True
        except Exception:
            pass

        try:
            last_id = int(getattr(channel, "last_message_id", 0) or 0)
            tgt = int(target_message_id or 0)
            return bool(last_id and tgt and last_id != tgt)
        except Exception:
            return True

    def _address(
        self,
        channel: discord.TextChannel,
        *,
        response: str,
        author_id: int,
        target_message_id: int,
        is_reply_to_bot: bool,
        batch_age: float = 9999.0,
    ) -> str:
        r = (response or "").strip()
        if not r:
            return r

        if f"<@{author_id}>" in r or f"<@!{author_id}>" in r:
            return r

        if self._needs_addressing(
            channel,
            target_message_id=int(target_message_id or 0),
            is_reply_to_bot=bool(is_reply_to_bot),
            batch_age=float(batch_age),
        ):
            return f"<@{author_id}> {r}"

        return r

    # -------- debug --------

    def _dbg(self, msg: str):
        try:
            log.info(msg)
        except Exception:
            pass
        print(msg)

    def _log_line(
        self,
        *,
        author_id: int,
        direct: bool,
        social_reason: str,
        state_reason: str,
        conv_reason: str,
        decision_action: str,
        decision_reason: str,
        age: float = 0.0,
        waited: float = 0.0,
        frag: bool = False,
        content: str = "",
    ):
        self._dbg(
            f"[AI_CHAT] author={author_id} direct={direct} "
            f"SOCIAL={social_reason} STATE={state_reason} CONV={conv_reason} "
            f"DECISION={decision_action}:{decision_reason} "
            f"age={round(age,2)}s waited={round(waited,2)}s frag={frag} "
            f"content={content[:120]!r}"
        )

    def _schedule(self, author_id: int, delay: float, coro_factory):
        task = self.pending_tasks.get(author_id)
        if task and not task.done():
            task.cancel()
        self.pending_tasks[author_id] = asyncio.create_task(coro_factory(delay))

    def _last_typing_ts(self, author_id: int, channel_id: int) -> float:
        fn = getattr(self.typing, "last_typing_ts", None)
        if callable(fn):
            try:
                v = fn(author_id, channel_id)
                return float(v or 0.0)
            except Exception:
                return 0.0
        return 0.0

    # -------- read intent (seguro / best-effort) --------

    def _safe_build_read_intent(self, message: discord.Message, bot_user) -> Optional[ReadIntent]:
        try:
            return build_read_intent(message, bot_user)
        except Exception:
            return None

    def _resolved_reference_message(self, message: discord.Message) -> Optional[discord.Message]:
        try:
            ref = getattr(message, "reference", None)
            if not ref:
                return None
            resolved = getattr(ref, "resolved", None)
            if isinstance(resolved, discord.Message):
                return resolved
        except Exception:
            return None
        return None

    # ----------------- MAIN -----------------

    async def handle_message(self, message: discord.Message, *, channel_main_id: int):
        if message.author.bot:
            return
        if not isinstance(message.channel, discord.TextChannel):
            return
        if message.channel.id != channel_main_id:
            return

        bot_user = getattr(self.bot, "user", None)
        mentioned = (bot_user in message.mentions) if bot_user else False
        replying = is_replying_to_bot(message, bot_user)
        name_called = (not mentioned and not replying and is_name_called(message))
        direct = bool(mentioned or replying or name_called)

        author_id = int(message.author.id)
        channel_id = int(message.channel.id)
        now = time.time()
        batch_active = author_id in self.pending_buffers

        # ✅ regra prática:
        # - pra começar: precisa direct
        # - se já tem batch: aceita fragmentos sem direct
        if (not direct) and (not batch_active):
            return

        # ---- SocialFocus (só valida quando direct) ----
        social = self.social_focus.signal(message, bot_user) if direct else None
        if direct and social and not social.allowed:
            self._log_line(
                author_id=author_id,
                direct=True,
                social_reason=social.reason,
                state_reason="(skipped)",
                conv_reason="(skipped)",
                decision_action="IGNORE",
                decision_reason="social_block",
                content=message.content,
            )
            return

        social_reason = social.reason if (social and direct) else ("batch_continue" if batch_active else "direct_allow")

        # ---- Policy / cooldown (IMPORTANTE) ----
        st = self.state.evaluate(message, bot_user) if direct else None
        state_reason = st.reason if st else "batch_continue"

        # ✅ Override só lê/responde se fora cooldown
        if direct and st and not bool(getattr(st, "should_respond", True)):
            self._log_line(
                author_id=author_id,
                direct=True,
                social_reason=social_reason,
                state_reason=state_reason,
                conv_reason="(skipped)",
                decision_action="IGNORE",
                decision_reason="cooldown_or_policy",
                content=message.content,
            )
            return

        # ---- Read intent (só se fora cooldown) ----
        read_intent = self._safe_build_read_intent(message, bot_user) if direct else None
        wants_read = bool(
            getattr(read_intent, "wants_read", False)
            or getattr(read_intent, "allow", False)
            or getattr(read_intent, "enabled", False)
            or getattr(read_intent, "hit", False)
        )

        # fallback: se a frase contém “lê” e “isso” (usando normalização leve)
        if direct and not wants_read:
            txt0 = pre_normalize_light(message.content)
            if ("override" in txt0) and ("lê" in txt0 or "le" in txt0) and ("isso" in txt0 or "isto" in txt0):
                wants_read = True

        try:
            read_inline_text = getattr(read_intent, "target_text", None)
        except Exception:
            read_inline_text = None

        # ---- ConversationManager (POR AUTOR) ----
        conv = self._get_conv(author_id)

        # snapshot global pra secondary
        active_before = self.global_active_author
        engaged_before = self.global_state in (ConversationState.ENGAGED, ConversationState.EXITING_SOFT)

        if direct:
            if wants_read:
                # leitura NÃO deve engajar conversa nem mexer no global_state
                conv_event = None
                conv_ok = True
                conv_reason = "read_intent"
            else:
                conv_event = conv.analyze_message(
                    author_id=author_id,
                    content=message.content,
                    mentioned=bool(mentioned or name_called),
                    replying_to_bot=replying,
                )
                conv_ok = bool(getattr(conv_event, "should_consider", False))
                conv_reason = getattr(conv_event, "reason", "unknown")

                st_now = getattr(conv_event, "state", getattr(conv, "state", ConversationState.OBSERVING))
                self.global_state = st_now
                self.global_state_ts = time.time()
                if st_now in (ConversationState.ENGAGED, ConversationState.EXITING_SOFT):
                    self.global_active_author = author_id
                elif self.global_active_author == author_id:
                    if (time.time() - self.global_state_ts) > 20.0:
                        self.global_active_author = None
        else:
            conv_event = None
            conv_ok = True
            conv_reason = "batch_fragment_non_direct"

        if not conv_ok and batch_active:
            conv_ok = True
            conv_reason = f"{conv_reason}|override_batch"

        if not conv_ok:
            self._log_line(
                author_id=author_id,
                direct=bool(direct),
                social_reason=social_reason,
                state_reason=state_reason,
                conv_reason=conv_reason,
                decision_action="IGNORE",
                decision_reason="conversation_block",
                content=message.content,
            )
            return

        # limpa memória por autor quando conversa termina
        if direct and conv_event and (
            getattr(conv_event, "should_exit", False)
            or getattr(conv_event, "reason", "") == "soft_exit_finished"
        ):
            try:
                self.buffers.pop(author_id, None)
                self.self_memory_by_author.pop(author_id, None)
            except Exception:
                pass

        # ---- batch start / last ----
        if author_id not in self.batch_first_ts:
            self.batch_first_ts[author_id] = now
        self.batch_last_ts[author_id] = now

        self.pending_buffers.setdefault(author_id, []).append(message.content)

        meta = self.pending_meta.get(author_id, {})
        meta["direct_seen"] = bool(meta.get("direct_seen", False) or direct)
        meta["social_reason"] = social_reason
        meta["state_reason"] = state_reason
        meta["conv_reason"] = conv_reason
        meta["channel_id"] = channel_id
        meta["author_name"] = message.author.display_name
        meta["last_message_id"] = int(getattr(message, "id", 0) or 0)
        meta["is_reply_to_bot"] = bool(meta.get("is_reply_to_bot", False) or replying)
        meta["conv_active_before"] = int(active_before) if active_before is not None else None
        meta["conv_engaged_before"] = bool(engaged_before)
        meta["wait_loops"] = int(meta.get("wait_loops", 0) or 0)
        meta["wants_read"] = bool(meta.get("wants_read", False) or wants_read)
        meta["read_inline_text"] = (read_inline_text or None)
        self.pending_meta[author_id] = meta

        # fragment hold
        clean_piece = strip_mentions(message.content)
        is_frag_piece = looks_like_fragment_clean(clean_piece)
        if is_frag_piece:
            hold_until = now + self.fragment_window
            prev = self.fragment_hold_until.get(author_id, 0.0)
            if hold_until > prev:
                self.fragment_hold_until[author_id] = hold_until

        # janela base
        window = self.base_window
        if is_frag_piece:
            window = max(window, self.fragment_window)

        # se usuário tá digitando, segura até parar (via grace)
        last_t = self._last_typing_ts(author_id, channel_id)
        if last_t and (time.time() - last_t) <= self.typing_grace:
            window = max(window, self.typing_grace)

        elapsed = now - self.batch_first_ts[author_id]
        if elapsed >= self.max_wait_soft:
            window = 0.8

        async def delayed(delay: float):
            start_sleep = time.time()
            await asyncio.sleep(delay)

            # espera silêncio real: mensagem + typing + hold fragmento
            while True:
                now2 = time.time()
                batch_age = now2 - self.batch_first_ts.get(author_id, now2)
                hard_hit = batch_age >= self.max_wait_hard

                last_msg_ts = self.batch_last_ts.get(author_id, now2)
                last_typing_ts = self._last_typing_ts(author_id, channel_id)
                last_activity = max(last_msg_ts, last_typing_ts or 0.0)
                quiet_for = now2 - last_activity

                if quiet_for < self.base_window and not hard_hit:
                    await asyncio.sleep(0.6)
                    continue

                if last_typing_ts and (now2 - last_typing_ts) <= self.typing_grace and not hard_hit:
                    await asyncio.sleep(0.6)
                    continue

                hold_until2 = self.fragment_hold_until.get(author_id, 0.0)
                if (now2 < hold_until2) and not hard_hit:
                    await asyncio.sleep(0.6)
                    continue

                break

            if author_id not in self.pending_buffers:
                return

            msgs = self.pending_buffers.get(author_id, [])
            meta2 = self.pending_meta.get(author_id, {})
            now3 = time.time()
            batch_age = now3 - self.batch_first_ts.get(author_id, now3)
            hard_hit = batch_age >= self.max_wait_hard

            raw_full = " ".join([m for m in msgs if m and m.strip()]).strip()
            clean_full = strip_mentions(raw_full)
            frag_batch = looks_like_fragment_clean(clean_full)

            # tentativa de atribuir/atualizar tópico pelo texto final do batch
            self._topic_cleanup()
            self._topic_assign(author_id, clean_full)

            if is_greeting_clean(clean_full):
                frag_batch = False
                decision = Decision("RESPOND", "greeting")
            else:
                decision = self.decision.decide(
                    content=raw_full,
                    direct=bool(meta2.get("direct_seen", False)),
                    policy_should_respond=True,
                    social_allowed=True,
                    conv_allowed=True,
                    max_wait_hit=hard_hit,
                )

                if self.block is not None and decision.action == "IGNORE" and decision.reason == "not_complete":
                    try:
                        batch = BlockBatch(text_clean=clean_full, direct=bool(meta2.get("direct_seen", False)))
                        bd = await self.block.classify(batch)
                        if bd.outcome == "ENGAGED":
                            decision = Decision("RESPOND", f"block:{bd.reason}")
                        elif bd.outcome == "DEAD":
                            decision = Decision("IGNORE", f"dead:{bd.reason}")
                        else:
                            decision = Decision("IGNORE", f"block_ignore:{bd.reason}")
                    except Exception:
                        pass

            # anti-loop WAIT
            if decision.action == "WAIT":
                loops = int(meta2.get("wait_loops", 0) or 0) + 1
                meta2["wait_loops"] = loops
                self.pending_meta[author_id] = meta2

                if (loops >= 6) or (batch_age >= (self.max_wait_soft + 2.0)):
                    decision = Decision("RESPOND", "wait_cutoff")
                else:
                    self._log_line(
                        author_id=author_id,
                        direct=bool(meta2.get("direct_seen", False)),
                        social_reason=str(meta2.get("social_reason", "unknown")),
                        state_reason=str(meta2.get("state_reason", "unknown")),
                        conv_reason=str(meta2.get("conv_reason", "unknown")),
                        decision_action="WAIT",
                        decision_reason=decision.reason,
                        age=batch_age,
                        waited=(time.time() - start_sleep),
                        frag=frag_batch,
                        content=clean_full if clean_full else raw_full,
                    )
                    if not hard_hit:
                        self._schedule(author_id, 0.8, delayed)
                    return

            self._log_line(
                author_id=author_id,
                direct=bool(meta2.get("direct_seen", False)),
                social_reason=str(meta2.get("social_reason", "unknown")),
                state_reason=str(meta2.get("state_reason", "unknown")),
                conv_reason=str(meta2.get("conv_reason", "unknown")),
                decision_action=decision.action,
                decision_reason=decision.reason,
                age=batch_age,
                waited=(time.time() - start_sleep),
                frag=frag_batch,
                content=clean_full if clean_full else raw_full,
            )

            # limpa batch
            self.pending_buffers.pop(author_id, None)
            self.pending_meta.pop(author_id, None)
            self.pending_tasks.pop(author_id, None)
            self.batch_first_ts.pop(author_id, None)
            self.batch_last_ts.pop(author_id, None)
            self.fragment_hold_until.pop(author_id, None)

            if decision.action != "RESPOND":
                return

            # fallbacks curtos
            if decision.reason in ("fragment_timeout", "wait_cutoff"):
                cf = (clean_full or "").strip()
                if is_greeting_clean(cf):
                    fallback = random.choice(["e aí", "fala", "salve"])
                else:
                    fallback = random.choice(["continua", "tá, e aí?", "fala direito"])

                is_reply_to_bot2 = bool(meta2.get("is_reply_to_bot", False))
                tgt2 = int(meta2.get("last_message_id", 0) or 0)
                txt2 = self._address(
                    message.channel,
                    response=fallback,
                    author_id=author_id,
                    target_message_id=tgt2,
                    is_reply_to_bot=is_reply_to_bot2,
                    batch_age=float(batch_age),
                )
                await message.channel.send(txt2)

                mem = self._get_self_memory(author_id)
                mem.append(fallback)
                self.self_memory_by_author[author_id] = mem[-self.self_memory_limit:]
                try:
                    self.chanmem.add(time.time(), fallback)
                except Exception:
                    pass
                return

            # ----------------- READ MODE (best-effort, NÃO SEQUESTRA CONVERSA) -----------------
            if bool(meta2.get("wants_read", False)):
                inline_txt = (meta2.get("read_inline_text") or "").strip()
                if inline_txt:
                    buf_r = self._get_buffer(author_id)
                    buf_r.add_user_message(
                        author_id=author_id,
                        author_name=str(meta2.get("author_name", "user")),
                        content=f"(Pedido de leitura) Texto: {sanitize(strip_mentions(inline_txt))}",
                    )

                    tone_hint = self._tone_hint_with_self_memory(
                        "Você vai ler o texto enviado e responder sobre ele. Curto, direto. "
                        "Se for zoeira, responde seco. Se for sério, responde sério."
                    )

                    await self._reply(
                        message.channel,
                        author_id=author_id,
                        target_message_id=int(meta2.get("last_message_id", 0) or 0),
                        is_reply_to_bot=bool(meta2.get("is_reply_to_bot", False)),
                        batch_age=float(batch_age),
                        tone_hint=tone_hint,
                        topic_authors=None,
                    )
                    return

                refmsg = self._resolved_reference_message(message)
                if refmsg and isinstance(refmsg, discord.Message):
                    ref_txt = sanitize(strip_mentions(getattr(refmsg, "content", "") or ""))
                    ref_author = getattr(getattr(refmsg, "author", None), "display_name", "alguém")

                    buf_r = self._get_buffer(author_id)
                    buf_r.add_user_message(
                        author_id=author_id,
                        author_name=str(meta2.get("author_name", "user")),
                        content=f"(Pedido de leitura) {ref_author}: {ref_txt}",
                    )

                    tone_hint = self._tone_hint_with_self_memory(
                        "Você vai ler a mensagem citada e responder sobre ela. Curto, direto. "
                        "Se for fofoca/zoeira, pode responder seco. Se for sério, responde sério."
                    )

                    await self._reply(
                        message.channel,
                        author_id=author_id,
                        target_message_id=int(meta2.get("last_message_id", 0) or 0),
                        is_reply_to_bot=bool(meta2.get("is_reply_to_bot", False)),
                        batch_age=float(batch_age),
                        tone_hint=tone_hint,
                        topic_authors=None,
                    )
                    return

                try:
                    await message.channel.send("Faz reply na mensagem que você quer que eu leia.")
                except Exception:
                    pass
                return

            # decide secondary/spontaneous/primary
            d2 = self.interject.decide(
                author_id=author_id,
                text=clean_full,
                now=now3,
                direct=True,
                conversation_engaged=bool(meta2.get("conv_engaged_before", False)),
                active_author=meta2.get("conv_active_before", None),
            )

            if d2.allow and d2.mode in ("secondary", "spontaneous"):
                await self._send_interjection(
                    message.channel,
                    author_id=author_id,
                    author_name=str(meta2.get("author_name", "user")),
                    content=clean_full,
                    target_message_id=int(meta2.get("last_message_id", 0) or 0),
                    mode=d2.mode,
                    is_reply_to_bot=bool(meta2.get("is_reply_to_bot", False)),
                    batch_age=float(batch_age),
                )
                try:
                    self.interject.mark_used(author_id, mode=d2.mode)
                except Exception:
                    pass
                return

            # ----------------- primary normal (com merge de assunto) -----------------

            buf = self._get_buffer(author_id)
            buf.add_user_message(
                author_id=author_id,
                author_name=str(meta2.get("author_name", "user")),
                content=clean_full if clean_full else raw_full,
            )

            soft_exit_hint = None
            try:
                st_now2 = getattr(self._get_conv(author_id), "state", None)
                if st_now2 == ConversationState.EXITING_SOFT:
                    soft_exit_hint = (
                        "Se for encerrar, encerra normal: 1 frase curta com desculpa leve "
                        "(trampo/afazeres/tenho que ir). Sem ficar fofo e sem parecer IA."
                    )
            except Exception:
                soft_exit_hint = None

            vibe_hint = None
            if self._should_follow_vibe(author_id):
                vibe_hint = (
                    "Se o usuário puxou zoeira/sarcasmo/analítico, você pode acompanhar um pouco. "
                    "Mas NÃO vire padrão: 1 resposta no máximo nessa vibe e volta ao normal depois."
                )

            tone_hint = self._tone_hint_with_self_memory(
                "\n".join([x for x in [soft_exit_hint, vibe_hint] if x])
            )

            topic_authors = self._topic_authors_for(author_id)
            if len(topic_authors) <= 1:
                topic_authors = None

            await self._reply(
                message.channel,
                author_id=author_id,
                target_message_id=int(meta2.get("last_message_id", 0) or 0),
                is_reply_to_bot=bool(meta2.get("is_reply_to_bot", False)),
                batch_age=float(batch_age),
                tone_hint=tone_hint,
                topic_authors=topic_authors,
            )

        self._schedule(author_id, window, delayed)

    # ----------------- interjection -----------------

    async def _send_interjection(
        self,
        channel: discord.TextChannel,
        *,
        author_id: int,
        author_name: str,
        content: str,
        target_message_id: int,
        mode: str,
        is_reply_to_bot: bool,
        batch_age: float,
    ):
        txt = (strip_mentions(content) or "").strip()
        if not txt:
            return

        prompt = (
            "Você é Override, um bot no Discord.\n"
            "Fale como alguém humano: direto, relaxado, levemente preguiçoso.\n"
            "Apareça raro e solte comentários secos.\n"
            f"Quando tiver brecha: {int(self.tone_analytic_ratio*100)}% analítico seco e {int(self.tone_sarcasm_ratio*100)}% sarcasmo leve.\n"
            "Se não tiver brecha, fica neutro/curto.\n"
            "Não force humor. Sem humilhação pesada, sem ataque pessoal.\n"
        )

        recent = self.chanmem.recent(limit=3)
        if recent:
            prompt += "\nRECENTE do Override (não repetir igual):\n- " + "\n- ".join(recent) + "\n"

        if mode == "spontaneous":
            prompt += (
                "Intervenção natural no chat.\n"
                "Pode ser um pouco maior se a mensagem do usuário for grande,\n"
                "mas não faça monólogo e não faça 3+ perguntas.\n"
            )
            max_tokens = 140
            temp = 0.95
        else:
            prompt += (
                "Conversa fraca com usuário secundário.\n"
                "1-2 frases curtas, no máximo 1 pergunta curta.\n"
                "Não roube o foco do chat.\n"
            )
            max_tokens = 95
            temp = 0.75

        prompt += f"MENSAGEM de {author_name!r}: {txt!r}\n"
        prompt += "Resposta do Override:"

        try:
            out = await self.engine.generate_raw_text(
                prompt,
                max_output_tokens=max_tokens,
                temperature=temp,
            )
        except Exception:
            return

        resp = postprocess_override_output(out, limit=400)
        if not resp:
            return

        norm = normalize(resp)
        mem = self._get_self_memory(author_id)
        if any(normalize(r) == norm for r in mem):
            resp = random.choice(["tá", "saquei", "hm"])

        mem.append(resp)
        self.self_memory_by_author[author_id] = mem[-self.self_memory_limit:]

        try:
            self.state.last_interaction[int(author_id)] = time.time()
        except Exception:
            pass

        msg = self._address(
            channel,
            response=resp,
            author_id=author_id,
            target_message_id=int(target_message_id or 0),
            is_reply_to_bot=bool(is_reply_to_bot),
            batch_age=float(batch_age),
        )
        await channel.send(msg)

        try:
            self.chanmem.add(time.time(), resp)
        except Exception:
            pass

    # ----------------- reply (com merge opcional por assunto) -----------------

    async def _reply(
        self,
        channel: discord.TextChannel,
        *,
        author_id: int,
        target_message_id: int,
        is_reply_to_bot: bool,
        batch_age: float,
        tone_hint: Optional[str] = None,
        topic_authors: Optional[Set[int]] = None,
    ):
        a = int(author_id)

        entries = []

        if topic_authors and len(topic_authors) > 1:
            ta = set(int(x) for x in topic_authors)
            ta.add(a)

            for uid in list(ta)[:4]:
                buf_u = self._get_buffer(uid)
                for m in buf_u.get_messages():
                    if m.get("role") == "user":
                        entries.append({"author_display": m.get("author_name", "user"), "content": m["content"]})

            if len(entries) > 18:
                entries = entries[-18:]
        else:
            buf = self._get_buffer(a)
            entries = [
                {"author_display": m.get("author_name", "user"), "content": m["content"]}
                for m in buf.get_messages()
                if m.get("role") == "user"
            ]

        if not entries:
            return

        try:
            response = await self.engine.generate_response(entries, tone_hint=tone_hint)
        except TypeError:
            response = await self.engine.generate_response(entries)

        response = postprocess_override_output(response, limit=400)
        norm = normalize(response)

        mem = self._get_self_memory(a)
        if any(normalize(r) == norm for r in mem):
            response = random.choice(["entendi", "tá", "saquei"])

        mem.append(response)
        self.self_memory_by_author[a] = mem[-self.self_memory_limit:]

        msg = self._address(
            channel,
            response=response,
            author_id=a,
            target_message_id=int(target_message_id or 0),
            is_reply_to_bot=bool(is_reply_to_bot),
            batch_age=float(batch_age),
        )
        await channel.send(msg)

        try:
            self._get_buffer(a).add_assistant_message(response)
        except Exception:
            pass

        try:
            self.chanmem.add(time.time(), response)
        except Exception:
            pass