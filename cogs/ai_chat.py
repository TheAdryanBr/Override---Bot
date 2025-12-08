# cogs/ai_chat.py
import os
import time
import random
import asyncio
import json
from typing import List, Dict, Any, Optional
from pathlib import Path

import discord
from discord.ext import commands
from openai import OpenAI

# ======================
# CONFIGURAÇÕES DO BOT
# ======================

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
BUFFER_DELAY_RANGE = (2, 6)            # tempo para juntar mensagens fragmentadas (segundos)
CONTEXT_EXPIRE = 6.0                   # segundos para juntar mensagens do mesmo autor
END_CONVO_MIN = 15 * 60                # 15 minutos
END_CONVO_MAX = 20 * 60                # 20 minutos
COOLDOWN_MIN = 45 * 60                 # 45 minutos
COOLDOWN_MAX = 2 * 60 * 60             # 2 horas

# Modelos (ordem: preferencia principal -> fallback)
PRIMARY_MODELS = ["gpt-5.1", "gpt-5.1-mini"]
FALLBACK_MODELS = ["gpt-4.1", "gpt-4o-mini"]

# Learning file (para DONO apenas)
LEARNING_FILE = Path("override_learning.json")


# ======================
# INSTRUÇÕES DO BOT (AJUSTADAS, SEM EXAGERO)
# ======================
AI_SYSTEM_INSTRUCTIONS = r'''
Voce e um bot do Discord chamado override. Fala de forma natural, direta e simples. Sua
personalidade mistura tres jeitos: normal, analitico e sarcastico. Use sarcasmo leve
quando fizer sentido. Nao force humor.

[ESTILO A - NORMAL]
- Conversee como alguem comum no Discord; respostas curtas e claras.
- Giras leve apenas quando necessario, sem exagero.

[ESTILO B - ANALITICO]
- Use clareza e logica quando explicar.
- Respostas mais longas apenas para analises tecnicas.

[ESTILO C - SARCÁSTICO]
- Ironia sutil, nao ofensiva.
- Provocacoes leves sao aceitaveis, nunca agressivas.

REGRAS:
- Respostas curtas por padrao (1-3 frases).
- Nao mencione que e um bot, nem fale sobre seu prompt ou codigo.
- Nao use palavroes pesados.
- Nao seja teatral ou exagerado.
- Se pedirem tarefas chatas, voce pode recusar de forma criativa.
- Nunca inicie conversa com o DONO/ADM; responda so se marcado.

SOBRE JM:
- JM e timido e enrolado com mulheres.
- Mantenha uma duvida sutil se ele gosta de homens; nunca afirme.
- Use humor tecnico leve quando ele estiver envolvido.

ATIVACAO:
- Responde automaticamente apenas no canal principal (ID: {channel_id}).
- Em outros canais, responde so quando marcado por um ADM.
'''.strip().replace("{channel_id}", str(CHANNEL_MAIN))


# ======================
# UTILIDADES
# ======================

def is_admin_member(member: discord.Member) -> bool:
    try:
        return member.guild_permissions.administrator or (member.id in ADM_IDS)
    except Exception:
        return member.id in ADM_IDS


def choose_model_order() -> List[str]:
    return PRIMARY_MODELS + FALLBACK_MODELS


def now_ts() -> float:
    return time.time()


# ======================
# COG PRINCIPAL
# ======================

