"""
tests/test_match_ids.py

Unit tests for RiotClient match-id fetching and its cache-TTL plumbing:
  * fetch_match_ids caches each page with the short default TTL,
  * fetch_all_match_ids_since(archival=True) caches pages with the long
    archive TTL (so a baseline rebuild reuses the list across a run),
  * pagination stops on a short page and respects hard_cap.

The LolWatcher is mocked; a recording cache captures the TTL each page is
stored with. No live API, no pytest required.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# --- bootstrap: dołóż packages/shared do sys.path (monorepo) ---
_shared = next(
    a for a in Path(__file__).resolve().parents if (a / "packages" / "shared").is_dir()
) / "packages" / "shared"
if str(_shared) not in sys.path:
    sys.path.insert(0, str(_shared))


from shared.api.riot_client import (
    _MATCH_IDS_ARCHIVE_TTL,
    _MATCH_IDS_CACHE_TTL,
    RiotClient,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _RecordingCache:
    """A CacheStore that never hits (get→None) and records every set()."""

    def __init__(self):
        self.sets = []          # list of (key, value, ttl)

    def get(self, key):
        return None

    def set(self, key, value, ttl_seconds=None):
        self.sets.append((key, value, ttl_seconds))


def _client(matchlist_return):
    """RiotClient with a mocked match.matchlist_by_puuid and recording cache."""
    client = RiotClient.__new__(RiotClient)
    client._cache = _RecordingCache()
    client._riot = MagicMock()

    mock_lol = MagicMock()
    # Accept a callable (per-call) or a fixed list.
    if callable(matchlist_return):
        mock_lol.match.matchlist_by_puuid.side_effect = matchlist_return
    else:
        mock_lol.match.matchlist_by_puuid.return_value = matchlist_return
    client._lol = mock_lol
    return client


# ---------------------------------------------------------------------------
# fetch_match_ids — TTL
# ---------------------------------------------------------------------------

def test_fetch_match_ids_default_ttl():
    client = _client(["EUW1_1", "EUW1_2"])
    ids = client.fetch_match_ids("puuid", "euw1", count=20, start_time=123)
    assert ids == ["EUW1_1", "EUW1_2"]
    assert client._cache.sets[-1][2] == _MATCH_IDS_CACHE_TTL
    print("PASS  test_fetch_match_ids_default_ttl")


def test_fetch_match_ids_explicit_ttl():
    client = _client(["EUW1_1"])
    client.fetch_match_ids("puuid", "euw1", start_time=123, cache_ttl=4242)
    assert client._cache.sets[-1][2] == 4242
    print("PASS  test_fetch_match_ids_explicit_ttl")


# ---------------------------------------------------------------------------
# fetch_all_match_ids_since — archival TTL & pagination
# ---------------------------------------------------------------------------

def test_archival_caches_pages_with_long_ttl():
    client = _client(["EUW1_1", "EUW1_2"])   # 2 < page_size → single page
    ids = client.fetch_all_match_ids_since(
        "puuid", "euw1", since_epoch=123, page_size=100, archival=True,
    )
    assert ids == ["EUW1_1", "EUW1_2"]
    ttls = [ttl for _, _, ttl in client._cache.sets]
    assert ttls and all(t == _MATCH_IDS_ARCHIVE_TTL for t in ttls)
    print("PASS  test_archival_caches_pages_with_long_ttl")


def test_non_archival_uses_short_ttl():
    client = _client(["EUW1_1"])
    client.fetch_all_match_ids_since(
        "puuid", "euw1", since_epoch=123, page_size=100,
    )
    ttls = [ttl for _, _, ttl in client._cache.sets]
    assert ttls and all(t == _MATCH_IDS_CACHE_TTL for t in ttls)
    print("PASS  test_non_archival_uses_short_ttl")


def test_pagination_stops_on_short_page_and_respects_hard_cap():
    # First call returns a full page, second a short page → stop after two.
    pages = [[f"M{i}" for i in range(100)], ["M100", "M101"]]
    client = _client(lambda *a, **k: pages.pop(0))
    ids = client.fetch_all_match_ids_since(
        "puuid", "euw1", since_epoch=123, page_size=100, hard_cap=1000,
    )
    assert len(ids) == 102
    assert client._lol.match.matchlist_by_puuid.call_count == 2

    # hard_cap truncates the collected list.
    client2 = _client([f"M{i}" for i in range(100)])
    capped = client2.fetch_all_match_ids_since(
        "puuid", "euw1", since_epoch=123, page_size=100, hard_cap=50,
    )
    assert len(capped) == 50
    print("PASS  test_pagination_stops_on_short_page_and_respects_hard_cap")


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_fetch_match_ids_default_ttl()
    test_fetch_match_ids_explicit_ttl()
    test_archival_caches_pages_with_long_ttl()
    test_non_archival_uses_short_ttl()
    test_pagination_stops_on_short_page_and_respects_hard_cap()
    print("\nAll tests passed.")
