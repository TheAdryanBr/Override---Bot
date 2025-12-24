# ai_state.py
import time
from typing import Optional


CONVERSATION_TIMEOUT = 120  # segundos


class AIState:
    def __init__(
        self,
        should_respond: bool,
        reason: str,
        allow_override: bool = False,
    ):
        self.should_respond = should_respond
        self.reason = reason
        self.allow_override = allow_override


class AIStateManager:
    def __init__(
        self,
        owner_id: int,
        admin_role_id: int,
        cooldown: int = 30,
    ):
        self.owner_id = owner_id
        self.admin_role_id = admin_role_id
        self.cooldown = cooldown

        self.active_conversations = set()
        self.last_interaction = {}

    def is_admin(self, member):
        if member.id == self.owner_id:
            return True
        return any(role.id == self.admin_role_id for role in member.roles)

    def evaluate(self, message, bot_user) -> AIState:
        user_id = message.author.id
        now = time.time()

        last = self.last_interaction.get(user_id)
        if last and (now - last) > CONVERSATION_TIMEOUT:
            self.end_conversation(user_id)

        is_admin = self.is_admin(message.author)
        mentioned = bot_user in message.mentions
        in_conversation = user_id in self.active_conversations

        if is_admin and mentioned:
            self._activate(user_id)
            return AIState(True, "admin_mention", True)

        if mentioned and not in_conversation:
            self._activate(user_id)
            return AIState(True, "user_mention", False)

        if in_conversation:
            self._touch(user_id)
            return AIState(True, "conversation_active", True)

        last = self.last_interaction.get(user_id, 0)
        if not is_admin and (now - last) < self.cooldown:
            return AIState(False, "cooldown")

        return AIState(False, "ignore")

    def _activate(self, user_id: int):
        self.active_conversations.add(user_id)
        self.last_interaction[user_id] = time.time()

    def _touch(self, user_id: int):
        self.last_interaction[user_id] = time.time()

    def end_conversation(self, user_id: int):
        self.active_conversations.discard(user_id)
