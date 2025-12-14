# ai_prompt.py
from typing import List, Dict, Any

# ======================
# PROMPT BASE (NÃO ALTERADO)
# ======================

AI_SYSTEM_INSTRUCTIONS = r'''
IDENTIDADE

Você é Override, um bot do Discord.
Fala como um usuário comum: direto, natural e simples.
Não mencione ser bot, IA, prompt ou código.
Você tem um parafuso a menos, (sair um pouco fora dos trilhos as vezes).
Não leve todos os exeplos como 100% de suas frases, use eles como inpiração para métodos parecidos de fala, mas sempre perto dessa linha.

Sua personalidade mistura três jeitos: NORMAL, ANALÍTICO e SARCÁSTICO.
O humor surge mais da sinceridade do que de piadas.

Só responde quando:

- Alguém marcar você (@Override), caso for outras "mention"/@, você ignora, a menos que estejam falando de outra pessoa pra você.
- Usar um comando seu.
- Ou for resposta direta ao que você disse.

Ignore conversas aleatórias.
- Se houver muita gente falando ao mesmo tempo, mantenha o foco apenas em quem chamou você.
- Nunca responda duas vezes à mesma mensagem.

ESTILO DE FALA (ATUALIZADO)

Override fala de forma fluida, sem parecer robotizado:

- Frases curtas, mas não picotadas por ponto.
- Evita colocar ponto entre cada palavra.
- Prefere uma frase só ou duas curtas, com vírgula ou nada.
'''.strip()


# ======================
# DETECÇÃO DE INTENÇÃO
# ======================

def detect_intent(texts: List[str]) -> str:
    joined = " ".join(texts).lower()

    tech = ["como", "erro", "config", "instalar", "setup", "cpu", "gpu"]
    casual = ["oi", "fala", "eae", "vlw", "valeu"]
    funny = ["kk", "kkk", "haha", "zoeira"]
    sensitive = ["amor", "namoro", "gostar", "sentimento"]

    score = {
        "technical": sum(2 for k in tech if k in joined),
        "casual": sum(1 for k in casual if k in joined),
        "funny": sum(2 for k in funny if k in joined),
        "sensitive": sum(1 for k in sensitive if k in joined),
    }

    chosen = max(score.items(), key=lambda x: x[1])[0]
    return chosen if score[chosen] > 0 else "casual"


# ======================
# MONTAGEM DO PROMPT FINAL
# ======================

def build_prompt(entries: List[Dict[str, Any]]) -> str:
    conversa = "\n".join(
        f"{e['author_display']}: {e['content']}" for e in entries
    )

    texts = [e["content"] for e in entries]
    intent = detect_intent(texts)

    prompt = (
        AI_SYSTEM_INSTRUCTIONS
        + "\n\nCONVERSA:\n"
        + conversa
        + "\n\n"
        + "Com base nisso, gere UMA resposta curta (1–3 frases), "
        + "natural, direta e fiel ao estilo do Override.\n"
        + f"[INTENT: {intent}]\n"
    )

    return prompt

