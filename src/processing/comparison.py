"""
src/processing/comparison.py

Porównanie pojedynczego gracza do kohorty baseline.

Wejście: lista wpisów baseline (dictów z draft_analyzer/db.fetch_soloq_baseline)
i obiekt RecentPerformance gracza, którego chcemy porównać. Wyjście:
dict metryka → ComparisonResult (wartość gracza, średnia kohorty, percentyl,
Z-score).

Lives in `src/processing/` per CLAUDE.md — cross-league normalization
(percentyle, Z-score) musi siedzieć tu, nie w api/ ani w app/.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

from src.processing.match_stats import RecentPerformance


# Metryki, po których porównujemy gracza vs kohorta. Wszystkie liczbowe
# (None jest pomijany w aggregacji). Kolejność = kolejność w UI.
#
# Każda krotka: (klucz, etykieta, większe-lepsze).
# 'damage_taken_per_min' jest neutralne (tank weźmie więcej, asasyn mniej)
# — oznaczamy None, UI rysuje bez kolorowania kierunku.
COMPARABLE_METRICS: list[tuple[str, str, bool | None]] = [
    ("winrate",              "Win rate",       True),
    ("kda",                  "KDA",            True),
    ("kp",                   "KP",             True),
    ("cs_per_min",           "CS/min",         True),
    ("gold_per_min",         "Gold/min",       True),
    ("dpm",                  "DPM",            True),
    ("damage_taken_per_min", "Dmg taken/min",  None),
    ("vision_per_min",       "Vision/min",     True),
    ("wards_per_min",        "Wards/min",      True),
    ("cs10",                 "CS@10",          True),
    ("gd15",                 "GD@15",          True),
    ("solo_kills",           "Solo kills",     True),
    ("first_blood_rate",     "FB rate",        True),
]


@dataclass(frozen=True, slots=True)
class CohortMetricStats:
    """Rozkład jednej metryki w kohorcie."""
    n: int
    mean: float | None
    std: float | None
    median: float | None
    p25: float | None
    p75: float | None


@dataclass(frozen=True, slots=True)
class ComparisonResult:
    """Wynik porównania jednej metryki: gracz vs kohorta."""
    metric: str
    label: str
    higher_is_better: bool | None
    player_value: float | None
    cohort: CohortMetricStats
    percentile: float | None      # 0-100, względem rozkładu kohorty
    z_score: float | None


def build_cohort_stats(
    baseline_rows: Sequence[dict],
) -> dict[str, CohortMetricStats]:
    """Z listy wierszy baseline buduje dict metryka → CohortMetricStats.

    Wiersz baseline to jeden gracz/konto/cutoff (zob. soloq_baseline w db.py).
    `payload` (JSON) jest opcjonalny i obecnie nieużywany — bierzemy
    standardowe kolumny.

    Konta z `games < 100` powinny być odfiltrowane PRZED wejściem tu —
    ten moduł nic nie wie o sezonowych progach, tylko sumuje co dostanie.
    """
    out: dict[str, CohortMetricStats] = {}
    for key, _label, _ in COMPARABLE_METRICS:
        values = [
            r.get(key) for r in baseline_rows
            if r.get(key) is not None
        ]
        out[key] = _metric_stats([float(v) for v in values])
    return out


def compare_to_cohort(
    perf: RecentPerformance,
    baseline_rows: Sequence[dict],
) -> list[ComparisonResult]:
    """Porównuje `perf` do rozkładu kohorty `baseline_rows`.

    Zwraca po jednym ComparisonResult na metrykę z COMPARABLE_METRICS
    (kolejność zachowana). Brak danych w kohorcie ALBO u gracza →
    percentile=None, z_score=None (UI pokazuje wtedy „—").
    """
    cohort = build_cohort_stats(baseline_rows)
    out: list[ComparisonResult] = []
    for key, label, higher in COMPARABLE_METRICS:
        stats = cohort[key]
        player_value = getattr(perf, key, None)
        percentile = _percentile_of(player_value, baseline_rows, key)
        z_score = _z_score(player_value, stats)
        out.append(ComparisonResult(
            metric=key,
            label=label,
            higher_is_better=higher,
            player_value=(
                float(player_value) if player_value is not None else None
            ),
            cohort=stats,
            percentile=percentile,
            z_score=z_score,
        ))
    return out


# --- Helpers ---------------------------------------------------------------

def _metric_stats(values: list[float]) -> CohortMetricStats:
    n = len(values)
    if n == 0:
        return CohortMetricStats(
            n=0, mean=None, std=None, median=None, p25=None, p75=None,
        )
    sorted_vals = sorted(values)
    mean = sum(sorted_vals) / n
    var = sum((v - mean) ** 2 for v in sorted_vals) / n
    std = math.sqrt(var)
    return CohortMetricStats(
        n=n,
        mean=round(mean, 3),
        std=round(std, 3) if std > 0 else 0.0,
        median=round(_percentile(sorted_vals, 50), 3),
        p25=round(_percentile(sorted_vals, 25), 3),
        p75=round(_percentile(sorted_vals, 75), 3),
    )


def _percentile(sorted_values: list[float], p: float) -> float:
    """Percentyl linearną interpolacją (jak numpy.percentile method='linear').

    `sorted_values` musi być posortowane rosnąco. `p` w zakresie 0-100.
    """
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    k = (p / 100.0) * (len(sorted_values) - 1)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_values[int(k)]
    return (
        sorted_values[f] * (c - k) + sorted_values[c] * (k - f)
    )


def _percentile_of(
    value: float | None,
    baseline_rows: Sequence[dict],
    key: str,
) -> float | None:
    """Jaki procent kohorty ma wynik mniejszy-równy niż `value`.

    Zwraca None gdy brak danych. Wartość 50 = mediana, 95 = top 5%.
    """
    if value is None:
        return None
    values = [
        r.get(key) for r in baseline_rows
        if r.get(key) is not None
    ]
    if not values:
        return None
    le = sum(1 for v in values if v <= value)
    return round(100 * le / len(values), 1)


def _z_score(
    value: float | None,
    stats: CohortMetricStats,
) -> float | None:
    if value is None or stats.mean is None or not stats.std:
        return None
    return round((value - stats.mean) / stats.std, 2)
