# cogs/ai_engine.py
import asyncio
import random
import time
from typing import List, Dict, Any, Optional

from openai import OpenAI

# ======================
# CLIENTE OPENAI
# ======================

client_ai = OpenAI()

# ======================
# ENGINE (CÉREBRO)
# ======================

class AIEngine:
    def __init__(self, system_prompt: str, primary_models, fallback_models):
        self.system_prompt = system_prompt
        self.primary_models = primary_models
        self.fallback_models = fallback_models
        self.current_model_in_use: Optional[str] = None
        self.recent_error: Optional[str] = None

    # ----------------------
    # Model order
    # ----------------------
    def choose_model_order(self):
        return self.primary_models + self.fallback_models

    # ----------------------
    # Chamada OpenAI (thread)
    # ----------------------
    async def _call_openai(
        self,
        model: str,
        prompt: str,
        max_output_tokens: int = 200,
        temperature: float = 0.5,
    ) -> str:
        def sync_call():
            return client_ai.responses.create(
                model=model,
                input=prompt,
                max_output_tokens=max_output_tokens,
                temperature=temperature,
            )

        resp = await asyncio.to_thread(sync_call)
        return resp.output_text

    async def ask_gpt_with_fallback(self, prompt: str) -> str:
        last_exc = None
        for m in self.choose_model_order():
            try:
                self.current_model_in_use = m
                text = await self._call_openai(m, prompt)
                self.recent_error = None
                return text
            except Exception as e:
                last_exc = e
                self.recent_error = f"Model {m} failed: {e}"
                await asyncio.sleep(0.3)

        raise RuntimeError(f"All models failed. Last error: {last_exc}")

    # ----------------------
    # Sanitização / limpeza
    # ----------------------
    def sanitize_giria(self, text: str) -> str:
        replacements = {
            "oxe,": "olha,",
            "oxe": "olha",
            "ué,": "olha,",
            "ué": "olha",
            "mano": "",
            "man": "",
            "boy": "",
            "vish": "",
        }
        for k, v in replacements.items():
            text = text.replace(k, v)
        return " ".join(text.split())

    def tone_cleanup(self, text: str) -> str:
        banned = [
            "tava aqui pensando",
            "voltei",
            "to de volta",
            "pensei na vida",
            "sou meio bugado",
            "meu codigo",
            "meu prompt",
        ]
        low = text.lower()
        for b in banned:
            if b in low:
                low = low.replace(b, "")
        return " ".join(low.split())

    def final_clean(self, text: str) -> str:
        t = text.strip()
        t = self.sanitize_giria(t)
        t = self.tone_cleanup(t)

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
            f"{e['author_display']}: {e['content']}" for e in entries
        )

        prompt = (
            self.system_prompt
            + "\n\nCONVERSA:\n"
            + texto_chat
            + "\n\nGere UMA resposta curta (1–3 frases), natural e no tom correto.\n"
        )

        return prompt

    # ----------------------
    # Resposta completa
    # ----------------------
    async def generate_response(self, entries: List[Dict[str, Any]]) -> str:
        prompt = self.build_prompt(entries)
        raw = await self.ask_gpt_with_fallback(prompt)

        if "\n[" in raw:
            lines = raw.strip().splitlines()
            if lines and "[" in lines[-1]:
                lines.pop()
            raw = "\n".join(lines)

        return self.final_clean(raw)
