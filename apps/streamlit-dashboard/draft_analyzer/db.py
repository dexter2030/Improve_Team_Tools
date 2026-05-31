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

import streamlit as st

from src.paths import COHORT_DB, DRAFTS_DB, PLAYERS_DB
from .leagues import more_specific

# TTL dla cache'u odczytów (sekundy). Streamlit rerunuje stronę przy każdej
# interakcji widżetu (klik w patch multiselect, zmiana checkboxa, ...), a
# bez cache te same SELECT-y wykonywałyby się 2-3x na render. Pięć minut
# to kompromis: ręczny refresh i tak unieważnia cache (clear_drafts_caches),
# więc nieaktualność może wystąpić tylko po edycji bazy spoza UI.
_READ_TTL = 300


@contextmanager
def _connect(db_path, attach: dict | None = None):
    """Połączenie do jednej bazy domenowej.

    `attach` (mapa alias -> ścieżka) dokłada inne pliki przez ATTACH DATABASE —
    używane przez kohortę, której zapytania JOIN-ują tabele z players.db.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    if attach:
        for alias, path in attach.items():
            conn.execute(f"ATTACH DATABASE ? AS {alias}", (str(path),))
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def get_conn_drafts():
    """drafts.db — drafty + metadane synchronizacji lig (league_sync)."""
    return _connect(DRAFTS_DB)


def get_conn_players():
    """players.db — rostery z lig + globalna baza graczy."""
    return _connect(PLAYERS_DB)


def get_conn_cohort():
    """cohort.db (lolpros_accounts + soloq_baseline), z players.db pod aliasem
    `players_db` — zapytania kohorty JOIN-ują players_all/players przez ATTACH.
    """
    return _connect(COHORT_DB, attach={"players_db": PLAYERS_DB})


def init_db():
    """Tworzy tabele we wszystkich bazach domenowych (idempotentnie)."""
    _init_drafts()
    _init_players()
    _init_cohort()


def _init_drafts():
    """drafts.db — drafty + metadane synchronizacji lig (league_sync)."""
    with get_conn_drafts() as conn:
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


def _init_players():
    """players.db — rostery z lig + globalna baza graczy."""
    with get_conn_players() as conn:
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


def _init_cohort():
    """cohort.db — konta lolpros + baseline SoloQ."""
    with get_conn_cohort() as conn:
        # SoloQ kohorta — konta zescrap'owane z lolpros + obliczone
        # statystyki sezonu. Dwie tabele:
        #
        # 1. lolpros_accounts — jeden wiersz na (gracz, konto na lolpros).
        #    Klucz logiczny: (overview_page, riot_id, platform). Pole
        #    `scrape_error` trzyma ostatni błąd scrapowania (NULL = sukces)
        #    — pozwala odróżnić „nie scrapowane" od „scrapowane, brak kont".
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS lolpros_accounts (
                overview_page  TEXT NOT NULL,
                game_name      TEXT NOT NULL,
                tag_line       TEXT NOT NULL,
                region         TEXT NOT NULL,
                platform       TEXT NOT NULL,
                scraped_at     TEXT NOT NULL,
                scrape_error   TEXT,
                PRIMARY KEY (overview_page, game_name, tag_line, platform)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_lolpros_accounts_player "
            "ON lolpros_accounts(overview_page)"
        )

        # 2. soloq_baseline — jeden wiersz na (konto, cutoff). Trzymamy
        #    surowe agregaty (kda, cs/min, ...) + role i meta. JSON
        #    `payload` daje miejsce na nowe metryki bez migracji.
        #    Klucz złożony: (overview_page, puuid, since_epoch).
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS soloq_baseline (
                overview_page  TEXT NOT NULL,
                puuid          TEXT NOT NULL,
                game_name      TEXT NOT NULL,
                tag_line       TEXT NOT NULL,
                platform       TEXT NOT NULL,
                role           TEXT,            -- dominująca rola w oknie
                league         TEXT,            -- skopiowane z players_all (pierwsza liga)
                since_epoch    INTEGER NOT NULL,
                games          INTEGER NOT NULL,
                winrate        REAL,
                kda            REAL,
                cs_per_min     REAL,
                dpm            REAL,
                gold_per_min   REAL,
                damage_taken_per_min REAL,
                vision_per_min REAL,
                wards_per_min  REAL,
                kp             REAL,
                cs10           REAL,
                gd15           REAL,
                solo_kills     REAL,
                first_blood_rate REAL,
                tier           TEXT,
                rank           TEXT,
                lp             INTEGER,
                computed_at    TEXT NOT NULL,
                payload        TEXT,             -- JSON dla nowych metryk
                PRIMARY KEY (overview_page, puuid, since_epoch)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_soloq_baseline_role "
            "ON soloq_baseline(role)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_soloq_baseline_league "
            "ON soloq_baseline(league)"
        )


def upsert_draft(d: dict):
    """Wstawia lub aktualizuje jeden draft. `d` to słownik z polami tabeli."""
    with get_conn_drafts() as conn:
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


@st.cache_data(ttl=_READ_TTL, show_spinner=False)
def fetch_all_drafts(patches: list[str] | None = None) -> list[dict]:
    """
    Zwraca wszystkie drafty (opcjonalnie zawężone do listy patchy).
    Bany deserializowane z JSON do list pythonowych.

    Cache: Streamlit hashuje argumenty (None lub listę patchy), więc
    powtórne wywołanie tym samym zestawem patchy trafia w cache zamiast
    ponownie skanować tabelę i parsować JSON. Unieważnia clear_drafts_caches()
    po fetchu nowych draftów.
    """
    query = "SELECT * FROM drafts"
    params: list = []
    if patches:
        placeholders = ",".join("?" * len(patches))
        query += f" WHERE patch IN ({placeholders})"
        params = patches

    with get_conn_drafts() as conn:
        rows = conn.execute(query, params).fetchall()

    out = []
    for r in rows:
        d = dict(r)
        d["blue_bans"] = json.loads(d["blue_bans"])
        d["red_bans"] = json.loads(d["red_bans"])
        out.append(d)
    return out


@st.cache_data(ttl=_READ_TTL, show_spinner=False)
def list_patches() -> list[str]:
    """Lista dostępnych patchy, od najnowszego."""
    with get_conn_drafts() as conn:
        rows = conn.execute(
            "SELECT DISTINCT patch FROM drafts WHERE patch IS NOT NULL "
            "ORDER BY patch DESC"
        ).fetchall()
    return [r["patch"] for r in rows]


@st.cache_data(ttl=_READ_TTL, show_spinner=False)
def list_teams() -> list[str]:
    """Lista drużyn występujących po stronie blue, alfabetycznie."""
    with get_conn_drafts() as conn:
        rows = conn.execute(
            "SELECT DISTINCT blue_team FROM drafts "
            "WHERE blue_team IS NOT NULL AND blue_team != '' "
            "ORDER BY blue_team"
        ).fetchall()
    return [r["blue_team"] for r in rows]


@st.cache_data(ttl=_READ_TTL, show_spinner=False)
def count_all_drafts() -> int:
    """Łączna liczba draftów w bazie."""
    with get_conn_drafts() as conn:
        return conn.execute("SELECT COUNT(*) AS n FROM drafts").fetchone()["n"]


@st.cache_data(ttl=_READ_TTL, show_spinner=False)
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
    with get_conn_drafts() as conn:
        row = conn.execute(sql, params).fetchone()
    return row["n"]


# --- metadane synchronizacji lig (tabela league_sync) -----------------------

def get_league_sync(league: str) -> dict | None:
    """Wiersz league_sync danej ligi (krótka nazwa) albo None, gdy brak."""
    with get_conn_drafts() as conn:
        row = conn.execute(
            "SELECT * FROM league_sync WHERE league = ?", (league,)
        ).fetchone()
    return dict(row) if row else None


@st.cache_data(ttl=_READ_TTL, show_spinner=False)
def all_league_sync() -> dict[str, dict]:
    """Cała tabela league_sync jako mapa: krótka nazwa ligi -> wiersz."""
    with get_conn_drafts() as conn:
        rows = conn.execute("SELECT * FROM league_sync").fetchall()
    return {r["league"]: dict(r) for r in rows}


def clear_drafts_caches() -> None:
    """Unieważnia cache wszystkich odczytów dotyczących draftów.

    Wołać po każdym fetch_league() / batchu upsert_draft() z UI, żeby
    następny render widział świeże dane. Czyści po jednej funkcji zamiast
    `st.cache_data.clear()`, żeby nie wywalać cache'ów spoza modułu drafts.
    """
    fetch_all_drafts.clear()
    list_patches.clear()
    list_teams.clear()
    count_all_drafts.clear()
    count_drafts_for_league.clear()
    all_league_sync.clear()


def mark_league_fetched(league: str, last_game_date: str | None) -> None:
    """Odnotowuje udane wczytanie ligi — ustawia `last_fetched` na teraz.

    `last_game_date` to data najnowszej gry w bazie dla tej ligi; służy
    jako kursor pobierania przyrostowego. None NIE nadpisuje zapisanego
    kursora (COALESCE) — dzięki temu obcięte/puste wczytanie go nie cofa.

    Wołać dopiero po pełnym przejściu ligi — uzasadnienie w sync.py.
    """
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn_drafts() as conn:
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
    with get_conn_drafts() as conn:
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
    with get_conn_players() as conn:
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
    with get_conn_players() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def count_all_players() -> int:
    """Łączna liczba wierszy w tabeli players (UWAGA: nie unikaty graczy)."""
    with get_conn_players() as conn:
        return conn.execute(
            "SELECT COUNT(*) AS n FROM players"
        ).fetchone()["n"]


def count_unique_players() -> int:
    """Liczba unikalnych graczy (po overview_page) — gracz może być w wielu ligach."""
    with get_conn_players() as conn:
        return conn.execute(
            "SELECT COUNT(DISTINCT overview_page) AS n FROM players"
        ).fetchone()["n"]


def count_players_for_league(league: str) -> int:
    """Liczba graczy zapisanych w bazie dla danej ligi."""
    with get_conn_players() as conn:
        return conn.execute(
            "SELECT COUNT(*) AS n FROM players WHERE league = ?", (league,)
        ).fetchone()["n"]


def get_players_sync(league: str) -> dict | None:
    """Wiersz players_sync danej ligi (krótka nazwa) albo None, gdy brak."""
    with get_conn_players() as conn:
        row = conn.execute(
            "SELECT * FROM players_sync WHERE league = ?", (league,)
        ).fetchone()
    return dict(row) if row else None


def all_players_sync() -> dict[str, dict]:
    """Cała tabela players_sync jako mapa: krótka nazwa ligi -> wiersz."""
    with get_conn_players() as conn:
        rows = conn.execute("SELECT * FROM players_sync").fetchall()
    return {r["league"]: dict(r) for r in rows}


def mark_players_fetched(league: str, player_count: int) -> None:
    """Odnotowuje udane pobranie graczy danej ligi (znacznik czasu + licznik)."""
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn_players() as conn:
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
    with get_conn_players() as conn:
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
    with get_conn_players() as conn:
        rows = conn.execute(
            "SELECT * FROM players_all ORDER BY player_id COLLATE NOCASE"
        ).fetchall()
    return [dict(r) for r in rows]


def count_all_players_global() -> int:
    """Liczba wierszy w globalnej bazie graczy."""
    with get_conn_players() as conn:
        return conn.execute(
            "SELECT COUNT(*) AS n FROM players_all"
        ).fetchone()["n"]


def get_all_players_global_sync() -> dict | None:
    """Pojedynczy wiersz players_all_sync (singleton)."""
    with get_conn_players() as conn:
        row = conn.execute(
            "SELECT * FROM players_all_sync WHERE id = 1"
        ).fetchone()
    return dict(row) if row else None


def mark_all_players_fetched(player_count: int) -> None:
    """Odnotowuje pełne pobranie globalnej bazy graczy (znacznik + licznik)."""
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn_players() as conn:
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
    with get_conn_players() as conn:
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
    with get_conn_players() as conn:
        return conn.execute(
            "SELECT COUNT(*) AS n FROM players_all "
            "WHERE lolpros_checked_at IS NULL"
        ).fetchone()["n"]


# --- Kohorta SoloQ: lolpros_accounts + soloq_baseline -----------------------

def players_with_lolpros() -> list[dict]:
    """Wszyscy gracze z niepustym lolpros_url (kandydaci do scrapowania kont).

    Zwraca też role i ligi — używamy ich w UI do filtrów. Dla `league`
    bierzemy DOWOLNĄ ligę z players (LIMIT 1) — gracz może występować w
    kilku, ale do filtra kohorty jedna wystarcza.
    """
    with get_conn_players() as conn:
        rows = conn.execute(
            """
            SELECT pa.overview_page, pa.player_id, pa.role, pa.country,
                   pa.nationality_primary, pa.lolpros_url,
                   (SELECT p.league FROM players p
                      WHERE p.overview_page = pa.overview_page
                      LIMIT 1) AS league
              FROM players_all pa
             WHERE pa.lolpros_url IS NOT NULL
               AND pa.lolpros_url != ''
             ORDER BY pa.player_id COLLATE NOCASE
            """
        ).fetchall()
    return [dict(r) for r in rows]


def upsert_lolpros_accounts(
    overview_page: str,
    accounts: list[dict],
    *,
    scrape_error: str | None = None,
) -> None:
    """Zapisuje listę kont scrap'owanych z lolpros dla jednego gracza.

    Każdy `accounts[i]` to słownik z polami: game_name, tag_line, region,
    platform. Wcześniejsze rekordy gracza nie są kasowane — kolejne scrap
    nadpisuje wpisy o tym samym (riot_id, platform) i dokleja nowe. Pusty
    `accounts` z niepustym `scrape_error` zapisuje placeholder, żeby UI
    wiedział że scrap był zrobiony i się wywalił.
    """
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn_cohort() as conn:
        if not accounts:
            # Placeholder żeby odróżnić "scrap zrobiony, brak kont" od "nigdy
            # nie scrapowane" (= overview_page nie ma w lolpros_accounts).
            conn.execute(
                """
                INSERT OR REPLACE INTO lolpros_accounts (
                    overview_page, game_name, tag_line, region, platform,
                    scraped_at, scrape_error
                ) VALUES (?, '', '', '', '', ?, ?)
                """,
                (overview_page, now, scrape_error or ""),
            )
            return
        for acc in accounts:
            conn.execute(
                """
                INSERT INTO lolpros_accounts (
                    overview_page, game_name, tag_line, region, platform,
                    scraped_at, scrape_error
                ) VALUES (
                    :overview_page, :game_name, :tag_line, :region, :platform,
                    :scraped_at, NULL
                )
                ON CONFLICT(overview_page, game_name, tag_line, platform)
                DO UPDATE SET
                    region       = excluded.region,
                    scraped_at   = excluded.scraped_at,
                    scrape_error = NULL
                """,
                {
                    "overview_page": overview_page,
                    "game_name": acc["game_name"],
                    "tag_line":  acc["tag_line"],
                    "region":    acc["region"],
                    "platform":  acc["platform"],
                    "scraped_at": now,
                },
            )


def fetch_lolpros_accounts(overview_page: str) -> list[dict]:
    """Konta z lolpros zapisane dla jednego gracza (bez placeholderów pustych)."""
    with get_conn_cohort() as conn:
        rows = conn.execute(
            """
            SELECT * FROM lolpros_accounts
             WHERE overview_page = ?
               AND game_name != ''
             ORDER BY platform, game_name
            """,
            (overview_page,),
        ).fetchall()
    return [dict(r) for r in rows]


def fetch_all_lolpros_accounts() -> list[dict]:
    """Wszystkie scrap'owane konta wszystkich graczy (bez placeholderów)."""
    with get_conn_cohort() as conn:
        rows = conn.execute(
            """
            SELECT la.*, pa.player_id, pa.role,
                   (SELECT p.league FROM players_db.players p
                      WHERE p.overview_page = la.overview_page
                      LIMIT 1) AS league
              FROM lolpros_accounts la
              LEFT JOIN players_db.players_all pa ON pa.overview_page = la.overview_page
             WHERE la.game_name != ''
             ORDER BY pa.player_id COLLATE NOCASE
            """
        ).fetchall()
    return [dict(r) for r in rows]


