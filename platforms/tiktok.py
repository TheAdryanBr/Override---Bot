import aiohttp
import json

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 10) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Mobile Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://www.tiktok.com/",
}

async def check_tiktok_live(username: str):
    url = f"https://www.tiktok.com/api/user/detail/?uniqueId={username}"

    async with aiohttp.ClientSession(headers=HEADERS) as session:
        async with session.get(url) as resp:
            text = await resp.text()

            # DEBUG CRÍTICO
            if not text.startswith("{"):
                print("[TikTok DEBUG] Resposta NÃO JSON")
                print(text[:300])
                return None

            try:
                data = json.loads(text)
            except Exception as e:
                print("[TikTok DEBUG] Falha ao parsear JSON:", e)
                return None

    user = data.get("userInfo", {}).get("user")
    if not user:
        return None

    room_id = user.get("roomId")
    if not room_id:
        return None

    return {
        "room_id": room_id,
        "url": f"https://www.tiktok.com/@{username}/live",
        "avatar": user.get("avatarLarger"),
        "nickname": user.get("nickname"),
    }
