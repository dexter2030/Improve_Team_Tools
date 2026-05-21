"""
sync.py — przyrostowe pobieranie lig z Leaguepedia.

Jedno miejsce, które spina warstwę API (leaguepedia.py) z bazą (db.py)
i pilnuje, by nie pobierać w kółko tego samego meczu.

Mechanizm anty-duplikacji:
  * po każdym UDANYM, pełnym wczytaniu ligi zapisujemy w tabeli
    `league_sync` datę najnowszej gry — to kursor pobierania;
  * kolejne wczytanie dokłada do filtra warunek
    `DateTime_UTC >= kursor`, więc API zwraca tylko mecze nowsze;
  * upsert i tak jest idempotentny — kursor to optymalizacja (mniej
    zapytań do limitowanego API), nie warunek poprawności danych.

Dlaczego kursor wolno przesunąć DOPIERO po pełnym przejściu ligi:
Cargo API nie zwraca gier w kolejności dat. Po przerwanym pobieraniu
nie wiadomo, czy mamy komplet meczów poniżej najnowszej zapisanej daty —
przesunięcie kursora mogłoby trwale pominąć starsze gry. Dlatego
przerwane (błąd) lub obcięte (limit wierszy) wczytanie zostawia kursor
bez zmian; już zapisane gry zostają w bazie (upsert idempotentny), a
ponowne wczytanie po prostu dokłada brakujące.

Bez zależności od Streamlita — warstwa UI woła to z własnym paskiem
postępu (draft_analyzer_page.py oraz database_page.py).
"""

from collections.abc import Callable
from dataclasses import dataclass

from .db import (
    get_league_sync,
    mark_all_players_fetched,
    mark_league_fetched,
    mark_players_fetched,
    set_remote_total,
    upsert_all_player,
    upsert_draft,
    upsert_player,
)
from .leaguepedia import (
    count_drafts,
    fetch_all_players_global,
    fetch_league_players,
    iter_draft_batches,
)

# Górny limit wierszy na jedno wczytanie ligi. Po jego osiągnięciu
# pobranie uznajemy za obcięte i NIE przesuwamy kursora (brak pewności
# kompletu). 20000 z zapasem starcza na całą historię nawet dużej ligi.
_MAX_ROWS = 20000


@dataclass
class FetchOutcome:
    """Wynik jednego wczytania ligi (jeden obiekt na ligę)."""

    league: str
    fetched: int = 0          # ile wierszy przyszło z API
    saved: int = 0            # ile zapisano (drafty z pełnym pick&ban)
    incremental: bool = False  # czy użyto kursora daty (pobranie przyrostowe)
    truncated: bool = False   # czy przerwano na limicie _MAX_ROWS
    remote_total: int | None = None  # liczba draftów ligi na Leaguepedia
    error: str | None = None  # komunikat błędu, jeśli pobieranie padło


def _date_cursor(last_game_date: str | None) -> str:
    """Warunek SQL-like zawężający pobieranie do gier od daty kursora w górę."""
    if not last_game_date:
        return ""
    return f"ScoreboardGames.DateTime_UTC >= '{last_game_date}'"


# Klucze 10 slotów pickow draftu (jak w leaguepedia._normalize i db.upsert_draft).
_PICK_KEYS = ("b1_pick", "r1_pick", "r2_pick", "b2_pick", "b3_pick",
              "r3_pick", "b4_pick", "b5_pick", "r4_pick", "r5_pick")


def _has_picks(draft: dict) -> bool:
    """Czy draft ma choć jednego picka.

    Odsiewa puste wiersze, ale NIE wymaga banów — na Leaguepedii bany
    bywają niezapisane, a draft z samymi pickami też jest użyteczny dla
    wyszukiwarki pick&ban, więc takie drafty również zapisujemy.
    """
    return any(draft.get(k) for k in _PICK_KEYS)


