import random
import time
import discord
from discord.ext import commands

from .ai_engine import AIEngine
from .message_buffer import MessageBuffer

# ===== CONFIG =====

ALLOWED_CHANNELS = {
    123456789012345678,  # ID do canal permitido
}

COOLDOWN_MIN = 40 * 60
COOLDOWN_MAX = 2 * 60 * 60
RARE_CHANCE = 0.01
FADING_THRESHOLD = 3

# ==================


class ConversationBlock:
    def __init__(self, author_id: int):
        self.author_id = author_id
        self.state = "ACTIVE"
        self.weak_count = 0

    def add_message(self, content: str):
        if self._is_weak(content):
            self.weak_count += 1
        else:
            self.weak_count = 0

        if self.weak_count >= FADING_THRESHOLD:
            self.state = "FADING"

    def _is_weak(self, content: str) -> bool:
        c = content.lower().strip()
        return len(c) <= 4 or c in {"kkk", "kkkk", "rs", "rsrs", "hm", "uh"}

    def should_end(self) -> bool:
        return self.state == "FADING" and self.weak_count >= (FADING_THRESHOLD + 1)


class ConversationBlockManager:
    def __init__(self):
        self.block = None
        self.cooldown_until = 0.0

    def in_cooldown(self) -> bool:
        return time.time() < self.cooldown_until

    def start_cooldown(self):
        self.cooldown_until = time.time() + random.randint(COOLDOWN_MIN, COOLDOWN_MAX)

    def clear_cooldown(self):
        self.cooldown_until = 0.0

    def can_user_invoke(self, is_admin: bool) -> bool:
        if not self.in_cooldown():
            return True
        if is_admin:
            self.clear_cooldown()
            return True
        return random.random() < RARE_CHANCE

    def receive_message(self, author_id: int, content: str) -> str:
        if not self.block:
            self.block = ConversationBlock(author_id)
            self.block.add_message(content)
            return "RESPOND"

        if self.block.author_id != author_id:
            return "IGNORE"

        self.block.add_message(content)

        if self.block.should_end():
            self.block = None
            self.start_cooldown()
            return "END"

        return "RESPOND"


class AIChat(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.manager = ConversationBlockManager()

        self.buffer = MessageBuffer(max_messages=8)

        # 🔹 INSTÂNCIA CORRETA DO AIEngine
        self.engine = AIEngine(
            primary_models=[
                "gpt-4.1-mini",   # rápido / barato
            ],
            fallback_models=[
                "gpt-4.1",
            ],
            max_output_tokens=220,
            temperature=0.55,
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        if message.channel.id not in ALLOWED_CHANNELS:
            return

        if not self._is_direct_call(message):
            return

        is_admin = self._is_admin(message.author)

        if not self.manager.can_user_invoke(is_admin):
            return

        self.buffer.add_message(
            author=message.author.display_name,
            content=message.content
        )

        action = self.manager.receive_message(
            message.author.id,
            message.content
        )

        if action == "RESPOND":
            await self._send_ai_response(message)

        elif action == "END":
            farewell = random.choice([
                "vou indo, trabalho chamou.",
                "tenho coisa pra resolver no spawnpoint.",
                "o trabalho tá me chamando, infelizmente."
            ])
            await message.channel.send(farewell)


async def setup(bot: commands.Bot):
    await bot.add_cog(AIChat(bot))