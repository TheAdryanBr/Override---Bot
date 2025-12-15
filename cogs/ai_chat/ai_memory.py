import json
import os
import time
from typing import Dict, Any

DATA_DIR = "data"
MEMORY_FILE = os.path.join(DATA_DIR, "user_memory.json")

class AIMemory:
    """
    Gerencia memória leve de usuários:
    - Cache em RAM para usuários ativos
    - Persistência em arquivo para usuários inativos
    """

    def __init__(self):
        self.active_users: Dict[int, Dict[str, Any]] = {}
        self._ensure_storage()
        self._load_file()

    # ─────────────────────────────
    # SETUP
    # ─────────────────────────────

    def _ensure_storage(self):
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR)

        if not os.path.exists(MEMORY_FILE):
            with open(MEMORY_FILE, "w", encoding="utf-8") as f:
                json.dump({}, f, ensure_ascii=False, indent=2)

    def _load_file(self):
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                self.file_data: Dict[str, Dict[str, Any]] = json.load(f)
        except Exception:
            self.file_data = {}

    def _save_file(self):
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(self.file_data, f, ensure_ascii=False, indent=2)

    # ─────────────────────────────
    # CORE
    # ─────────────────────────────

    def get_user(self, user_id: int) -> Dict[str, Any]:
        """
        Retorna o perfil do usuário.
        Se não estiver na RAM, carrega do arquivo ou cria um novo.
        """
        if user_id in self.active_users:
            return self.active_users[user_id]

        key = str(user_id)

        if key in self.file_data:
            profile = self.file_data[key]
        else:
            profile = self._create_default_profile(user_id)
            self.file_data[key] = profile
            self._save_file()

        self.active_users[user_id] = profile
        return profile

    def release_user(self, user_id: int):
        """
        Remove usuário da RAM e salva no arquivo.
        """
        if user_id not in self.active_users:
            return

        profile = self.active_users[user_id]
        self.file_data[str(user_id)] = profile
        self._save_file()

        del self.active_users[user_id]

    # ─────────────────────────────
    # UPDATE METHODS
    # ─────────────────────────────

    def update_interaction(
        self,
        user_id: int,
        message_length: int,
        asked_question: bool
    ):
        """
        Atualiza métricas simples de comportamento.
        """
        profile = self.get_user(user_id)

        profile["messages"] += 1
        profile["total_msg_size"] += message_length
        profile["last_seen"] = int(time.time())

        if asked_question:
            profile["questions"] += 1

        # Cálculos derivados
        profile["avg_msg_size"] = round(
            profile["total_msg_size"] / max(profile["messages"], 1), 2
        )

        profile["question_rate"] = round(
            profile["questions"] / max(profile["messages"], 1), 2
        )

    def set_style(self, user_id: int, style: str):
        """
        Ajusta estilo detectado do usuário.
        """
        profile = self.get_user(user_id)
        profile["style"] = style
        profile["last_seen"] = int(time.time())

    # ─────────────────────────────
    # DEFAULT PROFILE
    # ─────────────────────────────

    def _create_default_profile(self, user_id: int) -> Dict[str, Any]:
        return {
            "user_id": user_id,
            "style": "neutro",
            "messages": 0,
            "questions": 0,
            "total_msg_size": 0,
            "avg_msg_size": 0,
            "question_rate": 0,
            "last_seen": int(time.time())
        }

