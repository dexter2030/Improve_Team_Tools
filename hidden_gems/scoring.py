"""
hidden_gems/scoring.py

Hidden Gem Score — liczbowa miara "jak bardzo forma soloQ gracza przewyższa
średni poziom jego ligi pro". Łączy `leaguepedia.cohort_player_aggregates`
(rozkład metryk pro w lidze) z `soloq.SoloQProvider` (statystyki gracza).

Standalone — bez Streamlita. UI typowo woła:
    1. `compute_league_distribution(league, role)` — raz na ligę/rolę (drogie).
    2. `score_player(...)` lub `score_many(...)` — po jednym graczu z tym
       samym `league_distribution=` (znaczna oszczędność na Cargo).

KAWEAT METODOLOGICZNY
SoloQ KDA / CS/min są systemowo wyższe niż pro KDA / CS/min — inne tempo
gry, brak koordynacji 5v5. To NIE jest "fair" porównanie umiejętności;
to relatywny pomiar "powyżej / poniżej kohorty ligowej". Hidden gem = gracz
z wyraźnie wysokim Z-scoreem i wysoką rangą soloQ. Nie myl z prognozą
wyniku w turnieju.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from . import leaguepedia
from .soloq import SoloQProvider


# Skala dobrana tak, by przeskok dwóch tierów (Diamond -> Master) był wart
# ~1 unit — porównywalny z typowym Z-scorem 1σ na metrykę.
_TIER_BONUS: dict[str, float] = {
    "IRON":         -3.0,
    "BRONZE":       -2.5,
    "SILVER":       -2.0,
    "GOLD":         -1.5,
    "PLATINUM":     -1.0,
    "EMERALD":      -0.5,
    "DIAMOND":       0.0,
    "MASTER":        1.0,
    "GRANDMASTER":   2.0,
    "CHALLENGER":    3.0,
    "UNRANKED":     -1.5,
}

# Progi "wystarczającej próby" — poniżej `low_sample=True`.
_MIN_SOLOQ_GAMES = 10
_MIN_LEAGUE_PLAYERS = 5


# --- Typy ------------------------------------------------------------------

@dataclass(frozen=True)
class MetricDist:
    """Średnia i odchylenie standardowe jednej metryki w kohorcie."""
    mean: float | None
    std: float | None
    n: int


@dataclass(frozen=True)
class LeagueDistribution:
    """Rozkład metryk całej ligi (po graczach) — kohorta porównawcza."""
    league: str
    role: str | None
    n_players: int
    n_games: int
    kda:        MetricDist
    cs_per_min: MetricDist
    dpm:        MetricDist
    kp:         MetricDist


@dataclass(frozen=True)
class HiddenGemScore:
    """Wynik score'owania gracza vs. liga.

    `score` = średnia z policzalnych Z-score'ów + bonus za tier rangi soloQ.
    Wartości orientacyjne:
        > 2.0  — silny hidden gem
        > 1.0  — wart obejrzenia
        ~  0   — typowy zawodnik dla ligi
        < -1.0 — poniżej poziomu ligi
    """
    score:            float
    z_scores:         dict[str, float | None]  # per metryka, None gdy brak danych
    rank_tier:        str | None
    rank_division:    str | None
    rank_lp:          int | None
    rank_bonus:       float
    n_games_soloq:    int
    n_players_league: int
    low_sample:       bool


# --- Cohort distribution ---------------------------------------------------

def compute_league_distribution(
    league: str,
    role: str | None = None,
) -> LeagueDistribution:
    """Pełny rozkład (mean+std) metryk dla ligi/roli — kohorta do Z-score.

    UWAGA: kosztowne (ciąga ScoreboardPlayers całej ligi). W UI cache'uj
    z TTL ~24h. Score'owanie wielu graczy — przelicz raz, przekaż przez
    `league_distribution=` do score_player / score_many.
    """
    aggs = leaguepedia.cohort_player_aggregates(league, role)
    n_games = sum(a.get("games", 0) for a in aggs)
    return LeagueDistribution(
        league=league,
        role=role,
        n_players=len(aggs),
        n_games=n_games,
        kda=_metric_dist(aggs, "kda"),
        cs_per_min=_metric_dist(aggs, "cs_per_min"),
        dpm=_metric_dist(aggs, "dpm"),
        kp=_metric_dist(aggs, "kp"),
    )


def _metric_dist(aggs: list[dict[str, Any]], key: str) -> MetricDist:
    vals = [a[key] for a in aggs if a.get(key) is not None]
    n = len(vals)
    if n == 0:
        return MetricDist(mean=None, std=None, n=0)
    m = sum(vals) / n
    # Populacyjna wariancja (nie sample) — kohorta = cała populacja ligi.
    var = sum((v - m) ** 2 for v in vals) / n if n > 1 else 0.0
    return MetricDist(mean=m, std=var ** 0.5, n=n)


# --- Scoring ---------------------------------------------------------------

def score_player(
    provider: SoloQProvider,
    *,
    riot_id: str,
    region: str,
    league: str,
    role: str | None = None,
    n_recent: int = 20,
    league_distribution: LeagueDistribution | None = None,
) -> HiddenGemScore | None:
    """Hidden Gem Score dla jednego gracza.

    Args:
        provider: SoloQProvider (RiotProvider lub OpggProvider).
        riot_id: "Name#TAG" konta soloQ.
        region: platforma soloQ ("euw1", "kr"...).
        league: liga pro ("LFL", "LEC"...) — pasująca do Tournament.
        role: rola w pro play ("Mid", "Top"...). None = wszystkie.
        n_recent: ile ostatnich meczów rank wziąć (default 20).
        league_distribution: jeśli podany — pomijamy fetch benchmarka.
            Wymagane przy batchu (score_many to robi automatycznie).

    Zwraca None gdy soloQ kompletnie niedostępne (brak konta, klucz wygasł).
    """
    rank = provider.get_rank(riot_id, region)
    perf = provider.get_recent_performance(riot_id, region, n=n_recent)
    if rank is None and perf is None:
        return None

    dist = league_distribution or compute_league_distribution(league, role)

    z_scores: dict[str, float | None] = {
        "kda":        _z(perf.kda        if perf else None, dist.kda),
        "cs_per_min": _z(perf.cs_per_min if perf else None, dist.cs_per_min),
        "dpm":        _z(perf.dpm        if perf else None, dist.dpm),
        "kp":         _z(perf.kp         if perf else None, dist.kp),
    }

    tier_key = (rank.tier or "UNRANKED").upper() if rank else "UNRANKED"
    rank_bonus = _TIER_BONUS.get(tier_key, 0.0)

    z_valid = [v for v in z_scores.values() if v is not None]
    composite = (sum(z_valid) / len(z_valid) if z_valid else 0.0) + rank_bonus

    n_soloq = perf.games if perf else 0
    low_sample = (
        n_soloq < _MIN_SOLOQ_GAMES
        or dist.n_players < _MIN_LEAGUE_PLAYERS
    )

    return HiddenGemScore(
        score=composite,
        z_scores=z_scores,
        rank_tier=rank.tier if rank else None,
        rank_division=rank.division if rank else None,
        rank_lp=rank.lp if rank else None,
        rank_bonus=rank_bonus,
        n_games_soloq=n_soloq,
        n_players_league=dist.n_players,
        low_sample=low_sample,
    )


def score_many(
    provider: SoloQProvider,
    players: Sequence[dict[str, Any]],
    *,
    league: str,
    role: str | None = None,
    n_recent: int = 20,
) -> list[tuple[dict[str, Any], HiddenGemScore | None]]:
    """Score'uje wielu graczy używając jednego rozkładu ligi (1 fetch Cargo).

    `players` — sequence dictów z minimum `{riot_id, region}`. Reszta pól
    (nick, drużyna, rola, ...) przekazywana 1:1 w wyniku — UI dostaje
    od razu wzbogacony rekord do tabeli.

    Zwrot posortowany malejąco po score'ie: hidden gems na górze, gracze
    bez danych soloQ na dole (score=None).
    """
    dist = compute_league_distribution(league, role)
    out: list[tuple[dict[str, Any], HiddenGemScore | None]] = []
    for p in players:
        if "riot_id" not in p or "region" not in p:
            raise ValueError(
                f"score_many: każdy gracz wymaga riot_id + region; brak w {p!r}"
            )
        score = score_player(
            provider,
            riot_id=p["riot_id"],
            region=p["region"],
            league=league,
            role=role,
            n_recent=n_recent,
            league_distribution=dist,
        )
        out.append((p, score))
    out.sort(
        key=lambda pair: pair[1].score if pair[1] is not None else float("-inf"),
        reverse=True,
    )
    return out


# --- Helpers ---------------------------------------------------------------

def _z(value: float | None, dist: MetricDist) -> float | None:
    """Z-score albo None, gdy brak wartości / STD / kohorty."""
    if value is None or dist.mean is None or dist.std is None or dist.std == 0:
        return None
    return (value - dist.mean) / dist.std


# --- Demo ------------------------------------------------------------------

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    from .soloq import RiotProvider

    print("== compute_league_distribution('LFL', role='Mid') ==")
    dist = compute_league_distribution("LFL", role="Mid")
    print(dist)

    try:
        riot = RiotProvider()
        print("\n== score_player (Caps#EUW vs LEC Mid) ==")
        score = score_player(
            riot,
            riot_id="Caps#EUW",
            region="euw1",
            league="LEC",
            role="Mid",
        )
        print(score)

        print("\n== score_many (mini batch) ==")
        results = score_many(
            riot,
            players=[
                {"nick": "Caps",  "riot_id": "Caps#EUW",  "region": "euw1"},
                {"nick": "Humanoid", "riot_id": "Humanoid#EUW", "region": "euw1"},
            ],
            league="LEC",
            role="Mid",
        )
        for player, sc in results:
            print(f"  {player['nick']:12s} -> {sc}")
    except RuntimeError as exc:
        print(f"[Riot pominięty] {exc}")
