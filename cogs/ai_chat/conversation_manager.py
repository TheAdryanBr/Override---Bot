import time
from typing import Optional


class ConversationManager:
    def __init__(
        self,
        conversation_timeout: int = 90,
        global_cooldown: int = 30,
        owner_id: int | None = None,
        admin_role_id: int | None = None,
    ):
        self.conversation_timeout = conversation_timeout
        self.global_cooldown = global_cooldown

        self.owner_id = owner_id
        self.admin_role_id = admin_role_id

        self.active = False
        self.started_by: Optional[int] = None
        self.started_at: float = 0.0
        self.last_interaction: float = 0.0

        self.last_global_end: float = 0.0

    # ----------------------
    # Estado
    # ----------------------
    def is_active(self) -> bool:
        if not self.active:
            return False

        if time.time() - self.last_interaction > self.conversation_timeout:
            self.end_conversation()
            return False

        return True

    # ----------------------
    # Início / fim
    # ----------------------
    def start_conversation(self, user_id: int) -> None:
        self.active = True
        self.started_by = user_id
        self.started_at = time.time()
        self.last_interaction = time.time()

    def touch(self) -> None:
        self.last_interaction = time.time()

    def end_conversation(self) -> None:
        self.active = False
        self.started_by = None
        self.started_at = 0.0
        self.last_interaction = 0.0
        self.last_global_end = time.time()

    # ----------------------
    # Permissões
    # ----------------------
    def can_admin_start(self) -> bool:
        return True

    def can_user_start(self) -> bool:
        if self.is_active():
            return False

        return (time.time() - self.last_global_end) >= self.global_cooldown

    def can_call_without_mention(self, user_id: int) -> bool:
        if not self.is_active():
            return False

        return self.started_by == user_id

    # ----------------------
    # Utilidades
    # ----------------------
    def is_owner(self, user_id: int) -> bool:
        return self.owner_id is not None and user_id == self.owner_id

    def has_admin_role(self, member_roles_ids: list[int]) -> bool:
        if self.admin_role_id is None:
            return False
        return self.admin_role_id in member_roles_ids
