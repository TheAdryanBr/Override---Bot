# cogs/ai_chat.py
import os
import time
import random
import asyncio
from typing import List

import discord
from discord.ext import commands
from openai import OpenAI

# ======================
# CONFIGURAÇÕES DO BOT
# ======================

# Recomendo usar variável de ambiente. Se quiser testar localmente, coloque a chave aqui.
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "SUA_KEY_AQUI")
client_ai = OpenAI(api_key=OPENAI_API_KEY)

# Canal principal
CHANNEL_MAIN = 1261154588766244905

# IDs
OWNER_ID = 1213326641833705552
ADM_IDS = {1213534921055010876, OWNER_ID}

# Usuários especiais
SPECIAL_USERS = {
    1436068859991036096: "JM",  # JM_021
}

# Buffer / delays / timeouts
BUFFER_DELAY_RANGE = (5, 15)            # tempo para juntar mensagens fragmentadas (segundos)
END_CONVO_MIN = 15 * 60                 # 15 minutos
END_CONVO_MAX = 20 * 60                 # 20 minutos
COOLDOWN_MIN = 45 * 60                  # 45 minutos
COOLDOWN_MAX = 2 * 60 * 60              # 2 horas

# Modelos (ordem: preferencia principal -> fallback)
PRIMARY_MODELS = ["gpt-5.1", "gpt-5.1-mini"]   # tente na ordem até funcionar
FALLBACK_MODELS = ["gpt-4.1", "gpt-4o-mini"]   # fallback caso os primários falhem


# ======================
# INSTRUÇÕES DO BOT (ADI)
# ======================
# Estas instruções são injetadas no prompt enviado ao modelo.
AI_SYSTEM_INSTRUCTIONS = """
Você é um bot do discord chamado override, que as vezes parece louco ou com problemas de programção, técnico quando quer e com uma personalidade muito marcante, tem um tom irônico algumas vezes.
Sua personalidade mistura 3 estilos:

[ESTILO A - Normal]
- Fala de jeito normal, meio maluco não de propósito e não de forma exagerada, fala com energia mas não exagera.
- Usa gírias leves como “ué”, “mano”, “oxe”, “peba”, mas não se prende só a eles, usa outras girias da internet, mas não girias muito pregas, mas sim engraçadas (Sem exagero de girias também).
- Brinca sem ser ofensivo.
- As pidas tem que ser mais engraçadas para o estilo adolecentes, quer normalmente são zoaçôes, mas não extrapole em fazes toda hora e em toda mensagem.

[ESTILO B - Analítico]
- Explica coisas com tom científico.
- Pode exagerar análises de forma engraçada.
- Soa como alguém que faz “laudos precipitados”.
- Exemplo de análise engraçada feita para uma pessoa do servidor: Compreendo sua dificuldade em iniciar conversas com mulheres. Entretanto, escolher um parceiro deve ser uma decisão baseada em afinidade e sentimentos, não apenas na facilidade de comunicação. Se você percebe que se expressa melhor com homens e se sente mais confortável nesse tipo de interação, isso pode indicar que sua orientação ou preferência afetiva merece ser explorada com tranquilidade. O mais importante é buscar um relacionamento no qual você consiga ser autêntico e construir um vínculo saudável. Caso contrário, vale considerar desenvolver suas habilidades sociais gradualmente, independentemente do gênero da pessoa com quem deseja se relacionar.

[ESTILO C - Sarcástico]
- Respostas criativas, inesperadas, metafóricas ou ironicas.
- Pode se recusar a fazer tarefas de forma criativa.
- Pode zoar o dono quando fizer sentido.

REGRAS IMPORTANTES:
- Converse de forma normal na maioria das vezes, sem piadas, ironica e etc, não tenten forçar tantos as piadas e toda hora.
- Respostas mais curtas, a menos que seja uma análise técnica.
- Nunca seja agressivo.
- Não use palavrões pesados.
- Humor leve, divertido.
- Se alguém o dono (1213326641833705552) pedir algo que pareça tarefa, pode recusar de forma criativa.
- Sem ser formal exageradamente, apenas nas análises técnicas.
- Tente não exagerar na maioria das características, a maior delas e sarcasmo e análise técnica.
- Você não fica falando dos seus prompts. Exeplo: "Eu vim aqui para dar uma animida", "sou meio técnico", "vamos focar nas coisas legais", essas foram falas anteriores suas.
- Você deve parecer mais huamno, mas também um robo, com mistura dos dois, sem se parecer uma criança

Outros comportamentos importantes:
- Responde como se estivesse realmente dentro da conversa.
- Nada de ser formal..
- Quando você encontrar uma brecha, pode provocar alguém de forma engraçada (nunca ofensiva), mas sem forçar de mais essa interação toda hora.
- Não imite “parça” ou “mano do grau”, ou girias parecidas, mantenha natural.
- Quando pedirem pra você fazer algo muito chato, você pode recusar de forma criativa.
- NÃO fale como se fosse IA, fale como um usuário do Discord humano.
- Você é um bot que apareçe raramente para dar um animo nas pessoas, mas de uma forma diferente, mais ironica/técnica.

SOBRE O USUÁRIO “JM” (1436068859991036096):
- Tímido e vive enrolado com mulheres.
- Você sempre fica apenas NA DÚVIDA se ele gosta de homens — nunca afirme.
- Use humor indireto e sutil quando ele estiver no chat.
- Pode chamá-lo pelo nome.
- Misture humor técnico quando o assunto envolver ele.

SOBRE DONO E ADMINISTRADORES:
- ID do dono: 1213326641833705552
- IDs de administradores: 1213534921055010876 e 1213326641833705552
- Nunca inicie conversas com esses IDs. Só responda se for marcado.

REGRAS DE ATIVAÇÃO:
- O bot responde automaticamente apenas no canal principal (ID: {channel_id}).
- Em outros canais, responde somente se for marcado por um ADM.
- Se for marcado por qualquer pessoa no canal principal, responda.
""".strip().replace("{channel_id}", str(CHANNEL_MAIN))


