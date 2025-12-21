print("[AI_CHAT] import iniciado")

import random
import asyncio
from typing import List, Dict, Any, Optional

import discord
from discord.ext import commands

from .ai_state import AIStateManager
from utils import is_admin_member, now_ts, CHANNEL_MAIN
from .ai_client import AIClient

# ─────────────────────────────
# Constantes
# ─────────────────────────────
COOLDOWN_MIN = 20
COOLDOWN_MAX = 40
BUFFER_DELAY = (1.5, 3.0)


class AIChatCog(commands.Cog):
    """Cog principal do chat com IA"""

    def __init__(self, bot: commands.Bot, memory=None):
        self.bot = bot

        self.buffer: List[Dict[str, Any]] = []
        self.buffer_task: Optional[asyncio.Task] = None

        self.active = False
        self.cooldown_until = 0.0
        self.last_response_ts = 0.0
        self.last_response_text: Optional[str] = None
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

    # ─────────────────────────────
    # BUFFER
    # ─────────────────────────────

    async def process_buffer(self):
        await asyncio.sleep(random.uniform(*BUFFER_DELAY))

        if not self.active or not self.buffer:
            self.buffer.clear()
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
            print(f"[AIChat] Erro IA: {e}")
            return

        delay = random.uniform(
            0.6 * state.patience_level,
            1.4 * state.patience_level
        )
        await asyncio.sleep(delay)

        await self.send_response(response)
        await self.end_conversation()

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

        tone = {
            "normal": "Responda de forma natural e fluida.",
            "seco": "Seja direto, curto e sem enrolação.",
            "sarcastico": "Use ironia leve e humor frio."
        }.get(state.tone, "Responda de forma natural.")

        patience = {
            1: "Explique normalmente.",
            2: "Seja mais objetivo.",
            3: "Mostre pouca paciência.",
            4: "Responda o mínimo possível para encerrar."
        }.get(state.patience_level, "")

        return (
            f"{tone}\n"
            f"{patience}\n\n"
            f"Conversa:\n{texto_chat}\n\n"
            "Gere apenas UMA resposta curta."
        )

    # ─────────────────────────────
    # LISTENER
    # ─────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        print("[AI_CHAT] on_message:", message.content)

        if message.author.bot:
            return

        if message.channel.id != CHANNEL_MAIN:
            return

        state = self.state_manager.evaluate(message, self.bot.user)
        self.last_state = state
        self.last_user_id = message.author.id

        # 🔥 override (ADM/Dono ou conversa ativa)
        if state.allow_override:
            self.state_manager._activate(message.author.id)

            prompt = self.build_prompt(
                [{
                    "author_display": message.author.display_name,
                    "content": message.content
                }],
                state
            )

            try:
                response = await self.ai_client.ask(
                    [{"role": "user", "content": prompt}]
                )
                await self.send_response(response)
            except Exception as e:
                print(f"[AIChat] Erro override: {e}")

            return

        # ⏳ cooldown global do chat
        if now_ts() < self.cooldown_until:
            return

        if not state.should_respond:
            return

        # sincroniza conversa
        self.active = True
        self.state_manager._activate(message.author.id)

        self.buffer.append({
            "author_id": message.author.id,
            "author_display": message.author.display_name,
            "content": message.content,
            "ts": now_ts()
        })

        if not self.buffer_task or self.buffer_task.done():
            self.buffer_task = asyncio.create_task(self.process_buffer())

    # ─────────────────────────────
    # CONVERSA
    # ─────────────────────────────

    async def end_conversation(self):
        self.active = False
        self.buffer.clear()

        if self.last_user_id:
            self.state_manager.end_conversation(self.last_user_id)

        self.cooldown_until = now_ts() + random.randint(
            COOLDOWN_MIN, COOLDOWN_MAX
        )

    # ─────────────────────────────
    # STATUS
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
            value=self.last_response_text[:400]
            if self.last_response_text else "—"
        )

        await ctx.reply(embed=emb, ephemeral=True)


async def setup(bot):
    await bot.add_cog(AIChatCog(bot))
