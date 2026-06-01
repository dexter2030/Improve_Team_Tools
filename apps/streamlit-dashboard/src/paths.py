"""
src/paths.py — centralne ścieżki baz danych aplikacji streamlit-dashboard.

Każda domena danych trzyma się w osobnym pliku ``.db`` w katalogu ``data/``,
a kod sięga po nie przez te stałe zamiast hardcode'ować ścieżki względne.
Katalog można nadpisać zmienną środowiskową ``DASHBOARD_DATA_DIR``.

Podział per domena:
- ``profiles.db`` — kuratorskie profile scoutingowe (ProfileStore).
- ``cache.db``    — cache odpowiedzi API (SqliteCacheStore).
- ``drafts.db``   — drafty pick&ban + metadane synchronizacji lig.
- ``players.db``  — rostery z lig + globalna baza graczy.
- ``cohort.db``   — konta lolpros + baseline SoloQ (kohorta).

Zapytania kohorty JOIN-ują tabele z ``players.db`` — robimy to przez
``ATTACH DATABASE`` (zob. ``draft_analyzer/db.py``: ``get_conn_cohort``).
"""
from __future__ import annotations

import os
from pathlib import Path

DATA_DIR = Path(
    os.environ.get("DASHBOARD_DATA_DIR")
    or (Path(__file__).resolve().parents[1] / "data")
)
DATA_DIR.mkdir(parents=True, exist_ok=True)

PROFILES_DB = DATA_DIR / "profiles.db"  # profiles
CACHE_DB = DATA_DIR / "cache.db"        # api_cache
DRAFTS_DB = DATA_DIR / "drafts.db"      # drafts, league_sync
PLAYERS_DB = DATA_DIR / "players.db"    # players, players_sync, players_all, players_all_sync
COHORT_DB = DATA_DIR / "cohort.db"      # lolpros_accounts, soloq_baseline
