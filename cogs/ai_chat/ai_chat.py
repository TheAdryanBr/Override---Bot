import time
import random
import asyncio
from typing import List, Dict, Any, Optional

import discord
from discord.ext import commands

from ai_client import AIClient
from ai_state import AIStateManager
from utils import (
    is_admin_member,
    now_ts,
    CHANNEL_MAIN,
)

# ─────────────────────────────
# Constantes seguras (evitam crash)
# ─────────────────────────────
COOLDOWN_MIN = 20
COOLDOWN_MAX = 40
END_CONVO_MIN = 120
END_CONVO_MAX = 240


class AIChatCog(commands.Cog):
    """Cog de chat com IA: buffer, estado mental e resposta humanizada."""

    def __init__(self, bot: commands.Bot, memory=None):
        self.bot = bot

        # Buffer de mensagens
        self.buffer: List[Dict[str, Any]] = []
        self.buffer_task: Optional[asyncio.Task] = None

        # Estado da conversa
        self.active: bool = False
        self.cooldown_until: float = 0.0
        self.last_response_text: Optional[str] = None
        self.last_response_ts: float = 0.0
        self.last_state = None

        # Gerenciador de estado mental
        self.state_manager = AIStateManager(
            owner_id=473962013031399425,
            admin_role_id=1213534921055010876,
            cooldown=30,
            memory=memory
        )

        # Cliente IA
        self.ai_client = AIClient(
            api_key="SUA_KEY_AQUI",
            system_prompt="INSTRUÇÕES DA IA AQUI",
            primary_models=["gpt-5.1", "gpt-5.1-mini"],
            fallback_models=["gpt-4.1", "gpt-4o-mini"],
        )

    # ─────────────────────────────
    # CORE LOOP
    # ─────────────────────────────

    async def process_buffer(self):
        """Processa mensagens acumuladas respeitando o estado mental."""

        if not self.buffer or not self.active:
            self.buffer.clear()
            return

        entries = list(self.buffer)
        self.buffer.clear()

        state = self.last_state
        if not state or not state.should_respond:
            return

        prompt = self.build_prompt(entries, state)

        try:
            response = await self.ai_client.ask([
                {"role": "user", "content": prompt}
            ])
        except Exception as e:
            print(f"[AIChat] Erro IA: {e}")
            return

        delay = random.uniform(
            0.8 * state.patience_level,
            1.6 * state.patience_level
        )
        await asyncio.sleep(delay)

        await self.send_response(response)

    async def send_response(self, response: str):
        channel = self.bot.get_channel(CHANNEL_MAIN)
        if not channel:
            return

        await channel.send(response)
        self.last_response_text = response
        self.last_response_ts = now_ts()

    # ─────────────────────────────
    # PROMPT
    # ─────────────────────────────

    def build_prompt(self, entries: List[Dict[str, Any]], state) -> str:
        texto_chat = "\n".join(
            f"{e['author_display']}: {e['content']}" for e in entries
        )

        tone_instruction = {
            "normal": "Responda de forma natural e fluida.",
            "seco": "Seja direto, curto e sem enrolação.",
            "sarcastico": "Use ironia leve e humor frio."
        }.get(state.tone, "Responda de forma natural.")

        patience_instruction = {
            1: "Explique normalmente.",
            2: "Seja mais objetivo.",
            3: "Mostre pouca paciência.",
            4: "Responda o mínimo possível para encerrar."
        }.get(state.patience_level, "")

        return (
            f"{tone_instruction}\n"
            f"{patience_instruction}\n\n"
            f"Conversa:\n{texto_chat}\n\n"
            "Gere apenas UMA resposta curta, sem explicações extras."
        )

    # ─────────────────────────────
    # LISTENER
    # ─────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        if message.channel.id != CHANNEL_MAIN:
            return

        state = self.state_manager.evaluate(message, self.bot.user)
        self.last_state = state

        if not state.should_respond:
            return

        if not self.active:
            self.active = True

        entry = {
    "author_id": message.author.id,
    "author_display": message.author.display_name,
    "content": message.content,
    "ts": now_ts(),
    "state": state  # 👈 estado viaja com a mensagem
}

        self.buffer.append(entry)

        if not self.buffer_task or self.buffer_task.done():
            self.buffer_task = asyncio.create_task(self.process_buffer())

    # ─────────────────────────────
    # CONVERSA
    # ─────────────────────────────

    def should_end_conversation(self) -> bool:
        if not self.last_response_ts:
            return False

        return (
            now_ts() - self.last_response_ts
            > random.randint(END_CONVO_MIN, END_CONVO_MAX)
        )

    async def end_conversation(self):
        self.active = False
        self.buffer.clear()

        cooldown = random.randint(COOLDOWN_MIN, COOLDOWN_MAX)
        self.cooldown_until = now_ts() + cooldown

    # ─────────────────────────────
    # SLASH COMMAND
    # ─────────────────────────────

    @commands.hybrid_command(
        name="ai_status",
        with_app_command=True,
        description="Mostrar status do AI (ADM apenas)."
    )
    @commands.check(lambda ctx: is_admin_member(ctx.author))
    async def ai_status(self, ctx: commands.Context):
        emb = discord.Embed(
            title="AI Chat Status",
            color=discord.Color.blurple()
        )

        emb.add_field(name="Ativo", value=str(self.active))
        emb.add_field(
            name="Última resposta",
            value=(self.last_response_text[:400] + "...")
            if self.last_response_text else "—"
        )

        await ctx.reply(embed=emb, ephemeral=True)