def count_lolpros_scraped() -> int:
    """Ilu graczy ma scrap'owane konta (z placeholderem pustym włącznie)."""
    with get_conn_cohort() as conn:
        return conn.execute(
            "SELECT COUNT(DISTINCT overview_page) AS n FROM lolpros_accounts"
        ).fetchone()["n"]


def players_needing_lolpros_scrape() -> list[dict]:
    """Gracze z lolpros_url, których jeszcze nie scrapowaliśmy.

    Definicja „jeszcze nie": overview_page nieobecny w lolpros_accounts.
    Wynik zachowuje role i ligę, żeby filtry UI mogły z niego korzystać.
    """
    with get_conn_cohort() as conn:
        rows = conn.execute(
            """
            SELECT pa.overview_page, pa.player_id, pa.role,
                   pa.lolpros_url,
                   (SELECT p.league FROM players_db.players p
                      WHERE p.overview_page = pa.overview_page
                      LIMIT 1) AS league
              FROM players_db.players_all pa
             WHERE pa.lolpros_url IS NOT NULL
               AND pa.lolpros_url != ''
               AND NOT EXISTS (
                   SELECT 1 FROM lolpros_accounts la
                    WHERE la.overview_page = pa.overview_page
               )
             ORDER BY pa.player_id COLLATE NOCASE
            """
        ).fetchall()
    return [dict(r) for r in rows]


