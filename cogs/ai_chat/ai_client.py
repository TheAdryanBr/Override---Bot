import asyncio
from typing import List
from openai import OpenAI


class AIClient:
    def __init__(
        self,
        api_key: str,
        system_prompt: str,
        primary_models: List[str],
        fallback_models: List[str],
        max_tokens: int = 200,
        temperature: float = 0.6
    ):
        self.client = OpenAI(api_key=api_key)
        self.system_prompt = system_prompt
        self.models = primary_models + fallback_models
        self.max_tokens = max_tokens
        self.temperature = temperature

        self.last_model_used = None
        self.last_error = None

    # ----------------------
    # Chamada síncrona (isolada)
    # ----------------------
    def _sync_call(self, model: str, messages: List[dict]) -> str:
        response = self.client.responses.create(
            model=model,
            input=messages,
            max_output_tokens=self.max_tokens,
            temperature=self.temperature
        )
        return response.output_text.strip()

    # ----------------------
    # Chamada async com fallback
    # ----------------------
    async def ask(self, messages: List[dict]) -> str:
        payload = [
            {"role": "system", "content": self.system_prompt},
            *messages
        ]

        last_exception = None

        for model in self.models:
            try:
                self.last_model_used = model
                self.last_error = None

                result = await asyncio.to_thread(
                    self._sync_call,
                    model,
                    payload
                )
                return result

            except Exception as e:
                last_exception = e
                self.last_error = str(e)
                await asyncio.sleep(0.4)

        raise RuntimeError(f"Todos os modelos falharam: {last_exception}")
