"""
tests/test_lolpros.py

Unit tests for draft_analyzer/lolpros.py — the lolpros.gg NEXT_DATA scraper.
This parser is the documented #1 risk (lolpros can reshuffle its page schema
and silently yield zero accounts), so these tests pin the happy parse, the
field-alias tolerance, region mapping, and the schema-drift warning.

The network is mocked via an injected fake session. No live HTTP, no pytest.
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# --- bootstrap: dołóż packages/shared do sys.path (monorepo) ---
_shared = next(
    a for a in Path(__file__).resolve().parents if (a / "packages" / "shared").is_dir()
) / "packages" / "shared"
if str(_shared) not in sys.path:
    sys.path.insert(0, str(_shared))


from shared import lolpros
from shared.lolpros import scrape_lolpros_accounts, slugify


# ---------------------------------------------------------------------------
# Fake HTTP
# ---------------------------------------------------------------------------

class _Resp:
    def __init__(self, text="", status=200):
        self.text = text
        self.status_code = status

    def close(self):
        pass


class _Session:
    def __init__(self, resp):
        self._resp = resp
        self.calls = []

    def get(self, url, **kw):
        self.calls.append((url, kw))
        return self._resp


def _next_data_html(payload: dict) -> str:
    return (
        '<html><body>'
        f'<script id="__NEXT_DATA__" type="application/json">'
        f'{json.dumps(payload)}</script>'
        '</body></html>'
    )


# ---------------------------------------------------------------------------
# slugify
# ---------------------------------------------------------------------------

def test_slugify_basic():
    assert slugify("Hans Sama") == "hans-sama"
    assert slugify("Faker") == "faker"
    assert slugify("  Caps_99 ") == "caps-99"
    assert slugify("a--b") == "a-b"
    assert slugify("Łódź!") == "d"          # non-ASCII stripped (documented)
    assert slugify("") == ""
    print("PASS  test_slugify_basic")


# ---------------------------------------------------------------------------
# scrape_lolpros_accounts — happy path & tolerance
# ---------------------------------------------------------------------------

def test_scrape_parses_accounts_and_maps_regions():
    payload = {"props": {"pageProps": {"player": {"accounts": [
        {"game_name": "Caps", "tag_line": "EUW", "server": "EUW"},
        {"name": "Rekkles", "tag": "#1234", "region": "KR"},
    ]}}}}
    sess = _Session(_Resp(_next_data_html(payload)))
    accts = scrape_lolpros_accounts("https://lolpros.gg/player/caps", session=sess)

    assert [(a.game_name, a.platform) for a in accts] == [
        ("Caps", "euw1"), ("Rekkles", "kr"),
    ]
    assert accts[1].tag_line == "1234"      # leading '#' stripped
    print("PASS  test_scrape_parses_accounts_and_maps_regions")


def test_scrape_skips_unknown_region_and_dedupes():
    payload = {"pageProps": {"accounts": [
        {"summoner_name": "X", "riot_tag": "EUW", "rgn": "ZZ"},     # unknown rgn
        {"game_name": "Dup", "tag_line": "1", "server": "EUW"},
        {"game_name": "Dup", "tag_line": "1", "server": "EUW"},     # duplicate
    ]}}
    sess = _Session(_Resp(_next_data_html(payload)))
    accts = scrape_lolpros_accounts("https://lolpros.gg/player/x", session=sess)
    assert len(accts) == 1
    assert accts[0].game_name == "Dup"
    print("PASS  test_scrape_skips_unknown_region_and_dedupes")


# ---------------------------------------------------------------------------
# scrape_lolpros_accounts — failure modes
# ---------------------------------------------------------------------------

def test_scrape_empty_url_returns_empty():
    assert scrape_lolpros_accounts("") == []
    print("PASS  test_scrape_empty_url_returns_empty")


def test_scrape_non_200_returns_empty():
    sess = _Session(_Resp("nope", status=404))
    assert scrape_lolpros_accounts("https://lolpros.gg/player/x", session=sess) == []
    print("PASS  test_scrape_non_200_returns_empty")


def test_scrape_missing_next_data_returns_empty():
    sess = _Session(_Resp("<html>no next data here</html>"))
    assert scrape_lolpros_accounts("https://lolpros.gg/player/x", session=sess) == []
    print("PASS  test_scrape_missing_next_data_returns_empty")


def test_scrape_zero_accounts_logs_schema_warning():
    # NEXT_DATA present but no 'accounts' anywhere → schema drift symptom.
    payload = {"props": {"pageProps": {"player": {"name": "Caps"}}}}
    sess = _Session(_Resp(_next_data_html(payload)))
    with patch.object(lolpros.logger, "warning") as warn:
        accts = scrape_lolpros_accounts("https://lolpros.gg/player/caps", session=sess)
    assert accts == []
    assert warn.called
    # the URL is threaded into the warning for debuggability
    assert any("lolpros.gg/player/caps" in str(a)
               for a in warn.call_args.args)
    print("PASS  test_scrape_zero_accounts_logs_schema_warning")


def test_debug_keys_helper():
    assert lolpros._debug_keys({"b": 1, "a": 2}) == "a, b"   # sorted, bounded
    assert lolpros._debug_keys(None) == "NoneType"
    assert lolpros._debug_keys([1, 2]) == "list"
    print("PASS  test_debug_keys_helper")


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_slugify_basic()
    test_scrape_parses_accounts_and_maps_regions()
    test_scrape_skips_unknown_region_and_dedupes()
    test_scrape_empty_url_returns_empty()
    test_scrape_non_200_returns_empty()
    test_scrape_missing_next_data_returns_empty()
    test_scrape_zero_accounts_logs_schema_warning()
    test_debug_keys_helper()
    print("\nAll tests passed.")
