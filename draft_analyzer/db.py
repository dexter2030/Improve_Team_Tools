"""
db.py — warstwa danych dla modułu Draft Analyzer.

Jedna tabela `drafts` trzyma kompletną sekwencję pick&ban jednej gry.
Bany zapisujemy jako JSON-owe listy (kolejność zachowana, ale przy
dopasowaniu traktujemy je jako zbiór). SQLite -> łatwo podmienić na
Postgres: wystarczy zmienić connection string i sterownik.
"""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from .leagues import more_specific

DB_PATH = Path(__file__).parent / "drafts.db"


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    """Tworzy tabele, jeśli nie istnieją."""
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS drafts (
                match_id    TEXT PRIMARY KEY,
                patch       TEXT,
                league      TEXT,
                game_date   TEXT,
                blue_team   TEXT,
                red_team    TEXT,
                -- bany jako JSON: ["Champ1", "Champ2", "Champ3"]
                blue_bans   TEXT NOT NULL,
                red_bans    TEXT NOT NULL,
                -- pełna sekwencja pickow w kolejności draftu
                b1_pick     TEXT,
                r1_pick     TEXT,
                r2_pick     TEXT,
                b2_pick     TEXT,
                b3_pick     TEXT,
                r3_pick     TEXT,
                b4_pick     TEXT,
                b5_pick     TEXT,
                r4_pick     TEXT,
                r5_pick     TEXT,
                winner      TEXT
            )
            """
        )
        # indeks po pierwszym picku blue przyspiesza warstwę 3 analizy
        conn.execute("CREATE INDEX IF NOT EXISTS idx_b1 ON drafts(b1_pick)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_patch ON drafts(patch)")

        # Metadane synchronizacji lig — jeden wiersz na ligę (krótka nazwa
        # z leagues.py). Zasila zakładkę Database i pobieranie przyrostowe:
        #   last_game_date — data najnowszej pobranej gry (kursor),
        #   remote_total   — liczba draftów ligi na Leaguepedia (mianownik %).
        # Szczegóły mechanizmu kursora: sync.py.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS league_sync (
                league          TEXT PRIMARY KEY,
                last_fetched    TEXT,
                last_game_date  TEXT,
                remote_total    INTEGER,
                remote_checked  TEXT
            )
            """
        )

        # Baza graczy z lig (z TournamentPlayers + Players na Leaguepedia).
        # Klucz złożony (overview_page, league) — ten sam gracz może
        # pojawić się w wielu ligach (np. transfer z LEC do LCS),
        # zachowujemy oba wpisy, żeby filtr per liga był jednoznaczny.
        # `overview_page` to stabilny klucz pro-play (nazwa strony wiki);
        # `player_id` to bieżący nick i bywa zmieniany — nie łączyć po nim.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS players (
                overview_page        TEXT NOT NULL,
                league               TEXT NOT NULL,
                player_id            TEXT,
                team                 TEXT,
                role                 TEXT,
                country              TEXT,
                residency            TEXT,
                nationality_primary  TEXT,
                is_retired           TEXT,
                tournament           TEXT,
                date_start           TEXT,
                last_fetched         TEXT,
                PRIMARY KEY (overview_page, league)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_players_league ON players(league)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_players_role ON players(role)"
        )

        # Metadane synchronizacji graczy per liga — jeden wiersz na ligę.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS players_sync (
                league        TEXT PRIMARY KEY,
                last_fetched  TEXT,
                player_count  INTEGER
            )
            """
        )

        # Globalna baza graczy (cała tabela `Players` z Leaguepedia, bez
        # podziału na ligi). Oddzielna tabela, bo `players` jest kluczowana
        # po (overview_page, league) — chcielibyśmy tu jeden wiersz na
        # gracza, a kolumna ligi nie ma sensu (jeden gracz grał w wielu).
        # `lolpros_url` jest NULL gdy nie sprawdzano, "" gdy brak profilu,
        # albo pełnym URL-em gdy znaleziono — trzy stany pozwalają odróżnić
        # „nie sprawdziłem" od „sprawdzone, nie ma".
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS players_all (
                overview_page        TEXT PRIMARY KEY,
                player_id            TEXT,
                team                 TEXT,
                role                 TEXT,
                country              TEXT,
                residency            TEXT,
                nationality_primary  TEXT,
                is_retired           TEXT,
                lolpros_url          TEXT,
                lolpros_checked_at   TEXT,
                last_fetched         TEXT
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_players_all_role "
            "ON players_all(role)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_players_all_country "
            "ON players_all(country)"
        )

        # Metadane synchronizacji globalnej bazy graczy (jeden wiersz —
        # singleton, dlatego id=1 wymuszone CHECK-iem).
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS players_all_sync (
                id            INTEGER PRIMARY KEY CHECK (id = 1),
                last_fetched  TEXT,
                player_count  INTEGER
            )
            """
        )

        # Migracja na istniejących bazach: tabela players_all mogła być
        # stworzona starszą wersją bez kolumn lolpros — dołóż je, jeśli
        # brakuje. ALTER TABLE ADD COLUMN nie ma IF NOT EXISTS, więc
        # sprawdzamy schemat ręcznie.
        cols = {r["name"] for r in conn.execute(
            "PRAGMA table_info(players_all)"
        ).fetchall()}
        if "lolpros_url" not in cols:
            conn.execute("ALTER TABLE players_all ADD COLUMN lolpros_url TEXT")
        if "lolpros_checked_at" not in cols:
            conn.execute(
                "ALTER TABLE players_all ADD COLUMN lolpros_checked_at TEXT"
            )


