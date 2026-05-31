"""
tests/test_soloq_aggregates.py

Unit tests for src/processing/soloq_aggregates.py — per-champion and
per-role aggregation of MatchStats. Pure functions, no I/O.

Runnable two ways, same as the rest of tests/:
  * pytest tests/test_soloq_aggregates.py
  * python tests/test_soloq_aggregates.py      (no pytest needed)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.processing.match_stats import MatchStats
from src.processing.soloq_aggregates import (
    RoleBreakdown,
    aggregate_champions,
    aggregate_roles,
    filter_matches_by_champion,
)


# ---------------------------------------------------------------------------
# Helper — build a MatchStats with defaults; override any field by kwarg.
# ---------------------------------------------------------------------------

def _ms(**over) -> MatchStats:
    base = dict(
        match_id="m", win=True, champion="Ahri", role="MIDDLE",
        kills=5, deaths=2, assists=7, kda=6.0, cs=200, cs_per_min=8.0,
        dpm=500.0, gold_per_min=400.0, damage_taken_per_min=200.0,
        vision_score=30, vision_per_min=1.2, wards_placed=12, wards_killed=4,
        control_wards_bought=3, solo_kills=1, first_blood_kill=False,
        first_blood_assist=False, kp=0.6, cs10=80, gd15=100,
        duration_min=25.0, queue_id=420,
    )
    base.update(over)
    return MatchStats(**base)


# ---------------------------------------------------------------------------
# aggregate_champions
# ---------------------------------------------------------------------------

def test_aggregate_champions_empty():
    assert aggregate_champions([]) == []
    print("PASS  test_aggregate_champions_empty")


def test_aggregate_champions_groups_and_sorts_by_games():
    stats = aggregate_champions([
        _ms(champion="Azir"), _ms(champion="Azir"), _ms(champion="Azir"),
        _ms(champion="Orianna"), _ms(champion="Orianna"),
    ])
    assert [s.champion for s in stats] == ["Azir", "Orianna"]
    assert stats[0].games == 3
    assert stats[1].games == 2
    print("PASS  test_aggregate_champions_groups_and_sorts_by_games")


def test_aggregate_champions_alphabetical_tiebreak():
    stats = aggregate_champions([_ms(champion="Zed"), _ms(champion="Akali")])
    assert [s.champion for s in stats] == ["Akali", "Zed"]
    print("PASS  test_aggregate_champions_alphabetical_tiebreak")


def test_aggregate_champions_skips_blank_champion():
    stats = aggregate_champions([_ms(champion="Ahri"), _ms(champion="")])
    assert len(stats) == 1
    assert stats[0].champion == "Ahri"
    assert stats[0].games == 1
    print("PASS  test_aggregate_champions_skips_blank_champion")


def test_aggregate_champions_averages_and_kda():
    games = [
        _ms(champion="Azir", win=True,  kills=5, deaths=2, assists=8,
            cs=280, cs_per_min=9.0),
        _ms(champion="Azir", win=False, kills=3, deaths=4, assists=6,
            cs=260, cs_per_min=8.0),
        _ms(champion="Azir", win=True,  kills=7, deaths=1, assists=10,
            cs=300, cs_per_min=10.0),
    ]
    s = aggregate_champions(games)[0]
    assert s.games == 3
    assert s.wins == 2
    assert s.losses == 1
    assert abs(s.win_rate - 2 / 3) < 1e-9
    assert s.avg_kills == round(15 / 3, 2)       # 5.0
    assert s.avg_deaths == round(7 / 3, 2)       # 2.33
    assert s.avg_assists == round(24 / 3, 2)     # 8.0
    assert s.avg_cs == round(840 / 3, 1)         # 280.0
    assert s.avg_cs_per_min == round(27 / 3, 2)  # 9.0
    # KDA uses the averaged K/D/A (not per-game KDA), then rounds to 2dp.
    raw_avg_d = 7 / 3
    assert s.kda == round((5.0 + 8.0) / max(raw_avg_d, 1.0), 2)
    print("PASS  test_aggregate_champions_averages_and_kda")


def test_aggregate_champions_zero_deaths_kda():
    s = aggregate_champions(
        [_ms(champion="Thresh", kills=0, deaths=0, assists=10)]
    )[0]
    assert s.kda == 10.0                          # (0+10) / max(0, 1.0)
    print("PASS  test_aggregate_champions_zero_deaths_kda")


def test_aggregate_champions_kp_none_when_all_missing():
    s = aggregate_champions(
        [_ms(champion="Ahri", kp=None), _ms(champion="Ahri", kp=None)]
    )[0]
    assert s.avg_kp is None
    print("PASS  test_aggregate_champions_kp_none_when_all_missing")


def test_aggregate_champions_kp_skips_none():
    s = aggregate_champions([
        _ms(champion="Ahri", kp=0.5),
        _ms(champion="Ahri", kp=None),
        _ms(champion="Ahri", kp=0.7),
    ])[0]
    assert s.games == 3                           # all three count as games
    assert s.avg_kp == round((0.5 + 0.7) / 2, 3)  # but kp averages the 2 present
    print("PASS  test_aggregate_champions_kp_skips_none")


# ---------------------------------------------------------------------------
# aggregate_roles
# ---------------------------------------------------------------------------

def test_aggregate_roles_empty():
    assert aggregate_roles([]) == []
    print("PASS  test_aggregate_roles_empty")


def test_aggregate_roles_counts_and_sorts():
    stats = aggregate_roles([
        _ms(role="MIDDLE", win=True), _ms(role="MIDDLE", win=False),
        _ms(role="TOP", win=True),
    ])
    by = {r.role: r for r in stats}
    assert by["MIDDLE"].games == 2
    assert by["MIDDLE"].wins == 1
    assert by["TOP"].games == 1
    assert by["TOP"].wins == 1
    assert [r.role for r in stats] == ["MIDDLE", "TOP"]   # games desc
    print("PASS  test_aggregate_roles_counts_and_sorts")


def test_aggregate_roles_blank_and_none_bucket_unknown():
    stats = aggregate_roles([_ms(role=None), _ms(role="")])
    by = {r.role: r for r in stats}
    assert by["UNKNOWN"].games == 2
    # Total must always equal input length (no game silently dropped).
    assert sum(r.games for r in stats) == 2
    print("PASS  test_aggregate_roles_blank_and_none_bucket_unknown")


def test_aggregate_roles_win_rate():
    stats = aggregate_roles([
        _ms(role="TOP", win=True), _ms(role="TOP", win=True),
        _ms(role="TOP", win=False),
    ])
    assert abs(stats[0].win_rate - 2 / 3) < 1e-9
    print("PASS  test_aggregate_roles_win_rate")


def test_role_breakdown_zero_games_win_rate():
    assert RoleBreakdown(role="X", games=0, wins=0).win_rate == 0.0
    print("PASS  test_role_breakdown_zero_games_win_rate")


# ---------------------------------------------------------------------------
# filter_matches_by_champion
# ---------------------------------------------------------------------------

def test_filter_matches_by_champion():
    ms = [_ms(champion="Ahri"), _ms(champion="Yasuo"), _ms(champion="Ahri")]
    out = filter_matches_by_champion(ms, "Ahri")
    assert len(out) == 2
    assert all(m.champion == "Ahri" for m in out)
    assert filter_matches_by_champion(ms, "Zed") == []      # no games on it
    assert filter_matches_by_champion([], "Ahri") == []     # empty input
    print("PASS  test_filter_matches_by_champion")


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_aggregate_champions_empty()
    test_aggregate_champions_groups_and_sorts_by_games()
    test_aggregate_champions_alphabetical_tiebreak()
    test_aggregate_champions_skips_blank_champion()
    test_aggregate_champions_averages_and_kda()
    test_aggregate_champions_zero_deaths_kda()
    test_aggregate_champions_kp_none_when_all_missing()
    test_aggregate_champions_kp_skips_none()
    test_aggregate_roles_empty()
    test_aggregate_roles_counts_and_sorts()
    test_aggregate_roles_blank_and_none_bucket_unknown()
    test_aggregate_roles_win_rate()
    test_role_breakdown_zero_games_win_rate()
    test_filter_matches_by_champion()
    print("\nAll tests passed.")
