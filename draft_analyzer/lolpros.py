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

import re
import time
from collections.abc import Callable

import requests

LOLPROS_BASE = "https://lolpros.gg/player"
_USER_AGENT = (
    "lol-scouting-dashboard/0.1 "
    "(checking public lolpros.gg profile pages)"
)


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
