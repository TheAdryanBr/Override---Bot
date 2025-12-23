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
    ):
        self.should_respond = should_respond
        self.reason = reason
        self.allow_override = allow_override
        self.patience_level = patience_level
        self.tone = tone
        self.focused_user_id = focused_user_id


class AIStateManager:
    def __init__(
        self,
        owner_id: int,
        admin_role_id: int,
        cooldown: int = 30,
        memory=None,
    ):
        self.owner_id = owner_id
        self.admin_role_id = admin_role_id
        self.cooldown = cooldown
        self.memory = memory

        self.active_conversations = set()
        self.last_interaction = {}

        # quem chamou primeiro
        self.current_focus: dict[int, int] = {}

    # ─────────────────────────────
    # Permissões
    # ─────────────────────────────

    def is_admin(self, member) -> bool:
        if member.id == self.owner_id:
            return True
        return any(role.id == self.admin_role_id for role in member.roles)

    # ─────────────────────────────
    # Avaliação principal (Override)
    # ─────────────────────────────

    def evaluate(self, message, bot_user, intent=None) -> AIState:
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

        content_lower = message.content.lower()

        # ─────────────────────────────
        # 1) ADMIN com mention → força
        # ─────────────────────────────
        if is_admin and mentioned:
            self._activate(user_id)
            self._set_focus(user_id)
            return AIState(
                should_respond=True,
                reason="admin_mention",
                allow_override=True,
                patience_level=patience,
                tone=tone,
                focused_user_id=user_id,
            )

        # ─────────────────────────────
        # 2) Mention direta inicia foco
        # ─────────────────────────────
        if mentioned and not self.active_conversations:
            self._activate(user_id)
            self._set_focus(user_id)
            return AIState(
                should_respond=True,
                reason="user_mention",
                allow_override=False,
                patience_level=patience,
                tone=tone,
                focused_user_id=user_id,
            )

        # ─────────────────────────────
        # 3) Conversa ativa
        # ─────────────────────────────
        if self.active_conversations:
            self._touch(user_id)

            focus = self._get_focus()

            # respeita cooldown humano
            last = self.last_interaction.get("global", 0)
            if (now - last) < self.cooldown:
                return AIState(
                    should_respond=False,
                    reason="cooldown",
                    allow_override=False,
                    patience_level=patience,
                    tone=tone,
                    focused_user_id=focus,
                )

            self.last_interaction["global"] = now

            return AIState(
                should_respond=True,
                reason="conversation_active",
                allow_override=True,
                patience_level=patience,
                tone=tone,
                focused_user_id=focus,
            )

        # ─────────────────────────────
        # 4) Override indireto (raro)
        # ─────────────────────────────
        indirect = any(
            w in content_lower.split()
            for w in ("vc", "você", "tu")
        )

        last = self.last_interaction.get(user_id, 0)
        if indirect and not mentioned and (now - last) > self.cooldown * 3:
            self._activate(user_id)
            self._set_focus(user_id)
            return AIState(
                should_respond=True,
                reason="indirect_override",
                allow_override=False,
                patience_level=patience + 1,
                tone=tone,
                focused_user_id=user_id,
            )

        # ─────────────────────────────
        # 5) Ignora
        # ─────────────────────────────
        return AIState(
            should_respond=False,
            reason="ignore",
            allow_override=False,
            patience_level=patience,
            tone=tone,
        )

    # ─────────────────────────────
    # Controle interno
    # ─────────────────────────────

    def _activate(self, user_id: int):
        self.active_conversations.add(user_id)
        self.last_interaction[user_id] = time.time()

    def _touch(self, user_id: int):
        self.last_interaction[user_id] = time.time()

    def _set_focus(self, user_id: int):
        # só define se ainda não existir
        if not self.current_focus:
            self.current_focus["focus"] = user_id

    def _get_focus(self) -> Optional[int]:
        return self.current_focus.get("focus")

    def end_conversation(self):
        self.active_conversations.clear()
        self.current_focus.clear()
