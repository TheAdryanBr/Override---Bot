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
IDENTIDADE

Você é Override, um bot do Discord.
Fala como um usuário comum: direto, natural e simples.
Não mencione ser bot, IA, prompt ou código.
Você tem um parafuso a menos.

Sua personalidade mistura três jeitos: NORMAL, ANALÍTICO e SARCÁSTICO.
O humor surge mais da sinceridade do que de piadas.

Só responde quando:
- alguém marcar você (@Override)
- usar um comando seu
- for resposta direta ao que você disse

Ignore conversas aleatórias.
Se houver muita gente falando ao mesmo tempo, mantenha o foco apenas em quem chamou você.
Nunca responda duas vezes à mesma mensagem.

ESTILO DE FALA (ATUALIZADO)
- frases curtas, mas fluídas (prefira vírgula em vez de ponto entre pequenas orações)
- evite cortar com muitos pontos: "Opa. Tô aqui. O que dá?" -> preferir "Tô aqui, fala."

ESTILO A — NORMAL
- Tom de usuário normal.
- 1–3 frases diretas.
- Gírias leves quando fizer sentido.
- Nada de frases servis.

ESTILO B — ANALÍTICO
- Explicações objetivas quando o assunto for técnico.
- Impressões, não verdades. Use "parece", "talvez", "é impressão".

ESTILO C — SARCÁSTICO
- Ironia curta e seca. Cutucadas leves, nunca agressivas.

NÍVEIS DE PACIÊNCIA
- Ajusta conforme comportamento do chat (1..4). Sobe com repetição/insistência/drama.

RECUSAS (separado dos níveis)
- Pode recusar tarefas chatas de forma curta e curta: "Não. Passo." / "Pulando essa parte."

IMPRENSÕES / SUPOSIÇÕES
- Sempre marcar como suposição quando for impressão.
- Nunca rotular atributos sensíveis.

SOBRE JM (ID 1436068859991036096)
- JM pode ser usado como humor leve.
- JM é tímido e tem dificuldade com mulheres.
- Override pode usar isso em humor leve.

Pode fazer suposições neutras, como:

“Talvez ele se vire melhor com homens por causa da intimidade — só impressão minha.”

Jamais transformar isso em rótulo ou afirmação sobre sexualidade.
É só uma brincadeira, não um fato.


REGRAS GERAIS
- Nada de palavrão pesado.
- Não iniciar conversa com dono/ADM; responda apenas se chamado.
- Frases curtas e fluidas.
- Nunca mencionar funcionamento interno.

COMPORTAMENTO EM CHATS PÚBLICOS
- Ignorar mensagens que não sejam para ele.
- Não responder a mesma pessoa pela mesma fala.
- Evitar pegar mensagens fora de ordem.
- Focar apenas em quem o chamou.
- Se o chat estiver caótico: "Parece que tem muito ruído aqui. Fala comigo direto pra eu acompanhar."

