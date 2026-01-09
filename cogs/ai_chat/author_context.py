import time
from typing import Dict, Optional


class AuthorContext:
    def __init__(self):
        self.last_interaction_ts: float = 0.0
        self.last_topic: Optional[str] = None
        self.talking_to_override: bool = False


class AuthorContextMemory:
    def __init__(self, ttl: int = 300):
        self.ttl = ttl  # 5 minutos
        self.data: Dict[int, AuthorContext] = {}

    def _now(self) -> float:
        return time.time()

    def touch(
        self,
        author_id: int,
        *,
        talking_to_override: bool,
        topic: Optional[str] = None
    ):
        ctx = self.data.get(author_id)
        if not ctx:
            ctx = AuthorContext()
            self.data[author_id] = ctx

        ctx.last_interaction_ts = self._now()
        ctx.talking_to_override = talking_to_override

        if topic:
            ctx.last_topic = topic

    def is_recent(self, author_id: int) -> bool:
        ctx = self.data.get(author_id)
        if not ctx:
            return False
        return (self._now() - ctx.last_interaction_ts) <= self.ttl

    def was_talking_to_override(self, author_id: int) -> bool:
        ctx = self.data.get(author_id)
        if not ctx:
            return False
        return ctx.talking_to_override

    def cleanup(self):
        now = self._now()
        expired = [
            uid for uid, ctx in self.data.items()
            if (now - ctx.last_interaction_ts) > self.ttl
        ]
        for uid in expired:
            del self.data[uid]
