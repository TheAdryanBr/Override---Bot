# ai_decision.py
import random
from typing import List, Dict
from dataclasses import dataclass


@dataclass
class DecisionResult:
    should_respond: bool
    reason: str = ""


class AIDecision:
    def __init__(self, random_silence_chance: float = 0.12):
        self.random_silence_chance = random_silence_chance

        self.closure_words = {
            "ok", "blz", "hm", "osh", "entendi", "ta", "tá"
        }

        self.noise_words = {
            "kk", "kkk", "kkkk", "lol", "rs", "rsrs"
        }

        self.continuation_endings = (
            "e", "mas", "pq", "porque", "tipo", "então", "ai"
        )

    def _noise_has_context(self, entries: List[Dict]) -> bool:
        """
        Ruído só conta se houver contexto recente envolvendo o bot.
        """
        if not entries:
            return False

        # olha só as últimas 3 mensagens
        recent = entries[-3:]

        for msg in recent:
            content = msg["content"].lower()

            # alguém falou do bot
            if "override" in content:
                return True

        # se o bot falou recentemente
        if any(m.get("role") == "assistant" for m in recent):
            return True

        return False

    def _looks_like_closure(
        self,
        text: str,
        mentioned: bool,
        entries: List[Dict]
    ) -> bool:
        t = text.strip().lower()

        if not t:
            return False

        # menção direta sempre libera
        if mentioned:
            return True

        # pergunta direta
        if t.endswith("?"):
            return True

        # palavras de fechamento
        if t in self.closure_words:
            return True

        # ruído só se tiver contexto
        if t in self.noise_words:
            return self._noise_has_context(entries)

        # frase com ponto final seco
        if t.endswith("."):
            return True

        # bloqueia se parece continuação
        for end in self.continuation_endings:
            if t.endswith(" " + end) or t == end:
                return False

        return False

    def should_respond(
        self,
        entries: List[Dict],
        state,
        content: str,
        mentioned: bool
    ) -> DecisionResult:
        if not entries:
            return DecisionResult(False, "no_entries")

        if not state.should_respond:
            return DecisionResult(False, "state_blocked")

        if not self._looks_like_closure(content, mentioned, entries):
            return DecisionResult(False, "no_closure")

        if random.random() < self.random_silence_chance:
            return DecisionResult(False, "random_silence")

        return DecisionResult(True, "allowed")