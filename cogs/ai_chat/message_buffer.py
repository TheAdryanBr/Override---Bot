# message_buffer.py
import time
from collections import deque
from typing import Deque, Dict, List


class MessageBuffer:
    def __init__(
        self,
        max_messages: int = 12,
        merge_window: float = 4.0,  # segundos para juntar mensagens quebradas
    ):
        self.max_messages = max_messages
        self.merge_window = merge_window
        self._messages: Deque[Dict] = deque(maxlen=max_messages)

     def get_last_user_id(self):
        for msg in reversed(self._messages):
            if msg.get("role") == "user":
                return msg.get("author_id")
        return None
         
    # ─────────────────────────────
    # Controle
    # ─────────────────────────────

    def clear(self) -> None:
        self._messages.clear()

    def is_empty(self) -> bool:
        return len(self._messages) == 0

    def size(self) -> int:
        return len(self._messages)

    # ─────────────────────────────
    # Escrita (usuário)
    # ─────────────────────────────

    def add_user_message(
        self,
        author_id: int,
        author_name: str,
        content: str,
    ) -> None:
        now = time.time()

        # tenta juntar com a última mensagem
        if self._messages:
            last = self._messages[-1]
            if (
                last["role"] == "user"
                and last["author_id"] == author_id
                and (now - last["ts"]) <= self.merge_window
            ):
                # junta como pensamento contínuo
                last["content"] += " " + content
                last["ts"] = now
                return

        # nova entrada
        self._messages.append({
            "role": "user",
            "author_id": author_id,
            "author_name": author_name,
            "content": content,
            "ts": now,
        })

    # ─────────────────────────────
    # Escrita (IA)
    # ─────────────────────────────

    def add_assistant_message(self, content: str) -> None:
        self._messages.append({
            "role": "assistant",
            "content": content,
            "ts": time.time(),
        })

    # ─────────────────────────────
    # Leitura
    # ─────────────────────────────

    def get_messages(self) -> List[Dict]:
        return list(self._messages)
