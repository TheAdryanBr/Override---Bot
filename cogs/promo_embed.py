from __future__ import annotations

import re
import html
import asyncio
import os
import json
from dataclasses import dataclass
from typing import Optional, Dict, List, Tuple, Any
from difflib import SequenceMatcher

import discord
from discord import app_commands
from discord.ext import commands
import aiohttp

from utils import (
    GUILD_ID,
    PROMO_CHANNEL_ID,
    STORE_CONFIG_CHANNEL_ID,
    USE_APERTIUM_TRANSLATE,
    APERTIUM_PAIR,
    AUTO_TRANSLATE_DESC,
    AUTO_TRANSLATE_GENRES,
    USE_STEAMSPY_TAGS,
)

TEST_GUILD = discord.Object(id=GUILD_ID)

HTTP_TIMEOUT = 20
MAX_DESC_CHARS = 320
MAX_GENRES = 3

# /home/adryan/Override
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

MAIN_GENRES_PT = {"ação", "aventura", "rpg", "estratégia", "simulação", "esportes", "corrida", "casual", "indie"}
MAIN_TAGS_EN = {"Action", "Adventure", "RPG", "Strategy", "Simulation", "Sports", "Racing", "Casual", "Indie"}

PT_STOP = {"o","a","os","as","de","do","da","dos","das","que","para","com","em","um","uma","no","na","nos","nas","por","se","ao","à","às","é","são","você","vocês"}
EN_STOP = {"the","and","with","from","you","your","build","fight","explore","craft","defend","players","game","loot","weapons","armor","zombies","extract","scavenge"}

GENRE_MAP_EN_PT = {
    "Action": "Ação",
    "Adventure": "Aventura",
    "Indie": "Indie",
    "RPG": "RPG",
    "Strategy": "Estratégia",
    "Simulation": "Simulação",
    "Sports": "Esportes",
    "Racing": "Corrida",
    "Casual": "Casual",
    "Early Access": "Acesso Antecipado",
    "Free to Play": "Gratuito",
    "Free To Play": "Gratuito",
    "Massively Multiplayer": "MMO",
    "Co-op": "Cooperativo",
    "Singleplayer": "Um jogador",
    "Multiplayer": "Multijogador",
    "Online Co-Op": "Co-op online",
    "Local Co-Op": "Co-op local",
}
_GENRE_MAP_LC = {k.lower(): v for k, v in GENRE_MAP_EN_PT.items()}


def looks_english(text: str) -> bool:
    t = (text or "").lower()
    words = re.findall(r"[a-zA-Z']+", t)
    if len(words) < 8:
        return any(w in t.split() for w in ("the", "and", "with", "from", "you", "your"))
    en = sum(1 for w in words if w in EN_STOP)
    pt = sum(1 for w in words if w in PT_STOP)
    return en >= 2 and en > pt


def translate_genre_fast(label: str) -> str:
    s = (label or "").strip()
    if not s:
        return s
    return _GENRE_MAP_LC.get(s.lower(), s)


# --------------------
# Helpers
# --------------------
def _clean_text(s: str) -> str:
    s = (s or "").replace("\r", "").strip()
    return html.unescape(s)


def _smart_truncate(text: str, max_chars: int) -> str:
    t = _clean_text(text)
    if len(t) <= max_chars:
        return t

    cut = t[:max_chars].rstrip()
    for sep in [".", "!", "?", "\n"]:
        idx = cut.rfind(sep)
        if idx >= int(max_chars * 0.6):
            return cut[: idx + 1].strip()

    sp = cut.rfind(" ")
    if sp >= int(max_chars * 0.6):
        return cut[:sp].strip() + "…"

    return cut.strip() + "…"


def _parse_hex_color(token: str) -> Optional[int]:
    if not token:
        return None
    t = token.strip()
    if t.startswith("#"):
        t = t[1:]
    if t.lower().startswith("0x"):
        t = t[2:]
    if re.fullmatch(r"[0-9a-fA-F]{6}", t):
        return int(t, 16)
    return None


def _extract_role_id(token: str) -> Optional[int]:
    token = (token or "").strip()
    if token.isdigit() and len(token) >= 15:
        try:
            return int(token)
        except ValueError:
            return None
    return None


def _extract_steam_appid(url: str) -> Optional[int]:
    m = re.search(r"store\.steampowered\.com/app/(\d+)", url or "", re.I)
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def _domain_to_store_key(url: str) -> Optional[str]:
    u = (url or "").lower()
    if "store.steampowered.com" in u:
        return "steam"
    if "store.epicgames.com" in u:
        return "epic"
    if "gog.com" in u:
        return "gog"
    if "nuuvem.com" in u:
        return "nuuvem"
    if "humblebundle.com" in u:
        return "humble"
    if "greenmangaming.com" in u:
        return "gmg"
    if "gamersgate.com" in u:
        return "gamersgate"
    if "gaming.amazon.com" in u:
        return "prime"
    if "xbox.com" in u or "microsoft.com" in u:
        return "xbox"
    if "store.ubi.com" in u or "ubisoft.com" in u:
        return "ubisoft"
    if "robertsspaceindustries.com" in u:
        return "rsi"
    return None


