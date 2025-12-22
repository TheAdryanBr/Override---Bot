# cogs/ai_chat/ai_chat.py
import asyncio
import random
from typing import Optional

import discord
from discord.ext import commands

from .ai_state import AIStateManager
from .ai_engine import AIEngine
from .message_buffer import MessageBuffer
from .ai_prompt import build_prompt
from utils import CHANNEL_MAIN, now_ts


class AIChatCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

        # ======================
        # CORE COMPONENTS
        # ======================
        self.state = AIStateManager(
            owner_id=473962013031399425,
            admin_role_id=1213534921055010876,
            cooldown=30,
        )

        self.engine = AIEngine(
            system_prompt="",  # já incluso no ai_prompt
            primary_models=["gpt-5.1", "gpt-5.1-mini"],
            fallback_models=["gpt-4.1", "gpt-4o-mini"],
        )

        self.buffer = MessageBuffer(max_messages=12)

        # ======================
        # CONTROLE
        # ======================
        self.processing: bool = False
        self.last_response_ts: float = 0.0

    # ─────────────────────────────
    # LISTENER
    # ─────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        if message.channel.id != CHANNEL_MAIN:
            return

        # decisão única
        state = self.state.evaluate(message, self.bot.user)

        if not state.should_respond:
            return

        # adiciona ao buffer
        self.buffer.add_user_message(
            f"{message.author.display_name}: {message.content}"
        )

        # evita corrida
        if self.processing:
            return

        self.processing = True

        # pequeno atraso humano
        await asyncio.sleep(random.uniform(0.8, 2.0))

        try:
            await self._generate_and_send(message.channel)
        finally:
            self.processing = False

    # ─────────────────────────────
    # RESPOSTA
    # ─────────────────────────────

    async def _generate_and_send(self, channel: discord.TextChannel):
        if self.buffer.is_empty():
            return

        entries = [
            {
                "author_display": "chat",
                "content": m["content"]
            }
            for m in self.buffer.get_messages()
        ]

        prompt = build_prompt(entries)

        try:
            response = await self.engine.generate_response(entries)
        except Exception as e:
            return

        if not response:
            return

        await channel.send(response)

        self.buffer.add_assistant_message(response)
        self.last_response_ts = now_ts()

    # ─────────────────────────────
    # STATUS
    # ─────────────────────────────

    @commands.command(name="ai_status")
    @commands.has_permissions(administrator=True)
    async def ai_status(self, ctx: commands.Context):
        await ctx.send(
            f"🧠 AI ativo\n"
            f"Buffer: {self.buffer.size()} msgs\n"
            f"Última resposta: <t:{int(self.last_response_ts)}:R>"
            if self.last_response_ts else "—"
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(AIChatCog(bot))
