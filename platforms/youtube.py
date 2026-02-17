# platforms/youtube.py
"""
Detecção leve de LIVE no YouTube.
Não usa API oficial (que exige key e tem limite). Apenas scraping de metadados.

Função principal:
    check_youtube_live(channel, session=None) → LiveInfo | None

channel pode ser:
    - "theadryanbr"
    - "@theadryanbr"
    - URL de canal (ex: https://www.youtube.com/@theadryanbr)

LiveInfo:
{
  "platform": "youtube",
  "channel": "theadryanbr",
  "live_id": "abc123",
  "title": "...",
  "thumbnail": "...",
  "game": None,
  "url": "https://youtube.com/watch?v=abc123",
  "started_at": "2025-11-17T12:34:00Z"  (quando disponível)
}
"""

import aiohttp
import asyncio
import re
import json
from datetime import datetime, timezone
from typing import Optional

_YT_SEMAPHORE = asyncio.Semaphore(2)  # limitar requests simultâneos

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

# Util simples para GET
async def _fetch_text(url: str, session: aiohttp.ClientSession, timeout=12):
    try:
        async with session.get(url, headers=DEFAULT_HEADERS, timeout=timeout) as resp:
            return resp.status, await resp.text(errors="ignore")
    except:
        return None, None


# ------------------------------------------------------------
# Extração de ytInitialData (JSON enorme dentro do HTML)
# ------------------------------------------------------------

def _extract_yt_initial_data(html: str):
    """
    Tenta extrair o objeto JSON do ytInitialData.
    """
    m = re.search(r"ytInitialData\"\]\s*=\s*({.*?});</script>", html, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except:
            pass
    m = re.search(r"var ytInitialData\s*=\s*({.*?});", html, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except:
            pass
    return None


def _search_live_in_initial_data(data):
    """
    Procura vídeo ao vivo dentro de ytInitialData.
    """
    if not isinstance(data, dict):
        return None

    # Busca em todo o JSON (recursivo)
    def walk(obj):
        if isinstance(obj, dict):
            # Muitos vídeos aparecem em "gridVideoRenderer", "videoRenderer", etc.
            if "videoRenderer" in obj:
                v = obj["videoRenderer"]
                # se for live
                if v.get("badges") or v.get("thumbnailOverlays"):
                    # procurar "LIVE NOW" badge
                    overlays = v.get("thumbnailOverlays", [])
                    for o in overlays:
                        if "thumbnailOverlayTimeStatusRenderer" in o:
                            style = o["thumbnailOverlayTimeStatusRenderer"].get("style")
                            if style == "LIVE":
                                return v
            # continuar
            for val in obj.values():
                r = walk(val)
                if r:
                    return r
        elif isinstance(obj, list):
            for item in obj:
                r = walk(item)
                if r:
                    return r
        return None

    return walk(data)


# ------------------------------------------------------------
# Função principal
# ------------------------------------------------------------

async def check_youtube_live(channel: str, session: Optional[aiohttp.ClientSession] = None) -> Optional[dict]:
    """
    Detecta se o canal está ao vivo.
    channel pode ser:
        - username (@theadryanbr)
        - nome simples (theadryanbr)
        - url completa
    """

    # Normalizar entrada
    channel = channel.strip()

    # Gerar url
    if channel.startswith("http"):
        url_channel = channel
    else:
        channel = channel.lstrip("@")
        url_channel = f"https://www.youtube.com/@{channel}"

    own_session = False
    if session is None:
        session = aiohttp.ClientSession()
        own_session = True

    await _YT_SEMAPHORE.acquire()
    try:
        status, html = await _fetch_text(url_channel, session)
        if not html:
            return None

        # ------------------------------------------------
        # 1) Procurar live pela meta tag - mais rápido
        # ------------------------------------------------
        # às vezes aparece:
        # <link rel="canonical" href="https://www.youtube.com/watch?v=XXXX">
        m_canon = re.search(r'href="https://www\.youtube\.com/watch\?v=([A-Za-z0-9_-]{11})"', html)
        if m_canon and ("LIVE" in html or "isLive" in html):
            vid = m_canon.group(1)
            return {
                "platform": "youtube",
                "channel": channel,
                "live_id": vid,
                "title": None,
                "thumbnail": f"https://img.youtube.com/vi/{vid}/hqdefault.jpg",
                "game": None,
                "url": f"https://www.youtube.com/watch?v={vid}",
                "started_at": None,
            }

        # ------------------------------------------------
        # 2) Extrair ytInitialData e procurar live
        # ------------------------------------------------
        data = _extract_yt_initial_data(html)
        if data:
            live_renderer = _search_live_in_initial_data(data)
            if live_renderer:
                vid = live_renderer.get("videoId")
                title = None
                if "title" in live_renderer and "runs" in live_renderer["title"]:
                    title = "".join(t["text"] for t in live_renderer["title"]["runs"])

                thumb = None
                if "thumbnail" in live_renderer:
                    thumbs = live_renderer["thumbnail"].get("thumbnails")
                    if thumbs:
                        thumb = thumbs[-1]["url"]

                return {
                    "platform": "youtube",
                    "channel": channel,
                    "live_id": vid,
                    "title": title,
                    "thumbnail": thumb or f"https://img.youtube.com/vi/{vid}/hqdefault.jpg",
                    "game": None,
                    "url": f"https://www.youtube.com/watch?v={vid}",
                    "started_at": None,
                }

        # ------------------------------------------------
        # 3) fallback simples — procurar texto "LIVE NOW"
        # ------------------------------------------------
        if "LIVE NOW" in html or '"isLive":true' in html:
            # tentar achar algum ID
            m_v = re.search(r'watch\?v=([A-Za-z0-9_-]{11})', html)
            if m_v:
                vid = m_v.group(1)
                return {
                    "platform": "youtube",
                    "channel": channel,
                    "live_id": vid,
                    "title": None,
                    "thumbnail": f"https://img.youtube.com/vi/{vid}/hqdefault.jpg",
                    "game": None,
                    "url": f"https://www.youtube.com/watch?v={vid}",
                    "started_at": None,
                }

        return None

    finally:
        _YT_SEMAPHORE.release()
        if own_session:
            await session.close()
