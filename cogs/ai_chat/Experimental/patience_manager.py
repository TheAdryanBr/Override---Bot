# patience_manager.py
import time
from enum import Enum


class PatienceLevel(Enum):
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"
    EXHAUSTED = "exhausted"


class PatienceManager:
    def __init__(
        self,
        decay_per_message: float = 0.15,
        recovery_rate: float = 0.05,
        exhausted_threshold: float = 0.15,
        low_threshold: float = 0.35
    ):
        self.value = 1.0  # 1 = paciência cheia
        self.last_update = time.time()

        self.decay_per_message = decay_per_message
        self.recovery_rate = recovery_rate
        self.exhausted_threshold = exhausted_threshold
        self.low_threshold = low_threshold

    def _now(self) -> float:
        return time.time()

    def update(self, *, noise: bool, repetition: bool):
        """
        Atualiza paciência com base no comportamento atual.
        """
        now = self._now()
        elapsed = now - self.last_update
        self.last_update = now

        # recuperação natural
        self.value += elapsed * self.recovery_rate

        # penalizações
        if noise:
            self.value -= self.decay_per_message * 0.6

        if repetition:
            self.value -= self.decay_per_message

        # clamp
        self.value = max(0.0, min(1.0, self.value))

    def level(self) -> PatienceLevel:
        if self.value <= self.exhausted_threshold:
            return PatienceLevel.EXHAUSTED
        if self.value <= self.low_threshold:
            return PatienceLevel.LOW
        if self.value < 0.75:
            return PatienceLevel.NORMAL
        return PatienceLevel.HIGH

    def snapshot(self) -> dict:
        """
        Debug / observação.
        """
        return {
            "value": round(self.value, 2),
            "level": self.level().value
        }