def upsert_draft(d: dict):
    """Wstawia lub aktualizuje jeden draft. `d` to słownik z polami tabeli."""
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO drafts (
                match_id, patch, league, game_date, blue_team, red_team,
                blue_bans, red_bans,
                b1_pick, r1_pick, r2_pick, b2_pick, b3_pick, r3_pick,
                b4_pick, b5_pick, r4_pick, r5_pick, winner
            ) VALUES (
                :match_id, :patch, :league, :game_date, :blue_team, :red_team,
                :blue_bans, :red_bans,
                :b1_pick, :r1_pick, :r2_pick, :b2_pick, :b3_pick, :r3_pick,
                :b4_pick, :b5_pick, :r4_pick, :r5_pick, :winner
            )
            ON CONFLICT(match_id) DO UPDATE SET
                patch=excluded.patch, league=excluded.league,
                game_date=excluded.game_date,
                blue_team=excluded.blue_team, red_team=excluded.red_team,
                blue_bans=excluded.blue_bans, red_bans=excluded.red_bans,
                b1_pick=excluded.b1_pick, r1_pick=excluded.r1_pick,
                r2_pick=excluded.r2_pick, b2_pick=excluded.b2_pick,
                b3_pick=excluded.b3_pick, r3_pick=excluded.r3_pick,
                b4_pick=excluded.b4_pick, b5_pick=excluded.b5_pick,
                r4_pick=excluded.r4_pick, r5_pick=excluded.r5_pick,
                winner=excluded.winner
            """,
            {
                **d,
                "blue_bans": json.dumps(d["blue_bans"]),
                "red_bans": json.dumps(d["red_bans"]),
            },
        )


def fetch_all_drafts(patches: list[str] | None = None) -> list[dict]:
    """
    Zwraca wszystkie drafty (opcjonalnie zawężone do listy patchy).
    Bany deserializowane z JSON do list pythonowych.
    """
    query = "SELECT * FROM drafts"
    params: list = []
    if patches:
        placeholders = ",".join("?" * len(patches))
        query += f" WHERE patch IN ({placeholders})"
        params = patches

    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()

    out = []
    for r in rows:
        d = dict(r)
        d["blue_bans"] = json.loads(d["blue_bans"])
        d["red_bans"] = json.loads(d["red_bans"])
        out.append(d)
    return out


def list_patches() -> list[str]:
    """Lista dostępnych patchy, od najnowszego."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT patch FROM drafts WHERE patch IS NOT NULL "
            "ORDER BY patch DESC"
        ).fetchall()
    return [r["patch"] for r in rows]


