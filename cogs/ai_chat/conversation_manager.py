# conversation_manager.py
import time
from enum import Enum
from typing import Optional


class ConversationState(Enum):
    OBSERVING = "observing"
    ENGAGED = "engaged"
    EXITING_SOFT = "exiting_soft"
    ENDED = "ended"


class ConversationEvent:
    def __init__(
        self,
        should_consider: bool,
        should_wait: bool,
        direct: bool,
        state: ConversationState,
        reason: str,
        should_exit: bool = False,
        ended_recently: bool = False,
        resume_allowed: bool = False
    ):
        self.should_consider = should_consider
        self.should_wait = should_wait
        self.direct = direct
        self.state = state
        self.reason = reason
        self.should_exit = should_exit
        self.ended_recently = ended_recently
        self.resume_allowed = resume_allowed


class ConversationManager:
    def __init__(
        self,
        idle_timeout: int = 20 * 60,
        soft_exit_timeout: int = 120,
        max_presence: int = 8 * 60,
        recent_end_window: int = 90,
        patience=None
    ):
        self.idle_timeout = idle_timeout
        self.soft_exit_timeout = soft_exit_timeout
        self.max_presence = max_presence
        self.recent_end_window = recent_end_window
        self.patience = patience

        self.active_author: Optional[int] = None
        self.started_at = 0.0
        self.last_activity_ts = 0.0
        self.exit_started_at = 0.0
        self.ended_at = 0.0
        self.state = ConversationState.OBSERVING

        self._last_message_class: Optional[str] = None
        self._repeat_count = 0

    def _now(self) -> float:
        return time.time()

    def reset(self):
        self.active_author = None
        self.started_at = 0.0
        self.last_activity_ts = 0.0
        self.exit_started_at = 0.0
        self.ended_at = self._now()
        self.state = ConversationState.OBSERVING
        self._last_message_class = None
        self._repeat_count = 0

    def _classify_message(self, content: str) -> str:
        text = content.lower().strip()
        if text.startswith(("boa noite", "bom dia", "boa tarde", "oi", "opa")):
            return "greeting"
        if any(f in text for f in ("tchau", "falou", "vou dormir")):
            return "farewell"
        if len(text.split()) <= 4:
            return "short"
        return "normal"

    def analyze_message(
        self,
        *,
        author_id: int,
        content: str,
        mentioned: bool,
        replying_to_bot: bool,
        side_topic: bool = False
    ) -> ConversationEvent:

        now = self._now()
        direct = mentioned or replying_to_bot
        msg_class = self._classify_message(content)

        # 🔧 ASSUNTO LATERAL DO AUTOR ATIVO
        if (
            self.state == ConversationState.ENGAGED
            and author_id == self.active_author
            and side_topic
        ):
            self.last_activity_ts = now
            return ConversationEvent(
                should_consider=False,
                should_wait=True,
                direct=False,
                state=self.state,
                reason="side_topic_by_active_author"
            )

        # anti-loop simples
        if msg_class == self._last_message_class:
            self._repeat_count += 1
        else:
            self._repeat_count = 0
            self._last_message_class = msg_class

        if self._repeat_count >= 2:
            return ConversationEvent(
                should_consider=False,
                should_wait=True,
                direct=False,
                state=self.state,
                reason="blocked_repeated_pattern"
            )

        # início implícito
        if self.state == ConversationState.OBSERVING:
            self.state = ConversationState.ENGAGED
            self.active_author = author_id
            self.started_at = now
            self.last_activity_ts = now
            return ConversationEvent(
                should_consider=True,
                should_wait=True,
                direct=direct,
                state=self.state,
                reason="conversation_started"
            )

        # continuação normal
        if author_id == self.active_author:
            self.last_activity_ts = now
            return ConversationEvent(
                should_consider=True,
                should_wait=True,
                direct=direct,
                state=self.state,
                reason="continuation"
            )

        # ruído
        return ConversationEvent(
            should_consider=False,
            should_wait=False,
            direct=False,
            state=self.state,
            reason="noise"
        )
