import asyncio
import os
from typing import List, Dict, Optional

from openai import OpenAI
from .ai_prompt import build_prompt


OPENAI_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None


class AIEngine:
    def __init__(
        self,
        primary_models: List[str],
        fallback_models: Optional[List[str]] = None,
        max_output_tokens: int = 220,
        temperature: float = 0.55,
    ):
        self.primary_models = primary_models
        self.fallback_models = fallback_models or []
        self.max_output_tokens = max_output_tokens
        self.temperature = temperature

        self.current_model: Optional[str] = None
        self.last_error: Optional[str] = None

    def _model_order(self) -> List[str]:
        seen = set()
        order = []
        for m in self.primary_models + self.fallback_models:
            if m not in seen:
                seen.add(m)
                order.append(m)
        return order

    async def _call_openai(self, model: str, prompt: str) -> str:
        if not client:
            raise RuntimeError("OPENAI_API_KEY não configurada")

        def sync_call():
            return client.responses.create(
                model=model,
                input=prompt,
                max_output_tokens=self.max_output_tokens,
                temperature=self.temperature,
            )

        response = await asyncio.to_thread(sync_call)

        # ✅ FORMA CORRETA
        text = response.output_text

        if not text or not text.strip():
            raise RuntimeError("Resposta vazia da OpenAI")

        return text.strip()

    async def generate_response(self, entries: List[Dict[str, str]]) -> str:
        prompt = build_prompt(entries)

        for model in self._model_order():
            try:
                self.current_model = model
                return await self._call_openai(model, prompt)

            except Exception as e:
                self.last_error = str(e)
                print(f"[AI_ENGINE] falha em {model}: {self.last_error}")
                await asyncio.sleep(0.4)

        return "Agora não."