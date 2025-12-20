# utils.py
import time
import discord

# 🔹 ID do canal principal (ajuste se quiser puxar do ENV depois)
CHANNEL_MAIN = 1261154588766244905  # ← CONFIRA SE ESSE ID ESTÁ CERTO

# ─────────────────────────────
# TEMPO
# ─────────────────────────────

def now_ts() -> float:
    """Timestamp atual em segundos"""
    return time.time()

# ─────────────────────────────
# PERMISSÕES
# ─────────────────────────────

def is_admin_member(member: discord.Member) -> bool:
    """
    Retorna True se o membro for administrador
    (ADMINISTRATOR ou dono do servidor)
    """
    if member.guild_permissions.administrator:
        return True

    if member.guild.owner_id == member.id:
        return True

    return False
