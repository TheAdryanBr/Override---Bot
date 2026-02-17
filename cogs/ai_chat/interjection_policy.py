# cogs/ai_chat/interjection_policy.py
import random
import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class InterjectionDecision:
    allow: bool
    reason: str
    mode: str  # "none" | "secondary" | "spontaneous"


class InterjectionPolicy:
    """Política de interações fora do fluxo principal.

    IMPORTANTE:
    - Tudo aqui ainda exige direct (menção/reply/nome) PARA INICIAR.
    - secondary: se existe conversa engajada com outro autor, responde curto sem roubar foco.
    - spontaneous: quando chamado, pode preferir resposta curta (analítico/sarcasmo) com chance/cooldown.
    """

    def __init__(
        self,
        *,
        spontaneous_chance: float = 0.35,
        spontaneous_global_cooldown: float = 18.0,
        spontaneous_per_author_cooldown: float = 25.0,
        secondary_window: float = 35.0,
        secondary_max_turns: int = 2,
        secondary_per_author_cooldown: float = 45.0,
    ):
        self.spontaneous_chance = float(spontaneous_chance)
        self.spontaneous_global_cooldown = float(spontaneous_global_cooldown)
        self.spontaneous_per_author_cooldown = float(spontaneous_per_author_cooldown)

        self.secondary_window = float(secondary_window)
        self.secondary_max_turns = int(secondary_max_turns)
        self.secondary_per_author_cooldown = float(secondary_per_author_cooldown)

        self._secondary = {}  # author_id -> {until: ts, turns: int}
        self._last_secondary_by_author = {}  # author_id -> ts

        self._last_spontaneous_ts = 0.0
        self._last_spontaneous_by_author = {}  # author_id -> ts

    def _now(self) -> float:
        return time.time()

    def _is_noise(self, text: str) -> bool:
        t = " ".join((text or "").strip().lower().split())
        if not t:
            return True

        # ruído puro
        if t in {"kk", "kkk", "kkkk", "kkkkk", "kkkkkk", "lol", "hm", "hmm", "hmmm", "?", "??", "...", "…"}:
            return True

        # fragmentos super comuns que não valem interjeição
        if t in {"só", "so", "de", "boa", "tipo", "mano"}:
            return True

        return False

    def mark_used(self, author_id: int, *, mode: str):
        a = int(author_id)
        now = self._now()

        if mode == "secondary":
            self._last_secondary_by_author[a] = now
            st = self._secondary.get(a)
            if st:
                st["turns"] = int(st.get("turns", 0) or 0) + 1

        if mode == "spontaneous":
            self._last_spontaneous_ts = now
            self._last_spontaneous_by_author[a] = now

    def decide(
        self,
        *,
        author_id: int,
        text: str,
        now: float,
        direct: bool,
        conversation_engaged: bool,
        active_author: Optional[int],
    ) -> InterjectionDecision:
        a = int(author_id)
        t = float(now or self._now())

        if not direct:
            return InterjectionDecision(False, "not_direct", "none")

        if self._is_noise(text):
            return InterjectionDecision(False, "noise", "none")

        # --- secondary (prioridade) ---
        if conversation_engaged and active_author is not None and int(active_author) != a:
            last = float(self._last_secondary_by_author.get(a, 0.0) or 0.0)
            if last and (t - last) < self.secondary_per_author_cooldown:
                return InterjectionDecision(False, "secondary_cooldown", "none")

            st = self._secondary.get(a)
            if st and t > float(st.get("until", 0.0) or 0.0):
                self._secondary.pop(a, None)
                st = None

            if not st:
                self._secondary[a] = {"until": float(t + self.secondary_window), "turns": 0}
                return InterjectionDecision(True, "secondary_start", "secondary")

            turns = int(st.get("turns", 0) or 0)
            if turns >= self.secondary_max_turns:
                return InterjectionDecision(False, "secondary_turn_limit", "none")

            return InterjectionDecision(True, "secondary_continue", "secondary")

        # --- spontaneous (se não for secondary) ---
        if self._last_spontaneous_ts and (t - self._last_spontaneous_ts) < self.spontaneous_global_cooldown:
            return InterjectionDecision(False, "spont_global_cooldown", "none")

        last_a = float(self._last_spontaneous_by_author.get(a, 0.0) or 0.0)
        if last_a and (t - last_a) < self.spontaneous_per_author_cooldown:
            return InterjectionDecision(False, "spont_author_cooldown", "none")

        if random.random() < self.spontaneous_chance:
            return InterjectionDecision(True, "spontaneous", "spontaneous")

        return InterjectionDecision(False, "spont_no_roll", "none")