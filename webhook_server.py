# webhook_server.py
import asyncio
import logging
import json
from aiohttp import web

log = logging.getLogger("webhook_server")

# Fila async pro seu cog consumir
webhook_queue: asyncio.Queue = asyncio.Queue()

WEBHOOK_SECRET = ""  # opcional, mas recomendo
HOST = "0.0.0.0"
PORT = 8787
PATH = "/tikfinity"

_runner = None
_site = None

async def handler(request: web.Request) -> web.Response:
    # Segurança simples (evita qualquer device da rede te spammar)
    if WEBHOOK_SECRET:
        if request.headers.get("X-Webhook-Secret") != WEBHOOK_SECRET:
            return web.Response(status=401, text="unauthorized")

    payload = {}

    # querystring
    if request.query:
        payload.update(dict(request.query))

    # json / form / texto
    try:
        data = await request.json()
        if isinstance(data, dict):
            payload.update(data)
        else:
            payload["data"] = data
    except Exception:
        try:
            form = await request.post()
            if form:
                payload.update({k: str(v) for k, v in form.items()})
        except Exception:
            try:
                raw = (await request.text()).strip()
                if raw:
                    try:
                        j = json.loads(raw)
                        payload.update(j if isinstance(j, dict) else {"data": j})
                    except Exception:
                        payload["raw"] = raw
            except Exception:
                pass

    await webhook_queue.put(payload)
    return web.Response(text="ok")

async def ensure_webhook_server(host: str = "0.0.0.0", port: int = 8787, path: str = "/tikfinity"):
    global _runner, _site
    if _runner is not None:
        return

    app = web.Application(client_max_size=2 * 1024 * 1024)
    app.router.add_route("*", PATH, handler)

    _runner = web.AppRunner(app)
    await _runner.setup()
    _site = web.TCPSite(_runner, HOST, PORT)
    await _site.start()

    log.info(f"[OK] Webhook server em http://{HOST}:{PORT}{PATH}")