def upsert_soloq_baseline(row: dict) -> None:
    """Zapisuje (lub nadpisuje) jeden wpis baseline.

    `row` musi mieć: overview_page, puuid, game_name, tag_line, platform,
    since_epoch, games. Reszta pól opcjonalna — None zapisze NULL.
    `payload` (dict) jest serializowany do JSON.
    """
    now = datetime.now().isoformat(timespec="seconds")
    payload_json = json.dumps(row.get("payload") or {})
    with get_conn_cohort() as conn:
        conn.execute(
            """
            INSERT INTO soloq_baseline (
                overview_page, puuid, game_name, tag_line, platform,
                role, league, since_epoch, games, winrate,
                kda, cs_per_min, dpm, gold_per_min,
                damage_taken_per_min, vision_per_min, wards_per_min,
                kp, cs10, gd15, solo_kills, first_blood_rate,
                tier, rank, lp, computed_at, payload
            ) VALUES (
                :overview_page, :puuid, :game_name, :tag_line, :platform,
                :role, :league, :since_epoch, :games, :winrate,
                :kda, :cs_per_min, :dpm, :gold_per_min,
                :damage_taken_per_min, :vision_per_min, :wards_per_min,
                :kp, :cs10, :gd15, :solo_kills, :first_blood_rate,
                :tier, :rank, :lp, :computed_at, :payload
            )
            ON CONFLICT(overview_page, puuid, since_epoch) DO UPDATE SET
                role           = excluded.role,
                league         = excluded.league,
                games          = excluded.games,
                winrate        = excluded.winrate,
                kda            = excluded.kda,
                cs_per_min     = excluded.cs_per_min,
                dpm            = excluded.dpm,
                gold_per_min   = excluded.gold_per_min,
                damage_taken_per_min = excluded.damage_taken_per_min,
                vision_per_min = excluded.vision_per_min,
                wards_per_min  = excluded.wards_per_min,
                kp             = excluded.kp,
                cs10           = excluded.cs10,
                gd15           = excluded.gd15,
                solo_kills     = excluded.solo_kills,
                first_blood_rate = excluded.first_blood_rate,
                tier           = excluded.tier,
                rank           = excluded.rank,
                lp             = excluded.lp,
                computed_at    = excluded.computed_at,
                payload        = excluded.payload
            """,
            {
                **{
                    k: row.get(k) for k in (
                        "overview_page", "puuid", "game_name", "tag_line",
                        "platform", "role", "league", "since_epoch", "games",
                        "winrate", "kda", "cs_per_min", "dpm", "gold_per_min",
                        "damage_taken_per_min", "vision_per_min",
                        "wards_per_min", "kp", "cs10", "gd15", "solo_kills",
                        "first_blood_rate", "tier", "rank", "lp",
                    )
                },
                "computed_at": now,
                "payload": payload_json,
            },
        )


