# cogs/ai_chat/block_classifier.py

from dataclasses import dataclass
from typing import Literal, Optional

from .ai_engine import AIEngine
from .conversation_blocks import BlockBatch


Outcome = Literal["IGNORE", "ENGAGED", "DEAD"]
Tone = Literal["NEUTRAL", "ANALYTIC", "SARCASM"]


@dataclass
class BlockDecision:
    outcome: Outcome
    reason: str
    tone: Tone = "NEUTRAL"


class BlockClassifier:
    """
    Classifica um lote de blocos em:
    - IGNORE: não era para o bot
    - ENGAGED: continuar / responder
    - DEAD: encerrar / não responder e marcar fim
    """

    def __init__(self, engine: AIEngine):
        self.engine = engine

    def _parse(self, out: str) -> BlockDecision:
        raw = (out or "").strip().upper()
        if not raw:
            return BlockDecision("ENGAGED", "llm_empty", "NEUTRAL")

        parts = raw.split()
        # Aceita formatos:
        #  - IGNORE
        #  - ENGAGED
        #  - DEAD
        #  - ENGAGED ANALYTIC
        #  - IGNORE SARCASM
        outcome = None
        tone = None
        for p in parts[:3]:
            if p in ("IGNORE", "ENGAGED", "DEAD") and outcome is None:
                outcome = p
            if p in ("NEUTRAL", "ANALYTIC", "SARCASM") and tone is None:
                tone = p

        if outcome is None:
            # fallback seguro
            outcome = "ENGAGED"
        if tone is None:
            tone = "NEUTRAL"
        return BlockDecision(outcome, "llm", tone)  # type: ignore

    async def classify(self, batch: BlockBatch) -> BlockDecision:
        text = batch.text_clean
        direct = batch.direct

        # Hard guard: vazio
        if not text:
            return BlockDecision("IGNORE", "empty")

        # Hard guard: se não é direct e é muito curto → ignora
        if (not direct) and len(text) < 6:
            return BlockDecision("IGNORE", "short_non_direct")

        # IA: prompt curtíssimo
        prompt = (
            "Você é um classificador de conversa de um bot do Discord.\n"
            "Responda APENAS com 1 ou 2 palavras.\n"
            "Primeira palavra: IGNORE, ENGAGED ou DEAD.\n"
            "Segunda palavra (opcional): NEUTRAL, ANALYTIC ou SARCASM.\n"
            "IGNORE = não é para o bot / ruído.\n"
            "ENGAGED = é para o bot e deve responder.\n"
            "DEAD = encerra a conversa, não responder.\n"
            "NEUTRAL = normal. ANALYTIC = mais analítico. SARCASM = sarcasmo leve quando houver abertura.\n"
            "Considere que mensagens podem vir quebradas em partes.\n"
            f"FOI CHAMADO DIRETO (menção/reply): {direct}\n"
            f"MENSAGEM (já junta): {text!r}\n"
        )

        # A engine atual gera texto livre. Aqui queremos 1 token/linha.
        out = await self.engine.generate_raw_text(prompt, max_output_tokens=6, temperature=0.0)
        return self._parse(out)