# ai_decision.py
import random
from typing import List, Dict, Optional
from dataclasses import dataclass

@dataclass
class DecisionResult:
    should_respond: bool
    reason: str = ""


class AIDecision:
    def __init__(self, random_silence_chance: float = 0.12):
        self.random_silence_chance = random_silence_chance
        
        def should_respond(
            self,
            entries: List[Dict],
            state,
            content: str | None = None
        ) -> DecisionResult:
            """
            Decide se a IA deve responder ou não.
            """
            if not entries:
                return DecisionResult(
                    should_respond=False,
                    reason="no_entries"
                )
                
                if not state.should_respond:
                    return DecisionResult(
                        should_respond=False,
                        reason="state_blocked"
                    )
                    
                    if random.random() < self.random_silence_chance:
                        return DecisionResult(
                            should_respond=False,
                            reason="random_silence"
                        )
                        
    # nova decisão: pedido de baixo esforço
        if content:
            lowered = content.lower()
            for pattern in (
                "faz pra mim", "pode fazer", "me ajuda",
                "cria um", "monta um", "faz ai"
            ):
                if pattern in lowered:
                    return DecisionResult(
                        should_respond=False,
                        reason="auto_refuse"
                    )
                    
                    return DecisionResult(
                        should_respond=True,
                        reason="allowed"
                    )

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
