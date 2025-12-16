import time
import random
import asyncio
from typing import List, Dict, Any, Optional
import discord
from discord.ext import commands

from ai_client import AIClient
from utils import is_admin_member, now_ts, BUFFER_DELAY_RANGE, CONTEXT_EXPIRE, CHANNEL_MAIN, ADM_IDS, OWNER_ID

class AIChatCog(commands.Cog):
    """Cog de chat com IA: agrupamento, delays dinâmicos, aprendizado simples e fallback de modelos."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.buffer: List[Dict[str, Any]] = []
        self.buffer_task: Optional[asyncio.Task] = None
        self.cooldown_until: float = 0.0
        self.active = False
        self.last_response_text: Optional[str] = None

        # Novo cliente IA
        self.ai_client = AIClient(
            api_key="SUA_KEY_AQUI",
            system_prompt="INSTRUÇÕES DA IA AQUI",
            primary_models=["gpt-5.1", "gpt-5.1-mini"],
            fallback_models=["gpt-4.1", "gpt-4o-mini"]
        )

    async def process_buffer(self):
        """Processa mensagens do buffer, interagindo com o AIClient."""
        if not self.buffer:
            return

        # Verifica se a conversa pode ser encerrada (inatividade)
        if self.should_end_conversation():
            await self.end_conversation()
            return

        # Prepara as mensagens e limpa o buffer
        messages_to_process = list(self.buffer)
        self.buffer.clear()

        # Verifica se a conversa pode começar
        if not self.should_start_conversation(messages_to_process):
            return

        # Monta o prompt para IA e chama o AIClient
        prompt = self.build_prompt(messages_to_process)
        response = await self.ai_client.ask([{"content": prompt}])

        await self.send_response(response)

    async def send_response(self, response: str):
        """Envia a resposta ao canal de acordo com o fluxo."""
        channel = self.bot.get_channel(CHANNEL_MAIN)
        if channel:
            await channel.send(response)
            self.last_response_text = response

    def should_end_conversation(self) -> bool:
        """Determina se a conversa deve ser encerrada por inatividade."""
        now = now_ts()
        if self.last_response_text and (now - self.last_response_text_time) > random.randint(END_CONVO_MIN, END_CONVO_MAX):
            return True
        return False

    def should_start_conversation(self, entries: List[Dict[str, Any]]) -> bool:
        """Decide se o bot deve responder a esse conjunto de entradas."""
        if not entries:
            return False
        last = entries[-1]
        text = last["content"].lower()
        if any(keyword in text for keyword in ["oi", "fala", "preciso de ajuda"]):
            return True
        return False

    def build_prompt(self, entries: List[Dict[str, Any]], state) -> str:
    texto_chat = "\n".join(
        f"{e['author_display']}: {e['content']}" for e in entries
    )

    # 🎭 Tom da resposta
    tone_instruction = {
        "normal": "Responda de forma natural e fluida.",
        "seco": "Seja direto, curto e sem enrolação.",
        "sarcastico": "Use ironia leve, respostas secas e humor frio."
    }.get(state.tone, "Responda de forma natural.")

    # ⏳ Nível de paciência
    patience_instruction = {
        1: "Explique normalmente.",
        2: "Seja mais objetivo.",
        3: "Mostre pouca paciência.",
        4: "Responda o mínimo possível para encerrar."
    }.get(state.patience_level, "")

    prompt = (
        f"{tone_instruction}\n"
        f"{patience_instruction}\n\n"
        f"Conversa:\n{texto_chat}\n\n"
        "Gere apenas UMA resposta curta, sem explicações extras."
    )

    return prompt

    @commands.Cog.listener()
async def on_message(self, message: discord.Message):
    # Ignora bots
    if message.author.bot:
        return

    # Só atua no canal principal
    if message.channel.id != CHANNEL_MAIN:
        return

    # 🧠 Avalia estado mental / permissões
    state = self.state_manager.evaluate(message, self.bot.user)

    if not state.should_respond:
        return

    # Marca conversa como ativa
    if not self.active:
        self.active = True

    # Cria entrada para o buffer
    entry = {
        "author_id": message.author.id,
        "author_display": message.author.display_name,
        "content": message.content,
        "ts": now_ts()
    }

    self.buffer.append(entry)

    # Inicia processamento se não houver task rodando
    if not self.buffer_task or self.buffer_task.done():
        self.buffer_task = asyncio.create_task(self.process_buffer())


# ─────────────────────────────
# Encerrar conversa + cooldown
# ─────────────────────────────
async def end_conversation(self):
    self.active = False
    self.buffer.clear()

    cooldown = random.randint(COOLDOWN_MIN, COOLDOWN_MAX)
    self.cooldown_until = now_ts() + cooldown


# ─────────────────────────────
# Slash command: status
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
