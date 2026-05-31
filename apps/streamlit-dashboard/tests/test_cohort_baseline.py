"""
tests/test_cohort_baseline.py

Unit tests for src/processing/cohort_baseline.py — the per-account
baseline orchestration and its role-normalization helpers.

The Riot API boundary is mocked (a MagicMock RiotClient), and the
match-reduction functions (compute_match_stats / aggregate_recent, tested
in their own module) are patched out, so these tests isolate the
orchestration's status machine and row assembly.

Runnable two ways, same as the rest of tests/:
  * pytest tests/test_cohort_baseline.py
  * python tests/test_cohort_baseline.py      (no pytest needed)
"""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# --- bootstrap: dołóż packages/shared do sys.path (monorepo) ---
_shared = next(
    a for a in Path(__file__).resolve().parents if (a / "packages" / "shared").is_dir()
) / "packages" / "shared"
if str(_shared) not in sys.path:
    sys.path.insert(0, str(_shared))


from src.processing import cohort_baseline as cb
from src.processing.cohort_baseline import compute_account_baseline
from shared.processing.match_stats import MatchStats, RecentPerformance


# ---------------------------------------------------------------------------
# Fixtures / factories
# ---------------------------------------------------------------------------

def _account(puuid="puuid-1", level=300):
    return SimpleNamespace(puuid=puuid, summoner_level=level)


def _ranked(games=150, queue="RANKED_SOLO_5x5", tier="DIAMOND", rank="II", lp=50):
    return SimpleNamespace(
        queue_type=queue, games=games, tier=tier, rank=rank, lp=lp,
    )


def _client():
    """A RiotClient mock primed for the happy path; tweak per test."""
    c = MagicMock()
    c.resolve_account.return_value = _account()
    c.fetch_ranked.return_value = [_ranked()]
    c.fetch_all_match_ids_since.return_value = ["EUW1_1", "EUW1_2"]
    c.fetch_match.return_value = {"sentinel": True}
    c.fetch_match_timeline.return_value = None
    return c


def _call(client, **over):
    kwargs = dict(
        overview_page="Faker",
        game_name="Hide on bush",
        tag_line="KR1",
        platform="kr",
        league="LCK",
        role_hint="Mid",
        since_epoch=1_700_000_000,
        riot_client=client,
        include_timeline=False,
        min_season_games=100,
        max_matches=200,
    )
    kwargs.update(over)
    return compute_account_baseline(**kwargs)


def _matchstats(**over) -> MatchStats:
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


def _recent(**over) -> RecentPerformance:
    base = dict(
        games=2, wins=1, winrate=0.5, kda=3.0, cs_per_min=8.0, dpm=500.0,
        gold_per_min=400.0, damage_taken_per_min=200.0, vision_per_min=1.0,
        wards_per_min=0.5, kp=0.6, cs10=80.0, gd15=100.0, solo_kills=1.0,
        first_blood_rate=0.5,
    )
    base.update(over)
    return RecentPerformance(**base)


# ---------------------------------------------------------------------------
# Status machine — failure / skip branches (no patching needed)
# ---------------------------------------------------------------------------

def test_no_account_on_lookup_error():
    c = _client()
    c.resolve_account.side_effect = LookupError
    out = _call(c)
    assert out.status == "no_account"
    assert out.row is None
    print("PASS  test_no_account_on_lookup_error")


def test_error_on_resolve_exception():
    c = _client()
    c.resolve_account.side_effect = RuntimeError("boom")
    out = _call(c)
    assert out.status == "error"
    assert out.error.startswith("resolve:")
    print("PASS  test_error_on_resolve_exception")


def test_error_on_ranked_exception():
    c = _client()
    c.fetch_ranked.side_effect = RuntimeError("rip")
    out = _call(c)
    assert out.status == "error"
    assert out.error.startswith("ranked:")
    print("PASS  test_error_on_ranked_exception")


def test_skipped_when_below_min_games():
    c = _client()
    c.fetch_ranked.return_value = [_ranked(games=42)]
    out = _call(c, min_season_games=100)
    assert out.status == "skipped"
    assert "42" in out.error
    print("PASS  test_skipped_when_below_min_games")


def test_skipped_when_no_soloq_entry():
    c = _client()
    c.fetch_ranked.return_value = [_ranked(queue="RANKED_FLEX_SR", games=999)]
    out = _call(c)
    assert out.status == "skipped"          # no SoloQ entry → season_games 0
    print("PASS  test_skipped_when_no_soloq_entry")


def test_error_on_match_ids_exception():
    c = _client()
    c.fetch_all_match_ids_since.side_effect = RuntimeError("x")
    out = _call(c)
    assert out.status == "error"
    assert out.error.startswith("match_ids:")
    print("PASS  test_error_on_match_ids_exception")


def test_no_matches_when_empty_ids():
    c = _client()
    c.fetch_all_match_ids_since.return_value = []
    out = _call(c)
    assert out.status == "no_matches"
    assert out.row is None
    print("PASS  test_no_matches_when_empty_ids")


