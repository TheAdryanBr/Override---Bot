# platforms/tiktok.py
"""
Scraper leve para TikTok (método A).
Detecta se um usuário está em live consultando a página pública do perfil
e analisando metadados/JSON embutido. NÃO usa APIs privadas/pagas.
Retorna um dict LiveInfo ou None.

LiveInfo:
{
  "platform": "tiktok",
  "channel": "theadryanbr",
  "live_id": "1234567890",
  "title": "Título da live",
  "thumbnail": "https://...",
  "game": None,
  "url": "https://www.tiktok.com/@theadryanbr/live/12345",
  "started_at": "2025-11-17T12:34:00Z"  # opcional, se detectado
}
"""

import asyncio
import re
import json
from typing import Optional
import aiohttp
from datetime import datetime, timezone

# small semaphore to rate-limit concurrent tiktok checks from same process
_TIKTOK_SEMAPHORE = asyncio.Semaphore(2)

# sensible request headers
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (BotKeepAlive)",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# some basic backoff for transient errors
async def _fetch_text(url: str, session: aiohttp.ClientSession, timeout: int = 10):
    try:
        async with session.get(url, headers=DEFAULT_HEADERS, timeout=timeout) as resp:
            status = resp.status
            text = await resp.text(errors="ignore")
            return status, text
    except Exception:
        return None, None

