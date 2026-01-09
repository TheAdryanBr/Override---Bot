#social_focus
import time
from typing import Optional


class SocialFocus:
    def __init__(self, timeout: int = 120):
        self.active_author_id: Optional[int] = None
        self.last_direct_ts: float = 0.0
        self.timeout = timeout

    def _now(self) -> float:
        return time.time()

    def reset(self):
        self.active_author_id = None
        self.last_direct_ts = 0.0

    def is_expired(self) -> bool:
        if not self.active_author_id:
            return True
        return (self._now() - self.last_direct_ts) > self.timeout

    def consider(
        self,
        *,
        author_id: int,
        mentioned_override: bool,
        replying_to_override: bool
    ) -> bool:
        """
        Retorna True se Override PODE responder
        """

        # foco morreu sozinho
        if self.is_expired():
            self.reset()

        # sem foco → só entra se for chamado claramente
        if self.active_author_id is None:
            if mentioned_override or replying_to_override:
                self.active_author_id = author_id
                self.last_direct_ts = self._now()
                return True
            return False

        # foco ativo
        if author_id == self.active_author_id:
            self.last_direct_ts = self._now()
            return True

        # outra pessoa tentando puxar assunto
        if mentioned_override:
            # só troca foco se for MUITO claro
            self.active_author_id = author_id
            self.last_direct_ts = self._now()
            return True

        return False