def fetch_soloq_baseline(
    leagues: list[str] | None = None,
    roles: list[str] | None = None,
    *,
    since_epoch: int | None = None,
) -> list[dict]:
    """Pobiera wiersze kohorty z opcjonalnymi filtrami liga/rola/cutoff.

    `leagues` to lista krótkich nazw (LEC, LCK, ...) — dopasowuje po
    podciągu kolumny league (NLC ⊆ "NLC 2026 Spring"). `since_epoch`
    pozwala wybrać tylko wpisy obliczone dla konkretnego cutoff.
    """
    clauses: list[str] = []
    params: list = []
    if leagues:
        league_clauses = []
        for lg in leagues:
            league_clauses.append(
                "LOWER(league) LIKE '%' || LOWER(?) || '%'"
            )
            params.append(lg)
        clauses.append("(" + " OR ".join(league_clauses) + ")")
    if roles:
        placeholders = ",".join("?" * len(roles))
        clauses.append(f"role IN ({placeholders})")
        params.extend(roles)
    if since_epoch is not None:
        clauses.append("since_epoch = ?")
        params.append(since_epoch)
    sql = "SELECT * FROM soloq_baseline"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY overview_page, since_epoch DESC"
    with get_conn_cohort() as conn:
        rows = conn.execute(sql, params).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        if d.get("payload"):
            try:
                d["payload"] = json.loads(d["payload"])
            except json.JSONDecodeError:
                d["payload"] = {}
        out.append(d)
    return out