async def check_tiktok_live(username: str, session: Optional[aiohttp.ClientSession] = None) -> Optional[dict]:
    """
    Verifica se @username está em live no TikTok.
    - username: com ou sem '@' (aceita 'theadryanbr' ou '@theadryanbr')
    - session: opcional aiohttp.ClientSession (recomendado reutilizar uma sessão)
    Retorna LiveInfo dict ou None.
    """
    if not username:
        return None
    # sanitize
    username = username.lstrip("@").strip()

    url_profile = f"https://www.tiktok.com/@{username}"
    url_mobile = f"https://m.tiktok.com/@{username}"

    own_session = False
    if session is None:
        session = aiohttp.ClientSession()
        own_session = True

    await _TIKTOK_SEMAPHORE.acquire()
    try:
        # try mobile first (às vezes é mais simples)
        status, text = await _fetch_text(url_mobile, session)
        if status is None:
            # fallback to main
            status, text = await _fetch_text(url_profile, session)
        # if still no text, bail out
        if not text or status is None:
            return None

        # Heurística 1: procurar JSON embutido com "is_live" ou "isLive" ou "liveStream" flags
        try:
            # procura blocos <script id="__NEXT_DATA__" type="application/json"> ... </script>
            m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', text, re.DOTALL | re.IGNORECASE)
            json_text = None
            if m:
                json_text = m.group(1).strip()
            else:
                # fallback: procura por window['SIGI_STATE']= {...}
                m2 = re.search(r'window\.__INIT_PROPS__\s*=\s*({.*?});', text, re.DOTALL)
                if m2:
                    json_text = m2.group(1)

            if json_text:
                try:
                    data = json.loads(json_text)
                    # tenta navegar para uma possível flag de live
                    # caminhos variam por versão; tentamos alguns locais comuns
                    # Ex.: data['props']['pageProps']['liveInfo'] ...
                    # Verificações defensivas:
                    # procura por qualquer ocorrência de '"is_live":true' no JSON textual também
                    if '"is_live":true' in json_text or '"isLive":true' in json_text or '"is_live": true' in json_text:
                        # buscar informações concretas (tentar diversos caminhos)
                        live_info = None
                        # tentativa 1: props -> initialState -> ...
                        def deep_search(obj):
                            if isinstance(obj, dict):
                                for k, v in obj.items():
                                    if k in ("is_live", "isLive") and v:
                                        return obj
                                    res = deep_search(v)
                                    if res:
                                        return res
                            elif isinstance(obj, list):
                                for itm in obj:
                                    res = deep_search(itm)
                                    if res:
                                        return res
                            return None
                        candidate = deep_search(data)
                        if candidate and isinstance(candidate, dict):
                            # try to extract some useful info
                            live_id = candidate.get("live_id") or candidate.get("room_id") or candidate.get("id")
                            title = candidate.get("title") or candidate.get("feed_title") or None
                            thumb = candidate.get("cover") or candidate.get("thumbnailUrl") or None
                            start = candidate.get("start_time") or candidate.get("started_at") or None
                            if start and isinstance(start, (int, float)):
                                try:
                                    started_at = datetime.fromtimestamp(int(start), tz=timezone.utc).isoformat()
                                except Exception:
                                    started_at = None
                            else:
                                started_at = None
                            if live_id:
                                return {
                                    "platform": "tiktok",
                                    "channel": username,
                                    "live_id": str(live_id),
                                    "title": title,
                                    "thumbnail": thumb,
                                    "game": None,
                                    "url": f"https://www.tiktok.com/@{username}/live/{live_id}",
                                    "started_at": started_at,
                                }
                        # if we found only is_live true but no structured info, fallback to regex below
                except Exception:
                    pass
        except Exception:
            pass

        # Heurística 2: procurar por strings conhecidas indicando live (ex.: '/live/' links, "LIVE", "watch_live")
        # procura link de live: /@username/live/<id>
        m_live = re.search(rf'/@{re.escape(username)}/live/(\d+)', text, re.IGNORECASE)
        if m_live:
            live_id = m_live.group(1)
            # tentar extrair título/thumbnail por regex simples
            m_title = re.search(r'<meta property="og:title" content="([^"]+)"', text) or re.search(r'<title>(.*?)</title>', text, re.DOTALL)
            title = (m_title.group(1).strip() if m_title else None)
            m_thumb = re.search(r'<meta property="og:image" content="([^"]+)"', text)
            thumb = (m_thumb.group(1).strip() if m_thumb else None)
            return {
                "platform": "tiktok",
                "channel": username,
                "live_id": str(live_id),
                "title": title,
                "thumbnail": thumb,
                "game": None,
                "url": f"https://www.tiktok.com/@{username}/live/{live_id}",
                "started_at": None,
            }

        # Heurística 3: procurar flags simples "is_live" textual (sem JSON)
        if re.search(r'"is_live"\s*:\s*true', text, re.IGNORECASE) or re.search(r'"isLive"\s*:\s*true', text, re.IGNORECASE):
            # tentativa de extrair um id com regex mais solta
            m_id = re.search(r'live[_-]?id["\']?\s*[:=]\s*["\']?([0-9A-Za-z_-]{6,})["\']?', text)
            live_id = m_id.group(1) if m_id else None
            m_title = re.search(r'<meta property="og:title" content="([^"]+)"') or re.search(r'<title>(.*?)</title>', text, re.DOTALL)
            title = (m_title.group(1).strip() if m_title else None)
            m_thumb = re.search(r'<meta property="og:image" content="([^"]+)"', text)
            thumb = (m_thumb.group(1).strip() if m_thumb else None)
            if live_id:
                return {
                    "platform": "tiktok",
                    "channel": username,
                    "live_id": str(live_id),
                    "title": title,
                    "thumbnail": thumb,
                    "game": None,
                    "url": f"https://www.tiktok.com/@{username}/live/{live_id}",
                    "started_at": None,
                }
            else:
                # no id, but live flagged: return generic live result
                return {
                    "platform": "tiktok",
                    "channel": username,
                    "live_id": f"live_{username}",
                    "title": title,
                    "thumbnail": thumb,
                    "game": None,
                    "url": f"https://www.tiktok.com/@{username}",
                    "started_at": None,
                }

        # nothing found -> assume not live
        return None

    finally:
        _TIKTOK_SEMAPHORE.release()
        if own_session:
            try:
                await session.close()
            except Exception:
                pass
