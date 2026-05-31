"""
tests/test_ranked.py

Unit tests for RiotClient.fetch_ranked (League-V4 by_puuid).
Uses a mock site to avoid hitting the live API.
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


from shared.api.riot_client import RankedEntry, RiotClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FAKE_PUUID = "abc123-puuid-for-testing"
_PLATFORM = "euw1"

_SOLO_ENTRY = {
    "queueType": "RANKED_SOLO_5x5",
    "tier": "DIAMOND",
    "rank": "II",
    "leaguePoints": 74,
    "wins": 120,
    "losses": 100,
}
_FLEX_ENTRY = {
    "queueType": "RANKED_FLEX_SR",
    "tier": "PLATINUM",
    "rank": "I",
    "leaguePoints": 20,
    "wins": 40,
    "losses": 38,
}


def _make_client(league_response):
    """Build a RiotClient whose LolWatcher.league.by_puuid returns the given list."""
    client = RiotClient.__new__(RiotClient)
    client._cache = None

    mock_lol = MagicMock()
    mock_lol.league.by_puuid.return_value = league_response
    client._lol = mock_lol

    mock_riot = MagicMock()
    client._riot = mock_riot

    return client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_fetch_ranked_two_queues():
    client = _make_client([_SOLO_ENTRY, _FLEX_ENTRY])
    entries = client.fetch_ranked(_FAKE_PUUID, _PLATFORM)

    assert len(entries) == 2
    soloq = next(e for e in entries if e.queue_type == "RANKED_SOLO_5x5")
    flex  = next(e for e in entries if e.queue_type == "RANKED_FLEX_SR")

    assert soloq.tier == "DIAMOND"
    assert soloq.rank == "II"
    assert soloq.lp == 74
    assert soloq.wins == 120
    assert soloq.losses == 100
    assert soloq.games == 220
    assert abs(soloq.win_rate - 120 / 220) < 1e-9

    assert flex.tier == "PLATINUM"
    assert flex.lp == 20

    client._lol.league.by_puuid.assert_called_once_with(_PLATFORM, _FAKE_PUUID)
    print("PASS  test_fetch_ranked_two_queues")


def test_fetch_ranked_unranked_empty_list():
    client = _make_client([])
    entries = client.fetch_ranked(_FAKE_PUUID, _PLATFORM)
    assert entries == []
    print("PASS  test_fetch_ranked_unranked_empty_list")


def test_fetch_ranked_404_returns_empty():
    from riotwatcher import ApiError
    import requests

    client = RiotClient.__new__(RiotClient)
    client._cache = None
    client._riot = MagicMock()

    # Build an ApiError with status_code 404
    resp = MagicMock()
    resp.status_code = 404
    http_err = requests.exceptions.HTTPError(response=resp)
    api_err = ApiError(http_err, request=MagicMock(), response=resp)

    mock_lol = MagicMock()
    mock_lol.league.by_puuid.side_effect = api_err
    client._lol = mock_lol

    entries = client.fetch_ranked(_FAKE_PUUID, _PLATFORM)
    assert entries == []
    print("PASS  test_fetch_ranked_404_returns_empty")


def test_ranked_entry_win_rate_zero_games():
    e = RankedEntry(
        queue_type="RANKED_SOLO_5x5",
        tier="GOLD", rank="IV", lp=0, wins=0, losses=0,
    )
    assert e.games == 0
    assert e.win_rate == 0.0
    print("PASS  test_ranked_entry_win_rate_zero_games")


def test_fetch_ranked_cache_roundtrip():
    """Second call should return from cache without hitting the API."""
    from shared.api.riot_client import SqliteCacheStore
    import tempfile, pathlib

    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "test.db"
        cache = SqliteCacheStore(db)

        client = _make_client([_SOLO_ENTRY])
        client._cache = cache

        first = client.fetch_ranked(_FAKE_PUUID, _PLATFORM)
        assert len(first) == 1
        assert client._lol.league.by_puuid.call_count == 1

        # Second call — should hit cache, not the mock
        second = client.fetch_ranked(_FAKE_PUUID, _PLATFORM)
        assert len(second) == 1
        assert client._lol.league.by_puuid.call_count == 1   # still 1

        assert first[0].tier == second[0].tier
        assert first[0].lp   == second[0].lp
    print("PASS  test_fetch_ranked_cache_roundtrip")


def test_fetch_ranked_invalid_platform():
    client = _make_client([])
    try:
        client.fetch_ranked(_FAKE_PUUID, "invalid_platform_xyz")
        assert False, "Expected ValueError"
    except ValueError:
        pass
    print("PASS  test_fetch_ranked_invalid_platform")


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_fetch_ranked_two_queues()
    test_fetch_ranked_unranked_empty_list()
    test_fetch_ranked_404_returns_empty()
    test_ranked_entry_win_rate_zero_games()
    test_fetch_ranked_cache_roundtrip()
    test_fetch_ranked_invalid_platform()
    print("\nAll tests passed.")