def list_teams() -> list[str]:
    """Lista drużyn występujących po stronie blue, alfabetycznie."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT blue_team FROM drafts "
            "WHERE blue_team IS NOT NULL AND blue_team != '' "
            "ORDER BY blue_team"
        ).fetchall()
    return [r["blue_team"] for r in rows]


def count_all_drafts() -> int:
    """Łączna liczba draftów w bazie."""
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) AS n FROM drafts").fetchone()["n"]


def count_drafts_for_league(league: str) -> int:
    """Liczba draftów w lokalnej bazie pasujących do nazwy ligi.

    Pole `drafts.league` to pełna nazwa turnieju ("LEC 2024 Summer"), więc
    krótką nazwę ("LEC") dopasowujemy jako podciąg. Bardziej szczegółowe
    nazwy lig wykluczamy (leagues.more_specific) — spójnie z
    analyzer.filter_by_leagues() i leaguepedia.iter_draft_batches() —
    żeby np. „LFL" nie liczyło meczów „LFL Division 2".
    """
    clauses = ["LOWER(league) LIKE '%' || LOWER(?) || '%'"]
    params: list = [league]
    for excl in more_specific(league):
        clauses.append("LOWER(league) NOT LIKE '%' || LOWER(?) || '%'")
        params.append(excl)
    sql = "SELECT COUNT(*) AS n FROM drafts WHERE " + " AND ".join(clauses)
    with get_conn() as conn:
        row = conn.execute(sql, params).fetchone()
    return row["n"]


# --- metadane synchronizacji lig (tabela league_sync) -----------------------

def get_league_sync(league: str) -> dict | None:
    """Wiersz league_sync danej ligi (krótka nazwa) albo None, gdy brak."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM league_sync WHERE league = ?", (league,)
        ).fetchone()
    return dict(row) if row else None


def all_league_sync() -> dict[str, dict]:
    """Cała tabela league_sync jako mapa: krótka nazwa ligi -> wiersz."""
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM league_sync").fetchall()
    return {r["league"]: dict(r) for r in rows}


def mark_league_fetched(league: str, last_game_date: str | None) -> None:
    """Odnotowuje udane wczytanie ligi — ustawia `last_fetched` na teraz.

    `last_game_date` to data najnowszej gry w bazie dla tej ligi; służy
    jako kursor pobierania przyrostowego. None NIE nadpisuje zapisanego
    kursora (COALESCE) — dzięki temu obcięte/puste wczytanie go nie cofa.

    Wołać dopiero po pełnym przejściu ligi — uzasadnienie w sync.py.
    """
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO league_sync (league, last_fetched, last_game_date)
            VALUES (:league, :now, :lgd)
            ON CONFLICT(league) DO UPDATE SET
                last_fetched   = excluded.last_fetched,
                last_game_date = COALESCE(excluded.last_game_date,
                                          league_sync.last_game_date)
            """,
            {"league": league, "now": now, "lgd": last_game_date},
        )


def set_remote_total(league: str, total: int) -> None:
    """Zapisuje liczbę draftów ligi dostępnych na Leaguepedia.

    To mianownik „% kompletności" w zakładce Database. Cache'owany, bo
    wymaga zapytania do API — odświeżany przy każdym wczytaniu ligi.
    """
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO league_sync (league, remote_total, remote_checked)
            VALUES (:league, :total, :now)
            ON CONFLICT(league) DO UPDATE SET
                remote_total   = excluded.remote_total,
                remote_checked = excluded.remote_checked
            """,
            {"league": league, "total": total, "now": now},
        )


