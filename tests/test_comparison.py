"""
tests/test_comparison.py

Unit tests for src/processing/comparison.py — the cohort comparison math
(percentiles, Z-scores, distribution stats). Pure functions, no I/O.

Runnable two ways, same as the rest of tests/:
  * pytest tests/test_comparison.py
  * python tests/test_comparison.py      (no pytest needed)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.processing.comparison import (
    COMPARABLE_METRICS,
    build_cohort_stats,
    compare_to_cohort,
)
from src.processing.match_stats import RecentPerformance


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _perf(**over) -> RecentPerformance:
    """A RecentPerformance with sane defaults; override any field by kwarg."""
    base = dict(
        games=10, wins=5, winrate=0.5, kda=3.0, cs_per_min=8.0, dpm=500.0,
        gold_per_min=400.0, damage_taken_per_min=200.0, vision_per_min=1.0,
        wards_per_min=0.5, kp=0.6, cs10=80.0, gd15=100.0, solo_kills=1.0,
        first_blood_rate=0.2,
    )
    base.update(over)
    return RecentPerformance(**base)


def _rows(metric: str, values) -> list[dict]:
    """Cohort baseline rows carrying a single varying metric."""
    return [{metric: v} for v in values]


# ---------------------------------------------------------------------------
# build_cohort_stats / distribution math
# ---------------------------------------------------------------------------

def test_build_cohort_stats_distribution():
    # [10,20,30,40]: mean 25, std sqrt(125)=11.180, p50=25, p25=17.5, p75=32.5
    stats = build_cohort_stats(_rows("kda", [10, 20, 30, 40]))["kda"]
    assert stats.n == 4
    assert stats.mean == 25.0
    assert stats.std == 11.18
    assert stats.median == 25.0
    assert stats.p25 == 17.5
    assert stats.p75 == 32.5
    print("PASS  test_build_cohort_stats_distribution")


def test_build_cohort_stats_single_value():
    stats = build_cohort_stats(_rows("kda", [42.0]))["kda"]
    assert stats.n == 1
    assert stats.mean == 42.0
    assert stats.std == 0.0                 # variance of one point is 0
    assert stats.median == 42.0
    assert stats.p25 == 42.0
    assert stats.p75 == 42.0
    print("PASS  test_build_cohort_stats_single_value")


def test_build_cohort_stats_empty():
    stats = build_cohort_stats([])["kda"]
    assert stats.n == 0
    assert stats.mean is None
    assert stats.std is None
    assert stats.median is None
    assert stats.p25 is None
    assert stats.p75 is None
    print("PASS  test_build_cohort_stats_empty")


def test_build_cohort_stats_skips_none_and_missing():
    rows = [{"kda": 3.0}, {"kda": None}, {}, {"kda": 5.0}]
    built = build_cohort_stats(rows)
    assert built["kda"].n == 2              # None + absent row dropped
    assert built["kda"].mean == 4.0
    # A metric that never appears yields an all-None (n=0) bucket.
    assert built["winrate"].n == 0
    assert built["winrate"].mean is None
    print("PASS  test_build_cohort_stats_skips_none_and_missing")


# ---------------------------------------------------------------------------
# compare_to_cohort — shape & metadata
# ---------------------------------------------------------------------------

def test_compare_preserves_metric_order_and_labels():
    results = compare_to_cohort(_perf(), _rows("winrate", [0.5]))
    assert [r.metric for r in results] == [m[0] for m in COMPARABLE_METRICS]
    assert [r.label for r in results] == [m[1] for m in COMPARABLE_METRICS]
    assert len(results) == len(COMPARABLE_METRICS)
    print("PASS  test_compare_preserves_metric_order_and_labels")


def test_compare_higher_is_better_flags():
    by = {r.metric: r for r in compare_to_cohort(_perf(), [])}
    assert by["winrate"].higher_is_better is True
    # damage_taken_per_min is neutral (tank vs assassin) → None, never colored.
    assert by["damage_taken_per_min"].higher_is_better is None
    print("PASS  test_compare_higher_is_better_flags")


# ---------------------------------------------------------------------------
# compare_to_cohort — Z-score & percentile
# ---------------------------------------------------------------------------

def test_compare_z_score_and_percentile():
    rows = _rows("winrate", [0.40, 0.50, 0.60, 0.70, 0.80])  # mean .6 std .141
    by = {r.metric: r for r in compare_to_cohort(_perf(winrate=0.70), rows)}
    wr = by["winrate"]
    assert wr.player_value == 0.70
    assert wr.cohort.mean == 0.60
    assert wr.cohort.std == 0.141
    assert wr.z_score == 0.71                # (0.70-0.60)/0.141
    assert wr.percentile == 80.0             # 4 of 5 values <= 0.70
    print("PASS  test_compare_z_score_and_percentile")


def test_compare_player_at_mean_is_zero_z():
    rows = _rows("winrate", [0.40, 0.50, 0.60, 0.70, 0.80])
    wr = {r.metric: r for r in compare_to_cohort(_perf(winrate=0.60), rows)}["winrate"]
    assert wr.z_score == 0.0
    assert wr.percentile == 60.0             # 3 of 5 values <= 0.60
    print("PASS  test_compare_player_at_mean_is_zero_z")


def test_compare_zero_std_gives_no_z_but_keeps_percentile():
    rows = _rows("winrate", [0.5, 0.5, 0.5])
    wr = {r.metric: r for r in compare_to_cohort(_perf(winrate=0.9), rows)}["winrate"]
    assert wr.cohort.std == 0.0
    assert wr.z_score is None                # divide-by-zero guarded
    assert wr.percentile == 100.0            # still well defined
    print("PASS  test_compare_zero_std_gives_no_z_but_keeps_percentile")


def test_compare_missing_player_value():
    rows = _rows("kda", [2.0, 3.0, 4.0])
    kda = {r.metric: r for r in compare_to_cohort(_perf(kda=None), rows)}["kda"]
    assert kda.player_value is None
    assert kda.z_score is None
    assert kda.percentile is None
    print("PASS  test_compare_missing_player_value")


def test_compare_empty_cohort():
    wr = {r.metric: r for r in compare_to_cohort(_perf(winrate=0.6), [])}["winrate"]
    assert wr.cohort.n == 0
    assert wr.z_score is None
    assert wr.percentile is None
    assert wr.player_value == 0.6            # player value survives empty cohort
    print("PASS  test_compare_empty_cohort")


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_build_cohort_stats_distribution()
    test_build_cohort_stats_single_value()
    test_build_cohort_stats_empty()
    test_build_cohort_stats_skips_none_and_missing()
    test_compare_preserves_metric_order_and_labels()
    test_compare_higher_is_better_flags()
    test_compare_z_score_and_percentile()
    test_compare_player_at_mean_is_zero_z()
    test_compare_zero_std_gives_no_z_but_keeps_percentile()
    test_compare_missing_player_value()
    test_compare_empty_cohort()
    print("\nAll tests passed.")
