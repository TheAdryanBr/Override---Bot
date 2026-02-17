# cogs/ai_chat/typing_tracker.py
import time
from dataclasses import dataclass
from typing import Dict, Tuple


@dataclass
class TypingState:
    last_typing_ts: float = 0.0


class TypingTracker:
    """
    Guarda timestamps de typing por (author_id, channel_id).
    API usada pelo core:
      - notify_typing(author_id, channel_id)
      - last_typing_ts(author_id, channel_id) -> float
    """

    def __init__(self):
        self._states: Dict[Tuple[int, int], TypingState] = {}

    def notify_typing(self, author_id: int, channel_id: int):
        key = (int(author_id), int(channel_id))
        st = self._states.get(key)
        if not st:
            st = TypingState()
            self._states[key] = st
        st.last_typing_ts = time.time()

    def last_typing_ts(self, author_id: int, channel_id: int) -> float:
        key = (int(author_id), int(channel_id))
        st = self._states.get(key)
        return float(st.last_typing_ts) if st else 0.0