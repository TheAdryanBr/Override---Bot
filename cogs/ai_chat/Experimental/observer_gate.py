import random
import time
from collections import deque


class ObserverGate:
    def __init__(
        self,
        chance: float = 0.06,
        cooldown: int = 900,   # 15 minutos
        window: int = 6
    ):
        self.chance = chance
        self.cooldown = cooldown
        self.window = window

        self.last_trigger: float = 0.0
        self.recent_messages = deque(maxlen=window)

    def _now(self) -> float:
        return time.time()

    def feed(self, author_id: int, content: str):
        self.recent_messages.append((author_id, content))

    def can_trigger(self, bot_id: int) -> bool:
        now = self._now()

        if (now - self.last_trigger) < self.cooldown:
            return False

        if len(self.recent_messages) < self.window:
            return False

        # se o bot já falou recentemente, não entra
        for author_id, _ in self.recent_messages:
            if author_id == bot_id:
                return False

        if random.random() > self.chance:
            return False

        self.last_trigger = now
        return True
