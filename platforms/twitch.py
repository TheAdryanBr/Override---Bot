# platforms/twitch.py
"""
Detecção leve de LIVE na Twitch usando scraping e JSON embutidos.
Não usa API oficial, não usa OAuth.

Função principal:
    check_twitch_live(channel, session=None) → LiveInfo | None

channel pode ser:
    - "theadryanbr"
    - "@theadryanbr"
    - URL completa (https://twitch.tv/theadryanbr)

Retorno LiveInfo:
{
  "platform": "twitch",
  "channel": "theadryanbr",
  "live_id": "123456789",
  "title": "...",
  "thumbnail": "...",
  "game": "...",
  "url": "https://twitch.tv/theadryanbr",
  "started_at": "2025-11-17T13:22:05Z"
}
"""

import aiohttp
import asyncio
import re
import json
from datetime import datetime, timezone
from typing import Optional

_TTV_SEMAPHORE = asyncio.Semaphore(2)

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}


async def _fetch_text(url: str, session: aiohttp.ClientSession, timeout=12):
    try:
        async with session.get(url, headers=DEFAULT_HEADERS, timeout=timeout) as resp:
            return resp.status, await resp.text(errors="ignore")
    except:
        return None, None


# ------------------------------------------------------------------------------
# Extrair o objeto JSON "data-a-state", onde fica o estado da página da Twitch
# ------------------------------------------------------------------------------

def _extract_twitch_state(html: str):
    """
    Twitch insere um JSON gigante em data-a-state="...".
    Contém informações completas sobre o canal.
    """
    m = re.search(r'data-a-state="({.*?})"', html)
    if not m:
        return None
    try:
        # html entities → normal
        raw = m.group(1).replace("&quot;", '"').replace("&amp;", "&")
        return json.loads(raw)
    except:
        return None


def _parse_live_info(state: dict):
    """
    A Twitch inclui status de live em: state["channel"]["stream"] ou similar.
    """
    if not isinstance(state, dict):
        return None

    # procurar stream ativo
    stream = None

    # Novo layout moderno
    p1 = state.get("channel")
    if isinstance(p1, dict):
        stream = p1.get("stream")

    # Outro formato antigo
    if stream is None:
        p2 = state.get("stream", {})
        if isinstance(p2, dict):
            stream = p2

    if not stream or not isinstance(stream, dict):
        return None

    # Verificar se é live
    if stream.get("type") != "live":
        return None

    # Coletar info
    live_id = stream.get("id")
    title = stream.get("title")
    thumb = stream.get("previewImageURL")
    game = None
    if "game" in stream:
        game = stream["game"].get("displayName")

    # started at (timestamp)
    started_at = None
    if "createdAt" in stream:
        try:
            started_at = datetime.fromisoformat(stream["createdAt"].replace("Z", "+00:00")).astimezone(timezone.utc)
            started_at = started_at.isoformat()
        except:
            started_at = None

    return {
        "live_id": live_id,
        "title": title,
        "thumbnail": thumb,
        "game": game,
        "started_at": started_at,
    }


# ------------------------------------------------------------------------------
# Função principal
# ------------------------------------------------------------------------------

async def check_twitch_live(channel: str, session: Optional[aiohttp.ClientSession] = None) -> Optional[dict]:
    """
    Detecta lives na Twitch de forma leve e sem API.
    """

    channel = channel.strip()

    if channel.startswith("http"):
        url_channel = channel
        # tentar extrair username
        m = re.search(r"twitch\.tv/([^/?]+)", channel)
        if m:
            channel = m.group(1)
    else:
        channel = channel.lstrip("@")
        url_channel = f"https://www.twitch.tv/{channel}"

    own_session = False
    if session is None:
        session = aiohttp.ClientSession()
        own_session = True

    await _TTV_SEMAPHORE.acquire()
    try:
        status, html = await _fetch_text(url_channel, session)
        if not html:
            return None

        # ------------------------------------------------------------------
        # 1) Extrair JSON state do data-a-state
        # ------------------------------------------------------------------
        state = _extract_twitch_state(html)
        if state:
            parsed = _parse_live_info(state)
            if parsed:
                return {
                    "platform": "twitch",
                    "channel": channel,
                    "live_id": parsed["live_id"],
                    "title": parsed["title"],
                    "thumbnail": parsed["thumbnail"],
                    "game": parsed["game"],
                    "url": f"https://www.twitch.tv/{channel}",
                    "started_at": parsed["started_at"],
                }

        # ------------------------------------------------------------------
        # 2) fallback: procurar "isLiveBroadcast"
        # ------------------------------------------------------------------
        if '"isLiveBroadcast":true' in html or '"broadcastType":"live"' in html:
            # tentar puxar ID do vídeo do streamPlaybackAccessToken
            m_v = re.search(r'"id":"(\d+)"', html)
            vid = m_v.group(1) if m_v else None

            return {
                "platform": "twitch",
                "channel": channel,
                "live_id": vid,
                "title": None,
                "thumbnail": None,
                "game": None,
                "url": f"https://www.twitch.tv/{channel}",
                "started_at": None,
            }

        return None

    finally:
        _TTV_SEMAPHORE.release()
        if own_session:
            await session.close()