# --- baza graczy (tabela players + players_sync) ----------------------------

def upsert_player(p: dict, league: str) -> None:
    """Wstawia lub aktualizuje gracza dla danej ligi.

    `p` ma kształt jak zwraca LeaguepediaClient.get_league_players()
    (klucze: link, player_id, team, role, country, residency,
    nationality_primary, is_retired, tournament, date_start).
    `league` — krótka nazwa ligi (z LEAGUE_GROUPS), część klucza złożonego.
    """
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO players (
                overview_page, league, player_id, team, role,
                country, residency, nationality_primary, is_retired,
                tournament, date_start, last_fetched
            ) VALUES (
                :overview_page, :league, :player_id, :team, :role,
                :country, :residency, :nationality_primary, :is_retired,
                :tournament, :date_start, :last_fetched
            )
            ON CONFLICT(overview_page, league) DO UPDATE SET
                player_id           = excluded.player_id,
                team                = excluded.team,
                role                = excluded.role,
                country             = excluded.country,
                residency           = excluded.residency,
                nationality_primary = excluded.nationality_primary,
                is_retired          = excluded.is_retired,
                tournament          = excluded.tournament,
                date_start          = excluded.date_start,
                last_fetched        = excluded.last_fetched
            """,
            {
                "overview_page": p["link"],
                "league": league,
                "player_id": p.get("player_id", ""),
                "team": p.get("team", ""),
                "role": p.get("role", ""),
                "country": p.get("country", ""),
                "residency": p.get("residency", ""),
                "nationality_primary": p.get("nationality_primary", ""),
                "is_retired": p.get("is_retired", ""),
                "tournament": p.get("tournament", ""),
                "date_start": p.get("date_start", ""),
                "last_fetched": now,
            },
        )


def fetch_all_players(league: str | None = None) -> list[dict]:
    """Wszyscy gracze w bazie (opcjonalnie zawężeni do jednej ligi)."""
    query = "SELECT * FROM players"
    params: list = []
    if league:
        query += " WHERE league = ?"
        params = [league]
    query += " ORDER BY league, team, role, player_id"
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def count_all_players() -> int:
    """Łączna liczba wierszy w tabeli players (UWAGA: nie unikaty graczy)."""
    with get_conn() as conn:
        return conn.execute(
            "SELECT COUNT(*) AS n FROM players"
        ).fetchone()["n"]


def count_unique_players() -> int:
    """Liczba unikalnych graczy (po overview_page) — gracz może być w wielu ligach."""
    with get_conn() as conn:
        return conn.execute(
            "SELECT COUNT(DISTINCT overview_page) AS n FROM players"
        ).fetchone()["n"]


def count_players_for_league(league: str) -> int:
    """Liczba graczy zapisanych w bazie dla danej ligi."""
    with get_conn() as conn:
        return conn.execute(
            "SELECT COUNT(*) AS n FROM players WHERE league = ?", (league,)
        ).fetchone()["n"]


def get_players_sync(league: str) -> dict | None:
    """Wiersz players_sync danej ligi (krótka nazwa) albo None, gdy brak."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM players_sync WHERE league = ?", (league,)
        ).fetchone()
    return dict(row) if row else None


def all_players_sync() -> dict[str, dict]:
    """Cała tabela players_sync jako mapa: krótka nazwa ligi -> wiersz."""
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM players_sync").fetchall()
    return {r["league"]: dict(r) for r in rows}


