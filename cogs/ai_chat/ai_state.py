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
        tone: str = "normal"
    ):
        self.should_respond = should_respond
        self.reason = reason
        self.allow_override = allow_override

        # 🎭 Novos atributos mentais
        self.patience_level = patience_level   # 1 a 4
        self.tone = tone                       # normal | seco | sarcastico


class AIStateManager:
    def __init__(
        self,
        owner_id: int,
        admin_role_id: int,
        cooldown: int = 30,
        memory=None  # <- ai_memory injetado
    ):
        self.owner_id = owner_id
        self.admin_role_id = admin_role_id
        self.cooldown = cooldown
        self.memory = memory

        self.active_conversations = set()
        self.last_interaction = {}

    # ─────────────────────────────
    # UTIL
    # ─────────────────────────────

    def is_admin(self, member):
        if member.id == self.owner_id:
            return True
        return any(role.id == self.admin_role_id for role in member.roles)

    # ─────────────────────────────
    # CORE
    # ─────────────────────────────

    def evaluate(self, message, bot_user):
        user_id = message.author.id
        now = time.time()

        is_admin = self.is_admin(message.author)
        mentioned = bot_user in message.mentions
        in_conversation = user_id in self.active_conversations

        # 🧠 Puxa perfil do usuário (se existir)
        profile = None
        if self.memory:
            profile = self.memory.get_user(user_id)

        # 🎭 Valores padrão
        patience = 1
        tone = "normal"

        if profile:
            patience = profile.get("patience", 1)
            tone = profile.get("tone_bias", "normal")

            # usuário impaciente → tom mais seco
            if profile.get("last_emotion") == "impaciente":
                tone = "seco"
                patience = min(patience + 1, 4)

        # 🔒 Cooldown (usuário comum fora de conversa)
        last = self.last_interaction.get(user_id, 0)
        if not is_admin and not in_conversation:
            if now - last < self.cooldown:
                return AIState(
                    False,
                    "cooldown",
                    patience_level=patience,
                    tone=tone
                )

        # 🔒 ADM sempre pode iniciar com mention
        if is_admin and mentioned:
            self._activate(user_id)
            return AIState(
                True,
                "admin_mention",
                allow_override=True,
                patience_level=patience,
                tone=tone
            )

        # 🔒 Usuário comum inicia com mention se cooldown OK
        if not in_conversation:
            if mentioned:
                self._activate(user_id)
                return AIState(
                    True,
                    "user_mention_start",
                    patience_level=patience,
                    tone=tone
                )
            return AIState(
                False,
                "not_in_conversation",
                patience_level=patience,
                tone=tone
            )

        # 🔓 Conversa ativa → comportamento humano
        if in_conversation:
            self._touch(user_id)
            return AIState(
                True,
                "conversation_active",
                allow_override=True,
                patience_level=patience,
                tone=tone
            )

        return AIState(False, "default_block")

    # ─────────────────────────────
    # STATE CONTROL
    # ─────────────────────────────

    def _activate(self, user_id):
        self.active_conversations.add(user_id)
        self.last_interaction[user_id] = time.time()

    def _touch(self, user_id):
        self.last_interaction[user_id] = time.time()

    def end_conversation(self, user_id):
        self.active_conversations.discard(user_id)
