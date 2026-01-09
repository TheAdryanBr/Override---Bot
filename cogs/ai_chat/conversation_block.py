# conversation_block.py
import time
from enum import Enum
from typing import List, Optional


class BlockTarget(Enum):
    BOT = "bot"
    HUMAN = "human"
    UNKNOWN = "unknown"


class BlockState(Enum):
    ACTIVE = "active"        # pode receber mensagens
    WAITING = "waiting"      # bot respondeu, aguardando
    SUSPENDED = "suspended"  # autor falando com outra pessoa
    CLOSED = "closed"        # finalizado


class ConversationBlock:
    def __init__(
        self,
        *,
        owner_id: int,
        target: BlockTarget,
        confidence: float = 0.5
    ):
        self.owner_id = owner_id
        self.target = target
        self.confidence = confidence

        self.state: BlockState = BlockState.ACTIVE

        self.messages: List[str] = []

        self.created_at: float = time.time()
        self.last_activity: float = self.created_at
        self.last_bot_reply: Optional[float] = None

    # =========================
    # AÇÕES
    # =========================

    def add_message(self, content: str):
        self.messages.append(content)
        self.last_activity = time.time()

    def mark_bot_replied(self):
        self.state = BlockState.WAITING
        self.last_bot_reply = time.time()

    def suspend(self):
        if self.state in (BlockState.ACTIVE, BlockState.WAITING):
            self.state = BlockState.SUSPENDED

    def resume(self):
        if self.state == BlockState.SUSPENDED:
            self.state = BlockState.ACTIVE
            self.last_activity = time.time()

    def close(self):
        self.state = BlockState.CLOSED

    # =========================
    # HELPERS
    # =========================

    def is_alive(self) -> bool:
        return self.state != BlockState.CLOSED

    def can_bot_reply(self) -> bool:
        return (
            self.target == BlockTarget.BOT
            and self.state == BlockState.ACTIVE
            and self.confidence >= 0.6
        )

    def idle_time(self) -> float:
        return time.time() - self.last_activity