def mark_players_fetched(league: str, player_count: int) -> None:
    """Odnotowuje udane pobranie graczy danej ligi (znacznik czasu + licznik)."""
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO players_sync (league, last_fetched, player_count)
            VALUES (:league, :now, :count)
            ON CONFLICT(league) DO UPDATE SET
                last_fetched = excluded.last_fetched,
                player_count = excluded.player_count
            """,
            {"league": league, "now": now, "count": player_count},
        )


# --- globalna baza graczy (tabela players_all + players_all_sync) -----------

def upsert_all_player(p: dict) -> None:
    """Wstawia lub aktualizuje jeden wiersz w globalnej bazie graczy.

    `p` ma kształt jak zwraca `LeaguepediaClient.get_all_players()` —
    surowe dicty po `cargoquery` (klucze CamelCase: OverviewPage, ID,
    Team, Role, Country, Residency, NationalityPrimary, IsRetired).

    Nie nadpisuje już zapisanych `lolpros_url` / `lolpros_checked_at` —
    sprawdzanie lolpros jest drogie (HTTP per gracz) i robione osobno;
    odświeżenie metadanych z Leaguepedia nie powinno tego kasować.
    """
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO players_all (
                overview_page, player_id, team, role,
                country, residency, nationality_primary, is_retired,
                last_fetched
            ) VALUES (
                :overview_page, :player_id, :team, :role,
                :country, :residency, :nationality_primary, :is_retired,
                :last_fetched
            )
            ON CONFLICT(overview_page) DO UPDATE SET
                player_id           = excluded.player_id,
                team                = excluded.team,
                role                = excluded.role,
                country             = excluded.country,
                residency           = excluded.residency,
                nationality_primary = excluded.nationality_primary,
                is_retired          = excluded.is_retired,
                last_fetched        = excluded.last_fetched
            """,
            {
                "overview_page": p.get("OverviewPage") or "",
                "player_id": p.get("ID") or "",
                "team": p.get("Team") or "",
                "role": p.get("Role") or "",
                "country": p.get("Country") or "",
                "residency": p.get("Residency") or "",
                "nationality_primary": p.get("NationalityPrimary") or "",
                "is_retired": p.get("IsRetired") or "",
                "last_fetched": now,
            },
        )


def fetch_all_players_global() -> list[dict]:
    """Wszystkie wiersze z globalnej bazy graczy, posortowane po nicku."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM players_all ORDER BY player_id COLLATE NOCASE"
        ).fetchall()
    return [dict(r) for r in rows]


def count_all_players_global() -> int:
    """Liczba wierszy w globalnej bazie graczy."""
    with get_conn() as conn:
        return conn.execute(
            "SELECT COUNT(*) AS n FROM players_all"
        ).fetchone()["n"]


def get_all_players_global_sync() -> dict | None:
    """Pojedynczy wiersz players_all_sync (singleton)."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM players_all_sync WHERE id = 1"
        ).fetchone()
    return dict(row) if row else None


def mark_all_players_fetched(player_count: int) -> None:
    """Odnotowuje pełne pobranie globalnej bazy graczy (znacznik + licznik)."""
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO players_all_sync (id, last_fetched, player_count)
            VALUES (1, :now, :count)
            ON CONFLICT(id) DO UPDATE SET
                last_fetched = excluded.last_fetched,
                player_count = excluded.player_count
            """,
            {"now": now, "count": player_count},
        )


def update_lolpros(overview_page: str, url: str | None) -> None:
    """Zapisuje wynik sprawdzenia lolpros dla gracza.

    `url` jest pełnym URL-em (gdy profil znaleziono) lub pustym stringiem
    (gdy sprawdzono i nie znaleziono). NULL zostawiamy na „nie sprawdzono"
    — odróżnia się trzy stany w UI (—, ❌, link).
    """
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE players_all
               SET lolpros_url = :url,
                   lolpros_checked_at = :now
             WHERE overview_page = :page
            """,
            {"page": overview_page, "url": url or "", "now": now},
        )


def count_lolpros_unchecked() -> int:
    """Ilu graczy w globalnej bazie nie ma jeszcze sprawdzonego lolpros."""
    with get_conn() as conn:
        return conn.execute(
            "SELECT COUNT(*) AS n FROM players_all "
            "WHERE lolpros_checked_at IS NULL"
        ).fetchone()["n"]
