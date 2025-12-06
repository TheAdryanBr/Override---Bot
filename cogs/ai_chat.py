# cogs/ai_chat.py
import discord
from discord.ext import commands
import asyncio
import random
import time
import openai

# ======================
# CONFIGURAÇÕES DO BOT
# ======================

OPENAI_API_KEY = "SUA_KEY_AQUI"
openai.api_key = OPENAI_API_KEY

CHANNEL_MAIN = 1261154588766244905

OWNER_ID = 1213326641833705552
ADM_IDS = {1213534921055010876, OWNER_ID}

SPECIAL_USERS = {
    1436068859991036096: "JM",  # JM_021
}

# Delay para juntar mensagens separadas
BUFFER_DELAY_RANGE = (5, 15)

# Tempo parado para encerrar conversa
END_CONVO_MIN = 15 * 60
END_CONVO_MAX = 20 * 60

# Cooldown para começar outra conversa
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
    # Função auxiliar GPT
    # ======================

    async def ask_gpt(self, prompt):
        """Envia a mensagem para o GPT e retorna a resposta textual."""
        try:
            response = openai.ChatCompletion.create(
                model="gpt-4.1",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=250,
                temperature=0.9
            )
            return response["choices"][0]["message"]["content"]
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

        # ——————————————
        # Se marcado → responde sempre
        # ——————————————
        if self.bot.user in message.mentions:
            asyncio.create_task(self.respond_to_message(message, force_reply=True))
            return

        # ——————————————
        # Somente canal principal inicia conversas
        # ——————————————
        if message.channel.id != CHANNEL_MAIN:
            return

        # Dono ou ADM não iniciam conversa
        if message.author.id in ADM_IDS:
            return

        # Está em cooldown?
        if msg_time < self.cooldown_until:
            return

        # Atualiza última mensagem de conversa
        self.last_message_time = msg_time

        # Ativa conversa se ainda não ativa
        if not self.active:
            self.active = True

        # Adiciona ao buffer
        self.buffer.append(message)

        # Inicia delay humano para analisar mensagens
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

        # Verifica encerramento por inatividade
        now = time.time()
        if self.last_message_time and (now - self.last_message_time > random.randint(END_CONVO_MIN, END_CONVO_MAX)):
            await self.end_conversation()
            return

        # Monta prompt
        prompt = self.build_prompt(self.buffer)
        self.buffer.clear()

        # Responde no canal
        response = await self.ask_gpt(prompt)

        # Pequeno delay humano antes de enviar
        await asyncio.sleep(random.randint(5, 10))

        channel = self.bot.get_channel(CHANNEL_MAIN)
        if channel:
            await channel.send(response)

    # ======================
    # Construção da personalidade
    # ======================

    def build_prompt(self, messages):
        """Cria o prompt contendo estilo A/B/C, regras, humor e lógica do JM."""

        texto_chat = "\n".join([f"{m.author.display_name}: {m.content}" for m in messages])

        # Detecta se o JM está envolvido
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

SOBRE O USUÁRIO ESPECÍFICO “JM”:
- ID: 1436068859991036096
- Ele é tímido, vive enrolado com mulheres.
- Você sempre fica **na dúvida** (apenas na dúvida) se ele gosta de homens.
- NUNCA afirme explicitamente.
- Use isso como humor indireto.
- Suas respostas para ele podem ser um mix mais forte de análise técnica + zoeira leve.
- Pode chamá-lo diretamente pelo nome se a resposta for só para ele.

AGORA, ESTE É O CHAT:

{texto_chat}

Analise toda a conversa e responda usando o estilo que fizer mais sentido no momento.
Se o JM estiver envolvido, use uma pitada extra de humor técnico.
Sua resposta deve ser NATURAL, leve e fluida.
        """

        return prompt.strip()

    # ======================
    # Resposta quando marcado
    # ======================

    async def respond_to_message(self, message, force_reply=False):
        prompt = self.build_prompt([message])
        response = await self.ask_gpt(prompt)

        # Delay humano
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
