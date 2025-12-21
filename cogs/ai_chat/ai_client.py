import asyncio
from typing import List

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
        self.api_key = api_key
        self.system_prompt = system_prompt
        self.models = primary_models + fallback_models
        self.max_tokens = max_tokens
        self.temperature = temperature

        self.client = None  # ⬅️ NÃO cria aqui
        self.last_model_used = None
        self.last_error = None

    # ----------------------
    # Cliente lazy (cria só quando precisar)
    # ----------------------
    def _get_client(self):
        if self.client is None:
            from openai import OpenAI  # import tardio
            self.client = OpenAI(api_key=self.api_key)
        return self.client

    # ----------------------
    # Chamada síncrona
    # ----------------------
    def _sync_call(self, model: str, messages: List[dict]) -> str:
    client = self._get_client()

    prompt = "\n".join(
        f"{m['role']}: {m['content']}" for m in messages
    )

    response = client.responses.create(
        model=model,
        input=prompt,
        max_output_tokens=self.max_tokens,
        temperature=self.temperature
    )

    text = getattr(response, "output_text", None)
    if not text:
        raise RuntimeError("Resposta vazia da API")

    return text.strip()

    # ----------------------
    # Async com fallback
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

                return await asyncio.to_thread(
                    self._sync_call,
                    model,
                    payload
                )

            except Exception as e:
                last_exception = e
                self.last_error = str(e)
                await asyncio.sleep(0.4)

        raise RuntimeError(f"Todos os modelos falharam: {last_exception}")