def _format_desc_field(desc: str) -> str:
    desc = _smart_truncate(desc, MAX_DESC_CHARS)
    return f"```{desc}\n```"


def _format_genres_field(items: List[str]) -> str:
    items = [i.strip() for i in items if i and i.strip()]
    items = items[:MAX_GENRES]
    lines = "\n".join([f"• {x}" for x in items]) if items else "• (não informado)"
    return f"```{lines}```"


def _format_price_field(price_text: str) -> str:
    return f"```diff\n+ {price_text}\n```"


def _format_coupon_field(coupon: str) -> str:
    return f"``` {coupon} ```"


def _protect_phrases(text: str, phrases: List[str]) -> Tuple[str, Dict[str, str]]:
    """Substitui frases por tokens antes de traduzir e salva o mapa token->original."""
    out = text or ""
    mapping: Dict[str, str] = {}
    counter = 0

    # remove vazios e ordena por tamanho (maiores primeiro)
    uniq = []
    seen = set()
    for p in phrases:
        p = (p or "").strip()
        if len(p) >= 2 and p.lower() not in seen:
            seen.add(p.lower())
            uniq.append(p)
    uniq.sort(key=len, reverse=True)

    for phrase in uniq:
        pat = re.compile(re.escape(phrase), re.I)

        def repl(m: re.Match) -> str:
            nonlocal counter
            token = f"ZXQKEEP{counter}ZXQ"
            counter += 1
            mapping[token] = m.group(0)
            return token

        out = pat.sub(repl, out)

    return out, mapping


def _restore_phrases(text: str, mapping: Dict[str, str]) -> str:
    out = text
    for token, original in mapping.items():
        out = out.replace(token, original)
    return out

_EN_LEFTOVERS = {
    # números / conectores muito comuns
    "one": "uma",
    "two": "duas",
    "three": "três",
    "four": "quatro",
    "five": "cinco",
    "across": "ao redor de",
    "over": "mais de",
    "from": "de",
    "and": "e",
    "the": "o",
    "to": "para",
    "in": "em",
    "on": "em",
    "of": "de",
    "with": "com",

    # palavras de Steam-description bem frequentes
    "players": "jogadores",
    "player": "jogador",
    "million": "milhões",
    "millions": "milhões",
    "elite": "elite",
    "competitive": "competitiva",
    "experience": "experiência",
    "chapter": "capítulo",
    "story": "história",
    "begin": "começar",
    "globe": "mundo",
}

def _apertium_rescue_leftovers(t: str) -> str:
    s = t or ""

    # Frases clássicas que o Apertium costuma estragar nesse tipo de texto
    s = re.sub(r"\bacross\s+(?:o|a)\s+(?:bal[aã]o|globo)\b", "no mundo todo", s, flags=re.I)
    s = re.sub(r"\bpor\s+mais\s+de\s+duas\s+década\b", "por mais de duas décadas", s, flags=re.I)
    s = re.sub(r"\bum\s+elite\s+experiência\s+competitiv[oa]\b", "uma experiência competitiva de elite", s, flags=re.I)
    s = re.sub(r"\bpor\s+milh(?:ão|oes)\s+de\s+jogador\b", "por milhões de jogadores", s, flags=re.I)
    s = re.sub(r"\bé\s+aproximadamente\s+per\s+começar\b", "está prestes a começar", s, flags=re.I)

    # Se ainda tem tokens EN soltos, substitui por dicionário
    def repl(m: re.Match) -> str:
        w = m.group(0)
        return _EN_LEFTOVERS.get(w.lower(), w)

    # só mexe em palavras ASCII (pra não ferrar PT)
    s = re.sub(r"\b[A-Za-z]{2,}\b", repl, s)

    # ajeitos finais de concordância simples
    s = re.sub(r"\bduas\s+década\b", "duas décadas", s, flags=re.I)
    s = re.sub(r"\bum\s+elite\b", "uma elite", s, flags=re.I)
    s = re.sub(r"\bo\s+história\b", "a história", s, flags=re.I)

    return s


def _apertium_postprocess(text: str) -> str:
    t = text or ""
    t = t.replace("@-", "-").replace("@", "").replace("#", "").replace("*", "")
    t = re.sub(r"\b([A-Z][A-Za-z0-9]+)-(o|a|os|as)\b", r"\1", t)
    t = re.sub(r"\s+([,.;:!?])", r"\1", t)
    t = re.sub(r"\s{2,}", " ", t).strip()

    if t.lower().startswith("por sobre "):
        t = "Por mais de " + t[len("Por sobre "):]

    t = _apertium_rescue_leftovers(t)
    return t


