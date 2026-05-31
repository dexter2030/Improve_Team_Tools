"""
src/processing/champion_stats.py

Aggregates raw `ScoreboardPlayers` rows into per-champion statistics.

This module lives in `src/processing/` — its job is to turn the api/-layer's
flat list of per-game rows (one row = one game played) into the derived,
human-readable champion pool summary a scout actually reads.

Cross-league Z-score comparisons are *not* done here; that belongs in a
future normalization module. `aggregate_champion_stats` is purely about
one player's own numbers.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Sequence

from shared.api.leaguepedia_client import ScoreboardRow


@dataclass(frozen=True, slots=True)
class ChampionStat:
    """Aggregated statistics for one champion across all recorded games.

    All `avg_*` fields are per-game means. `kda` uses the standard
    formula (K + A) / max(D, 1) applied to the *averages*, so a player
    with 0.0 average deaths gets the theoretically maximum finite KDA
    of (avg_kills + avg_assists) / 1.
    """
    champion: str
    games: int
    wins: int
    losses: int
    avg_kills: float
    avg_deaths: float
    avg_assists: float
    avg_cs: float
    kda: float

    @property
    def win_rate(self) -> float:
        return self.wins / self.games if self.games else 0.0


def aggregate_champion_stats(
    rows: Sequence[ScoreboardRow],
) -> list[ChampionStat]:
    """Group raw scoreboard rows by champion and compute summary stats.

    Args:
        rows: Per-game rows from `LeaguepediaClient.get_player_scoreboard`.

    Returns:
        One `ChampionStat` per champion, sorted by games played (desc),
        then alphabetically by champion name. Empty input → empty list.
    """
    buckets: dict[str, list[ScoreboardRow]] = defaultdict(list)
    for row in rows:
        if row.champion:
            buckets[row.champion].append(row)

    result: list[ChampionStat] = []
    for champion, champ_rows in buckets.items():
        n = len(champ_rows)
        wins = sum(1 for r in champ_rows if r.win)
        avg_k = sum(r.kills for r in champ_rows) / n
        avg_d = sum(r.deaths for r in champ_rows) / n
        avg_a = sum(r.assists for r in champ_rows) / n
        avg_cs = sum(r.cs for r in champ_rows) / n
        kda = (avg_k + avg_a) / max(avg_d, 1.0)
        result.append(ChampionStat(
            champion=champion,
            games=n,
            wins=wins,
            losses=n - wins,
            avg_kills=round(avg_k, 2),
            avg_deaths=round(avg_d, 2),
            avg_assists=round(avg_a, 2),
            avg_cs=round(avg_cs, 1),
            kda=round(kda, 2),
        ))

    result.sort(key=lambda s: (-s.games, s.champion))
    return result
