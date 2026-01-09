# typing_tracker.py
import time
from typing import Dict


class TypingTracker:
    def __init__(self, typing_grace: float = 5.0):
        self.typing_grace = typing_grace
        self._typing_until: Dict[int, float] = {}
        self._last_message_ts: Dict[int, float] = {}

    def mark_typing(self, author_id: int):
        self._typing_until[author_id] = time.time() + self.typing_grace

    def mark_message(self, author_id: int):
        self._last_message_ts[author_id] = time.time()
        self.mark_typing(author_id)

    def is_still_typing(self, author_id: int) -> bool:
        until = self._typing_until.get(author_id)
        if not until:
            return False
        return time.time() < until

    def clear(self, author_id: int):
        self._typing_until.pop(author_id, None)
        self._last_message_ts.pop(author_id, None)
