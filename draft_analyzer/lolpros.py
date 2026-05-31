"""
lolpros.py — sprawdza, czy gracz ma profil na lolpros.gg.

Lolpros.gg używa URL-i typu https://lolpros.gg/player/<slug>, gdzie slug
to nick gracza w lowercase z myślnikami zamiast spacji (np. „Hans Sama"
→ „hans-sama", „Faker" → „faker"). To nie jest API — to po prostu
strona — ale sprawdzanie HEAD-em jest tanie i wystarczająco
wiarygodne dla naszego case'u (chcemy wiedzieć: jest taka strona czy
nie).

Funkcja `probe_lolpros` zwraca pełny URL gdy strona istnieje, pusty
string gdy nie. Pusty string (a nie None) odróżnia „sprawdzone, brak"
od „nigdy nie sprawdzano" — UI używa tej różnicy do trzech stanów
ikony (—, ❌, link).

Wynik zapisuje się do bazy (`db.update_lolpros`) — nie ma sensu pukać
do lolpros dwa razy o tego samego gracza. Batch-checker poniżej pauzuje
między żądaniami, żeby nie obciążać serwera.
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)

LOLPROS_BASE = "https://lolpros.gg/player"
_USER_AGENT = (
    "lol-scouting-dashboard/0.1 "
    "(checking public lolpros.gg profile pages)"
)


# --- Region mapping ---------------------------------------------------------
# Lolpros stores accounts with short region codes (EUW, KR, NA, ...); the
# Riot API uses platform routing values (euw1, kr, na1, ...). Same mapping
# the resolver / op.gg URL parser uses — kept here so this module stays
# self-contained.

_LOLPROS_REGION_TO_PLATFORM: dict[str, str] = {
    "EUW": "euw1", "EUNE": "eun1", "KR": "kr",
    "NA": "na1",   "BR": "br1",   "TR": "tr1",
    "JP": "jp1",   "LAN": "la1",  "LAS": "la2",
    "OCE": "oc1",  "RU": "ru",
}


@dataclass(frozen=True, slots=True)
class LolprosAccount:
    """One SoloQ account listed on a player's lolpros.gg page.

    `region` is the Lolpros short code (e.g. 'EUW'); `platform` is its
    Riot-API equivalent (e.g. 'euw1'). Both are kept so callers can
    display the source string and still feed RiotClient.
    """
    game_name: str
    tag_line: str
    region: str
    platform: str

    @property
    def riot_id(self) -> str:
        return f"{self.game_name}#{self.tag_line}"


def slugify(player_id: str) -> str:
    """Konwertuje nick gracza na slug lolpros.

    Reguły:
      * lowercase
      * spacje, podkreślniki → myślnik
      * wszystko poza [a-z0-9-] usuń
      * zwiń podwójne myślniki, obetnij myślniki z brzegów

    Nie próbujemy odgadnąć egzotycznych przypadków (np. polskie znaki).
    Lolpros zwykle używa formy ASCII — jeśli się nie zgadza, probe
    zwróci pusty wynik, co jest poprawnym sygnałem „nie ma profilu".
    """
    s = (player_id or "").strip().lower()
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"[^a-z0-9-]", "", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s


def probe_lolpros(
    player_id: str,
    *,
    timeout: float = 5.0,
    session: requests.Session | None = None,
) -> str:
    """Zwraca URL lolpros gdy istnieje, pusty string gdy nie.

    Używamy GET (nie HEAD) bo nie każdy CDN obsługuje HEAD poprawnie —
    GET z `stream=True` + zamknięcie połączenia jest tylko nieznacznie
    droższe (Lolpros zwraca SSR HTML, ale `stream=True` oddaje nam
    odpowiedź od razu po nagłówkach, więc nie ciągniemy ciała).

    Pusty player_id → pusty wynik (nic do sprawdzenia).
    Błąd sieci → pusty wynik (traktujemy jak „nie ma" — i tak będzie
    można powtórzyć później; nie ma sensu różnicować od „404" w UI).
    """
    slug = slugify(player_id)
    if not slug:
        return ""

    url = f"{LOLPROS_BASE}/{slug}"
    sess = session or requests
    try:
        r = sess.get(
            url,
            allow_redirects=True,
            timeout=timeout,
            headers={"User-Agent": _USER_AGENT},
            stream=True,
        )
        r.close()
    except requests.RequestException:
        return ""

    return url if r.status_code == 200 else ""


def scrape_lolpros_accounts(
    lolpros_url: str,
    *,
    timeout: float = 10.0,
    session: requests.Session | None = None,
) -> list[LolprosAccount]:
    """Scrape the SoloQ account list from a player's lolpros.gg page.

    Lolpros.gg is a Next.js SSR site — every page embeds its full state
    as JSON in `<script id="__NEXT_DATA__">`. We parse that (stable across
    DOM tweaks) and walk it for the accounts list. Returns [] on any
    failure (network, parse, missing data) — caller can retry later.

    Empty lolpros_url → [] (nothing to scrape).
    Unknown region code → account skipped (we can't route Riot API for it).
    """
    if not lolpros_url:
        return []

    sess = session or requests
    try:
        r = sess.get(
            lolpros_url,
            allow_redirects=True,
            timeout=timeout,
            headers={"User-Agent": _USER_AGENT},
        )
    except requests.RequestException as exc:
        logger.warning("lolpros GET fail %s: %s", lolpros_url, exc)
        return []
    if r.status_code != 200:
        logger.warning("lolpros %d %s", r.status_code, lolpros_url)
        return []

    try:
        data = _extract_next_data(r.text)
    except ValueError as exc:
        logger.warning("lolpros NEXT_DATA parse fail %s: %s", lolpros_url, exc)
        return []

    raw_accounts = _deep_first(data, "accounts") or []
    if not isinstance(raw_accounts, list):
        return []

    out: list[LolprosAccount] = []
    seen: set[tuple[str, str, str]] = set()
    for entry in raw_accounts:
        if not isinstance(entry, dict):
            continue
        # Lolpros has shuffled the schema a few times; tolerate the
        # common shapes by checking each possible field name.
        game_name = (
            entry.get("game_name")
            or entry.get("name")
            or entry.get("summoner_name")
            or ""
        ).strip()
        tag_line = (
            entry.get("tag_line")
            or entry.get("tag")
            or entry.get("riot_tag")
            or ""
        ).strip().lstrip("#")
        region_raw = (
            entry.get("server")
            or entry.get("region")
            or entry.get("rgn")
            or ""
        ).strip().upper()
        if not game_name or not region_raw:
            continue
        platform = _LOLPROS_REGION_TO_PLATFORM.get(region_raw)
        if not platform:
            continue
        key = (game_name.lower(), tag_line.lower(), region_raw)
        if key in seen:
            continue
        seen.add(key)
        out.append(LolprosAccount(
            game_name=game_name,
            tag_line=tag_line,
            region=region_raw,
            platform=platform,
        ))

    if not out:
        # Plan B z TODO: 0 kont to najczęściej dryf schematu lolpros.
        # Logujemy strukturalną podpowiedź (klucze pageProps), żeby dało się
        # dopasować parser bez zgadywania — bez zrzucania całego NEXT_DATA.
        logger.warning(
            "lolpros: 0 użytecznych kont z %s (raw_accounts=%d). "
            "Schemat mógł się zmienić; klucze pageProps=[%s]",
            lolpros_url,
            len(raw_accounts) if isinstance(raw_accounts, list) else -1,
            _debug_keys(_deep_first(data, "pageProps")),
        )
    return out


def _extract_next_data(html: str) -> dict:
    """Wyciąga osadzony JSON z <script id="__NEXT_DATA__">.

    Next.js'owy state strony — stabilniejszy niż HTML, ale nie API.
    """
    m = re.search(
        r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
        html, re.DOTALL,
    )
    if not m:
        raise ValueError("Brak __NEXT_DATA__ w HTML")
    return json.loads(m.group(1))


def _debug_keys(obj) -> str:
    """Ograniczona podpowiedź strukturalna do logów: klucze dicta albo typ.

    Używane gdy parser nie znalazł kont — pokazuje, gdzie lolpros przeniósł
    dane, bez logowania całego (dużego) NEXT_DATA.
    """
    if isinstance(obj, dict):
        return ", ".join(sorted(obj.keys())[:25])
    return type(obj).__name__


def _deep_first(obj, key: str):
    """BFS przez dict/listy — pierwsza wartość pod kluczem `key`."""
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            r = _deep_first(v, key)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _deep_first(v, key)
            if r is not None:
                return r
    return None


def batch_check_lolpros(
    players: list[dict],
    *,
    on_progress: Callable[[int, int, str], None] | None = None,
    pause_seconds: float = 0.35,
    save: Callable[[str, str], None] | None = None,
) -> dict[str, str]:
    """Sprawdza lolpros dla listy graczy, zapisując wynik per gracz.

    `players` to dicty z conajmniej `overview_page` i `player_id`
    (kształt z `db.fetch_all_players_global`).
    `on_progress(done, total, player_id)` wywoływane po każdym graczu —
    feeduje pasek postępu w UI.
    `save(overview_page, url)` zapisuje wynik (zwykle `db.update_lolpros`).
    `pause_seconds` to pauza między requestami — bądź miły dla lolpros.

    Zwraca mapę `overview_page -> url` (wyłącznie udane trafienia, nie
    dla pustych wyników — wtedy w bazie zostaje pusty string).
    """
    found: dict[str, str] = {}
    total = len(players)
    sess = requests.Session()
    try:
        for i, p in enumerate(players, start=1):
            pid = p.get("player_id") or ""
            page = p.get("overview_page") or ""
            url = probe_lolpros(pid, session=sess) if (page and pid) else ""
            if save is not None and page:
                save(page, url)
            if url:
                found[page] = url
            if on_progress is not None:
                on_progress(i, total, pid)
            if i < total and pause_seconds > 0:
                time.sleep(pause_seconds)
    finally:
        sess.close()
    return found
