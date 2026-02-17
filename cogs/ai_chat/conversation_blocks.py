# cogs/ai_chat/conversation_blocks.py

import time
from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class Block:
    author_id: int
    channel_id: int
    ts: float
    raw: str
    clean: str
    mentioned: bool
    replying: bool


@dataclass
class BlockBatch:
    author_id: int
    channel_id: int
    start_ts: float
    end_ts: float
    blocks: List[Block] = field(default_factory=list)

    @property
    def text_clean(self) -> str:
        return " ".join(b.clean for b in self.blocks if b.clean).strip()

    @property
    def text_raw(self) -> str:
        return " ".join(b.raw for b in self.blocks if b.raw).strip()

    @property
    def direct(self) -> bool:
        return any(b.mentioned or b.replying for b in self.blocks)


class BlockBuffer:
    """
    Mantém blocos por (author_id, channel_id).
    """
    def __init__(self):
        self._buf: Dict[tuple[int, int], List[Block]] = {}
        self._start_ts: Dict[tuple[int, int], float] = {}

    def add(self, block: Block):
        key = (block.author_id, block.channel_id)
        if key not in self._buf:
            self._buf[key] = []
            self._start_ts[key] = block.ts
        self._buf[key].append(block)

    def has_active(self, author_id: int, channel_id: int) -> bool:
        return (author_id, channel_id) in self._buf

    def flush(self, author_id: int, channel_id: int) -> Optional[BlockBatch]:
        key = (author_id, channel_id)
        blocks = self._buf.pop(key, None)
        start = self._start_ts.pop(key, None)
        if not blocks or start is None:
            return None
        end = time.time()
        return BlockBatch(
            author_id=author_id,
            channel_id=channel_id,
            start_ts=start,
            end_ts=end,
            blocks=blocks,
        )

    def clear(self, author_id: int, channel_id: int):
        key = (author_id, channel_id)
        self._buf.pop(key, None)
        self._start_ts.pop(key, None)