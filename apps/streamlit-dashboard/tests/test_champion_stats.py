"""
tests/test_champion_stats.py

Unit tests for:
  * LeaguepediaClient.get_player_scoreboard  (api/ layer, mock site)
  * aggregate_champion_stats                 (processing/ layer, pure function)
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


from shared.api.leaguepedia_client import LeaguepediaClient, ScoreboardRow
from src.processing.champion_stats import ChampionStat, aggregate_champion_stats


# ---------------------------------------------------------------------------
# Helpers — build a LeaguepediaClient with a mocked mwclient.Site
# ---------------------------------------------------------------------------

def _make_client(cargo_rows: list[dict]) -> LeaguepediaClient:
    """Return a client whose _run_cargo is stubbed to return cargo_rows."""
    client = LeaguepediaClient.__new__(LeaguepediaClient)
    client._cache = None

    mock_site = MagicMock()
    mock_site.api.return_value = {
        "cargoquery": [{"title": row} for row in cargo_rows]
    }
    client._site = mock_site
    return client


# ---------------------------------------------------------------------------
# LeaguepediaClient.get_player_scoreboard
# ---------------------------------------------------------------------------

_RAW_ROWS = [
    {"GameId": "g1", "Champion": "Azir",    "Kills": "5", "Deaths": "2",
     "Assists": "8", "CS": "280", "PlayerWin": "Yes"},
    {"GameId": "g2", "Champion": "Azir",    "Kills": "3", "Deaths": "4",
     "Assists": "6", "CS": "260", "PlayerWin": "No"},
    {"GameId": "g3", "Champion": "Orianna", "Kills": "2", "Deaths": "1",
     "Assists": "10", "CS": "240", "PlayerWin": "Yes"},
]


def test_get_player_scoreboard_returns_rows():
    client = _make_client(_RAW_ROWS)
    rows = client.get_player_scoreboard("Faker")
    assert len(rows) == 3
    assert all(isinstance(r, ScoreboardRow) for r in rows)
    print("PASS  test_get_player_scoreboard_returns_rows")


def test_scoreboard_row_fields_parsed():
    client = _make_client(_RAW_ROWS)
    rows = {r.game_id: r for r in client.get_player_scoreboard("Faker")}

    g1 = rows["g1"]
    assert g1.champion == "Azir"
    assert g1.kills == 5
    assert g1.deaths == 2
    assert g1.assists == 8
    assert g1.cs == 280
    assert g1.win is True

    g2 = rows["g2"]
    assert g2.win is False
    print("PASS  test_scoreboard_row_fields_parsed")


def test_scoreboard_rows_without_champion_are_skipped():
    rows_with_gap = _RAW_ROWS + [
        {"GameId": "g9", "Champion": "", "Kills": "0", "Deaths": "0",
         "Assists": "0", "CS": "0", "PlayerWin": "Yes"}
    ]
    client = _make_client(rows_with_gap)
    rows = client.get_player_scoreboard("Faker")
    assert len(rows) == 3   # gap row dropped
    print("PASS  test_scoreboard_rows_without_champion_are_skipped")


def test_empty_link_returns_empty():
    client = _make_client(_RAW_ROWS)
    rows = client.get_player_scoreboard("")
    assert rows == []
    client._site.api.assert_not_called()
    print("PASS  test_empty_link_returns_empty")


def test_missing_numeric_fields_coerce_to_zero():
    client = _make_client([
        {"GameId": "g1", "Champion": "Lux", "Kills": None,
         "Deaths": "", "Assists": None, "CS": "150", "PlayerWin": "No"},
    ])
    rows = client.get_player_scoreboard("SomePlayer")
    assert len(rows) == 1
    r = rows[0]
    assert r.kills == 0
    assert r.deaths == 0
    assert r.assists == 0
    assert r.cs == 150
    print("PASS  test_missing_numeric_fields_coerce_to_zero")


def test_cache_prevents_second_api_call():
    import tempfile, pathlib
    from shared.api.riot_client import SqliteCacheStore

    with tempfile.TemporaryDirectory() as tmp:
        cache = SqliteCacheStore(pathlib.Path(tmp) / "test.db")
        client = _make_client(_RAW_ROWS)
        client._cache = cache

        first = client.get_player_scoreboard("Faker")
        assert len(first) == 3
        assert client._site.api.call_count == 1

        second = client.get_player_scoreboard("Faker")
        assert len(second) == 3
        assert client._site.api.call_count == 1   # still 1 — served from cache
    print("PASS  test_cache_prevents_second_api_call")


# ---------------------------------------------------------------------------
# aggregate_champion_stats
# ---------------------------------------------------------------------------

_ROWS = [
    ScoreboardRow("g1", "Azir",    5, 2, 8,  280, True),
    ScoreboardRow("g2", "Azir",    3, 4, 6,  260, False),
    ScoreboardRow("g3", "Azir",    7, 1, 10, 300, True),
    ScoreboardRow("g4", "Orianna", 2, 1, 10, 240, True),
    ScoreboardRow("g5", "Orianna", 4, 2, 7,  220, False),
]


def test_aggregate_groups_by_champion():
    stats = aggregate_champion_stats(_ROWS)
    names = {s.champion for s in stats}
    assert names == {"Azir", "Orianna"}
    print("PASS  test_aggregate_groups_by_champion")


def test_aggregate_sorted_by_games_desc():
    stats = aggregate_champion_stats(_ROWS)
    assert stats[0].champion == "Azir"    # 3 games
    assert stats[1].champion == "Orianna" # 2 games
    print("PASS  test_aggregate_sorted_by_games_desc")


def test_aggregate_azir_stats():
    stats = {s.champion: s for s in aggregate_champion_stats(_ROWS)}
    azir = stats["Azir"]
    assert azir.games == 3
    assert azir.wins == 2
    assert azir.losses == 1
    assert abs(azir.win_rate - 2/3) < 1e-9
    # avg_* are stored rounded to 2dp, so compare to the same rounded value
    assert azir.avg_kills   == round(15/3, 2)     # (5+3+7)/3 = 5.0
    assert azir.avg_deaths  == round(7/3,  2)     # (2+4+1)/3 ≈ 2.33
    assert azir.avg_assists == round(24/3, 2)     # (8+6+10)/3 = 8.0
    assert azir.avg_cs      == round(840/3, 1)    # (280+260+300)/3 = 280.0
    # KDA uses raw (unrounded) averages, then the result is rounded to 2dp
    raw_avg_d = 7 / 3
    expected_kda = round((5.0 + 8.0) / max(raw_avg_d, 1.0), 2)
    assert azir.kda == expected_kda
    print("PASS  test_aggregate_azir_stats")


def test_aggregate_zero_deaths_kda():
    rows = [ScoreboardRow("x", "Thresh", 0, 0, 10, 100, True)]
    stats = aggregate_champion_stats(rows)
    assert stats[0].kda == 10.0   # (0+10) / max(0, 1)
    print("PASS  test_aggregate_zero_deaths_kda")


def test_aggregate_empty_input():
    assert aggregate_champion_stats([]) == []
    print("PASS  test_aggregate_empty_input")


def test_aggregate_alphabetical_tiebreak():
    rows = [
        ScoreboardRow("a", "Zed",   1, 1, 1, 100, True),
        ScoreboardRow("b", "Akali", 1, 1, 1, 100, True),
    ]
    stats = aggregate_champion_stats(rows)
    # Both have 1 game → sort alphabetically
    assert stats[0].champion == "Akali"
    assert stats[1].champion == "Zed"
    print("PASS  test_aggregate_alphabetical_tiebreak")


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_get_player_scoreboard_returns_rows()
    test_scoreboard_row_fields_parsed()
    test_scoreboard_rows_without_champion_are_skipped()
    test_empty_link_returns_empty()
    test_missing_numeric_fields_coerce_to_zero()
    test_cache_prevents_second_api_call()
    test_aggregate_groups_by_champion()
    test_aggregate_sorted_by_games_desc()
    test_aggregate_azir_stats()
    test_aggregate_zero_deaths_kda()
    test_aggregate_empty_input()
    test_aggregate_alphabetical_tiebreak()
    print("\nAll tests passed.")
