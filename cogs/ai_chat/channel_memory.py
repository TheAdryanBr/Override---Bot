# cogs/ai_chat/channel_memory.py
from collections import deque
from dataclasses import dataclass
from typing import Deque, List


@dataclass
class MemLine:
    ts: float
    text: str


class ChannelMemory:
    """Memória curtinha do canal: últimas falas do Override.

    Serve pra:
    - evitar repetição literal
    - dar continuidade natural
    - o bot não parecer amnésico
    """

    def __init__(self, max_lines: int = 10):
        self.max_lines = int(max_lines)
        self._lines: Deque[MemLine] = deque(maxlen=self.max_lines)

    def add(self, ts: float, text: str):
        t = (text or "").strip()
        if not t:
            return
        if self._lines and self._lines[-1].text == t:
            return
        self._lines.append(MemLine(ts=float(ts), text=t))

    def recent(self, limit: int = 4) -> List[str]:
        lim = max(0, int(limit))
        if lim <= 0:
            return []
        return [x.text for x in list(self._lines)[-lim:]]