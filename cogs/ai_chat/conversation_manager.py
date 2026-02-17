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
        resume_allowed: bool = False,
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
        patience=None,
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

    def _now(self) -> float:
        return time.time()

    def reset(self):
        # reset neutro (não renova ended_at)
        self.active_author = None
        self.started_at = 0.0
        self.last_activity_ts = 0.0
        self.exit_started_at = 0.0
        self.state = ConversationState.OBSERVING

    def mark_ended(self, now: Optional[float] = None):
        t = float(now or self._now())
        self.state = ConversationState.ENDED
        self.active_author = None
        self.ended_at = t
        self.exit_started_at = 0.0

    def _ended_recently(self, now: float) -> bool:
        if self.ended_at <= 0:
            return False
        return (now - self.ended_at) <= self.recent_end_window

    def _timed_out(self, now: float) -> bool:
        if self.last_activity_ts <= 0:
            return False
        return (now - self.last_activity_ts) >= self.idle_timeout

    def _presence_exceeded(self, now: float) -> bool:
        if self.started_at <= 0:
            return False
        return (now - self.started_at) >= self.max_presence

    def analyze_message(
        self,
        *,
        author_id: int,
        content: str,
        mentioned: bool,
        replying_to_bot: bool,
        side_topic: bool = False,
    ) -> ConversationEvent:
        now = self._now()
        direct = bool(mentioned or replying_to_bot)

        # ---- housekeeping: idle timeout ----
        if self.state in (ConversationState.ENGAGED, ConversationState.EXITING_SOFT):
            if self._timed_out(now):
                self.mark_ended(now)

        # ---- ENDED handling ----
        if self.state == ConversationState.ENDED:
            ended_recently = self._ended_recently(now)

            if ended_recently and direct:
                self.state = ConversationState.ENGAGED
                self.active_author = author_id
                self.started_at = now
                self.last_activity_ts = now
                self.exit_started_at = 0.0
                return ConversationEvent(
                    should_consider=True,
                    should_wait=True,
                    direct=True,
                    state=self.state,
                    reason="resume_after_recent_end",
                    ended_recently=True,
                    resume_allowed=True,
                )

            if ended_recently and not direct:
                return ConversationEvent(
                    should_consider=False,
                    should_wait=False,
                    direct=False,
                    state=self.state,
                    reason="ended_recently_noise",
                    ended_recently=True,
                    resume_allowed=False,
                )

            # fim antigo => volta pra observing (sem renovar ended_at)
            self.reset()

        # ---- OBSERVING ----
        if self.state == ConversationState.OBSERVING:
            if not direct:
                return ConversationEvent(
                    should_consider=False,
                    should_wait=False,
                    direct=False,
                    state=self.state,
                    reason="observing_no_direct",
                )

            self.state = ConversationState.ENGAGED
            self.active_author = author_id
            self.started_at = now
            self.last_activity_ts = now
            return ConversationEvent(
                should_consider=True,
                should_wait=True,
                direct=True,
                state=self.state,
                reason="conversation_started",
            )

        # ---- ENGAGED / EXITING_SOFT ----
        if self.state in (ConversationState.ENGAGED, ConversationState.EXITING_SOFT):
            if self._presence_exceeded(now) and self.state != ConversationState.EXITING_SOFT:
                self.state = ConversationState.EXITING_SOFT
                self.exit_started_at = now

            if author_id == self.active_author:
                self.last_activity_ts = now

                if side_topic:
                    return ConversationEvent(
                        should_consider=False,
                        should_wait=True,
                        direct=direct,
                        state=self.state,
                        reason="side_topic_by_active_author",
                    )

                if self.state == ConversationState.EXITING_SOFT:
                    should_exit = (now - self.exit_started_at) >= self.soft_exit_timeout
                    if should_exit:
                        self.mark_ended(now)
                        return ConversationEvent(
                            should_consider=False,
                            should_wait=False,
                            direct=direct,
                            state=self.state,
                            reason="soft_exit_finished",
                            should_exit=True,
                            ended_recently=True,
                            resume_allowed=True,
                        )

                return ConversationEvent(
                    should_consider=True,
                    should_wait=True,
                    direct=direct,
                    state=self.state,
                    reason="continuation",
                )

            if direct:
                self.state = ConversationState.ENGAGED
                self.active_author = author_id
                self.started_at = now
                self.last_activity_ts = now
                self.exit_started_at = 0.0
                return ConversationEvent(
                    should_consider=True,
                    should_wait=True,
                    direct=True,
                    state=self.state,
                    reason="switch_focus_direct",
                )

            return ConversationEvent(
                should_consider=False,
                should_wait=False,
                direct=False,
                state=self.state,
                reason="noise",
            )

        return ConversationEvent(
            should_consider=False,
            should_wait=False,
            direct=False,
            state=self.state,
            reason="fallback",
        )