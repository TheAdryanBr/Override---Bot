# cogs/ai_chat.py
import discord
from discord.ext import commands
import asyncio
import random
import time
import openai

# =============================
# CONFIGURAÇÕES DO SISTEMA
# =============================

CANAL_CONVERSA_ID = 1261154588766244905

# tempos:
DELAY_ANALISE_MIN = 5
DELAY_ANALISE_MAX = 15

TEMPO_PARADO_MIN = 15 * 60      # 15 minutos
TEMPO_PARADO_MAX = 20 * 60      # 20 minutos

COOLDOWN_MIN = 45 * 60          # 45 min
COOLDOWN_MAX = 120 * 60         # 2h

# configure sua API key POLITICAMENTE fora do código se possível
openai.api_key = "SUA_OPENAI_KEY_AQUI"


class AIChat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.buffer = []                # mensagens acumuladas antes de responder
        self.ultima_msg = 0             # timestamp da última mensagem ativa
        self.conversa_ativa = False     # se está no meio de uma conversa
        self.cooldown_ate = 0           # timestamp de quando o cooldown termina
        self.delay_task = None          # task para resposta com delay

    # Verifica se user é ADM
    def is_admin(self, member: discord.Member):
        return member.guild_permissions.administrator

    # Verifica se está dentro do cooldown
    def in_cooldown(self):
        return time.time() < self.cooldown_ate

    # Define cooldown aleatório
    def start_cooldown(self):
        self.cooldown_ate = time.time() + random.randint(COOLDOWN_MIN, COOLDOWN_MAX)
        self.conversa_ativa = False
        self.buffer.clear()
        self.ultima_msg = 0

    # Gerador de delay humano
    async def human_delay(self):
        await asyncio.sleep(random.randint(DELAY_ANALISE_MIN, DELAY_ANALISE_MAX))

    # ======================================================
    # EVENTO DE MENSAGENS
    # ======================================================
    @commands.Cog.listener()
    async def on_message(self, msg: discord.Message):

        # Ignorar bots
        if msg.author.bot:
            return

        agora = time.time()

        # Se está no cooldown -> ignorar tudo
        if self.in_cooldown():
            return

        # Modo padrão: apenas canal de conversa
        permitido = False

        if msg.channel.id == CANAL_CONVERSA_ID:
            permitido = True

        # Permitir em outros canais apenas se ADM marcar o bot
        elif msg.mentions and any(m.id == self.bot.user.id for m in msg.mentions):
            if self.is_admin(msg.author):
                permitido = True

        if not permitido:
            return

        # Atualiza atividade
        self.ultima_msg = agora

        # Adiciona mensagem ao buffer
        self.buffer.append(f"{msg.author.display_name}: {msg.content}")

        # Se já existe task pendente, cancela para reiniciar o delay
        if self.delay_task and not self.delay_task.done():
            self.delay_task.cancel()

        # Inicia task de resposta
        self.delay_task = asyncio.create_task(self.processar_resposta(msg.channel))

    # ======================================================
    # PROCESSAMENTO DA RESPOSTA
    # ======================================================
    async def processar_resposta(self, channel: discord.TextChannel):
        try:
            # Delay humano antes de analisar
            await self.human_delay()

            # Se o chat ficou parado por mais de 20 min -> termina conversa
            if self.ultima_msg != 0:
                if time.time() - self.ultima_msg > random.randint(TEMPO_PARADO_MIN, TEMPO_PARADO_MAX):
                    self.start_cooldown()
                    return

            # Prepara prompt para IA
            prompt = self.build_prompt()

            resposta = await self.gerar_resposta(prompt)

            if resposta:
                await channel.send(resposta)

            # conversa ativa continua
            self.conversa_ativa = True

            # reiniciar contagem de inatividade
            self.ultima_msg = time.time()

            # limpa buffer
            self.buffer.clear()

        except asyncio.CancelledError:
            pass
        except Exception as e:
            print("Erro IA:", e)

    # ======================================================
    # MODELO DE PERSONALIDADE
    # ======================================================
    def build_prompt(self):
        return f"""
Você é um bot de chat de Discord com uma personalidade muito marcante. 
Regras da sua personalidade:

A) Extrovertido, animado, meio maluco de propósito, fala com energia mas não exagera.
B) Sarcástico leve, engraçado, dá pequenas zoeiras quando percebe uma brecha.
C) Analítico, mas de um jeito cômico — análises técnicas que viram piada.

Outros comportamentos importantes:
- Pode dar uma pequena zoada no dono (Adryan) quando tiver chance, ou usar as brechas dele para zoar outras pessoas.
- Responde como se estivesse realmente dentro da conversa.
- Nada de ser formal.
- Usa linguagem leve como “mano”, “ué”, “oxe”, “que viagem é essa?”.
- Quando você encontrar uma brecha, pode provocar alguém de forma engraçada (nunca ofensiva).
- Não imite “parça” ou “mano do grau”, mantenha natural.
- Quando pedirem pra você fazer algo muito chato, você pode recusar de forma criativa.
- NÃO fale como se fosse IA, fale como um usuário do Discord.

Agora veja o contexto das mensagens recentes:

{chr(10).join(self.buffer)}

Com base nisso, escolha automaticamente qual estilo (A, B ou C) encaixa melhor.
Depois escreva uma única resposta natural como se estivesse participando da conversa.
"""

    # ======================================================
    # OPENAI – geração de texto
    # ======================================================
    async def gerar_resposta(self, prompt: str):
        try:
            resposta = await openai.ChatCompletion.acreate(
                model="gpt-5.1",  # usa o que estiver disponível
                messages=[{"role": "user", "content": prompt}],
                max_tokens=250,
                temperature=0.8,
            )
            return resposta["choices"][0]["message"]["content"]
        except Exception as e:
            print("Erro OpenAI:", e)
            return None


async def setup(bot):
    await bot.add_cog(AIChat(bot))
