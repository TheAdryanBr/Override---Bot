# cogs/ai_chat/ai_engine.py
import asyncio
import os
from typing import List, Dict, Any, Optional

from openai import OpenAI

# ======================
# CLIENTE OPENAI
# ======================

client_ai = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

# ======================
# ENGINE (CÉREBRO)
# ======================

class AIEngine:
    def __init__(
        self,
        system_prompt: str,
        primary_models: List[str],
        fallback_models: List[str],
        max_output_tokens: int = 200,
        temperature: float = 0.5,
    ):
        self.system_prompt = system_prompt
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
        return self.primary_models + self.fallback_models

    # ----------------------
    # Chamada OpenAI (thread)
    # ----------------------

    async def _call_openai(self, model: str, prompt: str) -> str:
        def sync_call():
            return client_ai.responses.create(
                model=model,
                input=prompt,
                max_output_tokens=self.max_output_tokens,
                temperature=self.temperature,
            )

        resp = await asyncio.to_thread(sync_call)

        text = getattr(resp, "output_text", None)
        if not text:
            raise RuntimeError("Resposta vazia da OpenAI")

        return text.strip()

    # ----------------------
    # Fallback
    # ----------------------

    async def ask_with_fallback(self, prompt: str) -> str:
        last_exc = None

        for model in self.choose_model_order():
            try:
                self.current_model_in_use = model
                text = await self._call_openai(model, prompt)
                self.recent_error = None
                return text

            except Exception as e:
                last_exc = e
                self.recent_error = str(e)
                print("[AI_ENGINE] erro:", self.recent_error)
                await asyncio.sleep(0.25)

        return "Tô meio lento agora, tenta de novo."

    # ----------------------
    # Limpeza de texto
    # ----------------------

    def final_clean(self, text: str) -> str:
        t = text.strip()

        if len(t) > 900:
            t = t[:900].rstrip() + "..."

        if t.count(". ") > 1 and "\n" not in t:
            t = t.replace(". ", ", ", 1)

        return t.strip()

    # ----------------------
    # Prompt builder
    # ----------------------

    def build_prompt(self, entries: List[Dict[str, Any]]) -> str:
        texto_chat = "\n".join(
            f"{e['author_display']}: {e['content']}"
            for e in entries
            if e.get("content")
        )

        if not texto_chat.strip():
            texto_chat = "Usuário chamou você."

        return (
            self.system_prompt
            + "\n\nCONVERSA:\n"
            + texto_chat
            + "\n\nGere UMA resposta curta (1–3 frases), natural e no tom correto.\n"
        )

    # ----------------------
    # API FINAL
    # ----------------------

    async def generate_response(self, entries: List[Dict[str, Any]]) -> str:
        prompt = self.build_prompt(entries)
        raw = await self.ask_with_fallback(prompt)

        if not raw or not raw.strip():
            return "Fala aí."

        return self.final_clean(raw)
