class SocialAlignment:
    def __init__(self, anchor_ids: set[int]):
        self.anchor_ids = anchor_ids
        self.last_anchor_tone: str | None = None

    def analyze(self, author_id: int, content: str):
        if author_id not in self.anchor_ids:
            return

        lowered = content.lower()

        if any(x in lowered for x in ("kkk", "haha", "zoa", "burro", "mds", "vsf")):
            self.last_anchor_tone = "sarcastic"
        elif any(x in lowered for x in ("acho", "penso", "talvez", "na real")):
            self.last_anchor_tone = "neutral"
        else:
            self.last_anchor_tone = "normal"

    def get_tone(self) -> str | None:
        return self.last_anchor_tone
