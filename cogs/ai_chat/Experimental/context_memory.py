# context_memory.py
import time
from typing import Dict, List


class ContextMemory:
    def __init__(
        self,
        ttl: int = 180,        # tempo máximo de vida (3 min)
        max_items: int = 4     # tamanho da memória
    ):
        self.ttl = ttl
        self.max_items = max_items
        self._memory: Dict[int, List[str]] = {}
        self._timestamps: Dict[int, float] = {}

    def _now(self) -> float:
        return time.time()

    def add(self, author_id: int, content: str):
        self._memory.setdefault(author_id, [])
        self._memory[author_id].append(content)

        if len(self._memory[author_id]) > self.max_items:
            self._memory[author_id] = self._memory[author_id][-self.max_items :]

        self._timestamps[author_id] = self._now()

    def get(self, author_id: int) -> List[str]:
        if not self.is_alive(author_id):
            self.clear(author_id)
            return []

        return self._memory.get(author_id, [])

    def is_alive(self, author_id: int) -> bool:
        ts = self._timestamps.get(author_id)
        if not ts:
            return False
        return (self._now() - ts) <= self.ttl

    def clear(self, author_id: int):
        self._memory.pop(author_id, None)
        self._timestamps.pop(author_id, None)

    def clear_all(self):
        self._memory.clear()
        self._timestamps.clear()
