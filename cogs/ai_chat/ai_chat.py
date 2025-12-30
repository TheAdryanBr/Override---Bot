# ai_chat.py
import asyncio
import random
import discord
from discord.ext import commands

from .ai_state import AIStateManager
from .ai_engine import AIEngine
from .message_buffer import MessageBuffer
from .ai_decision import AIDecision
from utils import CHANNEL_MAIN, now_ts


LOW_EFFORT_PATTERNS = [
    "faz pra mim", "pode fazer", "me ajuda", "cria um", "monta um", "faz ai"
]


def should_auto_refuse(text: str) -> bool:
    text = text.lower()
    return any(p in text for p in LOW_EFFORT_PATTERNS)


def sanitize(text: str) -> str:
    banned = ("claro", "com prazer", "fico feliz", "posso ajudar")
    for b in banned:
        if text.lower().startswith(b):
            return text[len(b):].lstrip(" ,.!?") or "Hm."
    return text


def hard_cut(text: str) -> str:
    text = text.split("\n")[0]
    if text.count(".") > 1:
        text = text.split(".", 1)[0]
    return text.strip()


class AIChatCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

        self.state = AIStateManager(
            owner_id=473962013031399425,
            admin_role_id=1213534921055010876,
            cooldown=30,
        )

        self.engine = AIEngine(primary_models=["gpt-4o-mini"])
        self.buffer = MessageBuffer(max_messages=12)
        self.decision = AIDecision()

        self.processing = False
        self.last_response_ts = 0.0

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if message.channel.id != CHANNEL_MAIN:
            return

        state = self.state.evaluate(message, self.bot.user)
        if not state.should_respond:
            return

        if random.random() < 0.12:
            return

        if should_auto_refuse(message.content):
            await message.channel.send(random.choice([
                "Não.", "Agora não.", "Nop.", "Sai fora."
            ]))
            return

        self.buffer.add_user_message(
            author_id=message.author.id,
            author_name=message.author.display_name,
            content=message.content,
        )

        if self.processing:
            return

        self.processing = True
        await asyncio.sleep(random.uniform(0.8, 1.6))

        try:
            await self._reply(message.channel)
        finally:
            self.processing = False

    async def _reply(self, channel: discord.TextChannel):
        entries = [
            {
                "author_display": m["author_name"],
                "content": m["content"],
            }
            for m in self.buffer.get_messages()
            if m["role"] == "user"
        ]

        if not entries:
            return

        response = await self.engine.generate_response(entries)
        response = hard_cut(sanitize(response))

        await channel.send(response)

        self.buffer.add_assistant_message(response)
        self.last_response_ts = now_ts()


async def setup(bot: commands.Bot):
    await bot.add_cog(AIChatCog(bot))
