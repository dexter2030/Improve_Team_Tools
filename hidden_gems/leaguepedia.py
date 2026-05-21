"""
hidden_gems/leaguepedia.py

Domenowe agregaty pro-play do scoringu "hidden gem": średnie metryki gracza
i benchmark całej ligi (1 ERL / 2 ERL).

Pobieranie wierszy ScoreboardPlayers idzie przez WSPÓLNY klient
`src/api/leaguepedia_client.py` — żaden moduł projektu nie utrzymuje już
własnej warstwy Cargo HTTP/retry/paginacji. Tutaj zostaje wyłącznie domain:
liczenie KDA / CS/min / DPM / KP / gold_share na podstawie wierszy meczowych.

Wywołania UI typowo idą tak:
    1. `cohort_player_aggregates(league, role)` — raz na ligę/rolę.
    2. `aggregate_player_stats(rows)` — per gracz (na tych samych wierszach).
    3. `league_benchmark(league, role)` — średnia po graczach do hidden-gem
       scoringu.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable

from src.api.leaguepedia_client import LeaguepediaClient

logger = logging.getLogger(__name__)


# Wspólna instancja klienta — leniwa, żeby import modułu nie ciągnął sieci.
# mwclient.Site konstruuje się jednym requestem; trzymamy ją modułowo bo
# między wywołaniami `compute_league_distribution` często chodzimy po tej
# samej lidze i chcemy korzystać z cache klienta.
_client: LeaguepediaClient | None = None


def _get_client() -> LeaguepediaClient:
    global _client
    if _client is None:
        _client = LeaguepediaClient()
    return _client


# --- Funkcje domenowe -------------------------------------------------------

def get_players(
    league: str | None = None,
    season: str | None = None,
) -> list[dict[str, Any]]:
    """Lista graczy z Leaguepedii — filtr po lidze / sezonie (roku).

    Bez filtra po lidze: pełny zrzut `Players` (drogo!). Z filtrem joinujemy
    `TournamentPlayers` + `Tournaments`, żeby zostawić tylko graczy, którzy
    rzeczywiście grali w tej lidze (i tym roku, jeśli `season` podany).
    """
    client = _get_client()

    if league is None:
        rows = client.cargo(
            tables="Players",
            fields=(
                "Players.ID=nick,"
                "Players.Team=team,"
                "Players.Role=role,"
                "Players.Country=country,"
                "Players.Age=age"
            ),
            where="Players.IsRetired='No'",
        )
        return [
            {
                "nick":    r.get("nick", ""),
                "team":    r.get("team", ""),
                "role":    r.get("role", ""),
                "country": r.get("country", ""),
                "age":     _to_int(r.get("age")),
                "league":  None,
            }
            for r in rows
        ]

    # Z filtrem ligi — join TournamentPlayers + Tournaments + Players.
    where_parts = [f"Tournaments.League='{_esc(league)}'"]
    if season is not None:
        where_parts.append(f"Tournaments.Year='{_esc(season)}'")
    rows = client.cargo(
        tables="TournamentPlayers=TP,Tournaments=T,Players=P",
        join_on="TP.OverviewPage=T.OverviewPage,TP.Player=P.OverviewPage",
        fields=(
            "P.ID=nick,"
            "TP.Team=team,"
            "TP.Role=role,"
            "P.Country=country,"
            "P.Age=age,"
            "T.League=league"
        ),
        where=" AND ".join(where_parts),
    )

    # Gracz może występować w wielu turniejach tej samej ligi/sezonu;
    # deduplikujemy po (nick, team, role) zostawiając pierwszy wiersz.
    seen: set[tuple[str, str, str]] = set()
    out: list[dict[str, Any]] = []
    for r in rows:
        key = (r.get("nick", ""), r.get("team", ""), r.get("role", ""))
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "nick":    r.get("nick", ""),
            "team":    r.get("team", ""),
            "role":    r.get("role", ""),
            "country": r.get("country", ""),
            "age":     _to_int(r.get("age")),
            "league":  r.get("league", ""),
        })
    return out


def get_scoreboard_stats(
    player: str | None = None,
    league: str | None = None,
) -> list[dict[str, Any]]:
    """Surowe staty per mecz z ScoreboardPlayers (Gold, Damage, TeamKills).

    Co najmniej jeden filtr (player / league) musi być podany — bez filtra
    zapytanie byłoby olbrzymie i wpadłoby w rate limit.

    Pole `player` to `Link` z Leaguepedii (OverviewPage gracza, np. "Caps").
    """
    if player is None and league is None:
        raise ValueError(
            "get_scoreboard_stats wymaga `player` lub `league` "
            "(bez filtra zapytanie zaciągnie zbyt wiele wierszy)."
        )
    # Cienki proxy — pełna logika zapytania (3-table join + paginacja
    # + cache) jest we wspólnym kliencie.
    return _get_client().get_scoreboard_stats(
        player_link=player, league=league,
    )


def aggregate_player_stats(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Agreguje wiersze meczowe jednego gracza w średnie scoutingowe.

    Wszystkie wskaźniki "ważone" są średnią z per-mecz wartości
    (a NIE z totali) — żeby pojedynczy mecz koksowy nie dominował średniej.

    UWAGA: damage_share wymagałby `TeamDamageToChampions`, którego
    ScoreboardPlayers nie udostępnia natywnie. Zwracamy None — żeby je
    policzyć, sumuj DamageToChampions wszystkich graczy drużyny w danym
    meczu w warstwie wyżej i przekaż jako wirtualne pole `team_damage`.
    """
    rows = list(rows)
    games = len(rows)
    if games == 0:
        return {
            "games": 0, "wins": 0, "winrate": None,
            "kda": None, "cs_per_min": None, "dpm": None,
            "kp": None, "gold_share": None, "damage_share": None,
        }

    wins = sum(1 for r in rows if r.get("win"))

    per_kda: list[float] = []
    per_cspm: list[float] = []
    per_dpm: list[float] = []
    per_kp: list[float] = []
    per_gold_share: list[float] = []
    per_dmg_share: list[float] = []

    for r in rows:
        k = r.get("kills", 0) or 0
        d = r.get("deaths", 0) or 0
        a = r.get("assists", 0) or 0
        # KDA z deaths=0 -> "perfekcyjny": używamy max(deaths, 1).
        per_kda.append((k + a) / max(d, 1))

        gl = r.get("gamelength_min") or 0
        if gl > 0:
            per_cspm.append((r.get("cs", 0) or 0) / gl)
            per_dpm.append((r.get("damage_champions", 0) or 0) / gl)

        tk = r.get("team_kills", 0) or 0
        if tk > 0:
            per_kp.append((k + a) / tk)

        tg = r.get("team_gold", 0) or 0
        if tg > 0:
            per_gold_share.append((r.get("gold", 0) or 0) / tg)

        td = r.get("team_damage", 0) or 0   # opcjonalne pole "virtualne"
        if td > 0:
            per_dmg_share.append((r.get("damage_champions", 0) or 0) / td)

    def _avg(xs: list[float]) -> float | None:
        return sum(xs) / len(xs) if xs else None

    return {
        "games":        games,
        "wins":         wins,
        "winrate":      wins / games,
        "kda":          _avg(per_kda),
        "cs_per_min":   _avg(per_cspm),
        "dpm":          _avg(per_dpm),
        "kp":           _avg(per_kp),
        "gold_share":   _avg(per_gold_share),
        "damage_share": _avg(per_dmg_share),
    }


