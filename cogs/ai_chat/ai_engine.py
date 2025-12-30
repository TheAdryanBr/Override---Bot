import asyncio
import os
from typing import List, Dict, Any, Optional

from openai import OpenAI
from .ai_prompt import build_prompt  # <<-- usa o builder do prompt aqui

OPENAI_KEY = os.getenv("OPENAI_API_KEY")
client_ai = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None


class AIEngine:
    def __init__(
        self,
        primary_models: List[str],
        fallback_models: List[str],
        max_output_tokens: int = 180,
        temperature: float = 0.6,
    ):
        self.primary_models = primary_models
        self.fallback_models = fallback_models
        self.max_output_tokens = max_output_tokens
        self.temperature = temperature

        self.current_model_in_use: Optional[str] = None
        self.recent_error: Optional[str] = None

    # ----------------------
    # Ordem dos modelos
    # ----------------------
    def choose_model_order(self) -> List[str]:
        seen = set()
        ordered = []
        for m in self.primary_models + self.fallback_models:
            if m not in seen:
                seen.add(m)
                ordered.append(m)
        return ordered

    # ----------------------
    # OpenAI call
    # ----------------------
    async def _call_openai(self, model: str, prompt: str) -> str:
        if not client_ai:
            raise RuntimeError("OPENAI_API_KEY não configurada")

        def sync_call():
            return client_ai.responses.create(
                model=model,
                input=prompt,
                max_output_tokens=self.max_output_tokens,
                temperature=self.temperature,
            )

        resp = await asyncio.to_thread(sync_call)

        text = getattr(resp, "output_text", None)
        if not text or not text.strip():
            raise RuntimeError("Resposta vazia da OpenAI")

        return text.strip()

    # ----------------------
    # Fallback
    # ----------------------
    async def ask_with_fallback(self, prompt: str) -> str:
        for model in self.choose_model_order():
            try:
                self.current_model_in_use = model
                return await self._call_openai(model, prompt)

            except Exception as e:
                self.recent_error = str(e)
                print(f"[AI_ENGINE] falha no modelo {model}: {self.recent_error}")
                await asyncio.sleep(0.4)

        return "Agora não."

    # ----------------------
    # Limpeza final
    # ----------------------
    def final_clean(self, text: str) -> str:
        t = text.strip()
        if len(t) > 800:
            t = t[:800].rstrip() + "..."
        return t

    # ----------------------
    # API FINAL
    # ----------------------
    async def generate_response(self, entries: List[Dict[str, Any]]) -> str:
        # usa o build_prompt do módulo ai_prompt (assim o prompt fica centralizado)
        try:
            prompt = build_prompt(entries)
        except Exception as e:
            print("[AI_ENGINE] erro ao montar prompt:", e)
            return "Agora não."

        try:
            raw = await self.ask_with_fallback(prompt)
        except Exception as e:
            print("[AI_ENGINE] erro na chamada ao modelo:", e)
            return "Agora não."

        if not raw:
            return "Agora não."

        return self.final_clean(raw)
