# ai_decision.py
from typing import List, Dict, Optional

class AIDecision:
    def __init__(self):
        pass

    def should_respond(
        self,
        entries: List[Dict],
        state
    ) -> bool:
        """
        Decide se a IA deve responder ou não.
        """
        if not entries:
            return False

        # regra base: o ai_state já validou
        if not state.should_respond:
            return False

        return True

    def force_short_reply(self, entries: List[Dict]) -> bool:
        """
        Decide se a resposta deve ser curta.
        """
        if len(entries) >= 4:
            return True

        last = entries[-1]["content"].strip().lower()
        if len(last) <= 2:
            return True

        return False

    def should_end_conversation(self, entries: List[Dict]) -> bool:
        """
        Decide se a conversa deve morrer aqui.
        """
        last = entries[-1]["content"].strip().lower()
        if last in ["ok", "blz", "hm", "a", "osh"]:
            return True

        return False