# --------------------
# Data
# --------------------
@dataclass
class StoreProfile:
    key: str
    display_name: str
    color: int
    logo_url: str
    role_id: Optional[int]


@dataclass
class GameInfo:
    store_key: str           # loja do LINK (nuuvem/epic/etc) - pra embed cor/logo/role
    url: str                 # link destino (o que você passou)
    title: str               # vem da Steam (quando possível)
    description: str         # vem da Steam (quando possível)
    image_url: Optional[str] # preferencialmente header da Steam
    price_text: Optional[str]# vem da loja destino (ou do "preco" manual quando cupom)
    genres: List[str]        # vem da Steam


class StoreRegistry:
    def __init__(self) -> None:
        self._stores: Dict[str, StoreProfile] = {}

    def get(self, key: str) -> Optional[StoreProfile]:
        return self._stores.get((key or "").lower())

    def is_empty(self) -> bool:
        return not bool(self._stores)

    async def load_from_pins(self, bot: commands.Bot, channel_id: int) -> int:
        self._stores.clear()
        if not channel_id:
            return 0

        ch = bot.get_channel(channel_id)
        if ch is None:
            ch = await bot.fetch_channel(channel_id)

        if not isinstance(ch, discord.TextChannel):
            return 0

        pins = await ch.pins()
        count = 0

        for msg in pins:
            content = (msg.content or "").strip()
            if not content:
                continue

            parts = content.split()
            if len(parts) < 2:
                continue

            key = parts[0].lower()

            color = None
            color_idx = None
            for i, token in enumerate(parts[1:], start=1):
                c = _parse_hex_color(token)
                if c is not None:
                    color = c
                    color_idx = i
                    break

            role_id = _extract_role_id(parts[-1])

            name_start = (color_idx + 1) if color_idx is not None else 1
            name_end = (len(parts) - 1) if role_id else len(parts)
            display_name = " ".join(parts[name_start:name_end]).strip() or key.capitalize()

            logo_url = msg.attachments[0].url if msg.attachments else ""
            if not logo_url:
                m = re.search(r"(https?://\S+)", content)
                if m:
                    logo_url = m.group(1)

            if not logo_url:
                continue

            self._stores[key] = StoreProfile(
                key=key,
                display_name=display_name,
                color=color if color is not None else 0x2F3136,
                logo_url=logo_url,
                role_id=role_id,
            )
            count += 1

        return count


