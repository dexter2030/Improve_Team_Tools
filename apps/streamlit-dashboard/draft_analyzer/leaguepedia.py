"""
draft_analyzer/leaguepedia.py — cienki adapter nad wspólnym klientem.

Wcześniej był tu osobny klient Cargo API (requests + bot-password +
retry + paginacja). Cała ta logika została scalona ze wspólnym
`src/api/leaguepedia_client.py`, którego używają teraz wszystkie moduły
projektu (draft_analyzer, hidden_gems, Gem-finder-main, app/main.py).

Tutaj zostaje TYLKO to, co jest specyficzne dla draftów:
  * normalizacja wiersza PicksAndBansS7 na słownik gotowy do
    `db.upsert_draft()` (kolejność draftu B1/R1/R2/B2/.../R5);
  * wykluczanie bardziej szczegółowych nazw lig (LFL ≠ LFL Division 2)
    — to projektowa polityka modułu, nie warstwy API.

UWAGA: PicksAndBansS7.GameId NIE łączy się bezpośrednio ze ScoreboardGames
— złączenie idzie przez MatchScheduleGame (Help:Leaguepedia_API). Mostek
jest zaszyty w `LeaguepediaClient.iter_pick_ban_batches` / `count_drafts`.
"""

from __future__ import annotations

from collections.abc import Iterator

from shared.api.leaguepedia_client import LeaguepediaClient

from .leagues import more_specific


# Wspólna instancja klienta. mwclient.Site loguje się przy konstrukcji,
# więc trzymamy ją modułowo — tworzona leniwie przy pierwszym fetchu,
# żeby import samego draft_analyzera nie ciągnął sieci.
_client: LeaguepediaClient | None = None


def _get_client() -> LeaguepediaClient:
    global _client
    if _client is None:
        _client = LeaguepediaClient()
    return _client


def reset_client() -> None:
    """Wymusza utworzenie klienta od nowa przy następnym fetchu.

    Wołane np. po zapisie nowych credencjali w Settings — klient w
    konstruktorze loguje się bot-passwordem z env, więc bez resetu
    siedziałby na starym (lub anonimowym) trybie aż do restartu
    Streamlita.
    """
    global _client
    _client = None


def auth_status() -> tuple[str, str]:
    """Tryb dostępu do Leaguepedia jako (poziom, opis); poziom: ok/info/warn.

    Cienki proxy nad `LeaguepediaClient.auth_status()` — UI wywołuje
    tę funkcję, żeby pokazać użytkownikowi, czy login bot-passwordem
    się udał.
    """
    return _get_client().auth_status()


def iter_draft_batches(
    league: str,
    season_where: str = "",
    max_rows: int = 20000,
) -> Iterator[list[dict]]:
    """Generator porcji draftów (po <=500) — yielduje znormalizowane dicty.

    Yieldowanie pozwala stronie zapisywać dane na bieżąco. Jeśli pobieranie
    przerwie błąd (np. rate limit), porcje pobrane do tej pory są zapisane,
    a ponowne uruchomienie tylko dokłada brakujące gry (upsert idempotentny).

    `league`       — krótka nazwa ("LEC", "LCK"...). Filtr po
                     ScoreboardGames.Tournament jako podciąg, z wykluczaniem
                     bardziej szczegółowych nazw (LFL ≠ LFL Division 2).
    `season_where` — dodatkowy filtr SQL-like.
    `max_rows`     — górny limit pobranych wierszy.
    """
    client = _get_client()
    for batch in client.iter_pick_ban_batches(
        league,
        season_where=season_where,
        exclude_more_specific=more_specific(league),
        max_rows=max_rows,
    ):
        yield [_normalize(r) for r in batch]


def count_drafts(league: str, season_where: str = "") -> int:
    """Liczba draftów danej ligi dostępnych na Leaguepedia.

    Liczy tylko gry z pickami — spójnie z tym, co zapisuje sync.py
    (`_has_picks`), żeby „% kompletności" mógł sięgnąć 100%.
    """
    return _get_client().count_drafts(
        league,
        season_where=season_where,
        exclude_more_specific=more_specific(league),
    )


def fetch_all_players_global(
    *,
    country: str | None = None,
    role: str | None = None,
    only_active: bool = False,
    on_progress=None,
) -> list[dict]:
    """Wszyscy gracze z tabeli Leaguepedia `Players` (bez podziału na ligi).

    Cienki proxy nad `LeaguepediaClient.get_all_players()` — UI używa
    do zasilenia globalnej bazy w zakładce Players Data. Filtry country /
    role / only_active są przekazywane do Cargo (zmniejszają payload).
    `on_progress(total)` jest wołane co stronę.
    """
    return _get_client().get_all_players(
        country=country,
        role=role,
        only_active=only_active,
        on_batch=on_progress,
    )


def fetch_league_players(
    league: str, *, batch_pause: float = 0.5,
) -> list[dict]:
    """Lista graczy danej ligi (TournamentPlayers + metadata z Players).

    Cienki proxy nad `LeaguepediaClient.get_league_players()` —
    automatycznie dokleja wykluczenia bardziej szczegółowych nazw
    (LFL ≠ LFL Division 2). `batch_pause` to pauza między chunkami
    zapytań meta (sekundy) — chroni przed rate-limitem MediaWiki przy
    masowym pobieraniu. Zwraca dicty znormalizowane przez warstwę API;
    zapis do bazy robi `sync.fetch_players_for_league`.
    """
    return _get_client().get_league_players(
        league,
        exclude_more_specific=more_specific(league),
        batch_pause=batch_pause,
    )


def _normalize(r: dict) -> dict:
    """
    Mapuje wiersz Cargo na słownik zgodny z db.upsert_draft().

    KONWENCJA STRON: w PicksAndBansS7 Team1 = blue side, Team2 = red side.
    Kolejność draftu turniejowego:
      B1, R1, R2, B2, B3, R3, R4, B4, B5, R5
    czyli Team1Pick1=B1, Team2Pick1=R1, Team2Pick2=R2, Team1Pick2=B2, ...
    """
    def g(key):  # bezpieczny dostęp; puste -> None
        v = r.get(key)
        return v if v else None

    blue_bans = [g(f"Team1Ban{i}") for i in range(1, 6)]
    red_bans = [g(f"Team2Ban{i}") for i in range(1, 6)]

    return {
        "match_id": (r.get("GameId")
                     or f"{r.get('Tournament')}-{r.get('DateTime UTC')}"),
        "patch": g("Patch"),
        "league": g("Tournament"),
        "game_date": g("DateTime UTC") or g("DateTime_UTC"),
        "blue_team": g("Team1"),
        "red_team": g("Team2"),
        "blue_bans": [b for b in blue_bans if b],
        "red_bans": [b for b in red_bans if b],
        "b1_pick": g("Team1Pick1"),
        "r1_pick": g("Team2Pick1"),
        "r2_pick": g("Team2Pick2"),
        "b2_pick": g("Team1Pick2"),
        "b3_pick": g("Team1Pick3"),
        "r3_pick": g("Team2Pick3"),
        "b4_pick": g("Team1Pick4"),
        "b5_pick": g("Team1Pick5"),
        "r4_pick": g("Team2Pick4"),
        "r5_pick": g("Team2Pick5"),
        "winner": g("Team1") if r.get("Winner") == "1" else (
            g("Team2") if r.get("Winner") == "2" else None
        ),
    }
