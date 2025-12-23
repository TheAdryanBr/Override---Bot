# cogs/ai_chat/context_interpreter.py
import re
from typing import List
import discord

from .intent_result import IntentResult


class ContextInterpreter:
    DIRECT_CALL_WORDS = ["override"]
    INDIRECT_CALL_WORDS = ["vc", "você", "tu", "teu", "contigo"]
    CONTINUATION_WORDS = ["então", "mas", "pq", "porque", "tipo", "assim"]

    def interpret(
        self,
        message: discord.Message,
        bot_user: discord.User,
        recent_messages: List[discord.Message]
    ) -> IntentResult:

        content = message.content.lower()
        score = 0.0
        reason = "ignore"

        # 1. Mention direta
        if bot_user in message.mentions:
            return IntentResult(
                True,
                1.0,
                "direct_mention",
                message.author.id
            )

        # 2. Nome citado sem mention
        if any(word in content for word in self.DIRECT_CALL_WORDS):
            score += 0.6
            reason = "name_called"

        # 3. Indiretas (vc, tu, você)
        if any(re.search(rf"\b{w}\b", content) for w in self.INDIRECT_CALL_WORDS):
            score += 0.25
            reason = "indirect_reference"

        # 4. Continuação de algo que o bot falou
        if recent_messages:
            last = recent_messages[-1]
            if last.author.id == bot_user.id:
                score += 0.3
                reason = "continuation_after_bot"

        # 5. Mensagens quebradas (mesmo autor, pouco tempo)
        if recent_messages:
            last = recent_messages[-1]
            if (
                last.author.id == message.author.id
                and (message.created_at.timestamp() - last.created_at.timestamp()) < 6
            ):
                score += 0.2
                reason = "message_split"

        is_for_me = score >= 0.55

        tone = None
        patience = 0

        if score >= 0.75:
            tone = "normal"
        elif score >= 0.6:
            tone = "analytic"
        elif score >= 0.55:
            tone = "sarcastic"
            patience += 1

        return IntentResult(
            is_probably_for_me=is_for_me,
            confidence=min(score, 1.0),
            reason=reason,
            user_id=message.author.id,
            suggested_tone=tone,
            patience_delta=patience
        )
