# ai_chat/read_intent.py
# (substitua o arquivo inteiro por este)

import re
from dataclasses import dataclass
from typing import Optional, Tuple

import discord


# Comandos explícitos de leitura (sem IA pesada)
# - aceita variações comuns: "le", "lê", "leia", "olha", "ve", "vê", "veja", "analisa", "resume", "explica"
# - o nome Override pode aparecer antes, depois, ou ser omitido (porque o core já exige direct)
_CMD_RE = re.compile(
    r"""
    (?:
        \boverride\b[\s,:-]*   # "override:" opcional
    )?
    (?:
        \b(?:l[eê]|leia|ler|olha|v[eê]|veja|analisa|resuma|resume|explica)\b
        (?:\s+(?:isso|isto|aqui|essa|esse|esta|este))?
    )
    """,
    flags=re.IGNORECASE | re.VERBOSE,
)


def _strip_command_prefix(text: str) -> Tuple[str, bool]:
    """
    Remove o comando do começo (ex: 'Override lê isso: <texto>') e retorna:
      (resto_do_texto, tinha_comando)
    """
    if not text:
        return "", False

    m = _CMD_RE.search(text)
    if not m:
        return text.strip(), False

    # só consideramos comando se ele aparece bem no começo (ou quase começo),
    # pra não confundir frases tipo "eu li isso ontem"
    if m.start() > 8:
        return text.strip(), False

    rest = text[m.end():].strip(" \t\r\n:,-")
    return rest.strip(), True


@dataclass
class ReadIntent:
    # Campo principal que o core vai checar
    wants_read: bool
    reason: str

    # Se for inline (texto na mesma mensagem), vem aqui
    target_text: Optional[str] = None

    # Se for reply resolvido, o core pode usar o reference.resolved; a gente só marca que é reply
    is_reply: bool = False

    # Informativo
    requester_author_id: Optional[int] = None
    requester_author_name: Optional[str] = None


def build_read_intent(message: discord.Message, bot_user=None) -> Optional[ReadIntent]:
    """
    Decide se a mensagem é um pedido explícito de leitura.
    Regras duras:
      - Reply sozinho NÃO ativa leitura.
      - Precisa comando explícito (le/lê/leia/olha/veja/analisa/resume/explica...).
      - Se não tiver alvo inline e não for reply resolvido → ainda é wants_read, mas sem target_text.
        (o core deve responder pedindo reply)
    """
    content = (getattr(message, "content", "") or "").strip()
    if not content:
        return None

    # Detecta se a pessoa usou comando (no começo)
    rest, has_cmd = _strip_command_prefix(content)

    # Verifica se é reply (referência existe)
    ref = getattr(message, "reference", None)
    is_reply = bool(ref)

    # Regra: reply só conta se tiver comando explícito
    if is_reply and not has_cmd:
        return None

    # Se não é reply, precisa comando explícito
    if (not is_reply) and (not has_cmd):
        return None

    # Inline: se tiver texto depois do comando, esse é o alvo
    target_text = rest.strip() if rest else None

    return ReadIntent(
        wants_read=True,
        reason=("reply_command" if is_reply else "inline_command"),
        target_text=target_text,
        is_reply=is_reply,
        requester_author_id=int(getattr(getattr(message, "author", None), "id", 0) or 0) or None,
        requester_author_name=getattr(getattr(message, "author", None), "display_name", None),
    )