def fetch_league(
    league: str,
    *,
    season_where: str = "",
    full_refresh: bool = False,
    on_batch: Callable[[int, int], None] | None = None,
) -> FetchOutcome:
    """Pobiera (przyrostowo) drafty jednej ligi i aktualizuje `league_sync`.

    `season_where`  — opcjonalny dodatkowy filtr SQL-like (jak w UI).
    `full_refresh`  — True ignoruje kursor i pobiera ligę od zera.
    `on_batch`      — callback(fetched, saved) po każdej porcji (pasek postępu).

    Zwraca FetchOutcome. Wyjątki z API są łapane i zwracane w polu
    `error` — już zapisane porcje zostają w bazie (upsert idempotentny).
    """
    sync = get_league_sync(league)
    prior_cursor = sync.get("last_game_date") if sync else None

    cursor_where = "" if full_refresh else _date_cursor(prior_cursor)
    where = " AND ".join(w for w in (season_where, cursor_where) if w)

    outcome = FetchOutcome(league=league, incremental=bool(cursor_where))
    max_game_date = prior_cursor  # kursor nigdy się nie cofa

    try:
        for batch in iter_draft_batches(league, where, max_rows=_MAX_ROWS):
            for d in batch:
                if _has_picks(d):
                    upsert_draft(d)
                    outcome.saved += 1
                    gd = d.get("game_date")
                    if gd and (max_game_date is None or gd > max_game_date):
                        max_game_date = gd
            outcome.fetched += len(batch)
            if on_batch is not None:
                on_batch(outcome.fetched, outcome.saved)
    except Exception as e:  # rate limit itp. — zapisane porcje zostają
        outcome.error = str(e)
        return outcome

    outcome.truncated = outcome.fetched >= _MAX_ROWS
    # Kursor przesuwamy tylko po pełnym przejściu ligi; przy obcięciu
    # przekazujemy None — db.mark_league_fetched zachowa stary kursor.
    mark_league_fetched(
        league, None if outcome.truncated else max_game_date
    )

    # Odśwież mianownik „% kompletności". Błąd licznika nie psuje
    # wczytania — % to tylko wskaźnik pomocniczy.
    try:
        outcome.remote_total = count_drafts(league, season_where)
        set_remote_total(league, outcome.remote_total)
    except Exception:
        pass

    return outcome


# --- pobieranie graczy ligi --------------------------------------------------

@dataclass
class PlayersFetchOutcome:
    """Wynik pobrania graczy jednej ligi (jeden obiekt na ligę)."""

    league: str
    fetched: int = 0          # ile graczy zwróciło API
    saved: int = 0            # ile zapisano do bazy
    error: str | None = None  # komunikat błędu, jeśli pobieranie padło


def fetch_players_for_league(
    league: str, *, batch_pause: float = 0.5,
) -> PlayersFetchOutcome:
    """Pobiera wszystkich graczy danej ligi i upsertuje do tabeli players.

    Pobieranie jest pełne (nie przyrostowe) — rostery zmieniają się przy
    transferach, więc każde uruchomienie pobiera świeży snapshot z
    Leaguepedia. Upsert jest idempotentny po (overview_page, league),
    więc kolejne pobranie po prostu aktualizuje zespół / rolę / kraj.

    `batch_pause` — pauza między chunkami w get_players_meta (chroni
    przed rate-limitem MediaWiki). Sumarycznie odpowiednik `batch_pause`
    z `iter_pick_ban_batches` (drafty), tylko że tu chunki są małe (30
    linków), więc i pauza może być krótsza.

    Wyjątki łapane i zwracane w polu `error` — już zapisane wiersze
    zostają w bazie.
    """
    outcome = PlayersFetchOutcome(league=league)
    try:
        players = fetch_league_players(league, batch_pause=batch_pause)
    except Exception as e:
        outcome.error = str(e)
        return outcome

    outcome.fetched = len(players)
    for p in players:
        try:
            upsert_player(p, league)
            outcome.saved += 1
        except Exception:
            # Pojedynczy zły wiersz nie zatrzymuje pobierania;
            # licznik `saved` pokaże ile faktycznie weszło do bazy.
            continue

    mark_players_fetched(league, outcome.saved)
    return outcome


# --- pobieranie globalnej bazy graczy (bez podziału na ligi) -----------------

@dataclass
class AllPlayersFetchOutcome:
    """Wynik pełnego pobrania globalnej bazy graczy z Leaguepedia."""

    fetched: int = 0          # ile wierszy zwróciło API
    saved: int = 0            # ile zapisano do tabeli players_all
    error: str | None = None  # komunikat błędu, jeśli pobieranie padło


def fetch_all_players(
    *,
    country: str | None = None,
    role: str | None = None,
    only_active: bool = False,
    on_progress: Callable[[int], None] | None = None,
) -> AllPlayersFetchOutcome:
    """Pobiera całą tabelę `Players` z Leaguepedia do `players_all`.

    Bez podziału na ligi — jeden wiersz na gracza. Filtry country / role /
    only_active są przekazywane do Cargo i ograniczają payload (najlepiej
    używać, gdy chcemy zacieśnić do konkretnego kraju lub roli).

    Bez kursora przyrostowego — `Players` jest mały (~30k wierszy), więc
    przy każdym wczytaniu robimy świeży snapshot. Upsert idempotentny po
    `overview_page` — kolejne pobranie tylko aktualizuje metadane.

    `on_progress(total_so_far)` jest wywoływane co stronę (500 wierszy)
    — feeduje pasek postępu w UI.
    """
    outcome = AllPlayersFetchOutcome()
    try:
        players = fetch_all_players_global(
            country=country,
            role=role,
            only_active=only_active,
            on_progress=on_progress,
        )
    except Exception as e:
        outcome.error = str(e)
        return outcome

    outcome.fetched = len(players)
    for p in players:
        try:
            upsert_all_player(p)
            outcome.saved += 1
        except Exception:
            # Pojedynczy zły wiersz nie zatrzymuje pobierania.
            continue

    mark_all_players_fetched(outcome.saved)
    return outcome