def test_no_matches_when_all_stats_none():
    c = _client()
    with patch.object(cb, "compute_match_stats", return_value=None):
        out = _call(c)
    assert out.status == "no_matches"       # every match reduced to None
    print("PASS  test_no_matches_when_all_stats_none")


# ---------------------------------------------------------------------------
# Happy path — row assembly
# ---------------------------------------------------------------------------

def test_ok_builds_row():
    c = _client()
    c.fetch_all_match_ids_since.return_value = ["A", "B"]
    summary = _recent()
    with patch.object(cb, "compute_match_stats",
                      return_value=_matchstats(role="MIDDLE")), \
         patch.object(cb, "aggregate_recent", return_value=summary):
        out = _call(c, role_hint="Top")

    assert out.status == "ok"
    assert out.matches_fetched == 2
    row = out.row
    assert row["overview_page"] == "Faker"
    assert row["puuid"] == "puuid-1"
    assert row["game_name"] == "Hide on bush"
    assert row["tag_line"] == "KR1"
    assert row["platform"] == "kr"
    assert row["league"] == "LCK"
    assert row["role"] == "Mid"             # dominant MIDDLE wins over role_hint
    assert row["games"] == summary.games
    assert row["kda"] == summary.kda
    assert row["winrate"] == summary.winrate
    assert row["tier"] == "DIAMOND"
    assert row["rank"] == "II"
    assert row["lp"] == 50
    assert row["payload"]["season_games_total"] == 150
    assert row["payload"]["summoner_level"] == 300
    print("PASS  test_ok_builds_row")


def test_ok_role_hint_fallback_when_no_dominant_role():
    c = _client()
    with patch.object(cb, "compute_match_stats",
                      return_value=_matchstats(role=None)), \
         patch.object(cb, "aggregate_recent", return_value=_recent()):
        out = _call(c, role_hint="Support")
    assert out.status == "ok"
    assert out.row["role"] == "Support"     # no dominant role → normalized hint
    print("PASS  test_ok_role_hint_fallback_when_no_dominant_role")


def test_on_match_callback_invoked_per_match():
    c = _client()
    c.fetch_all_match_ids_since.return_value = ["A", "B", "C"]
    calls = []
    with patch.object(cb, "compute_match_stats", return_value=_matchstats()), \
         patch.object(cb, "aggregate_recent", return_value=_recent()):
        _call(c, on_match=lambda i, n: calls.append((i, n)))
    assert calls == [(1, 3), (2, 3), (3, 3)]
    print("PASS  test_on_match_callback_invoked_per_match")


def test_baseline_requests_archival_match_id_cache():
    # The baseline rebuilds over a fixed season cutoff, so it must ask the
    # client to cache the match-id list with the long archive TTL.
    c = _client()
    with patch.object(cb, "compute_match_stats", return_value=_matchstats()), \
         patch.object(cb, "aggregate_recent", return_value=_recent()):
        _call(c)
    _, kwargs = c.fetch_all_match_ids_since.call_args
    assert kwargs.get("archival") is True
    print("PASS  test_baseline_requests_archival_match_id_cache")


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def test_normalize_role_mapping():
    assert cb._normalize_role(None) is None
    assert cb._normalize_role("TOP") == "Top"
    assert cb._normalize_role("top") == "Top"
    assert cb._normalize_role(" middle ") == "Mid"
    assert cb._normalize_role("MID") == "Mid"
    assert cb._normalize_role("BOTTOM") == "Bot"
    assert cb._normalize_role("ADC") == "Bot"
    assert cb._normalize_role("UTILITY") == "Support"
    assert cb._normalize_role("SUPPORT") == "Support"
    assert cb._normalize_role("Flex") == "Flex"     # unknown → passthrough
    print("PASS  test_normalize_role_mapping")


def test_dominant_role():
    stats = [
        _matchstats(role="MIDDLE"), _matchstats(role="MIDDLE"),
        _matchstats(role="TOP"),
    ]
    assert cb._dominant_role(stats) == "Mid"        # most common, normalized
    assert cb._dominant_role([]) is None
    assert cb._dominant_role(
        [_matchstats(role=None), _matchstats(role=None)]
    ) is None                                       # all blank → None
    print("PASS  test_dominant_role")


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_no_account_on_lookup_error()
    test_error_on_resolve_exception()
    test_error_on_ranked_exception()
    test_skipped_when_below_min_games()
    test_skipped_when_no_soloq_entry()
    test_error_on_match_ids_exception()
    test_no_matches_when_empty_ids()
    test_no_matches_when_all_stats_none()
    test_ok_builds_row()
    test_ok_role_hint_fallback_when_no_dominant_role()
    test_on_match_callback_invoked_per_match()
    test_baseline_requests_archival_match_id_cache()
    test_normalize_role_mapping()
    test_dominant_role()
    print("\nAll tests passed.")
