# ai_memory.py
import json
import os
import time
from typing import Dict, Any

DATA_DIR = "data"
MEMORY_FILE = os.path.join(DATA_DIR, "user_memory.json")


class AIMemory:
    """
    Memória leve de usuários:
    - RAM para usuários ativos
    - Arquivo para persistência
    - Fornece sinais para o fluxo mental 🧠
    """

    def __init__(self):
        self.active_users: Dict[int, Dict[str, Any]] = {}
        self._ensure_storage()
        self._load_file()

    # ─────────────────────────────
    # SETUP
    # ─────────────────────────────

    def _ensure_storage(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        if not os.path.exists(MEMORY_FILE):
            with open(MEMORY_FILE, "w", encoding="utf-8") as f:
                json.dump({}, f, ensure_ascii=False, indent=2)

    def _load_file(self):
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                self.file_data = json.load(f)
        except Exception:
            self.file_data = {}

    def _save_file(self):
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(self.file_data, f, ensure_ascii=False, indent=2)

    # ─────────────────────────────
    # CORE
    # ─────────────────────────────

    def get_user(self, user_id: int) -> Dict[str, Any]:
        if user_id in self.active_users:
            return self.active_users[user_id]

        key = str(user_id)
        profile = self.file_data.get(key, self._create_default_profile(user_id))
        self.file_data[key] = profile
        self.active_users[user_id] = profile
        return profile

    def release_user(self, user_id: int):
        if user_id not in self.active_users:
            return
        self.file_data[str(user_id)] = self.active_users[user_id]
        self._save_file()
        del self.active_users[user_id]

    # ─────────────────────────────
    # UPDATE / LEARNING 🧠
    # ─────────────────────────────

    def update_interaction(self, user_id: int, message_length: int, asked_question: bool):
        p = self.get_user(user_id)

        p["messages"] += 1
        p["total_msg_size"] += message_length
        p["last_seen"] = int(time.time())
        p["last_interaction"] = p["last_seen"]
        p["in_conversation"] = True

        if asked_question:
            p["questions"] += 1

        p["avg_msg_size"] = round(
            p["total_msg_size"] / max(p["messages"], 1), 2
        )
        p["question_rate"] = round(
            p["questions"] / max(p["messages"], 1), 2
        )

        # sinais comportamentais simples
        p["talkative"] = min(p["avg_msg_size"] / 120, 1.0)
        p["direct"] = 1.0 - p["question_rate"]

    def end_conversation(self, user_id: int):
        p = self.get_user(user_id)
        p["in_conversation"] = False
        self.release_user(user_id)

    # ─────────────────────────────
    # HELPERS PARA O FLUXO 🧠
    # ─────────────────────────────

    def prefers_questions(self, user_id: int) -> bool:
        return self.get_user(user_id)["question_rate"] > 0.4

    def is_talkative(self, user_id: int) -> bool:
        return self.get_user(user_id)["talkative"] > 0.5

    def get_style_hint(self, user_id: int) -> str:
        p = self.get_user(user_id)
        if p["talkative"] < 0.3:
            return "curto"
        if p["question_rate"] > 0.5:
            return "explicativo"
        return "neutro"

    # ─────────────────────────────
    # DEFAULT
    # ─────────────────────────────

    def _create_default_profile(self, user_id: int) -> Dict[str, Any]:
        now = int(time.time())
        return {
            "user_id": user_id,
            "style": "neutro",
            "messages": 0,
            "questions": 0,
            "total_msg_size": 0,
            "avg_msg_size": 0,
            "question_rate": 0,
            "talkative": 0.0,
            "direct": 0.5,
            "in_conversation": False,
            "last_seen": now,
            "last_interaction": now
        }
