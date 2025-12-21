import random
import asyncio
from typing import List, Dict, Any, Optional

import discord
from discord.ext import commands

from .ai_state import AIStateManager
from .ai_client import AIClient
from utils import CHANNEL_MAIN, now_ts


BUFFER_DELAY = (1.5, 3.0)


class AIChatCog(commands.Cog):
    def __init__(self, bot: commands.Bot, memory=None):
        self.bot = bot

        self.buffer: List[Dict[str, Any]] = []
        self.buffer_task: Optional[asyncio.Task] = None

        self.last_state = None
        self.last_user_id: Optional[int] = None

        self.state_manager = AIStateManager(
            owner_id=473962013031399425,
            admin_role_id=1213534921055010876,
            cooldown=30,
            memory=memory
        )

        self.ai_client = AIClient(
            api_key="SUA_KEY_AQUI",
            system_prompt="INSTRUÇÕES DA IA AQUI",
            primary_models=["gpt-5.1", "gpt-5.1-mini"],
            fallback_models=["gpt-4.1", "gpt-4o-mini"],
        )

    # ----------------------
    # BUFFER
    # ----------------------

    async def process_buffer(self):
        await asyncio.sleep(random.uniform(*BUFFER_DELAY))

        if not self.buffer:
            return

        entries = list(self.buffer)
        self.buffer.clear()

        state = self.last_state
        if not state or not state.should_respond:
            return

        prompt = self.build_prompt(entries, state)

        try:
            response = await self.ai_client.ask(
                [{"role": "user", "content": prompt}]
            )
        except Exception as e:
            print("[AIChat] Erro IA:", e)
            return

        await self.send_response(response)

    async def send_response(self, response: str):
        channel = self.bot.get_channel(CHANNEL_MAIN)
        if not channel:
            print("[AIChat] CHANNEL_MAIN inválido")
            return

        await channel.send(response)

    # ----------------------
    # PROMPT
    # ----------------------

    def build_prompt(self, entries: List[Dict[str, Any]], state) -> str:
        texto = "\n".join(
            f"{e['author_display']}: {e['content']}" for e in entries
        )

        tone = {
            "normal": "Responda de forma natural.",
            "seco": "Responda curto e direto.",
            "sarcastico": "Responda com sarcasmo leve."
        }.get(state.tone, "Responda de forma natural.")

        return (
            f"{tone}\n\n"
            f"Conversa:\n{texto}\n\n"
            "Gere apenas UMA resposta curta."
        )

    # ----------------------
    # LISTENER
    # ----------------------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        if message.channel.id != CHANNEL_MAIN:
            return

        state = self.state_manager.evaluate(message, self.bot.user)
        self.last_state = state
        self.last_user_id = message.author.id

        if not state.should_respond:
            return

        self.buffer.append({
            "author_id": message.author.id,
            "author_display": message.author.display_name,
            "content": message.content,
            "ts": now_ts()
        })

        if not self.buffer_task or self.buffer_task.done():
            self.buffer_task = asyncio.create_task(self.process_buffer())


async def setup(bot):
    await bot.add_cog(AIChatCog(bot))