def cohort_player_aggregates(
    league: str,
    role: str | None = None,
) -> list[dict[str, Any]]:
    """Zwraca aggregate_player_stats() dla każdego gracza ligi/roli.

    Wspólny helper, żeby Cargo nie był pytany dwa razy o ten sam zestaw
    meczów (raz na benchmark, raz na rozkład do Z-scoreów).
    """
    rows = get_scoreboard_stats(league=league)
    if role:
        target = role.strip().lower()
        rows = [r for r in rows if str(r.get("role", "")).lower() == target]
    by_player: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_player.setdefault(r["link"], []).append(r)
    return [aggregate_player_stats(games) for games in by_player.values()]


def league_benchmark(
    league: str,
    role: str | None = None,
) -> dict[str, Any]:
    """Średnie statystyki dla CAŁEJ ligi — benchmark "1 ERL / 2 ERL".

    Średnia jest "po graczach", nie "po meczach" — żeby zawodnik grający
    bardzo dużo gier nie ciągnął benchmarka pod swoje liczby.
    """
    aggs = cohort_player_aggregates(league, role)

    if not aggs:
        return {
            "league": league, "role": role,
            "n_players": 0, "n_games": 0,
            "kda": None, "cs_per_min": None, "dpm": None,
            "kp": None, "gold_share": None, "winrate": None,
        }

    n_games = sum(a.get("games", 0) for a in aggs)

    def _avg(key: str) -> float | None:
        vals = [a[key] for a in aggs if a.get(key) is not None]
        return sum(vals) / len(vals) if vals else None

    return {
        "league":     league,
        "role":       role,
        "n_players":  len(aggs),
        "n_games":    n_games,
        "kda":        _avg("kda"),
        "cs_per_min": _avg("cs_per_min"),
        "dpm":        _avg("dpm"),
        "kp":         _avg("kp"),
        "gold_share": _avg("gold_share"),
        "winrate":    _avg("winrate"),
    }


# --- Helpers ----------------------------------------------------------------

def _to_int(v: object) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(float(v))   # "23" oraz "23.0"
    except (TypeError, ValueError):
        return None


def _esc(s: str) -> str:
    """Escapuje wartość do WHERE Cargo (Cargo kompiluje do SQL)."""
    return s.replace("\\", "\\\\").replace("'", "\\'")


# --- Przykład użycia --------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    print("== get_players(league='LFL', season='2025') ==")
    players = get_players(league="LFL", season="2025")
    for p in players[:5]:
        print(p)
    print(f"łącznie: {len(players)} graczy\n")

    print("== get_scoreboard_stats(player='Caps') — 3 mecze ==")
    games = get_scoreboard_stats(player="Caps")
    for g in games[:3]:
        print(g)
    print()

    print("== aggregate_player_stats(Caps) ==")
    print(aggregate_player_stats(games))
    print()

    print("== league_benchmark('LFL', role='Mid') ==")
    print(league_benchmark("LFL", role="Mid"))