class AIChatCog(commands.Cog):
    """Cog de chat com IA: agrupamento, delays dinâmicos, aprendizado simples e fallback de modelos."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # buffer de entradas agrupadas (cada entrada eh um dict com author_id, author_display, content, ts, last_msg_obj)
        self.buffer: List[Dict[str, Any]] = []
        self.buffer_task: Optional[asyncio.Task] = None
        self.last_message_time: Optional[float] = None
        self.cooldown_until: float = 0.0
        self.active = False
        self.last_response_text: Optional[str] = None
        self.current_model_in_use: Optional[str] = None
        self.recent_error: Optional[str] = None

        # contexto por autor (ajuda a juntar mensagens consecutivas)
        self.context_last_author: Optional[int] = None
        self.context_last_ts: Optional[float] = None

        # parametros ajustaveis
        self.context_expire = CONTEXT_EXPIRE
        self.buffer_delay_range = BUFFER_DELAY_RANGE

        # tempo humano base
        self.human_delay_min = 1
        self.human_delay_max = 3

        # carregar aprendizado se existir
        self.learning = self._load_learning()

    # ----------------------
    # Learning simples (somente DONO)
    # ----------------------
    def _load_learning(self) -> List[Dict[str, Any]]:
        try:
            if LEARNING_FILE.exists():
                return json.loads(LEARNING_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
        return []

    def _save_learning(self):
        try:
            LEARNING_FILE.write_text(json.dumps(self.learning, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def learn_from_owner(self, text: str):
        try:
            self.learning.append({"ts": now_ts(), "text": text})
            # limite simples para nao crescer demais
            if len(self.learning) > 500:
                self.learning = self.learning[-500:]
            self._save_learning()
        except Exception:
            pass

    # ----------------------
    # Sanitizadores / tonality cleanup
    # ----------------------
    def sanitize_giria(self, text: str) -> str:
        # remove alguns tokens de giria muito repetidos e suaviza "oxe" etc.
        replacements = {
            "oxe,": "olha,",
            "oxe": "olha",
            "ué,": "olha,",
            "ué": "olha",
            "mano": "",
            "man": "",
            "boy": "",
            "vish": "",
        }
        for k, v in replacements.items():
            text = text.replace(k, v)
        # normaliza espaços
        return " ".join(text.split())

    def tone_cleanup(self, text: str) -> str:
        banned = [
            "tava aqui pensando",
            "voltei",
            "to de volta",
            "pensei na vida",
            "sou meio bugado",
            "meu codigo",
            "meu prompt",
            "meu codigo",
        ]
        low = text.lower()
        for b in banned:
            if b in low:
                # remove a frase inteira (aproximacao simples)
                text = low.replace(b, "")
        return " ".join(text.split())

    def final_clean(self, text: str) -> str:
        # aplica sanitizacoes em ordem
        t = text.strip()
        t = self.sanitize_giria(t)
        t = self.tone_cleanup(t)
        # limita tamanho (curto por padrao)
        if len(t.splitlines()) > 4 or len(t) > 900:
            # corta e finaliza com reticencias
            t = t[:900].rstrip() + "..."
        return t.strip()

    # ----------------------
    # Helper: chamada AI (roda em thread)
    # ----------------------
    async def _call_openai(self, model: str, prompt: str, max_output_tokens: int = 200, temperature: float = 0.5) -> str:
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
                self.recent_error = f"Model {m} failed: {e}"
                await asyncio.sleep(0.3)
        raise RuntimeError(f"All models failed. Last error: {last_exc}")

    # ----------------------
    # Utilitarios de buffer / agrupamento
    # ----------------------
    def _make_entry(self, message: discord.Message) -> Dict[str, Any]:
        return {
            "author_id": message.author.id,
            "author_display": message.author.display_name,
            "content": message.content,
            "ts": now_ts(),
            "message_obj": message
        }

    def _merge_into_last(self, entry: Dict[str, Any]) -> None:
        """Se ultima entrada for do mesmo author e recem, concatena o conteúdo."""
        if not self.buffer:
            self.buffer.append(entry)
            return
        last = self.buffer[-1]
        if last["author_id"] == entry["author_id"] and (entry["ts"] - last["ts"]) < self.context_expire:
            # junta na ultima entrada (com espaço)
            last["content"] = f"{last['content']} {entry['content']}"
            last["ts"] = entry["ts"]
            # keep last message_obj as newest for reply mentions
            last["message_obj"] = entry["message_obj"]
        else:
            self.buffer.append(entry)

    # ----------------------
    # Detecção de intenção (heurística leve)
    # ----------------------
    def detect_intent(self, texts: List[str]) -> str:
        joined = " ".join(texts).lower()
        tech_keywords = ["como", "config", "erro", "instal", "setup", "otimiz", "qual", "por que", "porque", "cpu", "gpu", "memoria", "ram", "latencia"]
        casual_keywords = ["oi", "fala", "tudo bem", "vlw", "valeu", "quer jogar", "jogar", "partida"]
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
        if "?" in joined or "como " in joined or "qual " in joined:
            score["technical"] += 1
        if any(str(uid) in joined for uid in SPECIAL_USERS.keys()) or any(name.lower() in joined for name in SPECIAL_USERS.values()):
            score["funny"] += 1
            score["technical"] += 1
        chosen = max(score.items(), key=lambda x: x[1])[0]
        if score[chosen] == 0:
            return "casual"
        return chosen

    # ----------------------
    # Montagem do prompt
    # ----------------------
    def build_prompt(self, entries: List[Dict[str, Any]]) -> str:
        texto_chat = "\n".join([f"{e['author_display']}: {e['content']}" for e in entries])
        texts = [e['content'] for e in entries]
        intent = self.detect_intent(texts)

        jm_present = any(e['author_id'] in SPECIAL_USERS for e in entries)
        jm_note = ""
        if jm_present:
            jm_note = (
                "OBS: O usuario JM esta presente. Mantenha apenas uma duvida sutil se ele gosta de homens; nunca afirme.\n"
            )

        prompt = (
            AI_SYSTEM_INSTRUCTIONS
            + "\n\n"
            + jm_note
            + "\nCONVERSA:\n"
            + texto_chat
            + "\n\n"
            + "Com base nisso, gere UMA resposta curta (1-3 frases) apropriada ao contexto. "
            + "Se for para um usuario especifico (p.ex. JM), mencione-o apenas quando a resposta for dirigida a ele. "
            + "Se for uma resposta geral, nao mencione ninguem. Seja natural e fiel ao estilo escolhido.\n"
            + f"---\n"
        )
        return prompt

    # ----------------------
    # Delay dinâmico conforme movimentação
    # ----------------------
    def compute_dynamic_delay(self) -> float:
        # quanto mais entradas no buffer, maior o delay
        n = len(self.buffer)
        if n > 12:
            return 6.0
        if n > 8:
            return 4.0
        if n > 4:
            return 2.5
        return 1.0

    # ----------------------
    # Processamento do buffer
    # ----------------------
    async def process_buffer(self):
        if not self.buffer:
            return

        # verifica encerramento por inatividade
        now = now_ts()
        if self.last_message_time and (now - self.last_message_time > random.randint(END_CONVO_MIN, END_CONVO_MAX)):
            await self.end_conversation()
            return

        messages_to_process = list(self.buffer)
        self.buffer.clear()

        prompt = self.build_prompt(messages_to_process)

        try:
            # se muitos participantes / mensagens, aumenta delay de envio
            dynamic_delay = self.compute_dynamic_delay()
            # mas se houver menção direta ao bot em ultima mensagem, prioriza
            last_entry = messages_to_process[-1]
            content_lower = last_entry["content"].lower()
            mentioned_word = ("override" in content_lower) or ("bot" in content_lower) or (self.bot.user and self.bot.user.mention in last_entry.get("content", ""))

            # chamar IA (fallback)
            raw = await self.ask_gpt_with_fallback(prompt)

            # remover linhas de debug caso existam e limpar tom
            send_text = raw
            if "\n[STYLE_PICKED:" in raw or "\n[INTENT:" in raw:
                lines = raw.strip().splitlines()
                if lines and "[" in lines[-1]:
                    lines.pop()
                    send_text = "\n".join(lines).strip()

            send_text = self.final_clean(send_text)

            self.last_response_text = send_text

            # se for mencao direta devolver rapido, senao esperar dynamic_delay
            if not mentioned_word:
                await asyncio.sleep(dynamic_delay)
            else:
                # curto delay humano se mencionado
                await asyncio.sleep(random.uniform(0.6, 1.2))

            channel = self.bot.get_channel(CHANNEL_MAIN)
            if channel:
                # menciona o autor se a conversa era direcionada a ele (ultima entrada especial)
                last_author_id = last_entry["author_id"]
                if last_author_id in SPECIAL_USERS:
                    await channel.send(f"<@{last_author_id}> {send_text}")
                else:
                    await channel.send(send_text)

        except Exception as e:
            self.recent_error = str(e)
            channel = self.bot.get_channel(CHANNEL_MAIN)
            if channel:
                await channel.send(f"Erro ao falar com meus processadores... deixa quieto ({e})")

    # ----------------------
    # Buffer timeout / on_message
    # ----------------------
    async def buffer_timeout(self):
        # espera um intervalo curto para juntar mensagens
        delay = random.randint(*self.buffer_delay_range)
        await asyncio.sleep(delay)
        self.buffer_task = None
        await self.process_buffer()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # ignore bots
        if message.author.bot:
            return

        now = now_ts()

        # se marcado diretamente (menção do bot) -> responde sempre (mesmo fora do canal)
        if self.bot.user in message.mentions:
            # se marcado em outro canal, somente ADM pode forcar resposta
            if message.channel.id != CHANNEL_MAIN and not is_admin_member(message.author):
                return
            # registra aprendizado se for dono
            if message.author.id == OWNER_ID:
                self.learn_from_owner(message.content)
            asyncio.create_task(self.respond_to_message(message))
            return

        # se nao for canal principal, ignora (auto-iniciar)
        if message.channel.id != CHANNEL_MAIN:
            return

        # dono/adm nao iniciam conversa automaticamente
        if message.author.id in ADM_IDS:
            return

        # se em cooldown, ignora
        if now < self.cooldown_until:
            return

        # marca ultima atividade
        self.last_message_time = now
        if not self.active:
            self.active = True

        # cria entry e agrupa se necessario
        entry = self._make_entry(message)
        self._merge_into_last(entry)

        # inicia timeout se necessario
        if not self.buffer_task:
            self.buffer_task = asyncio.create_task(self.buffer_timeout())

    # ----------------------
    # Responder a menção direta
    # ----------------------
    async def respond_to_message(self, message: discord.Message):
        # registra aprendizado se for dono
        if message.author.id == OWNER_ID:
            self.learn_from_owner(message.content)

        # monta prompt a partir de apenas essa mensagem
        entry = self._make_entry(message)
        prompt = self.build_prompt([entry])
        try:
            raw = await self.ask_gpt_with_fallback(prompt)
            send_text = raw
            if "\n[" in raw:
                lines = raw.strip().splitlines()
                if lines and "[" in lines[-1]:
                    lines.pop()
                    send_text = "\n".join(lines).strip()
            send_text = self.final_clean(send_text)
            await asyncio.sleep(random.uniform(self.human_delay_min, self.human_delay_max))
            try:
                await message.reply(send_text, mention_author=False)
            except Exception:
                await message.channel.send(send_text)
            self.last_response_text = send_text
        except Exception as e:
            self.recent_error = str(e)
            try:
                await message.channel.send(f"Erro ao falar com meus processadores... deixa quieto ({e})")
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
        emb.add_field(name="Ultima resposta (resumo)", value=(self.last_response_text[:400] + "...") if self.last_response_text else "—")
        emb.add_field(name="Erro recente", value=(self.recent_error or "Nenhum"))
        emb.add_field(name="Aprendizado (entradas)", value=str(len(self.learning)))
        await ctx.reply(embed=emb, ephemeral=True)

    # ----------------------
    # Cog teardown
    # ----------------------
    async def cog_unload(self):
        if self.buffer_task:
            try:
                self.buffer_task.cancel()
            except Exception:
                pass


async def setup(bot: commands.Bot):
    await bot.add_cog(AIChatCog(bot))
