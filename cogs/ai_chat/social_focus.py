# cogs/ai_chat/social_focus.py
import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class SocialSignal:
    allowed: bool
    confidence: float
    reason: str
    focus_author_id: Optional[int]


class SocialFocus:
    """Sensor social simplificado (direct-only).

    Regra do projeto:
      - o bot só reage quando é chamado:
        menção, reply ao bot, ou citar "Override" no texto.

    Sem foco entre autores aqui — isso foi removido de propósito.
    """

    # aceita kwargs extras por compatibilidade (ex: timeout=120)
    def __init__(self, name_pattern: str = r"\boverride\b", **_ignored):
        self._name_re = re.compile(name_pattern, flags=re.IGNORECASE)

    def reset(self):
        return

    def signal(self, message, bot_user) -> SocialSignal:
        author_id = message.author.id

        mentioned = False
        replied = False
        name_called = False

        # menção
        if bot_user:
            try:
                mentioned = bot_user in getattr(message, "mentions", [])
            except Exception:
                mentioned = False

        # reply ao bot
        try:
            ref = getattr(message, "reference", None)
            resolved = getattr(ref, "resolved", None) if ref else None
            if resolved is not None:
                replied = bool(resolved.author and resolved.author.id == bot_user.id) if bot_user else False
        except Exception:
            replied = False

        # nome no texto
        try:
            content = (getattr(message, "content", "") or "")
            name_called = bool(content and self._name_re.search(content))
        except Exception:
            name_called = False

        direct = bool(mentioned or replied or name_called)
        if direct:
            return SocialSignal(True, 0.95, "direct_allow", author_id)

        return SocialSignal(False, 0.05, "not_direct", None)