def count_soloq_baseline_for_cutoff(since_epoch: int) -> int:
    """Ile wpisów baseline policzono dla danego cutoff."""
    with get_conn_cohort() as conn:
        return conn.execute(
            "SELECT COUNT(*) AS n FROM soloq_baseline WHERE since_epoch = ?",
            (since_epoch,),
        ).fetchone()["n"]


def accounts_needing_baseline(since_epoch: int) -> list[dict]:
    """Konta z lolpros_accounts, dla których nie ma baseline z danym cutoff.

    Każdy wiersz ma overview_page, game_name, tag_line, platform, role,
    league (potrzebne potem do zapisu baseline).
    """
    with get_conn_cohort() as conn:
        rows = conn.execute(
            """
            SELECT la.overview_page, la.game_name, la.tag_line,
                   la.region, la.platform,
                   pa.role,
                   (SELECT p.league FROM players_db.players p
                      WHERE p.overview_page = la.overview_page
                      LIMIT 1) AS league
              FROM lolpros_accounts la
              LEFT JOIN players_db.players_all pa ON pa.overview_page = la.overview_page
             WHERE la.game_name != ''
               AND NOT EXISTS (
                   SELECT 1 FROM soloq_baseline sb
                    WHERE sb.overview_page = la.overview_page
                      AND sb.game_name     = la.game_name
                      AND sb.tag_line      = la.tag_line
                      AND sb.platform      = la.platform
                      AND sb.since_epoch   = ?
               )
             ORDER BY pa.player_id COLLATE NOCASE
            """,
            (since_epoch,),
        ).fetchall()
    return [dict(r) for r in rows]
