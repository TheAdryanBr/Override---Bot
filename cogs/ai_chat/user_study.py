# ai_chat/user_study.py
import time
import json
from pathlib import Path
from typing import Dict, Any

STUDY_FILE = Path("user_study.json")

class UserStudy:
    """
    Camada de observação passiva de usuários.
    Não altera respostas, apenas coleta padrões simples.
    """

    def __init__(self):
        self.data: Dict[int, Dict[str, Any]] = {}
        self.enabled: bool = True
        self._load()

    # ----------------------
    # Persistência
    # ----------------------
    def _load(self):
        if STUDY_FILE.exists():
            try:
                raw = json.loads(STUDY_FILE.read_text(encoding="utf-8"))
                # converte chaves para int
                self.data = {int(k): v for k, v in raw.items()}
            except Exception:
                self.data = {}

    def _save(self):
        try:
            STUDY_FILE.write_text(
                json.dumps(self.data, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
        except Exception:
            pass

    # ----------------------
    # Coleta
    # ----------------------
    def observe_message(self, user_id: int, content: str):
        if not self.enabled:
            return

        now = time.time()
        profile = self.data.setdefault(user_id, {
            "messages": 0,
            "avg_length": 0.0,
            "question_rate": 0.0,
            "casual_rate": 0.0,
            "technical_rate": 0.0,
            "last_seen": now,
        })

        profile["messages"] += 1
        profile["last_seen"] = now

        length = len(content.split())
        profile["avg_length"] = (
            (profile["avg_length"] * (profile["messages"] - 1)) + length
        ) / profile["messages"]

        if "?" in content:
            profile["question_rate"] += 1

        low = content.lower()
        if any(w in low for w in ("oi", "fala", "kk", "haha", "blz", "eae")):
            profile["casual_rate"] += 1

        if any(w in low for w in ("como", "erro", "config", "setup", "cpu", "gpu")):
            profile["technical_rate"] += 1

        self._normalize(profile)
        self._save()

    # ----------------------
    # Normalização
    # ----------------------
    def _normalize(self, profile: Dict[str, Any]):
        msgs = max(profile.get("messages", 1), 1)
        profile["question_rate"] = round(profile["question_rate"] / msgs, 2)
        profile["casual_rate"] = round(profile["casual_rate"] / msgs, 2)
        profile["technical_rate"] = round(profile["technical_rate"] / msgs, 2)

    # ----------------------
    # Leitura
    # ----------------------
    def get_profile(self, user_id: int) -> Dict[str, Any] | None:
        return self.data.get(user_id)

    def reset_user(self, user_id: int):
        if user_id in self.data:
            del self.data[user_id]
            self._save()
