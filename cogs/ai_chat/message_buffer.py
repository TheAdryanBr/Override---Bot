# cogs/ai_chat/message_buffer.py

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional


class MessageBuffer:
    """Buffer curto de conversa.

    Guarda mensagens recentes com metadados mínimos para:
    - montar prompt com nomes
    - debug básico (timestamps)

    Formato de cada item:
      {
        "role": "user" | "assistant",
        "content": str,
        "author_id": int,              # sempre presente (0 = unknown)
        "author_name": str,            # sempre presente
        "ts": float
      }
    """

    def __init__(self, max_messages: int = 8):
        self.max_messages = int(max_messages)
        self.messages: List[Dict[str, Any]] = []

    def _push(self, msg: Dict[str, Any]):
        self.messages.append(msg)
        overflow = len(self.messages) - self.max_messages
        if overflow > 0:
            del self.messages[0:overflow]

    def add_user_message(
        self,
        content: Optional[str] = None,
        *,
        author_id: Optional[int] = None,
        author_name: Optional[str] = None,
        ts: Optional[float] = None,
    ):
        """Compatível com:
        - add_user_message("texto")
        - add_user_message(content="texto", author_id=..., author_name=...)
        """
        if content is None or not str(content).strip():
            raise TypeError("add_user_message(): 'content' é obrigatório e não pode ser vazio")

        # Defaults para compatibilidade, mas explícitos no debug
        if author_id is None:
            author_id = 0
        if author_name is None:
            author_name = "unknown"

        self._push({
            "role": "user",
            "content": str(content),
            "author_id": int(author_id),
            "author_name": str(author_name),
            "ts": float(ts) if ts is not None else time.time(),
        })

    def add_assistant_message(self, content: str, ts: Optional[float] = None):
        if not str(content).strip():
            return  # evita entupir buffer com vazio

        self._push({
            "role": "assistant",
            "content": str(content),
            "author_id": 0,
            "author_name": "Override",
            "ts": float(ts) if ts is not None else time.time(),
        })

    def get_messages(self) -> List[Dict[str, Any]]:
        return list(self.messages)

    def clear(self):
        self.messages.clear()