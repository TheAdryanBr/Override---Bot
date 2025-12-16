# ai_persona.py

class PersonaProfile:
    def __init__(
        self,
        patience: int = 1,
        style: str = "normal",
        verbosity: str = "curta",
        aggressiveness: str = "leve"
    ):
        self.patience = patience
        self.style = style
        self.verbosity = verbosity
        self.aggressiveness = aggressiveness


class AIPersonaManager:
    def __init__(self):
        pass

    def build_persona(self, memory, state):
        """
        memory: dados do ai_memory (frequência, repetição, etc)
        state: resultado do ai_state
        """

        patience = self._calc_patience(memory)
        style = self._calc_style(memory)
        verbosity = self._calc_verbosity(memory)
        aggressiveness = self._calc_aggressiveness(patience)

        return PersonaProfile(
            patience=patience,
            style=style,
            verbosity=verbosity,
            aggressiveness=aggressiveness
        )

    # -------------------------
    # Heurísticas simples
    # -------------------------

    def _calc_patience(self, memory):
        """
        Aumenta impaciência com:
        - repetição
        - insistência
        """
        repeat = memory.get("repetition_score", 0)
        spam = memory.get("spam_score", 0)

        if repeat > 6 or spam > 5:
            return 4
        if repeat > 4:
            return 3
        if repeat > 2:
            return 2
        return 1

    def _calc_style(self, memory):
        """
        Decide o estilo principal
        """
        tech = memory.get("technical_ratio", 0)
        humor = memory.get("humor_ratio", 0)

        if humor > tech:
            return "sarcastic"
        if tech > 0.6:
            return "analytical"
        return "normal"

    def _calc_verbosity(self, memory):
        """
        Pessoas que mandam mensagens longas aceitam respostas médias
        """
        avg_len = memory.get("avg_message_length", 0)

        if avg_len > 120:
            return "media"
        return "curta"

    def _calc_aggressiveness(self, patience):
        """
        Direto, sem grosseria gratuita
        """
        if patience >= 4:
            return "media"
        if patience == 3:
            return "leve"
        return "leve"