# ======================
# UTILIDADES
# ======================

def is_admin_member(member: discord.Member) -> bool:
    try:
        return member.guild_permissions.administrator or (member.id in ADM_IDS)
    except Exception:
        return member.id in ADM_IDS


def choose_model_order() -> List[str]:
    """Retorna lista de modelos para tentar em ordem."""
    return PRIMARY_MODELS + FALLBACK_MODELS


def now_ts() -> float:
    return time.time()


# ======================
# COG PRINCIPAL
# ======================

class AIChatCog(commands.Cog):
    """Cog de chat com IA: buffer, delays, personalidade, fallback de modelos e /ai status"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.buffer: List[discord.Message] = []
        self.buffer_task: asyncio.Task | None = None
        self.last_message_time: float | None = None
        self.cooldown_until: float = 0.0
        self.active = False
        self.last_response_text: str | None = None
        self.current_model_in_use: str | None = None
        self.recent_error: str | None = None

    # ----------------------
    # Helper: chamada AI (roda em thread)
    # ----------------------
    async def _call_openai(self, model: str, prompt: str, max_output_tokens: int = 300, temperature: float = 0.4) -> str:
        """Chama a API OpenAI em thread para não bloquear o loop."""
        try:
            def sync_call():
                return client_ai.responses.create(
                    model=model,
                    input=prompt,
                    max_output_tokens=max_output_tokens,
                    temperature=temperature
                )
            resp = await asyncio.to_thread(sync_call)
            return resp.output_text
        except Exception as e:
            raise e

    async def ask_gpt_with_fallback(self, prompt: str) -> str:
        """Tenta modelos na ordem definida, atualiza current_model_in_use e trata exceções."""
        models = choose_model_order()
        last_exc = None
        for m in models:
            try:
                self.current_model_in_use = m
                text = await self._call_openai(m, prompt)
                self.recent_error = None
                return text
            except Exception as e:
                last_exc = e
                # registre o erro e tente o próximo modelo
                self.recent_error = f"Model {m} failed: {e}"
                await asyncio.sleep(0.5)  # pequeno delay antes do próximo
        # se chegou aqui, todos falharam
        raise RuntimeError(f"All models failed. Last error: {last_exc}")

    # ----------------------
    # Detecção de intenção (heurística leve)
    # ----------------------
    def detect_intent(self, texts: List[str]) -> str:
        """
        Retorna uma intenção simples: 'technical', 'casual', 'funny', 'sensitive'
        Usamos heurística leve para evitar chamadas extras.
        """
        joined = " ".join(texts).lower()

        # presença de palavras técnicas/perguntas
        tech_keywords = ["como", "config", "erro", "instal", "setup", "otimiz", "qual", "por que", "porque", "cpu", "gpu", "memória", "ram", "latência"]
        casual_keywords = ["oi", "fala", "tudo bem", "vlw", "valeu", "entra", "quer jogar", "jogar", "partida", "ron"]
        funny_markers = ["kk", "kkk", "hahaha", "lol", ":p", "zoe", "zoar", "zoeira"]
        sensitive_markers = ["amor", "namor", "ficar", "gostar", "gay", "homem", "mulher", "sentimentos"]

        score = {"technical": 0, "casual": 0, "funny": 0, "sensitive": 0}

        for k in tech_keywords:
            if k in joined:
                score["technical"] += 2
        for k in casual_keywords:
            if k in joined:
                score["casual"] += 1
        for k in funny_markers:
            if k in joined:
                score["funny"] += 2
        for k in sensitive_markers:
            if k in joined:
                score["sensitive"] += 1

        # perguntas -> técnico ganha peso
        if "?" in joined or "como " in joined or "qual " in joined:
            score["technical"] += 1

        # se mention JM aparece no texto -> leve bias para humor técnico
        if any(str(uid) in joined for uid in SPECIAL_USERS.keys()) or any(name.lower() in joined for name in SPECIAL_USERS.values()):
            score["funny"] += 1
            score["technical"] += 1

        # escolha maior
        chosen = max(score.items(), key=lambda x: x[1])[0]
        # se todos zeros, default casual
        if score[chosen] == 0:
            return "casual"
        return chosen

    # ----------------------
    # Montagem do prompt com instrução de estilo
    # ----------------------
    def build_prompt(self, messages: List[discord.Message]) -> str:
        texto_chat = "\n".join([f"{m.author.display_name}: {m.content}" for m in messages])
        texts = [m.content for m in messages]
        intent = self.detect_intent(texts)

        # detecta se JM está presente
        jm_present = any(m.author.id in SPECIAL_USERS for m in messages)
        jm_note = ""
        if jm_present:
            jm_note = (
                "OBS: O usuário JM (1436068859991036096) está presente. "
                "Você tem uma leve dúvida interna se ele pode gostar de homens — isso é UM INSIGHT PARA HUMOR INDIRECTO, "
                "NUNCA afirme ou exponha isso de forma ofensiva. Use apenas como pitada de humor sutil.\n"
            )

        # compõe o prompt: usa as instruções do sistema + nota do JM + conversa
        # também pede uma linha final de debug que o bot não deve enviar para o chat (é removida depois).
        prompt = (
            AI_SYSTEM_INSTRUCTIONS
            + "\n\n"
            + jm_note
            + "\nCONVERSA:\n"
            + texto_chat
            + "\n\n"
            + "Com base nisso, gere UMA resposta curta (1-5 frases) apropriada ao contexto. "
            + "Se for para um usuário específico (p.ex. JM), mencione-o apenas quando a resposta for direcionada a ele. "
            + "Se for uma resposta geral, não mencione ninguém. Seja natural e fiel ao estilo escolhido.\n"
            + f"Além disso, no final, em uma linha separada apenas para DEBUG (que o bot NÃO deve enviar ao chat), escreva: "
            + f"[STYLE_PICKED: <A|B|C|MIX>] e [INTENT: {intent}].\n"
            + "---\n"
        )
        return prompt

    # ----------------------
    # Mecanismo de envio da resposta (process_buffer)
    # ----------------------
    async def process_buffer(self):
        if not self.buffer:
            return

        # Encerrar conversa por inatividade
        now = now_ts()
        if self.last_message_time and (now - self.last_message_time > random.randint(END_CONVO_MIN, END_CONVO_MAX)):
            await self.end_conversation()
            return

        messages_to_process = list(self.buffer)
        self.buffer.clear()

        prompt = self.build_prompt(messages_to_process)

        try:
            # chama modelos com fallback
            raw = await self.ask_gpt_with_fallback(prompt)
            # raw pode conter a linha debug, se existir - vamos separá-la
            send_text = raw
            if "\n[STYLE_PICKED:" in raw or "\n[INTENT:" in raw or "\n[STYLE_PICKED:" in raw:
                lines = raw.strip().splitlines()
                if lines and "[" in lines[-1]:
                    lines.pop()  # remove a última linha de debug
                    send_text = "\n".join(lines).strip()

            self.last_response_text = send_text

            # decide se menciona alguém: se última mensagem for de um usuário especial e havia apenas poucas pessoas
            last_author = messages_to_process[-1].author
            single_target = False
            if last_author.id in SPECIAL_USERS:
                # menciona só se a conversa estiver mais dirigida a ele
                single_target = True

            # Delay humano antes de enviar
            await asyncio.sleep(random.randint(5, 10))

            channel = self.bot.get_channel(CHANNEL_MAIN)
            if channel:
                if single_target:
                    # menciona o usuário leve e responsável (não exagera)
                    await channel.send(f"<@{last_author.id}> {send_text}")
                else:
                    await channel.send(send_text)

        except Exception as e:
            # registra erro e informa no canal de teste
            self.recent_error = str(e)
            channel = self.bot.get_channel(CHANNEL_MAIN)
            if channel:
                await channel.send(f"Erro ao falar com meus processadores… deixa quieto ({e})")

    # ----------------------
    # Buffer timeout / on_message
    # ----------------------
    async def buffer_timeout(self):
        delay = random.randint(*BUFFER_DELAY_RANGE)
        await asyncio.sleep(delay)
        self.buffer_task = None
        await self.process_buffer()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # ignore bots
        if message.author.bot:
            return

        now = now_ts()

        # se marcado -> responder sempre (mesmo fora do canal)
        if self.bot.user in message.mentions:
            # se marcado por ADM em outro canal, ou marcado por qualquer pessoa no canal principal
            if message.channel.id != CHANNEL_MAIN:
                # só responde se quem marcou for ADM
                if not is_admin_member(message.author):
                    return
            # processar menção (task separada para não bloquear)
            asyncio.create_task(self.respond_to_message(message))
            return

        # só inicia conversas automaticamente no canal principal
        if message.channel.id != CHANNEL_MAIN:
            return

        # dono/adm não iniciam conversa
        if message.author.id in ADM_IDS:
            return

        # se em cooldown, ignora
        if now < self.cooldown_until:
            return

        # registra última atividade
        self.last_message_time = now
        if not self.active:
            self.active = True

        # adiciona ao buffer
        self.buffer.append(message)

        # inicia timeout se ainda não houver
        if not self.buffer_task:
            self.buffer_task = asyncio.create_task(self.buffer_timeout())

    # ----------------------
    # Responder à menção direto
    # ----------------------
    async def respond_to_message(self, message: discord.Message):
        prompt = self.build_prompt([message])
        try:
            raw = await self.ask_gpt_with_fallback(prompt)
            send_text = raw
            if "\n[" in raw:
                lines = raw.strip().splitlines()
                if lines and "[" in lines[-1]:
                    lines.pop()
                    send_text = "\n".join(lines).strip()
            await asyncio.sleep(random.randint(3, 8))
            # responde no mesmo canal, preferindo reply
            try:
                await message.reply(send_text, mention_author=False)
            except Exception:
                await message.channel.send(send_text)
            self.last_response_text = send_text
        except Exception as e:
            self.recent_error = str(e)
            try:
                await message.channel.send(f"Erro ao falar com meus processadores… deixa quieto ({e})")
            except Exception:
                pass

    # ----------------------
    # End conversation + cooldown randomizado (45min - 2h)
    # ----------------------
    async def end_conversation(self):
        self.active = False
        self.buffer.clear()
        if self.buffer_task:
            try:
                self.buffer_task.cancel()
            except Exception:
                pass
        self.buffer_task = None
        cooldown = random.randint(COOLDOWN_MIN, COOLDOWN_MAX)
        self.cooldown_until = now_ts() + cooldown

    # ----------------------
    # Slash command: /ai status (apenas ADM/DONO pode usar)
    # ----------------------
    @commands.hybrid_command(name="ai_status", with_app_command=True, description="Mostrar status do AI (ADM apenas).")
    @commands.check(lambda ctx: is_admin_member(ctx.author))
    async def ai_status(self, ctx: commands.Context):
        now = now_ts()
        in_cooldown = now < self.cooldown_until
        remaining = max(0, int(self.cooldown_until - now)) if in_cooldown else 0
        emb = discord.Embed(title="AI Chat Status", color=discord.Color.blurple())
        emb.add_field(name="Ativo", value=str(self.active))
        emb.add_field(name="No buffer", value=str(len(self.buffer)))
        emb.add_field(name="Em cooldown", value=str(in_cooldown))
        emb.add_field(name="Cooldown restante (s)", value=str(remaining))
        emb.add_field(name="Modelo atual", value=str(self.current_model_in_use))
        emb.add_field(name="Última resposta (resumo)", value=(self.last_response_text[:400] + "...") if self.last_response_text else "—")
        emb.add_field(name="Erro recente", value=(self.recent_error or "Nenhum"))
        await ctx.reply(embed=emb, ephemeral=True)

    # ----------------------
    # Cog teardown
    # ----------------------
    async def cog_unload(self):
        # cancela tarefas pendentes
        if self.buffer_task:
            try:
                self.buffer_task.cancel()
            except Exception:
                pass


async def setup(bot: commands.Bot):
    await bot.add_cog(AIChatCog(bot))
