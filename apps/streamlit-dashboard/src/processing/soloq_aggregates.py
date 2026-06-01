"""
src/processing/soloq_aggregates.py

Per-champion and per-role aggregation of SoloQ matches.

Counterpart to `champion_stats.py` (which aggregates pro-play
ScoreboardRow rows from Leaguepedia) — this one aggregates `MatchStats`
objects produced by `compute_match_stats` from Riot Match-V5 payloads.
Lives in `src/processing/` because it is pure data shaping over a
typed input; no I/O, no Riot client.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Sequence

from shared.processing.match_stats import MatchStats


@dataclass(frozen=True, slots=True)
class SoloQChampionStat:
    """Per-champion aggregate across a list of MatchStats.

    Averages are per-game means (None values skipped), with the exception
    of `kda` which is computed from the averaged K/D/A — same rule as
    `champion_stats.ChampionStat` so the two tables read consistently.
    """
    champion: str
    games: int
    wins: int
    losses: int
    avg_kills: float
    avg_deaths: float
    avg_assists: float
    kda: float
    avg_cs: float
    avg_cs_per_min: float
    avg_dpm: float
    avg_gold_per_min: float
    avg_vision_per_min: float
    avg_kp: float | None

    @property
    def win_rate(self) -> float:
        return self.wins / self.games if self.games else 0.0


def aggregate_champions(
    stats: Sequence[MatchStats],
) -> list[SoloQChampionStat]:
    """Group a player's MatchStats by champion and compute summary stats.

    Sorted by games played (desc), then alphabetically — same convention
    as `aggregate_champion_stats`.
    """
    buckets: dict[str, list[MatchStats]] = defaultdict(list)
    for s in stats:
        if s.champion:
            buckets[s.champion].append(s)

    result: list[SoloQChampionStat] = []
    for champion, games in buckets.items():
        n = len(games)
        wins = sum(1 for g in games if g.win)
        avg_k = sum(g.kills for g in games) / n
        avg_d = sum(g.deaths for g in games) / n
        avg_a = sum(g.assists for g in games) / n
        avg_cs = sum(g.cs for g in games) / n
        avg_cspm = sum(g.cs_per_min for g in games) / n
        avg_dpm = sum(g.dpm for g in games) / n
        avg_gpm = sum(g.gold_per_min for g in games) / n
        avg_vpm = sum(g.vision_per_min for g in games) / n
        kda = (avg_k + avg_a) / max(avg_d, 1.0)

        kp_vals = [g.kp for g in games if g.kp is not None]
        avg_kp = round(sum(kp_vals) / len(kp_vals), 3) if kp_vals else None

        result.append(SoloQChampionStat(
            champion=champion,
            games=n,
            wins=wins,
            losses=n - wins,
            avg_kills=round(avg_k, 2),
            avg_deaths=round(avg_d, 2),
            avg_assists=round(avg_a, 2),
            kda=round(kda, 2),
            avg_cs=round(avg_cs, 1),
            avg_cs_per_min=round(avg_cspm, 2),
            avg_dpm=round(avg_dpm, 1),
            avg_gold_per_min=round(avg_gpm, 1),
            avg_vision_per_min=round(avg_vpm, 2),
            avg_kp=avg_kp,
        ))

    result.sort(key=lambda s: (-s.games, s.champion))
    return result


@dataclass(frozen=True, slots=True)
class RoleBreakdown:
    """How often a player played each role in the analyzed window."""
    role: str           # Riot's teamPosition: TOP/JUNGLE/MIDDLE/BOTTOM/UTILITY/UNKNOWN
    games: int
    wins: int

    @property
    def win_rate(self) -> float:
        return self.wins / self.games if self.games else 0.0


def aggregate_roles(stats: Sequence[MatchStats]) -> list[RoleBreakdown]:
    """Count games per role in the window — useful for off-role detection.

    Empty/None roles bucket as 'UNKNOWN' so the total always matches the
    input length.
    """
    buckets: dict[str, list[MatchStats]] = defaultdict(list)
    for s in stats:
        buckets[s.role or "UNKNOWN"].append(s)

    result = [
        RoleBreakdown(
            role=role,
            games=len(rows),
            wins=sum(1 for r in rows if r.win),
        )
        for role, rows in buckets.items()
    ]
    result.sort(key=lambda r: (-r.games, r.role))
    return result


def filter_matches_by_champion(
    matches: Sequence[MatchStats], champion: str,
) -> list[MatchStats]:
    """Subset of `matches` played on `champion` (exact championName match).

    Lets the SoloQ comparison restrict a player's window to one champion so
    off-champion games don't skew the averages (a mid main's pocket picks
    shouldn't muddy their signature-champion read).
    """
    return [m for m in matches if m.champion == champion]
