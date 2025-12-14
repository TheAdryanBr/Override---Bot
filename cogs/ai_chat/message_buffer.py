from collections import deque
from typing import Deque, List


class MessageBuffer:
    def __init__(self, max_messages: int = 12):
        self.max_messages = max_messages
        self._messages: Deque[dict] = deque(maxlen=max_messages)

    # ----------------------
    # Controle
    # ----------------------
    def clear(self) -> None:
        self._messages.clear()

    def is_empty(self) -> bool:
        return len(self._messages) == 0

    # ----------------------
    # Escrita
    # ----------------------
    def add_user_message(self, content: str) -> None:
        self._messages.append({
            "role": "user",
            "content": content
        })

    def add_assistant_message(self, content: str) -> None:
        self._messages.append({
            "role": "assistant",
            "content": content
        })

    def add_system_message(self, content: str) -> None:
        self._messages.append({
            "role": "system",
            "content": content
        })

    # ----------------------
    # Leitura
    # ----------------------
    def get_messages(self) -> List[dict]:
        return list(self._messages)

    def size(self) -> int:
        return len(self._messages)
