# ai_state.py
import time

class AIState:
    def __init__(
        self,
        should_respond: bool,
        reason: str,
        allow_override: bool = False
    ):
        self.should_respond = should_respond
        self.reason = reason
        self.allow_override = allow_override


class AIStateManager:
    def __init__(
        self,
        owner_id: int,
        admin_role_id: int,
        cooldown: int = 30
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

    def evaluate(self, message, bot_user):
        user_id = message.author.id
        now = time.time()

        is_admin = self.is_admin(message.author)
        mentioned = bot_user in message.mentions
        in_conversation = user_id in self.active_conversations

        # 🔒 Cooldown
        last = self.last_interaction.get(user_id, 0)
        if not is_admin and not in_conversation:
            if now - last < self.cooldown:
                return AIState(False, "cooldown")

        # 🔒 ADM sempre pode iniciar com mention
        if is_admin and mentioned:
            self._activate(user_id)
            return AIState(True, "admin_mention", allow_override=True)

        # 🔒 Usuário comum só inicia se cooldown OK
        if not in_conversation:
            if mentioned:
                self._activate(user_id)
                return AIState(True, "user_mention_start")
            return AIState(False, "not_in_conversation")

        # 🔓 Conversa ativa → comportamento humano
        if in_conversation:
            self._touch(user_id)
            return AIState(True, "conversation_active", allow_override=True)

        return AIState(False, "default_block")

    def _activate(self, user_id):
        self.active_conversations.add(user_id)
        self.last_interaction[user_id] = time.time()

    def _touch(self, user_id):
        self.last_interaction[user_id] = time.time()

    def end_conversation(self, user_id):
        self.active_conversations.discard(user_id)
