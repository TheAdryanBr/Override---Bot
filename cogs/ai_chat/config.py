# cogs/ai_chat/config.py

from dataclasses import dataclass


@dataclass(frozen=True)
class AIChatConfig:
    # batching / fragmentos
    base_window: float = 3.0
    fragment_window: float = 8.0
    max_wait_soft: float = 14.0
    max_wait_hard: float = 60.0
    typing_grace: float = 12.0

    # memória antirepetição
    self_memory_limit: int = 6
    per_author_buffer_limit: int = 12

    # addressing
    # Se o batch fechou MUITO rápido (mensagens coladas), força mention para evitar ambiguidade.
    addressing_force_if_batch_age_lt: float = 1.2

    # interjeições (sempre precisam de direct)
    # spontaneous: comentário curto “zoeira/analítico” quando chamado
    spontaneous_chance: float = 0.35
    spontaneous_global_cooldown: float = 18.0
    spontaneous_per_author_cooldown: float = 25.0

    # secondary: quando já tem conversa engajada com outro autor e alguém chama o bot
    secondary_window: float = 35.0
    secondary_max_turns: int = 2
    secondary_per_author_cooldown: float = 45.0

    # “tom” (não é IA extra; é orientação do prompt)
    tone_analytic_ratio: float = 0.60
    tone_sarcasm_ratio: float = 0.40


CFG = AIChatConfig()