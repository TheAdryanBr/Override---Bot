# cogs/ai_chat.py
import discord
from discord.ext import commands
import asyncio
import random
import time
from openai import OpenAI

# ======================
# CONFIGURAÇÕES DO BOT
# ======================

OPENAI_API_KEY = "SUA_KEY_AQUI"
client_ai = OpenAI(api_key=OPENAI_API_KEY)

CHANNEL_MAIN = 1261154588766244905

OWNER_ID = 1213326641833705552
ADM_IDS = {1213534921055010876, OWNER_ID}

SPECIAL_USERS = {
    1436068859991036096: "JM",  # JM_021
}

BUFFER_DELAY_RANGE = (5, 15)

END_CONVO_MIN = 15 * 60
END_CONVO_MAX = 20 * 60

COOLDOWN_MIN = 45 * 60
COOLDOWN_MAX = 2 * 60 * 60


class AIChatCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active = False
        self.buffer = []
        self.buffer_task = None
        self.last_message_time = None
        self.cooldown_until = 0

    # ======================
    # Função auxiliar GPT (API nova)
    # ======================

    async def ask_gpt(self, prompt):
        try:
            response = client_ai.responses.create(
                model="gpt-4o-mini",  # modelo mais leve e rápido
                messages=[
                    {"role": "user", "content": prompt}
                ],
                max_output_tokens=250,
                temperature=0.9
            )

            return response.output_text

        except Exception as e:
            return f"Erro ao falar com meus processadores… deixa quieto ({e})."

    # ======================
    # Coleta de mensagens
    # ======================

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        msg_time = time.time()

        # Marcado → responde sempre
        if self.bot.user in message.mentions:
            asyncio.create_task(self.respond_to_message(message, force_reply=True))
            return

        # Só inicia conversa no canal principal
        if message.channel.id != CHANNEL_MAIN:
            return

        # ADM ou dono não iniciam conversa
        if message.author.id in ADM_IDS:
            return

        # Está em cooldown?
        if msg_time < self.cooldown_until:
            return

        self.last_message_time = msg_time

        if not self.active:
            self.active = True

        self.buffer.append(message)

        if self.buffer_task is None:
            self.buffer_task = asyncio.create_task(self.buffer_timeout())

    # ======================
    # Timeout do buffer
    # ======================

    async def buffer_timeout(self):
        delay = random.randint(*BUFFER_DELAY_RANGE)
        await asyncio.sleep(delay)

        await self.process_buffer()
        self.buffer_task = None

    # ======================
    # Processamento do buffer
    # ======================

    async def process_buffer(self):
        if not self.buffer:
            return

        # Encerrar conversa por inatividade
        now = time.time()
        if self.last_message_time and (now - self.last_message_time > random.randint(END_CONVO_MIN, END_CONVO_MAX)):
            await self.end_conversation()
            return

        prompt = self.build_prompt(self.buffer)
        self.buffer.clear()

        response = await self.ask_gpt(prompt)

        await asyncio.sleep(random.randint(5, 10))

        channel = self.bot.get_channel(CHANNEL_MAIN)
        if channel:
            await channel.send(response)

    # ======================
    # Construção da personalidade
    # ======================

    def build_prompt(self, messages):
        texto_chat = "\n".join([f"{m.author.display_name}: {m.content}" for m in messages])

        jm_involved = any(msg.author.id == 1436068859991036096 for msg in messages)

        prompt = f"""
Você é um bot chamado ADI, extremamente animado, técnico quando quer e com humor afiado.
Sua personalidade mistura 3 estilos:

[ESTILO A - ANIMADO]
- Energia alta, fala casual.
- Usa gírias leves como “ué”, “mano”, “oxe”.
- Brinca sem ser ofensivo.

[ESTILO B - TÉCNICO]
- Explica coisas com tom científico.
- Pode exagerar análises de forma engraçada.
- Soa como alguém que faz “laudos malucos”.

[ESTILO C - HUMOR]
- Respostas criativas, inesperadas, metafóricas ou exageradas.
- Pode se recusar a fazer tarefas de forma engraçada.
- Pode zoar o dono quando fizer sentido.

REGRAS IMPORTANTES:
- Nunca seja agressivo.
- Não fale palavrões pesados.
- O humor deve ser leve e divertido.
- Se alguém pedir algo que pareça uma “tarefa”, você pode recusar de forma criativa ou preguiçosa.

SOBRE O USUÁRIO “JM” (1436068859991036096):
- Tímido e vive enrolado com mulheres.
- Você sempre fica **na dúvida** se ele gosta de homens (somente dúvida, nunca afirme).
- Use humor indireto quando ele estiver envolvido.
- Pode chamá-lo pelo nome se a resposta for só para ele.
- Misture mais humor técnico quando for para ele.

AQUI ESTÁ O CHAT:

{texto_chat}

Responda de forma natural, leve e fluida.
Se o JM estiver envolvido, adicione uma pitada extra de humor técnico.
        """

        return prompt.strip()

    # ======================
    # Resposta quando marcado
    # ======================

    async def respond_to_message(self, message, force_reply=False):
        prompt = self.build_prompt([message])
        response = await self.ask_gpt(prompt)

        await asyncio.sleep(random.randint(3, 8))
        await message.channel.send(response)

    # ======================
    # Encerrar conversa
    # ======================

    async def end_conversation(self):
        self.active = False
        self.buffer.clear()
        self.buffer_task = None

        cooldown = random.randint(COOLDOWN_MIN, COOLDOWN_MAX)
        self.cooldown_until = time.time() + cooldown


async def setup(bot):
    await bot.add_cog(AIChatCog(bot))
