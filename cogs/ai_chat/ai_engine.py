import asyncio
import os
from typing import Dict, List, Optional

from .ai_prompt import build_prompt


def _read_ai_key() -> Optional[str]:
    # Novo padrão (genérico)
    key = os.getenv("AI_API_KEY")
    if key and key.strip():
        return key.strip()

    # Retrocompatibilidade (você disse que às vezes mantém por conveniência)
    key = os.getenv("OPENAI_API_KEY")
    if key and key.strip():
        return key.strip()

    # Compatibilidade com docs do Gemini (se alguém usar esse nome)
    key = os.getenv("GEMINI_API_KEY")
    if key and key.strip():
        return key.strip()

    return None


class AIEngine:
    """
    Engine simples com suporte a providers.
    - Padrão: Gemini (via google-genai)
    - Opcional: OpenAI (se AI_PROVIDER=openai)
    """

    def __init__(
        self,
        primary_models: List[str],
        fallback_models: Optional[List[str]] = None,
        max_output_tokens: int = 420,
        temperature: float = 0.65,
        provider: Optional[str] = None,
    ):
        self.primary_models = primary_models
        self.fallback_models = fallback_models or []
        self.max_output_tokens = int(max_output_tokens)
        self.temperature = float(temperature)

        self.provider = (provider or os.getenv("AI_PROVIDER") or "gemini").strip().lower()

        self.current_model: Optional[str] = None
        self.last_error: Optional[str] = None

        self._api_key: Optional[str] = _read_ai_key()

        # lazy-init
        self._openai_client = None
        self._gemini_client = None
        self._gemini_types = None

    def _model_order(self) -> List[str]:
        seen = set()
        order: List[str] = []
        for m in self.primary_models + self.fallback_models:
            m = (m or "").strip()
            if not m:
                continue
            if m not in seen:
                seen.add(m)
                order.append(m)
        return order

    def _is_retryable(self, msg: str) -> bool:
        m = (msg or "").lower()
        return (
            "429" in m
            or "resource_exhausted" in m
            or "quota" in m
            or "rate" in m and "limit" in m
            or "500" in m
            or "503" in m
            or "unavailable" in m
            or "timeout" in m
        )

    # ─────────────────────────────
    # OPENAI (opcional)
    # ─────────────────────────────
    def _ensure_openai(self):
        if self._openai_client is not None:
            return

        if not self._api_key:
            raise RuntimeError("AI_API_KEY não configurada")

        try:
            from openai import OpenAI  # type: ignore
        except Exception as e:
            raise RuntimeError(f"Dependência 'openai' não instalada: {e}")

        self._openai_client = OpenAI(api_key=self._api_key)

    async def _call_openai(
        self,
        model: str,
        prompt: str,
        *,
        max_output_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> str:
        self._ensure_openai()

        mot = int(max_output_tokens if max_output_tokens is not None else self.max_output_tokens)
        temp = float(temperature if temperature is not None else self.temperature)

        def sync_call():
            return self._openai_client.responses.create(
                model=model,
                input=prompt,
                max_output_tokens=mot,
                temperature=temp,
            )

        response = await asyncio.to_thread(sync_call)
        text = getattr(response, "output_text", None)
        if not text or not str(text).strip():
            raise RuntimeError("Resposta vazia da OpenAI")
        return str(text).strip()

    # ─────────────────────────────
    # GEMINI (padrão)
    # ─────────────────────────────
    def _ensure_gemini(self):
        if self._gemini_client is not None:
            return

        if not self._api_key:
            raise RuntimeError("AI_API_KEY não configurada")

        try:
            from google import genai  # type: ignore
            from google.genai import types  # type: ignore
        except Exception as e:
            raise RuntimeError(
                "Dependência 'google-genai' não instalada. "
                "Adicione no requirements.txt: google-genai\n"
                f"Detalhe: {e}"
            )

        self._gemini_client = genai.Client(api_key=self._api_key)
        self._gemini_types = types

    async def _call_gemini(
        self,
        model: str,
        prompt: str,
        *,
        max_output_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> str:
        self._ensure_gemini()

        mot = int(max_output_tokens if max_output_tokens is not None else self.max_output_tokens)
        temp = float(temperature if temperature is not None else self.temperature)

        types = self._gemini_types

        def sync_call():
            # google-genai: generate_content retorna objeto com .text
            cfg = types.GenerateContentConfig(
                temperature=temp,
                max_output_tokens=mot,
            )
            return self._gemini_client.models.generate_content(
                model=model,
                contents=prompt,
                config=cfg,
            )

        response = await asyncio.to_thread(sync_call)

        text = getattr(response, "text", None)
        if text and str(text).strip():
            return str(text).strip()

        # fallback bem defensivo (caso a lib mude)
        candidates = getattr(response, "candidates", None) or []
        for c in candidates:
            content = getattr(c, "content", None)
            parts = getattr(content, "parts", None) if content else None
            if parts:
                for p in parts:
                    t = getattr(p, "text", None)
                    if t and str(t).strip():
                        return str(t).strip()

        raise RuntimeError("Resposta vazia do Gemini")

    # ─────────────────────────────
    # API PÚBLICA
    # ─────────────────────────────
    async def _call_provider(self, model: str, prompt: str, *, max_output_tokens=None, temperature=None) -> str:
        if self.provider == "openai":
            return await self._call_openai(model, prompt, max_output_tokens=max_output_tokens, temperature=temperature)
        # default: gemini
        return await self._call_gemini(model, prompt, max_output_tokens=max_output_tokens, temperature=temperature)

    async def generate_response(
        self,
        entries: List[Dict[str, str]],
        *,
        tone_hint: Optional[str] = None,
    ) -> str:
        prompt = build_prompt(entries, tone_hint=tone_hint)

        for model in self._model_order():
            self.current_model = model
            try:
                # 2 tentativas por modelo (pra rate-limit/transiente)
                for attempt in range(2):
                    try:
                        return await self._call_provider(model, prompt)
                    except Exception as e:
                        msg = str(e)
                        self.last_error = msg
                        if attempt == 0 and self._is_retryable(msg):
                            await asyncio.sleep(0.6)
                            continue
                        raise
            except Exception as e:
                self.last_error = str(e)
                print(f"[AI_ENGINE] falha em {model}: {self.last_error}")
                await asyncio.sleep(0.4)

        return "Agora não."

    async def generate_raw_text(
        self,
        prompt: str,
        *,
        max_output_tokens: int = 12,
        temperature: float = 0.0,
    ) -> str:
        """Resposta curta (1 linha / poucas palavras).

        Útil para classificadores e interjeições curtas. Mantém o resto do pipeline intacto.
        """
        for model in self._model_order():
            self.current_model = model
            try:
                for attempt in range(2):
                    try:
                        return await self._call_provider(
                            model,
                            prompt,
                            max_output_tokens=int(max_output_tokens),
                            temperature=float(temperature),
                        )
                    except Exception as e:
                        msg = str(e)
                        self.last_error = msg
                        if attempt == 0 and self._is_retryable(msg):
                            await asyncio.sleep(0.35)
                            continue
                        raise
            except Exception as e:
                self.last_error = str(e)
                print(f"[AI_ENGINE] raw falha em {model}: {self.last_error}")
                await asyncio.sleep(0.2)

        return ""
