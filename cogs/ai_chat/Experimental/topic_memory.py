import time
from typing import Optional


class TopicMemory:
    def __init__(self, ttl: int = 180):
        self.ttl = ttl
        self.topic: Optional[str] = None
        self.author_id: Optional[int] = None
        self.started_at: float = 0.0

    def _now(self) -> float:
        return time.time()

    def set(self, topic: str, author_id: int):
        self.topic = topic
        self.author_id = author_id
        self.started_at = self._now()

    def is_active(self) -> bool:
        if not self.started_at:
            return False
        return (self._now() - self.started_at) <= self.ttl

    def matches(self, author_id: int) -> bool:
        return self.author_id == author_id

    def clear(self):
        self.topic = None
        self.author_id = None
        self.started_at = 0.0
