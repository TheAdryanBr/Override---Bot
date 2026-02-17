# utils.py
import time
import discord

# ─────────────────────────────
# IDs (CENTRALIZADOS AQUI)
#   • .env fica SÓ pra segredos (DISCORD_TOKEN etc.)
# ─────────────────────────────

# Canal principal
CHANNEL_MAIN = 1213316039350296638

# Owner / cargos base
OWNER_ID = 473962013031399425
ADMIN_ROLE_ID = 1213534921055010876
MEMBER_ROLE_ID = 1213324989202309220

# Guild principal (se no futuro for multi-servidor, isso vira config por guild)
GUILD_ID = 1213316038805164093

# Welcome / logs
WELCOME_CHANNEL_ID = 1213326279793840158
WELCOME_LOG_CHANNEL_ID = 0  # opcional: se tiver canal de logs, coloca o ID aqui

# Canais citados no embed do welcome
WELCOME_RULES_CHANNEL_ID = 1213332268618096690
WELCOME_SUGGEST_CHANNEL_ID = 1259311950958170205

# Denúncias
REPORT_CHANNEL_ID = 1408272847616344074

# Boosters
BOOSTER_RANK_CHANNEL_ID = 1415478538114564166
CUSTOM_BOOSTER_ROLE_ID = 1406307445306818683
BOOSTER_ROLE_ID = 0  # ⚠️ coloque aqui o ID do cargo "Server Booster" (se você usa essa automação)

# Platform monitor (TikTok)
PLATFORM_LIVE_CHANNEL_ID = 1214687236331667497
PLATFORM_PING_ROLE_ID = 1254470641944494131

# Promoções

PROMO_CHANNEL_ID = 1241172026715144306
STORE_CONFIG_CHANNEL_ID = 1466277513809367248

USE_APERTIUM_TRANSLATE = True
APERTIUM_PAIR = "en-pt"   # par instalado no sistema
AUTO_TRANSLATE_DESC = True
AUTO_TRANSLATE_GENRES = False  # eu deixaria falso, pq gênero já tem mapa

# Completar 3 gêneros (SteamSpy ajuda quando a Steam só dá 1-2)
USE_STEAMSPY_TAGS = True

# FreeStuff monitor
FREESTUFF_TEST_GUILD_ID = 1384621027627372714
FREESTUFF_TEST_CHANNEL_ID = 1444576416145346621
FREESTUFF_MAIN_CHANNEL_ID = 1216133008680292412
FREESTUFF_PING_ROLE_ID = 1254470219305324564
FREESTUFF_BOT_ID = 672822334641537041

# Voice Rooms (gatilhos -> categoria + prefixo)
CANAL_FIXO_CONFIG = {
    1469497077732999178: {"categoria_id": 1469496488823492608, "prefixo_nome": "🎧║𝐋𝐨𝐛𝐛𝐲║"},  # Conversas
    1406308661810171965: {"categoria_id": 1213316039350296637, "prefixo_nome": "🎧║𝐋𝐨𝐛𝐛𝐲║"},  # Outros jogos
    1404889040007725107: {"categoria_id": 1213319157639020564, "prefixo_nome": "♨║𝐉𝐚𝐯𝐚║"},     # Minecraft
    1213319477429801011: {"categoria_id": 1213319157639020564, "prefixo_nome": "🪨║𝐁𝐞𝐝𝐫𝐨𝐜𝐤║"},  # Minecraft
    1213321053196263464: {"categoria_id": 1213319620287664159, "prefixo_nome": "🎧║𝐋𝐨𝐛𝐛𝐲║"},  # Roblox
    1216123178548465755: {"categoria_id": 1216123032138154008, "prefixo_nome": "👥║𝐃𝐮𝐨║"},     # Valorant
    1216123306579595274: {"categoria_id": 1216123032138154008, "prefixo_nome": "👥║𝐓𝐫𝐢𝐨║"},    # Valorant
    1461921718346977372: {"categoria_id": 1216123032138154008, "prefixo_nome": "👥║𝐓𝐞𝐚𝐦║"},    # Valorant
    1447748570974261388: {"categoria_id": 1213532914520690739, "prefixo_nome": "👥║𝐃𝐮𝐨║"},     # Fortnite
    1447748610380005516: {"categoria_id": 1213532914520690739, "prefixo_nome": "👥║𝐓𝐫𝐢𝐨║"},    # Fortnite
    1447748647419908217: {"categoria_id": 1213532914520690739, "prefixo_nome": "👥║𝐒𝐪𝐮𝐚𝐝║"},   # Fortnite
    1213322485479637012: {"categoria_id": 1213322073594793994, "prefixo_nome": "👥║𝐃𝐮𝐨║"},     # COD
    1213322743123148920: {"categoria_id": 1213322073594793994, "prefixo_nome": "👥║𝐓𝐫𝐢𝐨║"},    # COD
    1213322826564767776: {"categoria_id": 1213322073594793994, "prefixo_nome": "👥║𝐒𝐪𝐮𝐚𝐝║"},   # COD
}


# ─────────────────────────────
# TEMPO
# ─────────────────────────────
def now_ts() -> float:
    return time.time()


# ─────────────────────────────
# PERMISSÕES
# ─────────────────────────────
def is_admin_member(member: discord.Member) -> bool:
    if member.guild_permissions.administrator:
        return True
    if member.guild.owner_id == member.id:
        return True
    return False