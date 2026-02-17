# cogs/ai_chat/ai_decision.py

import random
import re
from dataclasses import dataclass


@dataclass
class Decision:
    action: str  # "RESPOND" | "IGNORE" | "WAIT"
    reason: str


_MENTION_RE = re.compile(r"<@!?\d+>|<@&\d+>|<#\d+>")
_SPECIAL_MENTIONS = {"@everyone", "@here"}


def strip_mentions(text: str) -> str:
    if not text:
        return ""
    t = _MENTION_RE.sub("", text)
    for m in _SPECIAL_MENTIONS:
        t = t.replace(m, "")
    return " ".join(t.strip().split())


class AIDecision:
    def __init__(self, random_silence_chance: float = 0.10):
        self.random_silence_chance = float(random_silence_chance)

        self.noise_only = {"kk", "kkk", "kkkk", "lol", "😂", "🤣", "k", "hm", "hmm", "hmmm"}
        self.closure_words = {
            "blz", "beleza", "ok", "okay", "entendi", "tá", "ta", "certo",
            "valeu", "vlw", "show", "fechou", "isso", "sim", "não", "nao"
        }

        # ✅ saudações que NÃO são fragmento
        self.greetings = {
            "oi", "opa", "eae", "eai", "eaí", "e aí", "salve", "fala",
            "bom dia", "boa tarde", "boa noite", "yo", "iae", "iai"
        }

    def _norm(self, s: str) -> str:
        return " ".join((s or "").lower().strip().split())

    def _is_greeting(self, content: str) -> bool:
        c = self._norm(content)
        if not c:
            return False
        # match direto ou começa com saudação (ex: "eae mano", "boa noite chefe")
        if c in self.greetings:
            return True
        for g in self.greetings:
            if c.startswith(g + " "):
                return True
        return False

    def _looks_complete(self, content: str) -> bool:
        c = self._norm(content)
        if not c:
            return False

        # ✅ saudação curta é completa
        if self._is_greeting(c):
            return True

        if "?" in c:
            return True
        if c.endswith((".", "!", "…")):
            return True
        if len(c) >= 18:
            return True
        if c in self.closure_words:
            return True
        return False

    def _looks_fragment(self, content: str) -> bool:
        c = (content or "").strip()
        if not c:
            return False
        # ✅ saudação não vira fragmento
        if self._is_greeting(c):
            return False
        if "?" in c:
            return False
        if c.endswith((".", "!", "…")):
            return False
        return len(c) <= 10

    def decide(
        self,
        *,
        content: str,
        direct: bool,
        policy_should_respond: bool,
        social_allowed: bool,
        conv_allowed: bool,
        max_wait_hit: bool,
    ) -> Decision:
        if not content or not content.strip():
            return Decision("IGNORE", "empty")

        if not social_allowed:
            return Decision("IGNORE", "social_block")

        if not conv_allowed:
            return Decision("IGNORE", "conversation_block")

        clean = strip_mentions(content)
        norm = self._norm(clean)

        if norm in self.noise_only:
            return Decision("IGNORE", "noise")

        # ✅ se for saudação direta, responde (não pede "completa aí")
        if direct and self._is_greeting(clean):
            return Decision("RESPOND", "direct_greeting")

        if not policy_should_respond:
            if direct and self._looks_complete(clean):
                return Decision("RESPOND", "direct_override_policy_soft")
            return Decision("IGNORE", "policy_block")

        # Fragmento: WAIT antes do timeout; RESPOND no timeout
        if self._looks_fragment(clean):
            if max_wait_hit:
                return Decision("RESPOND", "fragment_timeout")
            return Decision("WAIT", "fragment_wait")

        if not self._looks_complete(clean):
            return Decision("IGNORE", "not_complete")

        if (not direct) and random.random() < self.random_silence_chance:
            return Decision("IGNORE", "random_silence")

        return Decision("RESPOND", "allowed")