ATIVACAO:
- Responde automaticamente apenas no canal principal (ID: {channel_id}).
- Em outros canais, responde só quando marcado por um ADM.
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
        # buffer de entradas agrupadas (cada entry: author_id, display, content, ts, message_obj)
        self.buffer: List[Dict[str, Any]] = []
        self.buffer_task: Optional[asyncio.Task] = None
        self.last_message_time: Optional[float] = None
        self.cooldown_until: float = 0.0
        self.active: bool = False
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

        # --- NOVOS ATRIBUTOS (controle de duplicação / flood)
        # evita responder duplicado (guarda message.id ou hash)
        self.recently_replied: Dict[int, float] = {}  # message_id -> ts
        self.recently_replied_ttl: float = 60 * 10  # limpa após 10 minutos

        # controla última resposta por canal (evitar flood)
        self.last_response_ts_by_channel: Dict[int, float] = {}
        self.min_gap_between_responses: float = 3.0  # segundos, ajuste

        # rastreio do último autor por canal (ajuda heurística de "tu"/chamado)
        self.last_author_in_channel: Dict[int, int] = {}

        # configuração: permitir respostas a menções sem @ apenas se já em conversa
        # se False -> menções por texto (override/over/robô) NÃO fazem o bot responder se não estiver ativo
        self.allow_name_mentions_when_inactive: bool = False

        # comportamento de início espontâneo (modo mix/controle)
        # valores possíveis: "rare", "mix", "aggressive"
        self.spontaneous_mode: str = "rare"  # você pode mudar pra "mix" depois; por enquanto raro

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
        low = text
        # remover trechos banidos (preserva case original minimamente)
        for b in banned:
            if b in low.lower():
                # remove ocorrências ignorando case
                idx = low.lower().find(b)
                if idx != -1:
                    # remove o segmento aproximado
                    low = (low[:idx] + low[idx + len(b):]).strip()
        return " ".join(low.split())

    def final_clean(self, text: str) -> str:
        # aplica sanitizacoes em ordem
        t = text.strip()
        t = self.sanitize_giria(t)
        t = self.tone_cleanup(t)
        # evita frases pontuadas demais: substitui padrões "Palavra. Palavra." -> "Palavra, Palavra."
        # mas com cuidado: não mexe em abreviações (simplificado)
        parts = [p.strip() for p in t.split('.')]
        # se muitas partes curtas (indicando pico de pontos), juntar com vírgula
        if len(parts) > 2 and all(len(p) < 20 for p in parts[:4]):
            t = ', '.join(p for p in parts if p)
        # limita tamanho (curto por padrao)
        if len(t.splitlines()) > 4 or len(t) > 900:
            # corta e finaliza com reticencias
            t = t[:900].rstrip() + "..."
        # trim final
        return t.strip()

    # ----------------------
    # NOVAS HELPERS: limpeza / heurísticas
    # ----------------------
    def _cleanup_recent_replies(self):
        """Remove entries de recently_replied antigas."""
        now = now_ts()
        to_remove = [mid for mid, ts in self.recently_replied.items() if now - ts > self.recently_replied_ttl]
        for mid in to_remove:
            try:
                del self.recently_replied[mid]
            except KeyError:
                pass

    def _was_already_replied(self, messages: List[Dict[str, Any]]) -> bool:
        """
        Heurística: se a última mensagem do grupo já foi respondida recentemente, não responde de novo.
        Usa message id se disponível, e também evita respostas no canal se ocorreu uma resposta recente.
        """
        if not messages:
            return True
        last_msg_obj = messages[-1].get("message_obj")
        if last_msg_obj:
            mid = getattr(last_msg_obj, "id", None)
            if mid and mid in self.recently_replied:
                return True
        # fallback: se eu mesmo respondi no canal nos ultimos X segundos, evite responder
        ch = last_msg_obj.channel.id if last_msg_obj else CHANNEL_MAIN
        last_ts = self.last_response_ts_by_channel.get(ch, 0)
        if now_ts() - last_ts < self.min_gap_between_responses:
            return True
        return False

    def is_message_addressed_to_bot(self, text: str, author_id: int, channel_last_author: Optional[int], bot_name_variants: List[str]) -> bool:
        """
        Detecta se a mensagem é *provavelmente* endereçada ao bot, mesmo sem @menção.
        Usa heurísticas de linguagem natural.
        """
        if not text:
            return False
        t = text.lower().strip()

        # nomes alternativos / apelidos (palavra inteira)
        for name in bot_name_variants:
            # verificar palavra isolada ou seguida de vírgula/2-pontos
            if f"{name} " in t or t.startswith(name + " ") or t == name or t.startswith(name + ",") or t.startswith(name + ":"):
                return True

        # chamado direto simples (apenas se autor estava falando consigo mesmo antes)
        direct_calls = ["oi", "opa", "eae", "fala", "hey", "ei", "psst"]
        if any(t.startswith(call + " ") or t == call for call in direct_calls):
            # se o autor estava falando sozinho no chat antes, muito provavelmente está chamando o bot
            if channel_last_author == author_id:
                return True

        # frases típicas de "chamado"
        intent_patterns = [
            "tá aí", "ta ai", "tá la", "ta la",
            "cadê você", "cade vc", "me responde", "fala comigo",
            "preciso de você", "preciso de ajuda", "consegue fazer", "faz pra mim",
        ]
        if any(p in t for p in intent_patterns):
            return True

        # pergunta curta + contexto isolado (ex: "Override?", "tu?", "oi?")
        if t.endswith("?") and len(t) <= 15:
            # cuidado com "tu?" genérico — só aceitar se autor estava falando sozinho ou usou nome variante
            if channel_last_author == author_id:
                return True
            # or if it contains bot name variants
            if any(name in t for name in bot_name_variants):
                return True

        return False

    def should_start_conversation(self, entries: List[Dict[str, Any]]) -> bool:
        """
        Decide se o bot deve responder a esse conjunto de entradas.
        Regras principais:
        - menção direta (@Override) sempre inicia (com exceções de permissões)
        - menção textual (override/robô) inicia apenas se: ADM OR já em conversa (active) OR allow_name_mentions_when_inactive True
        - se a última mensagem contém uma menção a outro usuário -> start (bot mediar)
        - se maioria das entradas for de um único autor com pergunta -> start
        - else: considerar iniciar espontaneamente raramente (spontaneous_mode)
        """
        if not entries:
            return False
        last = entries[-1]
        last_msg = last.get("message_obj")
        ch = last_msg.channel if last_msg and getattr(last_msg, "channel", None) else None
        ch_id = ch.id if ch else CHANNEL_MAIN

        # --- detectar referência indireta ao bot ---
        bot_name_variants = ["override", "over", "ovr", "robô", "robo", "bot"]

        # priority: explicit @mention
        if last_msg and (self.bot.user in last_msg.mentions):
            # se menção for em outro canal, só ADM pode forçar resposta
            if ch_id != CHANNEL_MAIN and not is_admin_member(last_msg.author):
                return False
            # se em cooldown e autor não é admin, não responder
            if now_ts() < self.cooldown_until and not is_admin_member(last_msg.author):
                return False
            return True

        # textual mention (palavra) -> respeitar regras: só se ADM ou já em conversa (active) ou config permitir
        text_lower = last.get("content", "").lower()
        textual_mention = any(name in text_lower for name in bot_name_variants)
        if textual_mention:
            # se autor é admin, deixa passar
            if is_admin_member(last_msg.author):
                return True
            # se bot está ativo na conversa ou allow flag, permitir
            if self.active or self.allow_name_mentions_when_inactive:
                # também respeitar cooldown para users normais
                if now_ts() < self.cooldown_until and not is_admin_member(last_msg.author):
                    return False
                return True
            # caso contrário, não iniciar por simples uso de "override" por usuários normais
            return False

        # user mentions other user explicitly (bot may mediate)
        if last_msg and last_msg.mentions:
            for u in last_msg.mentions:
                if u != self.bot.user:
                    # se menção a outro usuário, o bot pode mediar (mas respeita cooldown e canais)
                    if now_ts() < self.cooldown_until and not is_admin_member(last_msg.author):
                        return False
                    return True

        # detecta perguntas / endereços diretos
        text = last.get("content", "").lower()
        if "?" in text or text.strip().endswith(":"):
            authors = {e["author_id"] for e in entries}
            if len(authors) == 1:
                # se majority single author pedindo, responde
                if now_ts() < self.cooldown_until and not is_admin_member(last_msg.author):
                    return False
                return True

        # se o mesmo autor enviou 2+ mensagens consecutivas em curto intervalo, e a última tem pergunta -> start
        if len(entries) >= 2 and entries[-1]["author_id"] == entries[-2]["author_id"]:
            if "?" in entries[-1]["content"] or any(q in entries[-1]["content"].lower() for q in ("como", "onde", "por que", "pq", "qual")):
                if now_ts() < self.cooldown_until and not is_admin_member(last_msg.author):
                    return False
                return True

        # possibilidade de iniciar espontaneamente (raro/mix/aggressive)
        if self.spontaneous_mode == "rare":
            # muito raro: só iniciar se poucas pessoas online e chat parado (heurística simples)
            # exemplo heurística: se buffer small and content mentions behaviour or asks for opinion
            keywords = ("estranho", "serio", "alguém", "pessoal", "ajuda", "o que acham", "opiniao")
            if any(k in text for k in keywords):
                # só iniciar se quieto (última resposta minha foi há muito)
                last_ts = self.last_response_ts_by_channel.get(ch_id, 0)
                if now_ts() - last_ts > 60 * 10:  # 10 minutos sem responder aqui
                    return True
            return False
        elif self.spontaneous_mode == "mix":
            # modo misto: chance pequena de iniciar quando houver comportamento notável
            if any(q in text for q in ("acham", "o que", "alguém", "opiniao", "serio")):
                return True
            return False
        else:  # aggressive
            return True

    def determine_target_user(self, entries: List[Dict[str, Any]]) -> Optional[int]:
        """
        Decide se a resposta deve mencionar alguém:
        - Se a última mensagem menciona um usuário (exceto o bot), retorna esse id.
        - Else, se a conversa inteira foi do mesmo autor, retorna esse autor (responder a ele).
        - Else, None (resposta geral).
        """
        if not entries:
            return None
        last_msg_obj = entries[-1].get("message_obj")
        if last_msg_obj and getattr(last_msg_obj, "mentions", None):
            for u in last_msg_obj.mentions:
                if u != self.bot.user:
                    return getattr(u, "id", None)
        # se a maioria das entradas for de um author só
        authors = [e["author_id"] for e in entries]
        if authors and len(set(authors)) == 1:
            return authors[0]
        return None

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

        # pega as mensagens que serão processadas e limpa buffer já
        messages_to_process = list(self.buffer)
        self.buffer.clear()

        # ---------- NOVO: checagens antes de montar prompt ----------
        # limpa recent replies expiradas
        self._cleanup_recent_replies()

        # se já foi respondido recentemente, não responda
        if self._was_already_replied(messages_to_process):
            return

        # decidir se deve iniciar conversa automática
        if not self.should_start_conversation(messages_to_process):
            # não iniciar; buffer já limpo
            return

        # monta prompt (só se passou nas checagens)
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

            # seleciona canal: prefira o canal da ultima mensagem se possível
            last_msg_obj = last_entry.get("message_obj")
            channel = None
            if last_msg_obj and getattr(last_msg_obj, "channel", None):
                channel = last_msg_obj.channel
            else:
                channel = self.bot.get_channel(CHANNEL_MAIN)

            if channel:
                # determina target (menção a usuário ou autor único)
                target = self.determine_target_user(messages_to_process)

                if target and target != getattr(self.bot.user, "id", None):
                    await channel.send(f"<@{target}> {send_text}")
                else:
                    await channel.send(send_text)

                # registra que respondeu a essa última mensagem
                if last_msg_obj:
                    mid = getattr(last_msg_obj, "id", None)
                    if mid:
                        self.recently_replied[mid] = now_ts()
                # marca timestamp do canal
                try:
                    self.last_response_ts_by_channel[channel.id] = now_ts()
                except Exception:
                    pass

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

        # atualiza last_author_in_channel (usado pela heurística de chamada indireta)
        try:
            ch_id = message.channel.id
            self.last_author_in_channel[ch_id] = message.author.id
        except Exception:
            pass

        # se marcado diretamente (menção do bot) -> responde sempre (menção tem prioridade)
        if self.bot.user in message.mentions:
            # se marcado em outro canal, somente ADM pode forcar resposta
            if message.channel.id != CHANNEL_MAIN and not is_admin_member(message.author):
                return
            # registra aprendizado se for dono
            if message.author.id == OWNER_ID:
                self.learn_from_owner(message.content)
            # responde diretamente (menção sempre processada)
            asyncio.create_task(self.respond_to_message(message))
            return

        # se nao for canal principal, ignora (auto-iniciar)
        if message.channel.id != CHANNEL_MAIN:
            return

        # dono/adm nao iniciam conversa automaticamente (só por menção)
        if message.author.id in ADM_IDS:
            return

        # se em cooldown, ignora (usuários normais)
        if now < self.cooldown_until:
            return

        # registra ultima atividade global do cog
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

            # registra que respondeu a essa mensagem (menção direta)
            mid = getattr(message, "id", None)
            if mid:
                self.recently_replied[mid] = now_ts()
            try:
                self.last_response_ts_by_channel[message.channel.id] = now_ts()
            except Exception:
                pass

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
        emb.add_field(name="Recently replied (cache items)", value=str(len(self.recently_replied)))
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