# --------------------
# Apertium Manager (subprocess)
# --------------------
class ApertiumManager:
    def __init__(self) -> None:
        self.ready = False
        self.err: Optional[str] = None
        self._lock = asyncio.Lock()
        self._cache: Dict[Tuple[str, str], str] = {}  # (pair, text)->out

    def _env(self) -> dict:
        env = os.environ.copy()
        env.setdefault("LC_ALL", "C.UTF-8")
        env.setdefault("LANG", "C.UTF-8")
        return env

    async def _run(self, args: List[str], inp: Optional[str], timeout: float) -> Tuple[int, str, str]:
        proc = await asyncio.create_subprocess_exec(
            *args,
            cwd=BASE_DIR,
            env=self._env(),
            stdin=asyncio.subprocess.PIPE if inp is not None else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        data = inp.encode("utf-8") if inp is not None else None
        try:
            out_b, err_b = await asyncio.wait_for(proc.communicate(data), timeout=timeout)
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except Exception:
                pass
            return (124, "", "timeout")

        rc = proc.returncode or 0
        out = out_b.decode("utf-8", errors="ignore")
        err = err_b.decode("utf-8", errors="ignore")
        return (rc, out, err)

    async def ensure_ready(self) -> bool:
        if not USE_APERTIUM_TRANSLATE:
            self.ready = False
            self.err = "Apertium desativado no utils.py"
            return False

        pair = (APERTIUM_PAIR or "").strip()
        if not pair:
            self.ready = False
            self.err = "APERTIUM_PAIR vazio no utils.py"
            return False

        async with self._lock:
            if self.ready:
                return True

            rc, out, err = await self._run(["apertium", "-l"], inp=None, timeout=10.0)
            if rc != 0:
                self.ready = False
                self.err = (err.strip() or "apertium não executou (verifique instalação)")
                return False

            if pair not in out:
                self.ready = False
                self.err = f"Par não instalado: {pair} (veja `apertium -l`)"
                return False

            self.ready = True
            self.err = None
            return True

    async def translate_text(self, text: str) -> Optional[str]:
        t = _clean_text(text)
        if not t:
            return ""

        pair = (APERTIUM_PAIR or "").strip()
        key = (pair, t)
        if key in self._cache:
            return self._cache[key]

        ok = await self.ensure_ready()
        if not ok:
            return None

        rc, out, err = await self._run(
            ["apertium", "-f", "txt", pair],
            inp=t,
            timeout=40.0,
        )
        if rc != 0:
            self.ready = False
            self.err = (err.strip() or f"apertium rc={rc}")
            return None

        out = _clean_text(out)
        self._cache[key] = out
        return out


# --------------------
# Cog
# --------------------
class PromoEmbed(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.registry = StoreRegistry()
        self.session: Optional[aiohttp.ClientSession] = None
        self._lock = asyncio.Lock()
        self._stores_loaded_once = False
        self.translator = ApertiumManager()

    async def cog_load(self) -> None:
        timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT)
        self.session = aiohttp.ClientSession(timeout=timeout)

    async def cog_unload(self) -> None:
        if self.session and not self.session.closed:
            await self.session.close()

    async def _reload_stores(self) -> int:
        async with self._lock:
            return await self.registry.load_from_pins(self.bot, STORE_CONFIG_CHANNEL_ID)

    @commands.Cog.listener()
    async def on_ready(self):
        if self._stores_loaded_once:
            return
        try:
            await self._reload_stores()
        except Exception:
            pass
        self._stores_loaded_once = True

        if USE_APERTIUM_TRANSLATE:
            async def _warm():
                ok = await self.translator.ensure_ready()
                if not ok and self.translator.err:
                    print(f"[promo_embed] Apertium não pronto: {self.translator.err}")
            asyncio.create_task(_warm())

    # --------------------
    # Comandos (guild local)
    # --------------------
    @app_commands.guilds(TEST_GUILD)
    @app_commands.command(name="translator_test", description="Testa o tradutor offline (Apertium).")
    @app_commands.checks.has_permissions(administrator=True)
    async def translator_test(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True, thinking=True)

        ok = await self.translator.ensure_ready()
        if not ok:
            await interaction.followup.send(f"❌ Apertium não pronto: {self.translator.err}", ephemeral=True)
            return

        sample = "For over two decades, Counter-Strike has offered an elite competitive experience."
        protected, mp = _protect_phrases(sample, ["Counter-Strike"])
        tr = await self.translator.translate_text(protected)
        if tr is None:
            await interaction.followup.send(f"❌ Falha: {self.translator.err}", ephemeral=True)
            return

        tr = _restore_phrases(tr, mp)
        tr = _apertium_postprocess(tr)
        await interaction.followup.send(f"✅ Apertium OK ({APERTIUM_PAIR})\nEN: {sample}\nPT: {tr}", ephemeral=True)

    @app_commands.guilds(TEST_GUILD)
    @app_commands.command(name="logos_reload", description="Recarrega logos/cores/cargos lendo os pins do canal de config.")
    @app_commands.checks.has_permissions(administrator=True)
    async def logos_reload(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            n = await self._reload_stores()
            msg = f"✅ Recarregado: **{n}** loja(s)."
            if USE_APERTIUM_TRANSLATE:
                ok = await self.translator.ensure_ready()
                msg += " | 🌐 Apertium: OK" if ok else f" | ⚠️ Apertium: {self.translator.err}"
            await interaction.followup.send(msg, ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Falha ao recarregar pins: `{type(e).__name__}: {e}`", ephemeral=True)

    @app_commands.guilds(TEST_GUILD)
    @app_commands.command(name="promo", description="Cria uma embed de promoção a partir de um link.")
    @app_commands.checks.has_permissions(administrator=True)
    async def promo(
        self,
        interaction: discord.Interaction,
        link: str,
        preco: Optional[str] = None,
        cupom: Optional[str] = None,
    ):
        """
        Regras:
        - Metadata (título/descrição/gêneros/imagem) -> Steam (sempre que possível)
        - URL do embed -> o link passado (nuuvem/epic/gog/steam/etc)
        - Logo/role/cor -> loja do link
        - Preço -> loja do link, EXCETO:
            - se cupom foi informado => preco vira obrigatório e substitui scraping
        """
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True, thinking=True)

        cupom = (cupom or "").strip() or None
        preco = (preco or "").strip() or None

        if cupom and not preco:
            await interaction.followup.send("❌ Você informou **cupom**, então precisa informar também o **preço** (campo `preco`).", ephemeral=True)
            return

        if self.registry.is_empty():
            try:
                await self._reload_stores()
            except Exception:
                pass

        promo_channel = self.bot.get_channel(PROMO_CHANNEL_ID)
        if promo_channel is None:
            try:
                promo_channel = await self.bot.fetch_channel(PROMO_CHANNEL_ID)
            except discord.HTTPException:
                await interaction.followup.send("❌ Não achei o canal de promoções. Confere PROMO_CHANNEL_ID no utils.py.")
                return

        if not isinstance(promo_channel, discord.TextChannel):
            await interaction.followup.send("❌ PROMO_CHANNEL_ID não é um canal de texto válido.")
            return

        store_key = _domain_to_store_key(link) or "steam"
        profile = self.registry.get(store_key) or StoreProfile(
            key=store_key,
            display_name=store_key.capitalize(),
            color=0x2F3136,
            logo_url="",
            role_id=None,
        )

        info = await self._fetch_game_info(
            link,
            store_key=store_key,
            manual_price=preco,  # se houver, força preço manual
            has_coupon=bool(cupom),
        )

        embed = self._build_embed(profile, info, cupom=cupom)

        role_txt = f" <@&{profile.role_id}>" if profile.role_id else ""
        content = f"Promoção na {profile.display_name}{role_txt}".strip()

        await promo_channel.send(
            content=content,
            embed=embed,
            allowed_mentions=discord.AllowedMentions(roles=True),
        )

        await interaction.followup.send("✅ Enviado no canal de promoções.", ephemeral=True)

    # --------------------
    # Steam / Fetch
    # --------------------
    def _strip_site_suffix(self, title: str) -> str:
        t = (title or "").strip()
        if not t:
            return t

        # remove coisas comuns de título de aba
        # exemplos: "Jogo X | Nuuvem", "Jogo X - Nuuvem", "Jogo X on Steam"
        lower = t.lower()
        lower = re.sub(r"\s+on\s+steam\s*$", "", lower, flags=re.I)
        lower = re.sub(r"\s+na\s+nuuvem\s*$", "", lower, flags=re.I)

        # tenta cortes conservadores por separadores comuns
        for sep in [" | ", " — ", " – "]:
            if sep in t:
                left, right = t.split(sep, 1)
                r = right.lower()
                if any(k in r for k in ["nuuvem", "epic", "gog", "steam", "humble", "green man", "ubisoft", "xbox", "microsoft", "prime", "store"]):
                    return left.strip()

        # corte por " - " só se o sufixo parecer nome de loja/site
        if " - " in t:
            left, right = t.rsplit(" - ", 1)
            r = right.lower()
            if any(k in r for k in ["nuuvem", "epic", "gog", "steam", "humble", "greenmangaming", "ubisoft", "xbox", "microsoft", "prime", "store"]):
                return left.strip()

        return t

    def _norm(self, s: str) -> str:
        s = (s or "").lower().strip()
        s = re.sub(r"\s+", " ", s)
        s = re.sub(r"[^a-z0-9\s:!'\-]", "", s)
        return s

    def _similarity(self, a: str, b: str) -> float:
        a2 = self._norm(a)
        b2 = self._norm(b)
        if not a2 or not b2:
            return 0.0
        return SequenceMatcher(None, a2, b2).ratio()

    async def _steam_storesearch(self, term: str) -> List[dict]:
        if not self.session:
            return []
        q = (term or "").strip()
        if not q:
            return []

        # API "storesearch" costuma ser estável pra achar appid por nome
        api = "https://store.steampowered.com/api/storesearch/"
        params = {
            "term": q,
            "l": "english",
            "cc": "us",
        }
        headers = {"User-Agent": "Mozilla/5.0"}
        try:
            async with self.session.get(api, params=params, headers=headers) as r:
                if r.status != 200:
                    return []
                j = await r.json()
        except Exception:
            return []

        items = j.get("items")
        if isinstance(items, list):
            return items
        return []

    async def _steam_find_appid_by_title(self, title: str) -> Optional[int]:
        t = self._strip_site_suffix(title)
        t = re.sub(r"\s*\(.*?\)\s*$", "", t).strip()  # remove "(PC)", "(Steam)" etc do final
        if len(t) < 2:
            return None

        items = await self._steam_storesearch(t)
        if not items:
            return None

        # pega top N e escolhe por similaridade
        best_id = None
        best_score = 0.0
        for it in items[:10]:
            name = (it.get("name") or "").strip()
            appid = it.get("id")
            if not name or not isinstance(appid, int):
                continue
            score = self._similarity(t, name)
            if score > best_score:
                best_score = score
                best_id = appid

        # threshold mínimo pra evitar match lixo
        if best_id and best_score >= 0.55:
            return best_id
        return None

    async def _fetch_game_info(self, url: str, store_key: str, manual_price: Optional[str], has_coupon: bool) -> GameInfo:
        """
        - Sempre tenta Steam metadata, mesmo se o link for Nuuvem/etc.
        - Preço vem do link (store_key), exceto se manual_price foi dado (cupom).
        """
        og_title, og_desc, og_img = await self._fetch_opengraph(url)

        steam_appid = _extract_steam_appid(url)
        if not steam_appid and og_title:
            steam_appid = await self._steam_find_appid_by_title(og_title)

        steam_meta: Optional[GameInfo] = None
        if steam_appid and self.session:
            steam_meta = await self._fetch_steam_metadata(steam_appid, original_url=url, dest_store_key=store_key)

        # Metadata final (preferência Steam)
        title = (steam_meta.title if steam_meta else (og_title or "Jogo"))
        desc = (steam_meta.description if steam_meta else (og_desc or ""))
        img = (steam_meta.image_url if steam_meta else og_img)
        genres = (steam_meta.genres if steam_meta else [])

        # Preço final
        price_text: Optional[str] = None

        # se passou preço manual (principalmente quando tem cupom)
        if manual_price:
            price_text = manual_price
        else:
            # se for link steam e temos meta steam, aproveita preço da própria steam
            if store_key == "steam" and steam_appid and self.session:
                # puxa em PT primeiro (mesma lógica do meta)
                data_pt = (
                    await self._steam_appdetails(steam_appid, lang="brazilian", cc="br")
                    or await self._steam_appdetails(steam_appid, lang="portuguese", cc="br")
                )
                data_en = await self._steam_appdetails(steam_appid, lang="english", cc="us")
                data = data_pt or data_en or {}
                price_text = self._steam_price_text(data) if data else None
            else:
                price_text = await self._fetch_store_price_text(url)

        return GameInfo(
            store_key=store_key,
            url=url,
            title=title,
            description=desc,
            image_url=img,
            price_text=price_text,
            genres=genres[:MAX_GENRES],
        )

    async def _fetch_steam_metadata(self, appid: int, original_url: str, dest_store_key: str) -> Optional[GameInfo]:
        """
        Busca title/desc/genres/image na Steam.
        NÃO define preço aqui (porque o preço vem da loja do link, a não ser que o link seja Steam).
        """
        assert self.session is not None

        data_pt = (
            await self._steam_appdetails(appid, lang="brazilian", cc="br")
            or await self._steam_appdetails(appid, lang="portuguese", cc="br")
        )
        data_en = await self._steam_appdetails(appid, lang="english", cc="us")

        data = data_pt or data_en
        if not data:
            return None

        title = data.get("name") or "Jogo"

        desc_pt = _clean_text((data_pt or {}).get("short_description") or "")
        desc_en = _clean_text((data_en or {}).get("short_description") or "")
        desc = desc_pt or desc_en

        # ---- Tradução (Apertium) com proteção de nome ----
        if USE_APERTIUM_TRANSLATE and AUTO_TRANSLATE_DESC and desc and looks_english(desc):
            phrases = [title]

            # também protege o título sem número final (ex.: "Counter-Strike 2" -> "Counter-Strike")
            title_no_num = re.sub(r"\s+\d+\s*$", "", title).strip()
            if title_no_num and title_no_num != title:
                phrases.append(title_no_num)

            # protege blocos hifenizados dentro do título
            for m in re.finditer(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)+", title):
                phrases.append(m.group(0))

            protected, mp = _protect_phrases(desc, phrases)
            tr = await self.translator.translate_text(protected)
            if tr:
                tr = _restore_phrases(tr, mp)
                tr = _apertium_postprocess(tr)
                desc = tr

        header = data.get("header_image")

        # ---- GÊNEROS ----
        genres_raw: List[str] = []
        for g in (data.get("genres") or []):
            d = g.get("description")
            if d:
                genres_raw.append(_clean_text(d))

        def is_main(x: str) -> bool:
            return x.strip().lower() in MAIN_GENRES_PT

        secondary = [g for g in genres_raw if not is_main(g)]
        main = [g for g in genres_raw if is_main(g)]

        genres_final: List[str] = []
        for g in secondary + main:
            if g and g not in genres_final:
                genres_final.append(g)
            if len(genres_final) >= MAX_GENRES:
                break

        if USE_STEAMSPY_TAGS and len(genres_final) < MAX_GENRES:
            tags = await self._fetch_steamspy_tags(appid)
            tags = [t for t in tags if t not in MAIN_TAGS_EN]
            for t in tags:
                t2 = translate_genre_fast(t)
                if t2 and t2 not in genres_final:
                    genres_final.append(t2)
                if len(genres_final) >= MAX_GENRES:
                    break

        genres_final = [translate_genre_fast(x) for x in genres_final]

        if USE_APERTIUM_TRANSLATE and AUTO_TRANSLATE_GENRES:
            if any(looks_english(x) for x in genres_final):
                blob = "\n".join(genres_final[:MAX_GENRES])
                tr = await self.translator.translate_text(blob)
                if tr:
                    lines = [_apertium_postprocess(l.strip()) for l in tr.split("\n") if l.strip()]
                    if lines:
                        genres_final = lines[:MAX_GENRES]

        return GameInfo(
            store_key=dest_store_key,    # loja do link (não "steam")
            url=original_url,            # link destino (nuuvem/etc)
            title=title,
            description=desc,
            image_url=header,
            price_text=None,             # preço não aqui
            genres=genres_final[:MAX_GENRES],
        )

    async def _steam_appdetails(self, appid: int, lang: str, cc: str = "br") -> Optional[dict]:
        assert self.session is not None
        api = f"https://store.steampowered.com/api/appdetails?appids={appid}&l={lang}&cc={cc}"
        headers = {"User-Agent": "Mozilla/5.0"}
        try:
            async with self.session.get(api, headers=headers) as r:
                if r.status != 200:
                    return None
                j = await r.json()
        except Exception:
            return None

        root = j.get(str(appid), {})
        if not root.get("success"):
            return None
        return root.get("data") or {}

    def _steam_price_text(self, data: dict) -> Optional[str]:
        po = data.get("price_overview")
        if isinstance(po, dict):
            final_fmt = po.get("final_formatted")
            discount = int(po.get("discount_percent", 0) or 0)
            if final_fmt:
                if discount:
                    return f"{final_fmt} ({discount}% OFF)"
                return final_fmt
        if data.get("is_free"):
            return "Grátis"
        return None

    async def _fetch_steamspy_tags(self, appid: int) -> List[str]:
        if not self.session:
            return []
        url = f"https://steamspy.com/api.php?request=appdetails&appid={appid}"
        headers = {"User-Agent": "Mozilla/5.0"}
        try:
            async with self.session.get(url, headers=headers) as r:
                if r.status != 200:
                    return []
                j = await r.json()
        except Exception:
            return []

        tags = j.get("tags")
        if not isinstance(tags, dict):
            return []
        ordered = sorted(tags.items(), key=lambda kv: kv[1], reverse=True)
        return [k for k, _ in ordered]

    # --------------------
    # OpenGraph (fallback)
    # --------------------
    async def _fetch_opengraph(self, url: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        if not self.session:
            return None, None, None

        headers = {"User-Agent": "Mozilla/5.0"}
        try:
            async with self.session.get(url, headers=headers, allow_redirects=True) as r:
                if r.status != 200:
                    return None, None, None
                html_text = await r.text(errors="ignore")
        except Exception:
            return None, None, None

        def meta(prop: str) -> Optional[str]:
            m = re.search(
                rf'<meta[^>]+(?:property|name)=["\']{re.escape(prop)}["\'][^>]+content=["\']([^"\']+)["\']',
                html_text,
                re.I,
            )
            return _clean_text(m.group(1)) if m else None

        title = meta("og:title") or meta("twitter:title")
        desc = meta("og:description") or meta("description") or meta("twitter:description")
        img = meta("og:image") or meta("twitter:image")
        return title, desc, img

    # --------------------
    # Preço: loja do LINK
    # --------------------
    async def _fetch_store_price_text(self, url: str) -> Optional[str]:
        """
        Extrator genérico (bem mais robusto que regex puro):
        1) JSON-LD (offers->price/currency)
        2) meta product:price / og:price
        3) fallback regex de valores (R$, US$, €, £)
        """
        if not self.session:
            return None

        headers = {"User-Agent": "Mozilla/5.0"}
        try:
            async with self.session.get(url, headers=headers, allow_redirects=True) as r:
                if r.status != 200:
                    return None
                html_text = await r.text(errors="ignore")
        except Exception:
            return None

        txt = html_text

        # ---- 1) JSON-LD ----
        for m in re.finditer(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', txt, flags=re.I | re.S):
            blob = (m.group(1) or "").strip()
            if not blob:
                continue
            blob = blob.strip()
            try:
                data = json.loads(blob)
            except Exception:
                continue

            price, currency = self._jsonld_find_price(data)
            if price:
                if currency:
                    # tenta formatar "BRL 59.90" -> "R$ 59,90" quando BRL
                    return self._format_price_from_components(price, currency)
                return str(price).strip()

        # ---- 2) meta tags ----
        def meta_content(pattern: str) -> Optional[str]:
            mm = re.search(pattern, txt, flags=re.I)
            return _clean_text(mm.group(1)) if mm else None

        amount = meta_content(r'<meta[^>]+property=["\']product:price:amount["\'][^>]+content=["\']([^"\']+)["\']')
        curr = meta_content(r'<meta[^>]+property=["\']product:price:currency["\'][^>]+content=["\']([^"\']+)["\']')
        if amount:
            return self._format_price_from_components(amount, curr or "")

        amount = meta_content(r'<meta[^>]+property=["\']og:price:amount["\'][^>]+content=["\']([^"\']+)["\']')
        curr = meta_content(r'<meta[^>]+property=["\']og:price:currency["\'][^>]+content=["\']([^"\']+)["\']')
        if amount:
            return self._format_price_from_components(amount, curr or "")

        # ---- 3) fallback regex ----
        # pega vários candidatos e escolhe o "melhor" por heurística
        candidates = self._regex_price_candidates(txt)
        if candidates:
            return candidates[0]

        return None

    def _jsonld_find_price(self, data: Any) -> Tuple[Optional[str], Optional[str]]:
        """
        Procura recursivamente por offers->price/currency em JSON-LD.
        Retorna (price, currency)
        """
        def walk(node: Any) -> Tuple[Optional[str], Optional[str]]:
            if isinstance(node, dict):
                # offers pode ser dict ou list
                if "offers" in node:
                    off = node.get("offers")
                    p, c = walk(off)
                    if p:
                        return p, c

                # alguns sites usam diretamente "price" na raiz
                if "price" in node:
                    p = node.get("price")
                    c = node.get("priceCurrency") or node.get("currency")
                    if p is not None:
                        return str(p), str(c or "").strip() or None

                for v in node.values():
                    p, c = walk(v)
                    if p:
                        return p, c

            elif isinstance(node, list):
                for it in node:
                    p, c = walk(it)
                    if p:
                        return p, c

            return None, None

        return walk(data)

    def _format_price_from_components(self, price: str, currency: str) -> str:
        p = str(price).strip()
        c = (currency or "").strip().upper()

        # se já veio com símbolo, não inventa moda
        if any(sym in p for sym in ["R$", "US$", "$", "€", "£"]):
            return p

        # tenta número -> format pt-br se BRL
        if c == "BRL":
            # aceita "59.9" ou "59.90" ou "59,90"
            num = p.replace(".", "").replace(",", ".") if p.count(",") == 1 and p.count(".") > 1 else p.replace(",", ".")
            try:
                val = float(num)
                # formata 1.234,56
                s = f"{val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                return f"R$ {s}"
            except Exception:
                return f"R$ {p}"

        if c == "USD":
            return f"US$ {p}"
        if c == "EUR":
            return f"€ {p}"
        if c == "GBP":
            return f"£ {p}"

        # currency desconhecida: mostra "CUR 12.34"
        if c:
            return f"{c} {p}"
        return p

    def _regex_price_candidates(self, html_text: str) -> List[str]:
        """
        Extrai candidatos de preço e tenta escolher o mais provável (sale price).
        Heurística:
        - preferência BRL (R$) se existir
        - se houver vários, escolhe o menor valor (normalmente preço com desconto)
        """
        text = html.unescape(html_text or "")

        patterns = [
            ("BRL", re.compile(r"R\$\s*\d{1,3}(?:\.\d{3})*,\d{2}", re.I)),
            ("USD", re.compile(r"US\$\s*\d+(?:\.\d{2})?", re.I)),
            ("USD", re.compile(r"\$\s*\d+(?:\.\d{2})?", re.I)),
            ("EUR", re.compile(r"€\s*\d+(?:[.,]\d{2})?", re.I)),
            ("GBP", re.compile(r"£\s*\d+(?:[.,]\d{2})?", re.I)),
        ]

        found: List[Tuple[str, str]] = []
        for cur, pat in patterns:
            for m in pat.finditer(text):
                found.append((cur, m.group(0).strip()))

        if not found:
            return []

        # separa por moeda e escolhe
        def parse_value(cur: str, s: str) -> Optional[float]:
            x = s
            x = re.sub(r"[^0-9,.\-]", "", x)
            if cur == "BRL":
                # BR: 1.234,56
                x = x.replace(".", "").replace(",", ".")
            else:
                # US/EU: geralmente 1234.56 ou 1,234.56 (remove milhares)
                if x.count(",") > 0 and x.count(".") > 0:
                    x = x.replace(",", "")
                x = x.replace(",", ".")
            try:
                return float(x)
            except Exception:
                return None

        # preferência BRL se existir
        brl = [s for cur, s in found if cur == "BRL"]
        if brl:
            scored = []
            for s in brl:
                v = parse_value("BRL", s)
                if v is not None:
                    scored.append((v, s))
            if scored:
                scored.sort(key=lambda t: t[0])  # menor (promo) primeiro
                return [scored[0][1]]
            return [brl[0]]

        # senão, tenta menor valor da primeira moeda encontrada
        cur0 = found[0][0]
        same = [s for cur, s in found if cur == cur0]
        scored = []
        for s in same:
            v = parse_value(cur0, s)
            if v is not None:
                scored.append((v, s))
        if scored:
            scored.sort(key=lambda t: t[0])
            return [scored[0][1]]

        return [same[0]]

    # --------------------
    # Embed
    # --------------------
    def _build_embed(self, profile: StoreProfile, info: GameInfo, cupom: Optional[str]) -> discord.Embed:
        embed = discord.Embed(title=info.title, url=info.url, color=profile.color)

        embed.add_field(name="DESCRIÇÃO:", value=_format_desc_field(info.description), inline=False)
        embed.add_field(name="GÊNERO:", value=_format_genres_field(info.genres), inline=False)

        if info.price_text:
            embed.add_field(name="PREÇO:", value=_format_price_field(info.price_text), inline=False)

        if cupom and cupom.strip():
            embed.add_field(name="CUPOM:", value=_format_coupon_field(cupom.strip()), inline=False)

        if info.image_url:
            embed.set_image(url=info.image_url)

        if profile.logo_url:
            embed.set_thumbnail(url=profile.logo_url)

        return embed


async def setup(bot: commands.Bot):
    await bot.add_cog(PromoEmbed(bot))