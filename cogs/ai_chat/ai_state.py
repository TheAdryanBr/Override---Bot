# cogs/ai_chat/ai_state.py

import time
from dataclasses import dataclass


CONVERSATION_TIMEOUT = 120  # segundos (inatividade para expirar conversa ativa)


@dataclass
class AIState:
    should_respond: bool
    reason: str
    allow_override: bool = False


class AIStateManager:
    def __init__(
        self,
        owner_id: int,
        admin_role_id: int,
        cooldown: int = 30,
    ):
        self.owner_id = int(owner_id)
        self.admin_role_id = int(admin_role_id)
        self.cooldown = int(cooldown)

        self.active_conversations = set()   # user_ids
        self.last_interaction = {}          # user_id -> ts

    def is_admin(self, member) -> bool:
        if member.id == self.owner_id:
            return True
        roles = getattr(member, "roles", []) or []
        return any(getattr(role, "id", None) == self.admin_role_id for role in roles)

    def _mentioned_bot(self, message, bot_user) -> bool:
        if not bot_user:
            return False
        return bot_user in getattr(message, "mentions", [])

    def evaluate(self, message, bot_user) -> AIState:
        user_id = message.author.id
        now = time.time()

        # expira conversa ativa por inatividade
        last = self.last_interaction.get(user_id)
        if last and (now - last) > CONVERSATION_TIMEOUT:
            self.end_conversation(user_id)

        is_admin = self.is_admin(message.author)
        mentioned = self._mentioned_bot(message, bot_user)
        in_conversation = user_id in self.active_conversations

        if is_admin and mentioned:
            self._activate(user_id)
            return AIState(True, "admin_mention", True)

        if mentioned:
            self._activate(user_id)
            return AIState(True, "direct_mention", True)

        if in_conversation:
            self._touch(user_id)
            return AIState(True, "conversation_active", True)

        last2 = self.last_interaction.get(user_id, 0.0)
        if (not is_admin) and (now - last2) < self.cooldown:
            return AIState(False, "cooldown", False)

        return AIState(True, "policy_ok", False)

    def _activate(self, user_id: int):
        self.active_conversations.add(user_id)
        self.last_interaction[user_id] = time.time()

    def _touch(self, user_id: int):
        self.last_interaction[user_id] = time.time()

    def end_conversation(self, user_id: int):
        self.active_conversations.discard(user_id)
        self.last_interaction[user_id] = time.time()  # ✅ alimenta cooldown pós-fim