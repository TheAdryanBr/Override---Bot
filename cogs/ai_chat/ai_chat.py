import asyncio
import random

import discord
from discord.ext import commands

from .ai_state import AIStateManager
from .ai_engine import AIEngine
from .message_buffer import MessageBuffer
from utils import CHANNEL_MAIN, now_ts


LOW_EFFORT_PATTERNS = [
    "faz pra mim",
    "pode fazer",
    "me ajuda",
    "cria um",
    "monta um",
    "faz ai",
]


def should_auto_refuse(content: str) -> bool:
    text = content.lower()
    return any(p in text for p in LOW_EFFORT_PATTERNS)


def sanitize_response(text: str) -> str:
    FORBIDDEN_STARTS = (
        "claro",
        "com prazer",
        "fico feliz",
        "posso ajudar",
        "se precisar",
    )

    lower = text.lower()
    for f in FORBIDDEN_STARTS:
        if lower.startswith(f):
            cleaned = text[len(f):].lstrip(" ,.!?")
            return cleaned if cleaned else "Hm."

    return text


def hard_style_cut(text: str) -> str:
    if not text:
        return text

    # corta respostas longas demais
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

        self.engine = AIEngine(
            primary_models=["gpt-4o-mini"],
            fallback_models=[],
        )

        self.buffer = MessageBuffer(max_messages=12)

        self.processing = False
        self.last_response_ts = 0.0

    # ─────────────────────────────
    # LISTENER
    # ─────────────────────────────
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        if message.channel.id != CHANNEL_MAIN:
            return

        state = self.state.evaluate(message, self.bot.user)
        if not state.should_respond:
            return

        # silêncio intencional (override não responde sempre)
        if random.random() < 0.12:
            return

        # evita se meter na conversa de outro usuário
        last_user = self.buffer.get_last_user_id()
        if last_user and last_user != message.author.id and not message.mentions:
            return

        # auto-recusa seca
        if should_auto_refuse(message.content):
            await message.channel.send(random.choice([
                "Não.",
                "Eu passo.",
                "Agora não.",
                "Isso aí não.",
                "Nop.",
                "Sai fora.",
            ]))
            return

        # adiciona ao buffer
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
                "author_display": m.get("author_name", "user"),
                "content": m.get("content", "")
            }
            for m in self.buffer.get_messages()
            if m.get("role") == "user"
        ]

        if not entries:
            return

        try:
            # engine já monta o prompt internamente
            response = await self.engine.generate_response(entries)
        except Exception as e:
            print("[AI_CHAT] erro ao gerar resposta:", e)
            return

        if not response:
            return

        response = sanitize_response(response)
        response = hard_style_cut(response)

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
