# ai_state.py
import time
from typing import Optional


class AIState:
    def __init__(
        self,
        should_respond: bool,
        reason: str,
        allow_override: bool = False,
        patience_level: int = 1,
        tone: str = "normal",
        focused_user_id: Optional[int] = None,
        focus_reason: Optional[str] = None,
    ):
        self.should_respond = should_respond
        self.reason = reason
        self.allow_override = allow_override
        self.patience_level = patience_level
        self.tone = tone

        # 🔹 NOVO
        self.focused_user_id = focused_user_id
        self.focus_reason = focus_reason


class AIStateManager:
    def __init__(
        self,
        owner_id: int,
        admin_role_id: int,
        cooldown: int = 30,
        memory=None
    ):
        self.owner_id = owner_id
        self.admin_role_id = admin_role_id
        self.cooldown = cooldown
        self.memory = memory

        self.active_conversations = set()
        self.last_interaction = {}

        # 🔹 NOVO: foco por conversa
        self.current_focus = {}

    # ----------------------
    # Permissões
    # ----------------------

    def is_admin(self, member):
        if member.id == self.owner_id:
            return True
        return any(role.id == self.admin_role_id for role in member.roles)

    # ----------------------
    # Avaliação principal
    # ----------------------

    def evaluate(self, message, bot_user) -> AIState:
        user_id = message.author.id
        now = time.time()

        is_admin = self.is_admin(message.author)
        mentioned = bot_user in message.mentions
        in_conversation = user_id in self.active_conversations

        patience = 1
        tone = "normal"

        if self.memory:
            profile = self.memory.get_user(user_id)
            if profile:
                patience = profile.get("patience", 1)
                tone = profile.get("tone_bias", "normal")

        # ----------------------
        # ADMIN com mention → força foco
        # ----------------------
        if is_admin and mentioned:
            self._activate(user_id)
            self._set_focus(user_id, "admin_mention")
            return AIState(
                True,
                "admin_mention",
                allow_override=True,
                patience_level=patience,
                tone=tone,
                focused_user_id=user_id,
                focus_reason="admin_mention"
            )

        # ----------------------
        # Usuário comum inicia conversa com mention
        # ----------------------
        if mentioned and not in_conversation:
            self._activate(user_id)
            self._set_focus(user_id, "user_mention")
            return AIState(
                True,
                "user_mention",
                allow_override=False,
                patience_level=patience,
                tone=tone,
                focused_user_id=user_id,
                focus_reason="user_mention"
            )

        # ----------------------
        # Conversa ativa → mantém foco
        # ----------------------
        if in_conversation:
            self._touch(user_id)
            focused = self.current_focus.get(user_id)
            return AIState(
                True,
                "conversation_active",
                allow_override=True,
                patience_level=patience,
                tone=tone,
                focused_user_id=focused,
                focus_reason="conversation_active"
            )

        # ----------------------
        # Cooldown fora de conversa
        # ----------------------
        last = self.last_interaction.get(user_id, 0)
        if not is_admin and (now - last) < self.cooldown:
            return AIState(
                False,
                "cooldown",
                False,
                patience,
                tone
            )

        return AIState(
            False,
            "ignore",
            False,
            patience,
            tone
        )

    # ----------------------
    # Controle interno
    # ----------------------

    def _activate(self, user_id: int):
        self.active_conversations.add(user_id)
        self.last_interaction[user_id] = time.time()

    def _touch(self, user_id: int):
        self.last_interaction[user_id] = time.time()

    def _set_focus(self, user_id: int, reason: str):
        self.current_focus[user_id] = user_id

    def end_conversation(self, user_id: int):
        self.active_conversations.discard(user_id)
        self.current_focus.pop(user_id, None)
