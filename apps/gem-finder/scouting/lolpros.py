"""lolpros.gg — best-effort match graczy do ich kont soloQ (wariant Gem-finder).

Strategia:
1) GET https://lolpros.gg/player/<slug>
2) Jeśli 404 — fallback do /api/players?query=...
3) Parsujemy __NEXT_DATA__ i wyciągamy wszystkie {riot_id, tag, region}
   znalezione w drzewie. Struktura HTML potrafi się zmienić — logujemy
   miss/fail.

Sekwencyjnie, throttle min 1.5s między requestami (konfig).

UWAGA — to NIE jest przypadkowy duplikat ``packages/shared/shared/lolpros.py``;
oba parsują __NEXT_DATA__, ale różnice są CELOWE i ten moduł zostaje osobno:
  * pokrycie regionów — pipeline Gem-findera (``soloq.REGION_ALIASES``) obsługuje
    14 regionów (m.in. JP/PH/SG/TH/TW/VN); ``shared`` mapuje tylko 11 i ODRZUCA
    pozostałe, więc delegacja zgubiłaby konta z tych regionów;
  * ekstrakcja — tu przechodzimy CAŁE drzewo (``_walk_for_accounts``, odporne na
    dryf schematu); ``shared`` bierze tylko klucz „accounts";
  * kształt wyniku — zwracamy ``{riot_id, tag, region}`` (region = krótki kod,
    mapowany dalej w ``soloq.py``), a ``shared`` zwraca ``LolprosAccount`` z
    gotowym ``platform``.
Naprawdę współdzielony kod (klienci Riot/Leaguepedia, ``match_stats``) mieszka w
``packages/shared``; tutaj zostaje wyłącznie warstwa specyficzna dla pipeline'u.
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

LOG = logging.getLogger(__name__)

BASE = "https://lolpros.gg"
SLUG_RE = re.compile(r"[^a-z0-9]+")

# Region codes używane przez lolpros — mapowanie na Riot platform IDs robi soloq.py.
KNOWN_REGION_TOKENS = {
    "EUW", "EUW1", "EUNE", "EUN1", "NA", "NA1", "BR", "BR1",
    "KR", "JP", "JP1", "LAN", "LA1", "LAS", "LA2", "OCE", "OC1",
    "TR", "TR1", "RU", "PH", "PH2", "SG", "SG2", "TH", "TH2",
    "TW", "TW2", "VN", "VN2",
}


def normalize_slug(nick: str) -> str:
    s = nick.lower().strip()
    s = SLUG_RE.sub("-", s)
    return s.strip("-")


class LolprosClient:
    def __init__(
        self,
        user_agent: str,
        delay_seconds: float = 1.5,
        session: requests.Session | None = None,
    ):
        self.session = session or requests.Session()
        self.session.headers["User-Agent"] = user_agent
        self.delay = delay_seconds
        self._last_request = 0.0

    def _throttle(self) -> None:
        dt = time.monotonic() - self._last_request
        if dt < self.delay:
            time.sleep(self.delay - dt)
        self._last_request = time.monotonic()

    def _get(self, url: str) -> requests.Response | None:
        self._throttle()
        try:
            return self.session.get(url, timeout=20)
        except requests.RequestException as e:
            LOG.warning("lolpros GET failed: %s (%s)", url, e)
            return None

    def fetch_profile_html(self, slug: str) -> str | None:
        url = f"{BASE}/player/{quote(slug)}"
        r = self._get(url)
        if r is None or r.status_code == 404:
            return None
        if r.status_code != 200:
            LOG.warning("lolpros %s -> HTTP %s", url, r.status_code)
            return None
        return r.text

    def search_api(self, nick: str) -> list[dict]:
        """Lolpros ma niepublicznie udokumentowane API — best effort."""
        url = f"{BASE}/api/players?query={quote(nick)}"
        r = self._get(url)
        if r is None or r.status_code != 200:
            return []
        try:
            payload = r.json()
        except ValueError:
            return []
        if isinstance(payload, dict):
            return payload.get("results") or payload.get("players") or []
        if isinstance(payload, list):
            return payload
        return []


def _extract_next_data(html: str) -> dict | None:
    soup = BeautifulSoup(html, "lxml")
    tag = soup.find("script", id="__NEXT_DATA__")
    if not tag or not tag.string:
        return None
    try:
        return json.loads(tag.string)
    except json.JSONDecodeError:
        return None


def _normalize_region(token: str) -> str | None:
    t = token.strip().upper()
    if t in KNOWN_REGION_TOKENS:
        return t
    return None


def _walk_for_accounts(node: Any) -> list[dict]:
    """Walk dowolnego JSON-a — zbiera dict-y wyglądające jak konto Riot.

    Lolpros kilka razy zmieniał shape; szukamy par {game_name/tagline/region}
    pod różnymi kluczami.
    """
    found: list[dict] = []

    def riot_account_like(d: dict) -> dict | None:
        game = (
            d.get("game_name")
            or d.get("gameName")
            or d.get("riot_id")
            or d.get("riotId")
            or d.get("summoner_name")
            or d.get("summonerName")
        )
        tag = (
            d.get("tag_line")
            or d.get("tagLine")
            or d.get("tag")
            or d.get("riot_id_tag")
        )
        region = (
            d.get("region")
            or d.get("server")
            or d.get("platform")
            or d.get("platform_id")
        )
        if not game or not region:
            return None
        normalized = _normalize_region(str(region))
        if not normalized:
            return None
        return {
            "riot_id": str(game).strip(),
            "tag": (str(tag).strip().lstrip("#") if tag else None),
            "region": normalized,
        }

    def visit(x: Any) -> None:
        if isinstance(x, dict):
            acc = riot_account_like(x)
            if acc:
                found.append(acc)
            for v in x.values():
                visit(v)
        elif isinstance(x, list):
            for v in x:
                visit(v)

    visit(node)

    seen: set[tuple] = set()
    unique: list[dict] = []
    for a in found:
        key = (a["riot_id"].lower(), (a.get("tag") or "").lower(), a["region"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(a)
    return unique


def find_lolpros_profile(player: dict, client: LolprosClient) -> list[dict]:
    """Krok 2 pipeline'u: dla danego gracza zwraca listę kont {riot_id, tag, region}.

    Zwraca [] jeśli profil nie istnieje lub nie udało się sparsować kont.
    """
    nick = (player.get("nick") or player.get("page_name") or "").strip()
    if not nick:
        return []

    candidates: list[str] = []
    slug = normalize_slug(nick)
    if slug:
        candidates.append(slug)
    alt = nick.lower().replace(" ", "")
    if alt and alt != slug:
        candidates.append(alt)

    html: str | None = None
    used_slug: str | None = None
    for c in candidates:
        html = client.fetch_profile_html(c)
        if html:
            used_slug = c
            break

    if not html:
        results = client.search_api(nick)
        for r in results:
            slug_found = r.get("slug") or r.get("normalized_name") or r.get("id")
            if slug_found:
                html = client.fetch_profile_html(str(slug_found))
                if html:
                    used_slug = str(slug_found)
                    break

    if not html:
        LOG.info("lolpros miss: %s", nick)
        return []

    data = _extract_next_data(html)
    if not data:
        LOG.warning("lolpros: __NEXT_DATA__ parse failed for %s (slug=%s)", nick, used_slug)
        return []

    accounts = _walk_for_accounts(data)
    if not accounts:
        LOG.warning("lolpros: no accounts extracted for %s (slug=%s)", nick, used_slug)
    else:
        LOG.info("lolpros hit: %s -> %d account(s)", nick, len(accounts))
    return accounts
